"""Third reference asset: a signal beacon, bright chunky cartoon camp.

The first two examples both live in chunky-horror. This one exercises
chunky-cartoon-design.json: the zeroed wear, rust and grime recipes, and the
motif that an emissive signal is built from discrete small units rather than one
large smooth glowing plate.

Prop judge history, which is the point of keeping this example:
  round 1  the lamp head was one glowing drum, straight against the new motif
  round 2  the units were discrete but did not emit; the preview rig only lights
           the emissive role in the dark look shot, never in the five rig shots
  round 3  the shape read as a column, and every cut sat on a face the rig does
           not show: `side` looks from +x and this file cut into -x
  round 4  cuts moved onto the faces the rig shows (-y, +x, +z), head made wider
           than the base, and the emissive role given its own hue in the palette

The rig angles are fixed (render_asset.RIG): front looks from -y, side from +x,
top from +z, three-quarter and read-40 from +x/-y. A cut on -x is invisible in
every judged shot, so detail goes on -y, +x and +z.

Run:  blender -b --python scripts/blender/examples/beacon/build.py -- --stage previews|bake|all [--out <dir>]
Lint: python3 scripts/blender/review_build.py scripts/blender/examples/beacon/build.py
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.abspath(os.path.join(HERE, "..", ".."))

# Flat quads sit exactly on the box wall; each window is a 0.02 band around it so
# the bevel strips beside it (centres roughly 0.01 further out) stay outside.
FOOT_FRONT = {"normal": "-y", "within": [None, None, -0.51, -0.49, 0.00, 0.52]}
FOOT_SIDE = {"normal": "+x", "within": [0.49, 0.51, None, None, 0.00, 0.52]}
HEAD_SIDE = {"normal": "+x", "within": [0.61, 0.63, None, None, 0.84, 1.44]}
CAP_TOP = {"normal": "+z", "within": [None, None, None, None, 1.75, 1.77]}

# The carry handle: a U of 0.32 pipe whose legs end 0.06 inside the cap.
HANDLE = [[-0.20, 0.0, 1.70], [-0.20, 0.0, 1.86], [0.20, 0.0, 1.86], [0.20, 0.0, 1.70]]

SPEC = {
    "slug": "beacon",
    "name": "Beacon",
    "design_system": os.path.join(TOOLKIT, "presets", "chunky-cartoon-design.json"),
    "tri_budget": 6000,
    "plate_scale": 1.0,
    # Foot, column, lamp head, cap, handle: five volumes. The head is 1.24 across
    # against the foot's 1.00, so the widest thing in the frame is the lamp.
    "volumes": [
        {"name": "foot", "kind": "box", "role": "body2", "bounds": [-0.50, 0.50, -0.50, 0.50, 0.00, 0.52],
         "bevel": 0.10, "segments": 2},
        {"name": "column", "kind": "box", "role": "body", "bounds": [-0.32, 0.32, -0.32, 0.32, 0.52, 0.84],
         "bevel": 0.10, "segments": 2},
        {"name": "lamp head", "kind": "box", "role": "body", "bounds": [-0.62, 0.62, -0.62, 0.62, 0.84, 1.44],
         "bevel": 0.14, "segments": 3},
        {"name": "cap", "kind": "box", "role": "body2", "bounds": [-0.34, 0.34, -0.34, 0.34, 1.44, 1.76],
         "bevel": 0.10, "segments": 2},
        {"name": "handle", "kind": "tube", "role": "trim", "points": HANDLE, "radius": 0.16, "joins": ["cap"]},
    ],
    "cuts": [
        # The one accent surface: a recessed marker panel on the foot front. A raised plate
        # stood proud of the base silhouette and read as a glued-on box (prop judge round 1).
        {"kind": "inset_panel", "face": FOOT_FRONT, "inset": 0.09, "depth": 0.05, "role": "accent"},
        # One cut per face the rig shows, so no judged shot is bare (rounds 2 and 3, finding 5).
        {"kind": "grille", "face": FOOT_SIDE, "pitch": 0.30, "bar": 0.12, "depth": 0.04, "role": "body2"},
        {"kind": "groove", "face": HEAD_SIDE, "inset": 0.10, "depth": 0.05, "role": "body2"},
        {"kind": "groove", "face": CAP_TOP, "inset": 0.10, "depth": 0.05, "role": "body2"},
    ],
    "studs": [
        # Motif: round studs in body2 in a short counted row. Three, across the column front.
        {"points": [[x, -0.34, 0.68] for x in (-0.15, 0.0, 0.15)],
         "axis": "y", "radius": 0.045, "height": 0.045, "role": "body2"},
        # The one emissive signal, as four discrete units rather than one glowing plate.
        {"points": [[x, -0.66, 1.08] for x in (-0.36, -0.12, 0.12, 0.36)],
         "axis": "y", "radius": 0.10, "height": 0.07, "role": "emissive"},
    ],
}

if __name__ == "__main__":
    import sys

    sys.path.insert(0, TOOLKIT)
    import pipeline  # noqa: E402

    sys.exit(pipeline.main(SPEC, HERE))
