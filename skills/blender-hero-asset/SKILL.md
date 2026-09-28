---
name: blender-hero-asset
description: Model, preview, bake and export one hero asset in Blender with the plugin's scripts/blender toolkit (palette as data, Builder with cut-in detail, fixed preview rig, guarded bake, headless check), through blender -b or the blender MCP bridge, judged by the prop rubric before the owner imports the GLB. Use when the owner names a modeled asset. Not for procedural Part geometry (roblox-hardsurface), never for unapproved content, never for external meshes outside the gated AI-mesh import step below, never for invented asset ids.
---

# Blender hero asset (method)

The enemy is an agent that models blindly and delivers a mesh it never saw.
The overcorrection is an asset only Blender can render, or a prop that is
"detailed" because it is busy. Every asset is self-made, chunky, cut into
rather than glued on, previewed on the fixed rig, baked, checked by script
and judged before the owner imports it and owns the asset id.

## Representation ladder (decide before modelling)

A mesh is the most expensive way to show something. Walk the ladder and
stop at the first rung that reads at the camera distance the owner cares
about; only the top rung belongs to this skill:

1. Procedural Parts from the blueprint (roblox-hardsurface).
2. A 2D drawing on a ParticleEmitter or BillboardGui (roblox-vfx): an
   entity or sign that moves as a flat image; cheapest on mobile.
3. A static MeshPart baked once, cloned many times.
4. A rigged, animated mesh: only for the few things the camera dwells on.

