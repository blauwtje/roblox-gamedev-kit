"""End-to-end proof of scripts/blender on the installed Blender: build, render, bake, check, export.

Sample prop: a squat lantern. Primary: lathe body on a box base. Secondary: one groove
band and one raised panel cut into the skin, four studs. Tertiary: baked wear only.
Run: blender -b --python scripts/blender/selfcheck.py [-- --out /tmp/selfcheck]
"""

import os
import subprocess
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assetlib  # noqa: E402
import bake_asset  # noqa: E402
import check_asset  # noqa: E402
import palette as palette_module  # noqa: E402
import render_asset  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PRESET = os.path.join(HERE, "presets", "chunky-cartoon.json")


def build(palette):
    builder = assetlib.Builder(palette)
    builder.box(-0.9, 0.9, -0.9, 0.9, 0.0, 0.35, "body2", bevel=0.12, segments=2)
    builder.lathe([(0.55, 0.3), (0.75, 0.6), (0.75, 1.6), (0.55, 2.1), (0.30, 2.4)], "body", sides=16, bevel=0.10, segments=2)
    # Handle: a real 3D tube from the ring wall up and over; 0.30 thick is the design-system floor.
    builder.tube([(-0.30, 0.0, 2.30), (-0.30, 0.0, 2.95), (0.30, 0.0, 2.95), (0.30, 0.0, 2.30)], 0.15, "trim")
    builder.groove(lambda face: abs(face.normal.z) < 0.3 and 1.0 < face.calc_center_median().z < 1.25, inset=0.08, depth=0.06, role="trim")
    front = {"normal": "-y", "within": [None, None, None, None, 0.0, 0.3]}
    builder.plate(front, 0.12, 0.05, "trim")
    back = {"normal": "+y", "within": [None, None, None, None, 0.0, 0.3]}
    # Three upright slots: the base is 0.35 tall, too low for slots stacked along z.
    builder.vent_slots(back, 3, "z", 0.08, 0.05, "trim")
    # Studs extrude along +Y: front ones start inside the raised plate (its top sits at y = -0.95),
    # back ones on the unsunk bars of the back face (slot centres at x -0.41, 0 and 0.41).
    builder.studs([(-0.6, -1.0, 0.17), (0.6, -1.0, 0.17), (-0.6, 0.85, 0.17), (0.6, 0.85, 0.17)], "y", 0.06, 0.06, "accent")
    builder.ring(0.36, 0.08, 2.35, 2.5, "emissive", sides=16, bevel=0.03, segments=1)
    return builder.finish("SelfCheckLantern")


def check_wear_sits_on_edges(palette):
    """The Bevel-node mask is 0 on a face centre and rises on the edges: on a bevelled box the
    median must stay under 0.05 and the maximum must pass 0.5 (measured 2026-09-02: 0 and 0.93)."""
    builder = assetlib.Builder(palette)
    builder.box(-1.0, 1.0, -1.0, 1.0, 0.0, 1.0, "body", bevel=0.10)
    box = builder.finish("SelfCheckWearBox")
    bake_asset.unwrap(box)
    bake_asset.enrich_materials(box, palette)
    values = bake_asset.wear_mask_values(box, size=128)
    bpy.data.objects.remove(box, do_unlink=True)
    if not values:
        print("SELFCHECK_FAIL: wear mask bake covered no pixel")
        return False
    median, highest = values[len(values) // 2], values[-1]
    if median > 0.05 or highest < 0.5:
        print(f"SELFCHECK_FAIL: wear mask median {median:.3f} max {highest:.3f}, expected under 0.05 and over 0.5")
        return False
    print(f"SELFCHECK_WEAR ok median {median:.3f} max {highest:.3f}")
    return True


def check_cli_on_saved_blend(obj, out_dir):
    """The check_asset CLI on a saved .blend: a valid run exits 0, a non-integer budget exits 1."""
    blend = os.path.join(out_dir, "selfcheck.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend, copy=True)
    script = os.path.join(HERE, "check_asset.py")
    base = [bpy.app.binary_path, "-b", blend, "--python", script, "--", "--object", obj.name]
    expectations = (
        (["--budget", "6000"], 0, "CHECK_VALID:true"),
        (["--budget", "lots"], 1, "CHECK_FAIL: --budget 'lots' is not an integer"),
    )
    ok = True
    for extra, expected_code, expected_line in expectations:
        run = subprocess.run(base + extra, capture_output=True, text=True, check=False)
        lines = run.stdout.splitlines()
        if run.returncode != expected_code or expected_line not in lines:
            ok = False
            print(f"SELFCHECK_FAIL: check_asset {' '.join(extra)} exit {run.returncode}, expected {expected_code} with {expected_line!r}")
            print("\n".join(lines[-5:]))
    if ok:
        print("SELFCHECK_CLI ok")
    return ok


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[argv.index("--out") + 1] if "--out" in argv else "/tmp/selfcheck"
    problems = palette_module.validate(palette_module.load(PRESET))
    if problems:
        for problem in problems:
            print(f"SELFCHECK_FAIL: preset {problem}")
        sys.exit(1)
    palette = palette_module.load(PRESET)

    obj = build(palette)
    render_asset.setup()
    previews = render_asset.render_rig(obj, os.path.join(out_dir, "previews"), width=512, height=512)
    print("SELFCHECK_PREVIEWS " + " ".join(sorted(previews)))

    bake_asset.unwrap(obj)
    maps = bake_asset.bake_maps(obj, out_dir, "selfcheck", palette, plate_scale=0.6, size=256)
    print("SELFCHECK_MAPS " + " ".join(sorted(maps)))
    bake_asset.collapse_to_single_material(obj, "selfcheck", out_dir)

    look = render_asset.render_look(obj, os.path.join(out_dir, "previews"), "cycles-three-quarter", samples=4, width=256, height=256)
    print(f"SELFCHECK_CYCLES {os.path.basename(look)}")

    ok = check_asset.report(obj, tri_budget=6000)
    ok = check_wear_sits_on_edges(palette) and ok
    ok = check_cli_on_saved_blend(obj, out_dir) and ok
    glb = assetlib.export_glb(obj, os.path.join(out_dir, "selfcheck.glb"))
    print(f"SELFCHECK_GLB {os.path.getsize(glb)}")
    print(f"SELFCHECK_VALID:{'true' if ok else 'false'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
