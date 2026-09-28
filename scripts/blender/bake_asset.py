"""Unwrap, enrich, bake and collapse one asset to a single material with five maps.

Node materials do not survive the GLB: everything except baseColorFactor is lost,
and the Roblox importer drops even that without a texture file. So: lay UVs, put
plate variation, edge wear, rust, grime, floor dirt and soot into each role material
from the design-system recipes, bake ColorMap / RoughnessMap / NormalMap /
EmissiveMask / MetalnessMap, and collapse to one `<slug>Surface` material so the
importer yields one MeshPart per file. Cycles is mandatory: the Bevel node is Cycles only.

Every failure raises BakeError. A bake that silently skips a step ships a plausible
but wrong texture, and that is only found a judge round later.
"""

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assetlib  # noqa: E402
import palette as palette_module  # noqa: E402

# Grime sits where a rag never reaches: crevices (ambient occlusion) plus a few
# noise splotches of rust. Tertiary detail, bake only. These are texture shapes;
# the strengths per role live in the design-system recipes.
GRIME_AO_DISTANCE = 0.35
GRIME_CREVICE_STRENGTH = 0.6
RUST_SPLOTCH_STRENGTH = 0.6
WEAR_MASK_NODE = "WearMask"
WEAR_NODE = "Wear"
METAL_NODE = "Metal"
# Edge wear from the Bevel node: dot(bevelled normal, true normal) is 1.0 on a flat
# face and drops inside the bevel band. Measured 2026-09-02 (radius 0.06, 128 px EMIT
# bake): a 2x2x1 box reads 1.0 on 95 percent of its pixels and 0.906 at the edges; a
# 0.30 bar keeps 75 percent at 0.984 or above; a 0.10 bar is worn everywhere, which
# is what thickness_min guards. The radius is absolute, so unlike Pointiness a bar
# that clears thickness_min is not "all edge".
WEAR_DOT_CLEAN = 0.985
WEAR_DOT_FULL = 0.90
BEVEL_SAMPLES = 4
MAPS = ("color", "roughness", "normal", "emissive", "metalness")
# Which shader value the EMIT bake carries for each emission-driven map.
EMISSION_SOURCE = {"emissive": "mask", "metalness": "metal"}
MIN_COLORMAP_LUMINANCE = 0.05


class BakeError(RuntimeError):
    pass


def textures_dir(path):
    """The textures directory of an asset, from either the asset dir or the textures dir itself."""
    path = str(path).rstrip(os.sep)
    if os.path.basename(path) == "textures":
        return path
    return os.path.join(path, "textures")


def _select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def unwrap(obj, angle_limit_degrees=66.0, island_margin=0.02):
    """UVs over the whole asset; without UVs there is nothing to bake."""
    import math

    _select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle_limit_degrees), island_margin=island_margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    if not obj.data.uv_layers:
        raise BakeError(f"{obj.name}: unwrap produced no UV layer")
    return len(obj.data.uv_layers)


def _find(tree, bl_idname, material_name):
    for node in tree.nodes:
        if node.bl_idname == bl_idname:
            return node
    raise BakeError(f"material {material_name!r} has no {bl_idname} node")


def _grime_factors(tree, coords, plate_scale, crevice_strength, splotch_strength):
    """(crevice, splotch) 0..1 masks: dark grime where AO is low, rust in noise splotches."""
    occlusion = tree.nodes.new("ShaderNodeAmbientOcclusion")
    occlusion.inputs["Distance"].default_value = GRIME_AO_DISTANCE
    crevice = tree.nodes.new("ShaderNodeMapRange")
    crevice.inputs["From Min"].default_value = 1.0
    crevice.inputs["From Max"].default_value = 0.45
    crevice.inputs["To Min"].default_value = 0.0
    crevice.inputs["To Max"].default_value = crevice_strength
    tree.links.new(occlusion.outputs["AO"], crevice.inputs["Value"])

    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.5 / plate_scale
    noise.inputs["Detail"].default_value = 4.0
    tree.links.new(coords.outputs["Object"], noise.inputs["Vector"])
    splotch = tree.nodes.new("ShaderNodeMapRange")
    splotch.inputs["From Min"].default_value = 0.52
    splotch.inputs["From Max"].default_value = 0.68
    splotch.inputs["To Min"].default_value = 0.0
    splotch.inputs["To Max"].default_value = splotch_strength
    tree.links.new(noise.outputs["Fac"], splotch.inputs["Value"])
    return crevice.outputs["Result"], splotch.outputs["Result"]


