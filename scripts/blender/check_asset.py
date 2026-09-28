"""Acceptance check for one built asset: budget, watertightness, UV, origin, texture maps.

Library use: check(obj, tri_budget) -> list of failure strings.
CLI use (after the .blend is loaded by blender -b):
    blender -b asset.blend --python check_asset.py -- --object Name --budget 2000
    blender -b --python check_asset.py -- --selftest
"""

import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assetlib  # noqa: E402
import palette as palette_module  # noqa: E402

ROBLOX_TRIANGLE_LIMIT = 20_000
MAX_TEXTURE_SIZE = 1024


def _is_power_of_two(size):
    return size > 0 and size & (size - 1) == 0


def texture_maps(obj):
    """Every image that ships with this mesh, unique by image name.

    After the bake the asset carries one material whose image nodes are exactly
    the five maps the GLB takes to Roblox, so the node tree is the list to check;
    before the bake there are no image nodes and this returns nothing.
    """
    by_name = {}
    for material in obj.data.materials:
        if material is None or material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None:
                by_name[node.image.name] = node.image
    return [by_name[name] for name in sorted(by_name)]


def check_textures(obj):
    """What the Roblox importer demands of a texture, per map file.

    Square because the toolkit bakes one tileable map per asset: a non-square map
    stretches over the UV island it was baked from.
    """
    failures = []
    for image in texture_maps(obj):
        width, height = image.size
        name = os.path.basename(image.filepath) or image.name
        if (width, height) == (0, 0):
            # Blender reports 0x0 for a file it cannot open: the asset folder moved
            # away from the .blend, or the bake never ran. Not a shape problem.
            failures.append(f"texture {name} could not be read from {image.filepath or 'no path'}")
            continue
        if width > MAX_TEXTURE_SIZE or height > MAX_TEXTURE_SIZE:
            failures.append(f"texture {name} is {width}x{height}, over the {MAX_TEXTURE_SIZE} limit")
        if not (_is_power_of_two(width) and _is_power_of_two(height)):
            failures.append(f"texture {name} is {width}x{height}, not a power of two")
        if width != height:
            failures.append(f"texture {name} is {width}x{height}, not square")
    return failures


def check_uv_sets(obj):
    """Roblox's importer reads only the first UV set; a second one bakes to nothing
    but still ships in the GLB, so an extra set is dead weight left by an unwrap
    that was never cleaned up."""
    count = len(obj.data.uv_layers)
    if count > 1:
        return [f"{count} UV sets, only the first reaches Roblox"]
    return []


def check_transforms(obj):
    """Vertex data, not object scale or rotation, must carry the asset's shape:
    an unapplied transform reads correctly in this file but exports at a
    different size or orientation once Roblox re-parents the mesh."""
    failures = []
    scale = tuple(round(value, 4) for value in obj.scale)
    if scale != (1.0, 1.0, 1.0):
        failures.append(f"unapplied scale {tuple(round(value, 3) for value in obj.scale)}")
    rotation = tuple(round(value, 4) for value in obj.rotation_euler)
    if rotation != (0.0, 0.0, 0.0):
        failures.append(f"unapplied rotation {tuple(round(value, 3) for value in obj.rotation_euler)}")
    return failures


def check_material_slots(obj):
    """The bake collapses every role material to one slot; a second slot still on
    the mesh rode through unbaked, and Roblox shows only the first slot's surface."""
    count = len(obj.data.materials)
    if count > 1:
        return [f"{count} material slots, only the first reaches Roblox"]
    return []


def check_manifold(obj):
    """A solid must have no boundary: every edge borders at least two faces, or
    the surface has a hole that leaves the mesh open, which reads as a lit gap
    in Roblox and a leak in its collision. An edge shared by three or more
    faces is a separate, intersecting-geometry tell this check does not cover."""
    edge_face_count = {}
    for polygon in obj.data.polygons:
        for edge_key in polygon.edge_keys:
            edge_face_count[edge_key] = edge_face_count.get(edge_key, 0) + 1
    open_edges = sum(1 for count in edge_face_count.values() if count < 2)
    if open_edges:
        return [f"{open_edges} open (non-manifold) edges"]
    return []


