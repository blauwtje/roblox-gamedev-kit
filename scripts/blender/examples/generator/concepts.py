"""Four concept silhouettes for the generator on one sheet; the owner picks one.

Each concept is a SPEC dict (schema in spec.py) with volumes and studs only: no
cuts and no bake, because the silhouette is the question at this step.

Run: blender -b --python scripts/blender/examples/generator/concepts.py [-- --out <dir>]
Writes front.png and three-quarter.png of all four concepts side by side.
"""

import os
import sys

import bmesh
import bpy

TOOLKIT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, TOOLKIT)
import assetlib  # noqa: E402
import palette as palette_module  # noqa: E402
import render_asset  # noqa: E402

PRESET = os.path.join(TOOLKIT, "presets", "chunky-cartoon.json")
HERE = os.path.dirname(os.path.abspath(__file__))
TWIN_DRUM_PROFILE = [[0.5, 0.3], [0.62, 0.45], [0.62, 1.4], [0.5, 1.55]]
FLYWHEEL = [[u, 0.95 + v] for u, v in assetlib.ngon(0.75, 16)]
FLYWHEEL_HUB = [[u, 0.95 + v] for u, v in assetlib.ngon(0.2, 8)]

# A: low engine block on a skid frame, vertical fuel drum beside it.
CONCEPT_A_SKID = {
    "name": "Concept_A_skid",
    "volumes": [
        {"name": "skid", "kind": "box", "role": "body2", "bounds": [-1.4, 1.4, -1.0, 1.0, 0.0, 0.25], "bevel": 0.10},
        {"name": "block", "kind": "box", "role": "body", "bounds": [-1.1, 0.3, -0.8, 0.8, 0.25, 1.35], "bevel": 0.22, "segments": 3},
        {"name": "drum", "kind": "lathe", "role": "body2", "profile": [[0.45, 0.25], [0.55, 0.4], [0.55, 1.5], [0.45, 1.65]],
         "sides": 16, "bevel": 0.10, "at": [0.85, 0.0, 0.0]},
        {"name": "pipe", "kind": "tube", "role": "trim", "points": [[-0.6, -0.4, 1.5], [-0.6, -0.4, 2.0], [-0.6, 0.4, 2.0]], "radius": 0.15},
    ],
    "studs": [{"points": [[-0.4, -0.81, 0.9]], "axis": "y", "radius": 0.10, "height": 0.06, "role": "accent"}],
}

# B: tall drum with a cage crown and a side panel; reads as a fuel pump gone wrong.
CONCEPT_B_TOWER = {
    "name": "Concept_B_tower",
    "volumes": [
        {"name": "base", "kind": "box", "role": "body2", "bounds": [-0.9, 0.9, -0.9, 0.9, 0.0, 0.3], "bevel": 0.12},
        {"name": "drum", "kind": "lathe", "role": "body", "profile": [[0.55, 0.3], [0.7, 0.5], [0.7, 2.2], [0.5, 2.45]],
         "sides": 16, "bevel": 0.14, "segments": 3},
        {"name": "crown", "kind": "ring", "role": "trim", "radius": 0.62, "thickness": 0.10, "z": [2.45, 2.8],
         "sides": 16, "bevel": 0.04, "segments": 1},
        {"name": "panel", "kind": "box", "role": "body2", "bounds": [-0.35, 0.35, -1.0, -0.6, 0.9, 1.5], "bevel": 0.10},
    ],
    "studs": [{"points": [[0.0, -1.01, 1.2]], "axis": "y", "radius": 0.10, "height": 0.06, "role": "accent"}],
}