def _mix_colour(tree, base_socket, rgb, factor_socket):
    mixed = tree.nodes.new("ShaderNodeMix")
    mixed.data_type = "RGBA"
    mixed.inputs[7].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    tree.links.new(factor_socket, mixed.inputs["Factor"])
    tree.links.new(base_socket, mixed.inputs[6])
    return mixed.outputs[2]


def _maximum(tree, first, second):
    node = tree.nodes.new("ShaderNodeMath")
    node.operation = "MAXIMUM"
    tree.links.new(first, node.inputs[0])
    tree.links.new(second, node.inputs[1])
    return node.outputs["Value"]


def _wear_mask(tree, radius):
    """0..1 edge mask from the Bevel node, in the node named WEAR_MASK_NODE; 0 on a flat face."""
    bevel = tree.nodes.new("ShaderNodeBevel")
    bevel.samples = BEVEL_SAMPLES
    bevel.inputs["Radius"].default_value = radius
    geometry = tree.nodes.new("ShaderNodeNewGeometry")
    dot = tree.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    tree.links.new(bevel.outputs["Normal"], dot.inputs[0])
    tree.links.new(geometry.outputs["True Normal"], dot.inputs[1])
    mask = tree.nodes.new("ShaderNodeMapRange")
    mask.name = WEAR_MASK_NODE
    mask.clamp = True
    mask.inputs["From Min"].default_value = WEAR_DOT_CLEAN
    mask.inputs["From Max"].default_value = WEAR_DOT_FULL
    mask.inputs["To Min"].default_value = 0.0
    mask.inputs["To Max"].default_value = 1.0
    tree.links.new(dot.outputs["Value"], mask.inputs["Value"])
    return mask.outputs["Result"]


def _floor_factor(tree, coords, height, strength):
    """Dirt climbing from the floor: `strength` at z 0, nothing above `height` (object coordinates)."""
    split = tree.nodes.new("ShaderNodeSeparateXYZ")
    tree.links.new(coords.outputs["Object"], split.inputs["Vector"])
    fade = tree.nodes.new("ShaderNodeMapRange")
    fade.clamp = True
    fade.inputs["From Min"].default_value = 0.0
    fade.inputs["From Max"].default_value = height
    fade.inputs["To Min"].default_value = strength
    fade.inputs["To Max"].default_value = 0.0
    tree.links.new(split.outputs["Z"], fade.inputs["Value"])
    return fade.outputs["Result"]


def _soot_factor(tree, coords, sources, radius, strength):
    """Soot around every tagged volume: full inside its extent, gone at extent + radius; None without sources."""
    combined = None
    for x, y, z, extent in sources:
        distance = tree.nodes.new("ShaderNodeVectorMath")
        distance.operation = "DISTANCE"
        tree.links.new(coords.outputs["Object"], distance.inputs[0])
        distance.inputs[1].default_value = (x, y, z)
        fade = tree.nodes.new("ShaderNodeMapRange")
        fade.clamp = True
        fade.inputs["From Min"].default_value = extent
        fade.inputs["From Max"].default_value = extent + radius
        fade.inputs["To Min"].default_value = strength
        fade.inputs["To Max"].default_value = 0.0
        tree.links.new(distance.outputs["Value"], fade.inputs["Value"])
        combined = fade.outputs["Result"] if combined is None else _maximum(tree, combined, fade.outputs["Result"])
    return combined


def soot_sources(obj):
    """[(x, y, z, extent), ...] that assetlib.finish stored on the object."""
    flat = list(obj.get("soot_sources", []))
    return [tuple(flat[index:index + 4]) for index in range(0, len(flat), 4)]