def check(obj, tri_budget=ROBLOX_TRIANGLE_LIMIT, require_uv=True):
    figures = assetlib.stats(obj)
    failures = []
    if figures["triangles"] > tri_budget:
        failures.append(f"triangles {figures['triangles']} over budget {tri_budget}")
    if figures["triangles"] > ROBLOX_TRIANGLE_LIMIT:
        failures.append(f"triangles {figures['triangles']} over the Roblox mesh limit {ROBLOX_TRIANGLE_LIMIT}")
    if figures["loose_vertices"] > 0:
        failures.append(f"{figures['loose_vertices']} loose vertices")
    if require_uv and not figures["has_uv"]:
        failures.append("no UV layer")
    if not figures["origin_at_base"]:
        failures.append("origin is not at the centre of the base")
    if min(figures["dimensions"]) <= 0.0:
        failures.append(f"degenerate dimensions {figures['dimensions']}")
    failures.extend(check_uv_sets(obj))
    failures.extend(check_transforms(obj))
    failures.extend(check_manifold(obj))
    failures.extend(check_textures(obj))
    failures.extend(check_material_slots(obj))
    return failures, figures


def report(obj, tri_budget, require_uv=True):
    failures, figures = check(obj, tri_budget, require_uv)
    print("CHECK_STATS " + json.dumps(figures))
    for failure in failures:
        print(f"CHECK_FAIL: {failure}")
    print(f"CHECK_VALID:{'true' if not failures else 'false'}")
    return not failures


def _selftest_map(width, height):
    """One image datablock of this size; 0x0 stands for a map file Blender cannot open."""
    name = f"SelfTestMap{width}x{height}"
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    if (width, height) == (0, 0):
        image = bpy.data.images.new(name, 64, 64)
        image.source = "FILE"
        image.filepath = "/selftest-missing/map.png"
        return image
    return bpy.data.images.new(name, width, height)


def _texture_selftest(palette):
    """check_textures on one map per rejection reason, plus the size the bake writes."""
    builder = assetlib.Builder(palette)
    builder.box(-1.0, 1.0, -1.0, 1.0, 0.0, 1.0, "body")
    obj = builder.finish("SelfTestTexture")
    material = bpy.data.materials.new("SelfTestTextureSurface")
    material.use_nodes = True
    obj.data.materials.clear()
    obj.data.materials.append(material)
    node = material.node_tree.nodes.new("ShaderNodeTexImage")

    expectations = (
        ((1024, 1024), None),
        ((2048, 2048), f"over the {MAX_TEXTURE_SIZE} limit"),
        ((512, 300), "not a power of two"),
        ((512, 256), "not square"),
        ((0, 0), "could not be read"),
    )
    ok = True
    for size, expected in expectations:
        node.image = _selftest_map(*size)
        failures = check_textures(obj)
        if expected is None:
            accepted = not failures
        else:
            accepted = any(expected in failure for failure in failures)
        if not accepted:
            ok = False
            print(f"CHECK_FAIL: selftest {size[0]}x{size[1]} expected {expected!r}, got {failures}")
    return ok


def _uv_sets_selftest(palette):
    """check_uv_sets on one UV set (accepted) and a second one added on top (rejected)."""
    builder = assetlib.Builder(palette)
    builder.box(-1.0, 1.0, -1.0, 1.0, 0.0, 1.0, "body")
    obj = builder.finish("SelfTestUVSets")
    obj.data.uv_layers.new(name="UVMap")
    good = check_uv_sets(obj)
    obj.data.uv_layers.new(name="UVMap2")
    bad = check_uv_sets(obj)
    ok = not good and bad
    if not ok:
        print(f"CHECK_FAIL: selftest uv sets good={good} bad={bad}")
    return ok