# C: two squat drums on one plate, joined by an arch pipe; wide and heavy.
CONCEPT_C_TWIN = {
    "name": "Concept_C_twin",
    "volumes": [
        {"name": "plate", "kind": "box", "role": "body2", "bounds": [-1.6, 1.6, -0.9, 0.9, 0.0, 0.3], "bevel": 0.12},
        {"name": "drum left", "kind": "lathe", "role": "body", "profile": TWIN_DRUM_PROFILE, "sides": 16,
         "bevel": 0.12, "segments": 3, "at": [-0.85, 0.0, 0.0]},
        {"name": "drum right", "kind": "lathe", "role": "body", "profile": TWIN_DRUM_PROFILE, "sides": 16,
         "bevel": 0.12, "segments": 3, "at": [0.85, 0.0, 0.0]},
        {"name": "control box", "kind": "box", "role": "trim", "bounds": [-0.3, 0.3, -0.5, 0.5, 0.3, 1.0], "bevel": 0.10},
        {"name": "arch", "kind": "tube", "role": "trim",
         "points": [[-0.85, -0.2, 1.55], [-0.85, -0.2, 1.95], [0.85, -0.2, 1.95], [0.85, -0.2, 1.55]], "radius": 0.15},
        {"name": "lamp", "kind": "box", "role": "accent", "bounds": [-0.15, 0.15, -0.95, -0.55, 0.55, 0.85], "bevel": 0.05, "segments": 1},
    ],
}

# D: cube engine with a big flywheel on the side and a stack exhaust; the workshop relic.
CONCEPT_D_FLYWHEEL = {
    "name": "Concept_D_flywheel",
    "volumes": [
        {"name": "base", "kind": "box", "role": "body2", "bounds": [-1.0, 1.0, -0.9, 0.9, 0.0, 0.3], "bevel": 0.12},
        {"name": "engine", "kind": "box", "role": "body", "bounds": [-0.8, 0.6, -0.75, 0.75, 0.3, 1.5], "bevel": 0.22, "segments": 3},
        {"name": "flywheel", "kind": "prism_x", "role": "body2", "points": FLYWHEEL, "x": [0.6, 0.85], "bevel": 0.06, "segments": 1},
        {"name": "hub", "kind": "prism_x", "role": "trim", "points": FLYWHEEL_HUB, "x": [0.85, 1.05], "bevel": 0.04, "segments": 1},
        {"name": "stack", "kind": "lathe", "role": "trim", "profile": [[0.12, 1.5], [0.16, 1.7], [0.16, 2.4], [0.22, 2.55]],
         "sides": 10, "bevel": 0.03, "segments": 1},
    ],
    "studs": [{"points": [[-0.3, -0.76, 1.1]], "axis": "y", "radius": 0.10, "height": 0.06, "role": "accent"}],
}

CONCEPTS = (CONCEPT_A_SKID, CONCEPT_B_TOWER, CONCEPT_C_TWIN, CONCEPT_D_FLYWHEEL)
SPACING = 4.2


def build_sheet(palette):
    """All four concepts joined into one object so the fixed rig frames the whole row."""
    sheet = bmesh.new()
    for index, concept in enumerate(CONCEPTS):
        obj = assetlib.build(concept, palette)
        offset = (index - (len(CONCEPTS) - 1) / 2.0) * SPACING
        part = bmesh.new()
        part.from_mesh(obj.data)
        bmesh.ops.translate(part, verts=part.verts, vec=(offset, 0.0, 0.0))
        temp = bpy.data.meshes.new("_concept_tmp")
        part.to_mesh(temp)
        part.free()
        sheet.from_mesh(temp)
        bpy.data.meshes.remove(temp)
        bpy.data.objects.remove(obj, do_unlink=True)
    mesh = bpy.data.meshes.new("ConceptSheet")
    sheet.to_mesh(mesh)
    sheet.free()
    for material in assetlib.ensure_materials(palette):
        mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = False
    obj = bpy.data.objects.new("ConceptSheet", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(HERE, "concepts")
    palette = palette_module.load(PRESET)
    sheet = build_sheet(palette)
    render_asset.setup()
    previous = render_asset.solo(sheet.name)
    try:
        # The sheet is four props wide: frame on the row, not on the rig's single-prop distance.
        for name, distance_factor in (("front", 1.7), ("three-quarter", 2.4)):
            direction, _ = render_asset.RIG[name]
            path = render_asset.shot(sheet, out_dir, name, direction, distance_factor, 1800, 700)
            print(f"CONCEPTS {name} {path}")
    finally:
        render_asset.unsolo(previous)


if __name__ == "__main__":
    main()