def _rebuild(material, plate_scale, roughness, recipe, design_system, sources):
    """Rebuild one material from scratch: plate variation, Bevel-node wear, rust, grime, floor dirt, soot.

    Rebuild instead of patch: a patch script that fails halfway leaves the node
    tree in a half state (learning 2026-08-26). Strengths come from the role's
    recipe in the design system; this module owns only the texture shapes.
    """
    base = tuple(material.diffuse_color)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    # Plate variation: one Voronoi cell is about one plate; plates never match exactly.
    coords = tree.nodes.new("ShaderNodeTexCoord")
    voronoi = tree.nodes.new("ShaderNodeTexVoronoi")
    voronoi.inputs["Scale"].default_value = 1.0 / plate_scale
    tree.links.new(coords.outputs["Object"], voronoi.inputs["Vector"])
    grey = tree.nodes.new("ShaderNodeRGBToBW")
    tree.links.new(voronoi.outputs["Color"], grey.inputs["Color"])
    plate = tree.nodes.new("ShaderNodeMapRange")
    plate.inputs["To Min"].default_value = 0.94
    plate.inputs["To Max"].default_value = 1.06
    tree.links.new(grey.outputs["Val"], plate.inputs["Value"])

    tinted = tree.nodes.new("ShaderNodeMix")
    tinted.data_type = "RGBA"
    tinted.blend_type = "MULTIPLY"
    tinted.inputs["Factor"].default_value = 1.0
    tinted.inputs[6].default_value = base
    tree.links.new(plate.outputs["Result"], tinted.inputs[7])

    # Edge wear tints toward bare metal, never replaces the paint; the recipe scales it.
    mask = _wear_mask(tree, design_system["wear"]["radius"])
    wear = tree.nodes.new("ShaderNodeMath")
    wear.name = WEAR_NODE
    wear.operation = "MULTIPLY"
    wear.inputs[1].default_value = design_system["wear"]["max"] * recipe["wear"]
    tree.links.new(mask, wear.inputs[0])
    colour = _mix_colour(tree, tinted.outputs[2], design_system["wear"]["bare_metal_rgb"], wear.outputs["Value"])

    crevice, splotch = _grime_factors(tree, coords, plate_scale,
                                      GRIME_CREVICE_STRENGTH * recipe["grime"],
                                      RUST_SPLOTCH_STRENGTH * recipe["rust"])
    colour = _mix_colour(tree, colour, design_system["rust_rgb"], splotch)
    colour = _mix_colour(tree, colour, design_system["dirt"]["rgb"], crevice)
    floor = _floor_factor(tree, coords, design_system["dirt"]["height"],
                          design_system["dirt"]["strength"] * recipe["grime"])
    colour = _mix_colour(tree, colour, design_system["dirt"]["rgb"], floor)
    dull = _maximum(tree, _maximum(tree, crevice, splotch), floor)
    soot = _soot_factor(tree, coords, sources, design_system["soot"]["radius"],
                        design_system["soot"]["strength"] * recipe["soot"])
    if soot is not None:
        colour = _mix_colour(tree, colour, design_system["soot"]["rgb"], soot)
        dull = _maximum(tree, dull, soot)
    tree.links.new(colour, shader.inputs["Base Color"])

    rough = tree.nodes.new("ShaderNodeMix")
    rough.data_type = "FLOAT"
    rough.inputs[2].default_value = roughness
    rough.inputs[3].default_value = roughness * 0.5
    tree.links.new(wear.outputs["Value"], rough.inputs["Factor"])
    rough_dull = tree.nodes.new("ShaderNodeMix")
    rough_dull.data_type = "FLOAT"
    rough_dull.inputs[3].default_value = 0.95
    tree.links.new(dull, rough_dull.inputs["Factor"])
    tree.links.new(rough.outputs["Result"], rough_dull.inputs[2])
    tree.links.new(rough_dull.outputs["Result"], shader.inputs["Roughness"])

    # MetalnessMap source: the recipe's base metal, and bare metal wherever the paint
    # wore through (only on roles that wear at all). Baked through EMIT because Cycles
    # has no metallic bake type.
    worn_metal = tree.nodes.new("ShaderNodeMath")
    worn_metal.operation = "MULTIPLY"
    worn_metal.inputs[1].default_value = 1.0 if recipe["wear"] > 0.0 else 0.0
    tree.links.new(mask, worn_metal.inputs[0])
    metal = tree.nodes.new("ShaderNodeMath")
    metal.name = METAL_NODE
    metal.operation = "MAXIMUM"
    metal.inputs[1].default_value = recipe["metal"]
    tree.links.new(worn_metal.outputs["Value"], metal.inputs[0])

    # Metallic stays 0 during the bake: a higher value only darkens the DIFFUSE
    # bake on exactly the worn edges, the opposite of wear. The map carries it.
    shader.inputs["Metallic"].default_value = 0.0
    return shader