Evidence for this ladder as a shipped practice: the entity roster of DOORS,
which draws most entities as ParticleEmitters or BillboardGuis and keeps rigged
meshes for a few (https://doors-game.fandom.com/wiki/List_of_Entities). The
rest of that game's asset workflow is undocumented and is not claimed here.

## Project layer (per game)

- `assets/blender/palette.json` (copied from a preset by init-project) is the
  only source of colours and roughness; `assets/blender/design-system.json`
  next to it (same command) holds everything else every asset of the game
  shares: scale, bevel and seam floors, `thickness_min`, the volume cap, the
  wear, rust, grime and soot recipe per role, the signature motifs and the
  forbidden list. `assets/blender/<slug>/` holds `build.py`, `refs/`,
  `previews/`, `textures/`, `.blend`, `.glb`.
- Triangle budget and style camp from the style guide; owner verdicts in the
  owner-taste file are binding until the owner reverses them.
- Measured import facts (scale, yaw, importer grey) in the project learnings;
  reconfirm once per game against a real import.

## Toolkit (this plugin, `scripts/blender/`, see its README)

`build.py` is a `SPEC` dict (schema in `spec.py`: `volumes`, `cuts`, `studs`,
roles by name, the design-system path) plus one `__main__` block that calls
`pipeline.main(SPEC, HERE)`; the toolkit imports stay under `__main__` so
the linter reads the dict without Blender. Volumes: `box`, `prism_*`, `ring`,
`lathe`, `sweep` (a Y skin), `tube` (a 3D pipe); cuts: `groove`,
`inset_panel`, `plate`, `vent_slots`, `grille`; then `studs`. Run it as
`blender -b --python build.py -- --stage previews|bake|all` when no MCP
bridge is connected: `previews` costs seconds, `bake` about a minute, so the
shape is settled on previews before anything bakes. Lint with
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/blender/review_build.py build.py`
(overlaps, thin bars, seams, roles, the volume cap, pasted lists). Start a
new `build.py` from `examples/generator/build.py` or `examples/locker/build.py`.

## Loop

0. **Taste**: read the owner-taste file; a rejected shape stays rejected.
1. **Reference board**: three to six images the owner may see into `refs/`,
   and `refs/NOTES.md` with one line per image: what to steal (a proportion,
   a material break, a wear pattern) and what not to. Reading rules in
   `skills/_shared/reference-board.md`; never trace or copy geometry, no
   external meshes as references, ever (the AI-mesh import step below is the
   one exception, and only for an owner-supplied mesh, never a reference).
   A prop lifted out of a zone inherits two limits
   from that zone's `board.json`: its SPEC roles stay a subset of the roles
   that board mapped, and the board's `do_not_steal` lines join the prop
   review.
2. **Concepts**: four clearly different silhouettes in one `front` render;
   the owner picks. Never present one shape and ask whether it is good.
3. **Primary form**: one dominant volume, subordinate volumes, one accent;
   at most about eight volumes; bevel 0.10 to 0.35 with 2 to 3 segments. A
   prop a character carries or operates is oversized against that body, a hand
   tool at about half a body length, because a correctly scaled tool stops
   reading at the design system's read distance (five of the eight chunky
   reference studies; the prop judge's design gate on `read-40` fails it).
4. **Secondary detail, cut in**: two or three grooves, panels or stud rows
   placed by predicate; leave zones deliberately empty. Seams under 0.08 do
   not read at 40 studs and pull the prop out of the camp.
5. **Look**: `--stage previews` every time; what you did not see is not
   done. `read-40.png` decides what counts as detail. Open the shot and say
   in one line what the owner will see, with the assumptions you made.
6. **Revise** (the design session): the owner reacts to the previews in
   plain words. Quote each remark verbatim, then map it to exactly one of: a
   SPEC change (key, old value, new value), a design-system change, or an
   OWNER question; never to geometry code. A design-system change ("more
   rust") changes every asset of the game: say so before editing it. Apply
   the SPEC changes, run `--stage previews`, open the shot the remark was
   about, and report in one line what moved and what the run cost. Fix every
   `REVIEW_FAIL` from `review_build.py` before the next render. Repeat until
   the owner says it is good; only then bake (step 7) and judge (step 9).
   Never bake to answer a shape question, and never read "good" into silence.
7. **Tertiary detail in the bake only**: `--stage bake` (plate variation,
   Bevel-node edge wear, rust, grime, floor dirt, soot, five maps, one
   material). A `BakeError` blocks; never work around it.
8. **Check**: `blender -b <file.blend> --python scripts/blender/check_asset.py -- --object <name> --budget <n>`
   must print `CHECK_VALID:true` (the bake stage prints it as well).
9. **Prop judge**: `visual-judge` prop mode on the five rig previews, the dark
   look shot step 7 wrote, and the design-system summary; FAIL goes back to
   step 6 with the findings, at most three prop rounds.
10. **Export and report**: `.blend`, GLB, five textures, previews; report
    path, triangles, dimensions, and what to check after the Studio import
    (MetalnessMap assigned, the emissive mask glowing). Name one recommended
    CollisionFidelity (Box, Hull, Default or PreciseConvexDecomposition) with
    one sentence on why this asset's shape earns it: Box for a boxy volume,
    Hull for a convex one, Default for a prop with a shallow recess a player
    never enters, PreciseConvexDecomposition only where geometry must be
    walked through or shot past. It is a MeshPart property in Roblox, not
    something Blender can measure, so `check_asset.py` never reports it. The
    owner returns the asset id; never invent one.
11. **Record**: lessons through `skills/_shared/learnings-protocol.md`; the
    owner's verdict verbatim into the owner-taste file, with one line on what
    it means for the next asset.

## AI mesh import (Meshy, Tripo, Hunyuan3D, Roblox Cube)

A mesh from an AI generator (Meshy, Tripo, Hunyuan3D, Roblox Cube) never
enters through the reference board and never skips the checks a self-made
asset gets. Before it reaches step 8 of the loop, run
`blender -b <file.blend> --python scripts/blender/check_asset.py -- --object <name> --budget <n>`
for the triangle budget and the four checks `check_asset.py` adds beyond
geometry counts: extra UV sets, an unapplied transform, non-manifold edges,
and more than one material slot. `CHECK_VALID:false` on any of these blocks
the import; fix the mesh and re-run rather than importing around the
failure. Tells `check_asset.py` cannot see in pixels or in bone data:
reject a colour map with light and shadow painted in (flat colour only;
Roblox lighting draws the shading); reject a vertex-colour layer from the
generator too, since it does not react to Roblox lighting either (bake its
intent into the ColorMap image and drop the layer); export the GLB with
every texture packed/embedded, never referenced by an external relative
path, or the import shows grey; limit every vertex to its top four
bone-weight influences and apply/freeze the rest pose before export,
because Roblox reads only four; keep the mesh under the ~2048-stud max
BasePart/MeshPart dimension, splitting into parts or scale-correcting
otherwise; hide normal-map seams by baking with margin/padding and routing
seams through low-curvature areas; hand-fix or remodel melted, blobby small
details rather than shipping the generator's guess at them; recalculate
normals outside and check the Face Orientation overlay before export,
because a flipped face renders dark or vanishes in Studio; and require
OpenGL tangent-space normals, never DirectX (the green channel convention
is inverted between the two and Roblox reads OpenGL).

## Traps

- Headless has no window: work through `bpy.data` and `bmesh`; set selection
  and active object before every `bpy.ops.object.*` call.
- Through the MCP bridge one call runs on the main thread with a timeout:
  build, render and bake in separate calls and save the `.blend` between.
- Blender 5.x has no `use_auto_smooth`; the toolkit shades flat and lets
  bevels carry the rounding.
- `sweep` bridges a profile along Y only; a pipe that turns is a `tube` with
  3D points, never a sweep with dx and dz tricks (generator, round 2).
- A bevel on a flat interior edge (a ring edge that changes no direction)
  degenerates; put the step into the lathe profile instead (generator, round 3).
- Edge wear uses the Bevel node with an absolute radius; a bar under
  `thickness_min` is all edge and bakes bare, which is why `tube` and the
  linter refuse it (generator, round 4).
- The rig angles are fixed (`render_asset.RIG`): `front` looks from -y, `side`
  from +x, `top` from +z, `three-quarter` and `read-40` from +x and -y. A cut
  or a stud on -x or on +y is therefore invisible in every judged shot; read
  that table before placing secondary detail rather than assuming `side` shows
  the flank you cut (beacon, round 3, where a grille and a groove both landed
  on -x and the judge scored the flank as bare twice).
- Workbench, which renders those five shots, evaluates no emission: the
  emissive role is flat colour there and a glow is only visible in the dark
  look shot the bake writes (beacon, rounds 2 and 3; numbers in
  `assetlib.EMISSION_PREVIEW_STRENGTH`).