def _transforms_selftest(palette):
    """check_transforms on an identity transform (accepted) and a scaled one (rejected)."""
    builder = assetlib.Builder(palette)
    builder.box(-1.0, 1.0, -1.0, 1.0, 0.0, 1.0, "body")
    obj = builder.finish("SelfTestTransforms")
    good = check_transforms(obj)
    obj.scale = (2.0, 1.0, 1.0)
    bad = check_transforms(obj)
    ok = not good and bad
    if not ok:
        print(f"CHECK_FAIL: selftest transforms good={good} bad={bad}")
    return ok


def _material_slots_selftest(palette):
    """check_material_slots on the one material the bake leaves behind (accepted)
    and a second slot added on top (rejected)."""
    builder = assetlib.Builder(palette)
    builder.box(-1.0, 1.0, -1.0, 1.0, 0.0, 1.0, "body")
    obj = builder.finish("SelfTestMaterialSlots")
    obj.data.materials.clear()
    obj.data.materials.append(bpy.data.materials.new("SelfTestSlotA"))
    good = check_material_slots(obj)
    obj.data.materials.append(bpy.data.materials.new("SelfTestSlotB"))
    bad = check_material_slots(obj)
    ok = not good and bad
    if not ok:
        print(f"CHECK_FAIL: selftest material slots good={good} bad={bad}")
    return ok


def _manifold_selftest(palette):
    """check_manifold on a closed box (accepted) and the same box with one face
    deleted, which turns that face's edges into single-face boundary edges (rejected)."""
    import bmesh

    builder = assetlib.Builder(palette)
    builder.box(-1.0, 1.0, -1.0, 1.0, 0.0, 1.0, "body")
    obj = builder.finish("SelfTestManifold")
    good = check_manifold(obj)

    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    bad = check_manifold(obj)

    ok = not good and bad
    if not ok:
        print(f"CHECK_FAIL: selftest manifold good={good} bad={bad}")
    return ok


def _selftest():
    preset = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets", "chunky-cartoon.json")
    palette = palette_module.load(preset)
    builder = assetlib.Builder(palette)
    builder.box(-1.0, 1.0, -1.0, 1.0, 0.0, 1.0, "body")
    good = builder.finish("SelfTestGood")
    # The Builder assigns one material per palette role; collapse to the single
    # slot the bake leaves behind so this stand-in matches a real, bake-ready asset.
    good.data.materials.clear()
    good.data.materials.append(bpy.data.materials.new("SelfTestGoodSurface"))
    good_ok = report(good, tri_budget=2000, require_uv=False)

    builder = assetlib.Builder(palette)
    builder.box(-1.0, 1.0, -1.0, 1.0, 0.0, 1.0, "body")
    bad = builder.finish("SelfTestBad")
    bad.data.materials.clear()
    bad.data.materials.append(bpy.data.materials.new("SelfTestBadSurface"))
    bad.data.vertices.add(1)
    bad_ok = report(bad, tri_budget=2000, require_uv=False)
    return (
        good_ok
        and not bad_ok
        and _texture_selftest(palette)
        and _uv_sets_selftest(palette)
        and _transforms_selftest(palette)
        and _manifold_selftest(palette)
        and _material_slots_selftest(palette)
    )


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--selftest" in argv:
        sys.exit(0 if _selftest() else 1)
    name = argv[argv.index("--object") + 1] if "--object" in argv else None
    budget_text = argv[argv.index("--budget") + 1] if "--budget" in argv else str(ROBLOX_TRIANGLE_LIMIT)
    try:
        budget = int(budget_text)
    except ValueError:
        print(f"CHECK_FAIL: --budget {budget_text!r} is not an integer")
        print("CHECK_VALID:false")
        sys.exit(1)
    require_uv = "--no-uv" not in argv
    obj = bpy.data.objects.get(name) if name else None
    if obj is None:
        print(f"CHECK_FAIL: object {name!r} not found")
        print("CHECK_VALID:false")
        sys.exit(1)
    sys.exit(0 if report(obj, budget, require_uv) else 1)


if __name__ == "__main__":
    main()