def wear_mask_values(obj, size=128):
    """Bake the WearMask of every material once and return the covered pixel values, sorted.

    Diagnostic for selfcheck: the mask is 0 on a face centre and rises on an edge, so
    a bevelled box gives a median near 0 and a maximum well above 0.5. The bake carries
    0.5 + mask / 2 so uncovered texels (0) separate from clean paint (0.5).
    """
    restore = []
    for material in obj.data.materials:
        tree = material.node_tree
        shader = _find(tree, "ShaderNodeBsdfPrincipled", material.name)
        lift = tree.nodes.new("ShaderNodeMapRange")
        lift.inputs["To Min"].default_value = 0.5
        lift.inputs["To Max"].default_value = 1.0
        tree.links.new(tree.nodes[WEAR_MASK_NODE].outputs["Result"], lift.inputs["Value"])
        link = tree.links.new(lift.outputs["Result"], shader.inputs["Emission Color"])
        shader.inputs["Emission Strength"].default_value = 1.0
        restore.append((tree, lift, link, shader))
    _cycles(samples=4)
    _select_only(obj)
    image = bpy.data.images.new("_wear_mask", size, size)
    image.colorspace_settings.name = "Non-Color"
    try:
        _bake_into(obj, image, "EMIT")
        pixels = list(image.pixels)
        values = sorted((value - 0.5) * 2.0 for value in pixels[0::4] if value > 0.25)
    finally:
        bpy.data.images.remove(image)
        for tree, lift, link, shader in restore:
            tree.links.remove(link)
            tree.nodes.remove(lift)
            shader.inputs["Emission Strength"].default_value = 0.0
    return values


def enrich_materials(obj, style, plate_scale=1.0):
    """Rebuild every role material from its design-system recipe; returns the soot sources used."""
    if not obj.data.materials:
        raise BakeError(f"{obj.name}: no materials to enrich")
    palette = palette_module.palette_of(style)
    design_system = palette_module.design_system_of(style)
    sources = soot_sources(obj)
    for material in obj.data.materials:
        role = material.get("role")
        if role is None:
            raise BakeError(f"material {material.name!r} carries no role; build it with assetlib")
        _rebuild(material, plate_scale, palette_module.role_roughness(palette, role),
                 palette_module.recipe(design_system, role), design_system, sources)
    return sources


def set_emission_source(obj, source):
    """What the EMIT bake carries: 'mask' (the emissive role's own colour, black elsewhere:
    the emissive map) or 'metal' (the Metal node of every role, the MetalnessMap).

    The emissive map is coloured, not a white mask, so it can sit straight on Emission
    Color: the glTF exporter cannot express ColorMap times mask (it resolved that to the
    ColorMap and the whole prop glowed), and Roblox's importer averages the channels
    into its EmissiveMaskContent anyway.
    """
    if source not in ("mask", "metal"):
        raise BakeError(f"unknown emission source {source!r}")
    for material in obj.data.materials:
        tree = material.node_tree
        shader = _find(tree, "ShaderNodeBsdfPrincipled", material.name)
        for link in list(tree.links):
            if link.to_socket == shader.inputs["Emission Color"]:
                tree.links.remove(link)
        if source == "mask":
            lit = material.get("role") == "emissive"
            if lit:
                base_colour = [link for link in tree.links if link.to_socket == shader.inputs["Base Color"]]
                if not base_colour:
                    raise BakeError(f"material {material.name!r}: Base Color is not driven by a node")
                tree.links.new(base_colour[0].from_socket, shader.inputs["Emission Color"])
            shader.inputs["Emission Strength"].default_value = 1.0 if lit else 0.0
        else:
            tree.links.new(tree.nodes[METAL_NODE].outputs["Value"], shader.inputs["Emission Color"])
            shader.inputs["Emission Strength"].default_value = 1.0


