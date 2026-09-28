"""Staged run of one SPEC-driven asset: previews in seconds, the bake only on an accepted shape.

    blender -b --python build.py -- --stage previews|bake|all [--out <dir>]

Every run builds the object once (a bmesh build costs well under a second). previews:
the five Workbench rig shots, check without UVs. bake: unwrap, the maps, collapse, look
shots, check, .blend and .glb. all: both. The default stage is all. Every run ends with a
STAGE <name> <seconds>s line so the design session can see what a change costs.
"""

import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assetlib  # noqa: E402
import bake_asset  # noqa: E402
import check_asset  # noqa: E402
import palette as palette_module  # noqa: E402
import render_asset  # noqa: E402
import spec as spec_module  # noqa: E402

STAGES = ("previews", "bake", "all")
REQUIRED_KEYS = ("slug", "name", "design_system", "tri_budget", "plate_scale", "volumes")


class StageError(RuntimeError):
    pass


def parse_args(argv):
    """(stage, out_dir or None) from the arguments after '--'."""
    stage = "all"
    out_dir = None
    if "--stage" in argv:
        stage = argv[argv.index("--stage") + 1]
    if stage not in STAGES:
        raise StageError(f"--stage must be one of {STAGES}, not {stage!r}")
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    return stage, out_dir


def load_style(spec, spec_dir):
    """The design system named by the SPEC, validated together with its palette."""
    path = spec["design_system"]
    if not os.path.isabs(path):
        path = os.path.join(spec_dir, path)
    style = palette_module.load_design_system(path)
    problems = palette_module.validate_design_system(style) + palette_module.validate(style["palette"])
    if problems:
        raise StageError(f"{path}: " + "; ".join(problems))
    return style


def previews(obj, spec, out_dir):
    render_asset.setup()
    paths = render_asset.render_rig(obj, os.path.join(out_dir, "previews"), width=1024, height=1024)
    print("PREVIEWS " + " ".join(sorted(paths)))
    return check_asset.report(obj, tri_budget=spec["tri_budget"], require_uv=False)


def bake(obj, spec, style, out_dir):
    slug = spec["slug"]
    bake_asset.unwrap(obj)
    maps = bake_asset.bake_maps(obj, out_dir, slug, style, plate_scale=spec["plate_scale"], size=1024)
    print("MAPS " + " ".join(sorted(maps)))
    bake_asset.collapse_to_single_material(obj, slug, out_dir)
    previews_dir = os.path.join(out_dir, "previews")
    look = render_asset.render_look(obj, previews_dir, "look", samples=48, width=1024, height=1024)
    dark = render_asset.render_look(obj, previews_dir, "look-dark", samples=48, width=1024, height=1024,
                                    world_strength=0.03, light_scale=0.12)
    print("LOOK " + look + " " + dark)
    ok = check_asset.report(obj, tri_budget=spec["tri_budget"])
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, slug + ".blend"), copy=True)
    glb = assetlib.export_glb(obj, os.path.join(out_dir, slug + ".glb"))
    print(f"GLB {os.path.getsize(glb)} {glb}")
    return ok


def run(spec, spec_dir, argv):
    started = time.monotonic()
    stage, out_dir = parse_args(argv)
    out_dir = out_dir or spec_dir
    missing = [key for key in REQUIRED_KEYS if key not in spec]
    if missing:
        raise StageError(f"SPEC misses {missing}")
    style = load_style(spec, spec_dir)
    obj = assetlib.build(spec, style)
    ok = True
    if stage in ("previews", "all"):
        ok = previews(obj, spec, out_dir) and ok
    if stage in ("bake", "all"):
        ok = bake(obj, spec, style, out_dir) and ok
    print(f"STAGE {stage} {time.monotonic() - started:.1f}s")
    return ok


def main(spec, spec_dir):
    """Exit code for a build.py: 0 when every check passed, 1 on a failed check, 2 on a bad SPEC or argument."""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    try:
        return 0 if run(spec, spec_dir, argv) else 1
    except (StageError, spec_module.SpecError, OSError, ValueError) as error:
        print(f"SPEC_ERROR: {error}")
        return 2
