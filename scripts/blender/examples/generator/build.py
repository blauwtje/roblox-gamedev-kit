"""Reference hero asset: a twin-drum portable generator (concept C), dark co-op horror camp.

The prop is the SPEC dict below and nothing else: owner feedback changes a number,
a role or a list entry here, never geometry code. Every value that appears twice
is a constant above the dict. The toolkit imports sit under __main__ so
review_build.py can read SPEC under plain python3.

Run:  blender -b --python scripts/blender/examples/generator/build.py -- --stage previews|bake|all [--out <dir>]
Lint: python3 scripts/blender/review_build.py scripts/blender/examples/generator/build.py
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLKIT = os.path.abspath(os.path.join(HERE, "..", ".."))

DRUM_X = (-0.85, 0.85)
DRUM_RADIUS = 0.62
# The groove band is part of the profile: a flat interior ring edge would be
# bevelled too and that degenerates, so the profile steps in and out itself.
# The band is 0.10 wide and 0.05 deep: the 0.08 by 0.04 band read as a hairline at read-40 (judge round 5).
DRUM_PROFILE = [[0.50, 0.30], [DRUM_RADIUS, 0.48], [DRUM_RADIUS, 0.92], [DRUM_RADIUS - 0.05, 0.94],
                [DRUM_RADIUS - 0.05, 1.04], [DRUM_RADIUS, 1.06], [DRUM_RADIUS, 1.45], [0.50, 1.62]]
# One carry frame behind the drums, a single U-shaped prism from plate to crossbar:
# one manifold volume, no elbow joints, feet on the plate so it reads as carrying
# the whole unit rather than lifting the tanks.
FRAME_PROFILE = [[-1.35, 0.32], [-1.35, 2.20], [1.35, 2.20], [1.35, 0.32],
                 [1.05, 0.32], [1.05, 1.90], [-1.05, 1.90], [-1.05, 0.32]]
PANEL_Y = -0.92

SPEC = {
    "slug": "generator",
    "name": "Generator",
    "design_system": os.path.join(TOOLKIT, "presets", "chunky-horror-design.json"),
    "tri_budget": 10000,
    "plate_scale": 0.8,
    # One plate, two drums, two caps, one control box, one exhaust, one frame: eight volumes.
    "volumes": [
        {"name": "plate", "kind": "box", "role": "body2", "bounds": [-1.65, 1.65, -0.95, 0.95, 0.0, 0.32],
         "bevel": 0.12, "segments": 2},
        {"name": "drum left", "kind": "lathe", "role": "body", "profile": DRUM_PROFILE, "sides": 24,
         "bevel": 0.10, "segments": 2, "at": [DRUM_X[0], 0.0, 0.0]},
        {"name": "drum right", "kind": "lathe", "role": "body", "profile": DRUM_PROFILE, "sides": 24,
         "bevel": 0.10, "segments": 2, "at": [DRUM_X[1], 0.0, 0.0]},
        {"name": "cap left", "kind": "ring", "role": "trim", "radius": 0.22, "thickness": 0.09, "z": [1.60, 1.78],
         "sides": 12, "bevel": 0.03, "segments": 1, "at": [DRUM_X[0], 0.0, 0.0], "joins": ["drum left"]},
        {"name": "cap right", "kind": "ring", "role": "trim", "radius": 0.22, "thickness": 0.09, "z": [1.60, 1.78],
         "sides": 12, "bevel": 0.03, "segments": 1, "at": [DRUM_X[1], 0.0, 0.0], "joins": ["drum right"]},
        # Control box in front of the drums, in the gap between them: at y -0.35 the
        # drums span x 0.34 outward, so a box of half-width 0.22 touches nothing.
        {"name": "control box", "kind": "box", "role": "trim", "bounds": [-0.22, 0.22, -0.92, -0.35, 0.32, 1.0],
         "bevel": 0.08, "segments": 2},
        # Exhaust stack on the control box: the one thing that says engine, not tank. The
        # collar and the cap step out over 0.02 instead of tapering (judge round 7); a
        # flat interior ring edge would degenerate under the bevel, hence the small rise.
        {"name": "exhaust", "kind": "lathe", "role": "body2",
         "profile": [[0.10, 0.90], [0.10, 1.03], [0.15, 1.05], [0.15, 1.83], [0.20, 1.85], [0.20, 1.95], [0.12, 1.98]],
         "sides": 12, "bevel": 0.03, "segments": 1, "at": [0.0, -0.62, 0.0], "tags": ["exhaust"], "joins": ["control box"]},
        {"name": "carry frame", "kind": "prism_y", "role": "trim", "points": FRAME_PROFILE, "y": [0.62, 0.92],
         "bevel": 0.05, "segments": 1},
    ],
    # The control panel is the one accent surface; the drum grooves sit in the lathe profile.
    "cuts": [
        {"kind": "inset_panel", "face": {"normal": "-y", "within": [-0.2, 0.2, PANEL_Y - 0.02, PANEL_Y + 0.02, None, None]},
         "inset": 0.08, "depth": 0.04, "role": "accent"},
        # Cooling grilles cut into both sides of the control box: four cells each.
        {"kind": "grille", "face": {"normal": "-x", "within": [-0.23, -0.21, -0.92, -0.35, 0.32, 1.0]},
         "pitch": 0.20, "bar": 0.08, "depth": 0.04, "role": "body2"},
        {"kind": "grille", "face": {"normal": "+x", "within": [0.21, 0.23, -0.92, -0.35, 0.32, 1.0]},
         "pitch": 0.20, "bar": 0.08, "depth": 0.04, "role": "body2"},
    ],
    "studs": [
        # Hex bolt heads in dark iron, not paint-coloured domes.
        {"points": [[-1.50, -0.75, 0.32], [1.50, -0.75, 0.32], [-1.50, 0.45, 0.32], [1.50, 0.45, 0.32]],
         "axis": "z", "radius": 0.10, "height": 0.08, "role": "body2", "sides": 6},
        # Exactly one warm indicator on the panel the player operates; the two accent
        # buttons that sat above it read as three warm dots (judge round 5).
        {"points": [[0.0, -0.97, 0.66]], "axis": "y", "radius": 0.07, "height": 0.05, "role": "emissive"},
    ],
}

if __name__ == "__main__":
    import sys

    sys.path.insert(0, TOOLKIT)
    import pipeline  # noqa: E402

    sys.exit(pipeline.main(SPEC, HERE))