def _cycles(samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.render.bake.use_pass_direct = False
    scene.render.bake.use_pass_indirect = False
    scene.render.bake.use_pass_color = True


def _bake_into(obj, image, bake_type, **kwargs):
    """Hang image as the active texture node in every material and bake into it."""
    if not obj.data.uv_layers:
        raise BakeError(f"{obj.name}: no UV layer; call unwrap first")
    attached = []
    for material in obj.data.materials:
        tree = material.node_tree
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = image
        node.select = True
        tree.nodes.active = node
        attached.append((tree, node))
    try:
        result = bpy.ops.object.bake(type=bake_type, margin=8, use_clear=True, **kwargs)
    finally:
        for tree, node in attached:
            tree.nodes.remove(node)
    if "FINISHED" not in result:
        raise BakeError(f"{obj.name}: bake {bake_type} returned {result}")


def _mean_luminance(image):
    pixels = list(image.pixels)
    count = len(pixels) // 4
    if count == 0:
        return 0.0
    total = 0.0
    for index in range(0, len(pixels), 4):
        total += palette_module.luminance(pixels[index:index + 3])
    return total / count


def bake_maps(obj, out_dir, slug, style, plate_scale=1.0, size=1024):
    """Bake the five maps to `<out_dir>/textures/` and return their paths.

    style is a palette or a design system; the recipes come from the design system.
    """
    enrich_materials(obj, style, plate_scale)
    _cycles(samples=8)
    _select_only(obj)
    out_textures = textures_dir(out_dir)
    os.makedirs(out_textures, exist_ok=True)
    paths = {}
    passes = (
        ("color", "DIFFUSE", True, {"pass_filter": {"COLOR"}}),
        ("roughness", "ROUGHNESS", False, {}),
        ("normal", "NORMAL", False, {}),
        ("emissive", "EMIT", True, {}),
        ("metalness", "EMIT", False, {}),
    )
    for name, bake_type, srgb, kwargs in passes:
        if bake_type == "EMIT":
            set_emission_source(obj, EMISSION_SOURCE[name])
        image_name = f"{slug}_{name}"
        old = bpy.data.images.get(image_name)
        if old is not None:
            bpy.data.images.remove(old)
        image = bpy.data.images.new(image_name, size, size)
        image.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        _bake_into(obj, image, bake_type, **kwargs)
        if name == "color":
            mean = _mean_luminance(image)
            if mean < MIN_COLORMAP_LUMINANCE:
                raise BakeError(f"{slug}: ColorMap mean luminance {mean:.3f}, near-black bake")
        path = os.path.join(out_textures, image_name + ".png")
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
        paths[name] = path
    return paths


def collapse_to_single_material(obj, slug, asset_or_textures_dir):
    """Replace every material slot by one `<slug>Surface` that uses only the five maps.

    The importer splits a GLB into one MeshPart per material; one material means one MeshPart.
    """
    textures = textures_dir(asset_or_textures_dir)
    for map_name in MAPS:
        path = os.path.join(textures, f"{slug}_{map_name}.png")
        if not os.path.exists(path):
            raise BakeError(f"missing {path}; run bake_maps first")
    name = slug + "Surface"
    old = bpy.data.materials.get(name)
    if old is not None:
        bpy.data.materials.remove(old)
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    shader = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    def image_node(map_name, srgb):
        node = tree.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(os.path.join(textures, f"{slug}_{map_name}.png"), check_existing=True)
        node.image.colorspace_settings.name = "sRGB" if srgb else "Non-Color"
        return node

    colour = image_node("color", True)
    tree.links.new(colour.outputs["Color"], shader.inputs["Base Color"])
    tree.links.new(image_node("roughness", False).outputs["Color"], shader.inputs["Roughness"])
    normal_map = tree.nodes.new("ShaderNodeNormalMap")
    tree.links.new(image_node("normal", False).outputs["Color"], normal_map.inputs["Color"])
    tree.links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])

    # The emissive map already carries the indicator's colour (black elsewhere), so it
    # sits straight on Emission Color: one image, which the glTF exporter writes as
    # emissiveTexture. A Mix of two images is not exportable (it shipped the ColorMap).
    tree.links.new(image_node("emissive", True).outputs["Color"], shader.inputs["Emission Color"])
    # Above 1.0 so the indicator reads as a glow in a dark preview; Roblox decides the
    # final intensity through EmissiveStrength.
    shader.inputs["Emission Strength"].default_value = assetlib.EMISSION_PREVIEW_STRENGTH
    # MetalnessMap into Metallic: the glTF exporter packs it with roughness into one
    # metallicRoughness texture (metal in B, roughness in G); Roblox reads MetalnessMap.
    tree.links.new(image_node("metalness", False).outputs["Color"], shader.inputs["Metallic"])

    mesh = obj.data
    mesh.materials.clear()
    mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.material_index = 0
    return material
