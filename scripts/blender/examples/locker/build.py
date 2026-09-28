"""Second reference asset: a two-door steel locker, dark co-op horror camp.

Built from the same design system as the generator to prove one file keeps two
assets in one style: the same hex bolts, the same one warm indicator, the same wear.
It exercises the cut-in primitives the generator does not: plate, vent_slots, grille, tube.

Run:  blender -b --python scripts/blender/examples/locker/build.py -- --stage previews|bake|all [--out <dir>]
Lint: python3 scripts/blender/review_build.py scripts/blender/examples/locker/build.py
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.abspath(os.path.join(HERE, "..", ".."))

FRONT_Y = -0.5
# Face selectors carry a narrow y window: the flat body front sits at y -0.5 exactly,
# the first bevel strip beside it (normal dot 0.92, so it passes the 0.9 test) has its
# centre near -0.48, and the handles' front quads sit near -1.0. A raised door plate
# ends up at -0.55.
# The whole front face of the body, before the doors are cut.
FRONT = {"normal": "-y", "within": [None, None, -0.51, -0.49, 0.3, 3.6]}
# Each door face after the gap is cut (the gap strip itself has centre x 0).
DOOR_LEFT = {"normal": "-y", "within": [-0.9, -0.04, -0.51, -0.49, 0.3, 3.6]}
DOOR_RIGHT = {"normal": "-y", "within": [0.04, 0.9, -0.51, -0.49, 0.3, 3.6]}
# The raised plate top of each door only (x -0.64..-0.18, z 0.76..3.34): its seam
# chamfers have centres outside these windows.
DOOR_LEFT_TOP = {"normal": "-y", "within": [-0.6, -0.2, -0.6, -0.5, 0.8, 3.4]}
DOOR_RIGHT_TOP = {"normal": "-y", "within": [0.2, 0.6, -0.6, -0.5, 0.8, 3.4]}
# Handles: a U of 0.30 pipe whose ends sit 0.05 inside the raised door plate (top at y -0.55).
HANDLE_LEFT = [[-0.30, FRONT_Y, 1.20], [-0.30, -0.85, 1.20], [-0.30, -0.85, 1.70], [-0.30, FRONT_Y, 1.70]]
HANDLE_RIGHT = [[0.30, FRONT_Y, 1.20], [0.30, -0.85, 1.20], [0.30, -0.85, 1.70], [0.30, FRONT_Y, 1.70]]
# Hinge bolt heights: clear of the handles (z 1.05..1.85), the label (z 2.45..2.85)
# and the louvres (z 2.76..3.04).
HINGE_Z = (0.95, 1.95, 3.15)

SPEC = {
    "slug": "locker",
    "name": "Locker",
    "design_system": os.path.join(TOOLKIT, "presets", "chunky-horror-design.json"),
    "tri_budget": 8000,
    "plate_scale": 1.0,
    # One body, one plinth, one cap, two handles: five volumes.
    "volumes": [
        {"name": "body", "kind": "box", "role": "body", "bounds": [-0.9, 0.9, FRONT_Y, 0.5, 0.50, 3.60],
         "bevel": 0.12, "segments": 2},
        {"name": "plinth", "kind": "box", "role": "body2", "bounds": [-0.95, 0.95, -0.55, 0.55, 0.0, 0.50],
         "bevel": 0.10, "segments": 2},
        {"name": "cap", "kind": "box", "role": "body2", "bounds": [-0.95, 0.95, -0.55, 0.55, 3.60, 3.90],
         "bevel": 0.10, "segments": 2},
        {"name": "handle left", "kind": "tube", "role": "trim", "points": HANDLE_LEFT, "radius": 0.15, "joins": ["body"]},
        {"name": "handle right", "kind": "tube", "role": "trim", "points": HANDLE_RIGHT, "radius": 0.15, "joins": ["body"]},
    ],
    "cuts": [
        # The door gap: one upright slot down the middle of the front face.
        {"kind": "vent_slots", "face": FRONT, "count": 1, "along": "z", "width": 0.10, "depth": 0.06, "role": "body2"},
        # Each door is a plate with its own seam.
        {"kind": "plate", "face": DOOR_LEFT, "inset": 0.10, "thickness": 0.05},
        {"kind": "plate", "face": DOOR_RIGHT, "inset": 0.10, "thickness": 0.05},
        # A warning label on the right door: the one accent surface.
        {"kind": "plate", "face": DOOR_RIGHT_TOP, "inset": 0.08, "thickness": 0.04, "role": "accent",
         "region": [0.20, 0.62, 2.45, 2.85]},
        # Two louvres high on the left door.
        {"kind": "vent_slots", "face": DOOR_LEFT_TOP, "count": 2, "along": "x", "width": 0.10, "depth": 0.05,
         "span": [2.60, 3.20], "role": "body2"},
        # Ventilation grille across the plinth front (flat face at y -0.55, z 0.10..0.40; its
        # bevel strips centre near -0.535 and stay out): two rows of cells. Pitch 0.30 and bar
        # 0.12 because 0.20 by 0.08 collapsed into noise at read-40 (judge rounds 1 and 2).
        {"kind": "grille", "face": {"normal": "-y", "within": [None, None, -0.56, -0.545, 0.0, 0.5]},
         "pitch": 0.30, "bar": 0.12, "depth": 0.04, "role": "body2"},
    ],
    "studs": [
        # Hex hinge bolts in dark iron, three per door, sunk 0.01 into the raised door plates.
        {"points": [[-0.58, -0.62, z] for z in HINGE_Z] + [[0.58, -0.62, z] for z in HINGE_Z],
         "axis": "y", "radius": 0.08, "height": 0.08, "role": "body2", "sides": 6},
        # One warm indicator: the lock keypad on the left door, above the handle and under
        # the louvres, so the accent label on the right door stands alone (judge round 1).
        {"points": [[-0.40, -0.62, 2.15]], "axis": "y", "radius": 0.07, "height": 0.08, "role": "emissive"},
    ],
}

if __name__ == "__main__":
    import sys

    sys.path.insert(0, TOOLKIT)
    import pipeline  # noqa: E402

    sys.exit(pipeline.main(SPEC, HERE))
