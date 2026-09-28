# scripts/blender: the prop toolkit

Generic Blender 5.x tooling for one hero asset. A game repo does not copy these
files; `build.py` in `assets/blender/<slug>/` imports them from the plugin with
these two lines at the top (indented code, paste as is):

    import os, sys
    sys.path.insert(0, os.path.join(os.environ["CLAUDE_PLUGIN_ROOT"], "scripts", "blender"))

Through the blender MCP bridge `CLAUDE_PLUGIN_ROOT` is not set; paste the absolute
plugin path instead.

| Module | Gives | Never |
|---|---|---|
| `palette.py` | `load`, `validate`, `role_index`, roles `body, body2, trim, accent, emissive`; `load_design_system`, `validate_design_system`, `palette_of`, `design_system_of`, `recipe`; `--check` on a palette or a design system | bpy import |
| `spec.py` | the SPEC schema (docstring), `validate`, `face_predicate`, `in_plane_axes`, `volume_bounds`, `thin_extent`, `ngon`, `SpecError` | bpy import |
| `assetlib.py` | `build(spec, style)`; `Builder(style)` with `box`, `prism_x/y/z`, `ring`, `lathe`, `sweep`, `tube`, `groove`, `inset_panel`, `plate`, `vent_slots`, `grille`, `studs`, `finish`; `stats`, `export_glb` | integer material indices; a tube, plate, slot or grille under the design-system floors |
| `pipeline.py` | `main(SPEC, HERE)` for a build.py: `-- --stage previews\|bake\|all [--out <dir>]`, prints `PREVIEWS`, `MAPS`, `LOOK`, `GLB`, `STAGE <name> <s>s` | a bake before the shape is accepted |
| `review_build.py` | `<build.py> [--design-system <json>]`: `REVIEW_FAIL` overlap, thin, seam, role; `REVIEW_WARN` cap, repeat; `REVIEW_VALID:`; `--selftest` | bpy import |
| `render_asset.py` | `setup`, `cycles_setup`, `render_rig` (five named angles), `render_look` (one Cycles shot), `RenderError` on an empty frame | ad-hoc camera vectors |
| `bake_asset.py` | `unwrap`, `bake_maps` (five maps: color, roughness, normal, emissive, metalness; Bevel-node wear, rust, grime, floor dirt, soot from the design-system recipes), `collapse_to_single_material`, `BakeError` on missing UV, node, or a near-black ColorMap | silent skips |
| `check_asset.py` | `check`, `report`, CLI with `--object`, `--budget`, `--no-uv`, `--selftest` | passing over budget |
| `selfcheck.py` | end-to-end proof, exit 0 | writing into the repo |

Verification, from the plugin root:

    python3 scripts/blender/palette.py --check scripts/blender/presets/chunky-cartoon.json
    python3 scripts/blender/palette.py --check scripts/blender/presets/chunky-horror-design.json
    python3 scripts/blender/review_build.py --selftest
    blender -b --python scripts/blender/check_asset.py -- --selftest
    blender -b --python scripts/blender/selfcheck.py

Presets live in `presets/` (`chunky-cartoon.json` bright, `chunky-horror.json` dark
co-op horror); a game copies one to `assets/blender/palette.json` through
`/roblox-gamedev-kit:init-project` and edits the numbers there, never here.

Each palette preset has a design-system preset beside it
(`chunky-cartoon-design.json`, `chunky-horror-design.json`): scale, bevel and
seam floors, `thickness_min`, `join_fraction`, `volume_cap`, one wear, rust,
grime, soot and metal recipe per role, motifs and a forbidden list. A game
copies one to `assets/blender/design-system.json` (init-project) and points
its `palette` at the `palette.json` next to it. `Builder`, `bake_maps`,
`review_build.py` and the prop judge read it; a bare palette handed to the
toolkit borrows the chunky-cartoon design constants.

`examples/generator/` is the reference hero asset built with this toolkit end
to end (`concepts.py` for the four-silhouette sheet, `build.py` for the prop);
`examples/locker/` is the second asset on the same design system and shows
`plate`, `vent_slots`, `grille` and `tube`. A new `build.py` starts from one
of them: a `SPEC` dict, then `pipeline.main(SPEC, HERE)` under `__main__`.
