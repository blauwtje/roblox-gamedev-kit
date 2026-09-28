# Reference board protocol (shared)

This file is not a skill and is never invoked on its own. It is the single home
of the protocol for turning owner-supplied reference images into buildable data.
Change it here; never re-state it inside a `SKILL.md`.

The enemy is an agent that is handed a folder of concept art, looks once, forms
an impression, and builds from memory: it copies characters, believes geometry
the generator invented, imports a colour that is only there because of the
render's bloom, and drifts from the images over ten edits with nothing able to
notice. The overcorrection is a board that grows into a second style guide, or
a bar of "look more like the picture" that no procedural build can reach.

## What the board is

One `board.json` per **zone**, in the game repo at `assets/refs/<zone>/`, with
the owner's images and the generated `sheet.png` beside it. The kit downloads
nothing and stores no images; the owner puts them there.

A single prop keeps its `refs/NOTES.md` exactly as it is. A board is for a
space: a room, a corridor, a hall. Six images per board is the ceiling.

An image folder without a `board.json` is a `BOARD_FAIL noboard`: deleting the
board is not how a picture stops being a source. The board may tighten its own
`tolerances` and never loosen them, and every value it moves is warned.

## Three blocks, three owners

| Block | Written by | Read by |
|---|---|---|
| `measured` | only `refboard.py --measure`, sealed with a digest | nobody directly; it is the evidence |
| declarations | by hand: `masks`, `characters`, `steal`, `do_not_steal`, `cannot_tell`, `role_map`, `unmatched`, `lights_declared` | `--check`, which holds them against `measured` |
| `zone_facts` | by hand | **the only block a builder reads** |

They fail apart on purpose. `zone_facts` speaks in studs, palette role names and
ranges: no hex, no image language, nothing a builder has to interpret.

Never edit `measured` in a text editor. The digest covers the image bytes, the
sampler constants and the block itself, so a hand-typed number is a
`BOARD_FAIL stale`.

## The loop

0. **Taste first.** Read the project's owner-taste file and `palette.json`. A
   colour or a shape the owner rejected stays rejected even when every
   reference is full of it.
1. **Intake.** The owner drops three to six images into `assets/refs/<zone>/`.
   `refboard.py --init <dir> --zone <id>` writes the skeleton: one entry per
   image with its sha256 and `"characters": "TODO"`, and nothing else.
2. **Declare before measuring.** Per image, answer `characters`, draw a mask
   box with a reason around every character region and every generator
   watermark, and write `do_not_steal` (never empty), `cannot_tell`, and
   `steal` lines that each name the key they `produces`. Masking first is what
   keeps those pixels out of every number that follows.
3. **Measure.** `--measure` writes the sealed block. Then `--sheet` and open
   `sheet.png`: masks hatched, light blobs ringed, family swatches with shares,
   and each frame at read distance beside it. What you did not look at is not
   measured.
4. **Admit only what survives read distance.** A `steal` line is admissible
   only for something still legible in the read-distance panel. Everything that
   dissolves there becomes a `do_not_steal` line, together with everything that
   does not resolve as geometry: a pipe run that crosses itself, a cable that
   hangs from nothing, invented signage text. This is where a generator artefact
   gets written down instead of believed.
5. **Reconcile colour.** Assign families to palette roles by name in
   `role_map`. Never type a hex the tool did not print, and never a sixth role.
6. **Scale by declaration.** Name one `scale_anchor` that resolves to a real
   constant in the project's blueprint source, then write `zone_facts` as
   ranges.
7. **Check.** `--check` must print `REFBOARD_VALID:true`. Fix every
   `BOARD_FAIL` before a single Part is placed; report every `BOARD_WARN` to
   the owner rather than silencing it.
8. **Hand off.** See the table below.
9. **Judge.** Refresh the zone's shot-list rows so each names the board key and
   the measured number it must answer, and put the `--compare` delta table into
   the shot list's measured-deviations slot. `judge-prompt.md` stays frozen and
   the judge never receives the concept art.
10. **Record.** Lessons through `skills/_shared/learnings-protocol.md`; owner
    verdicts verbatim into the owner-taste file. A motif proven on a second
    board is promoted (moved, not copied) into `design-system.json` `motifs[]`,
    which is announced first because it changes every asset of the game.

## The colour rule

Concept art is a lit render; `palette.json` is albedo. The tool compares them in
CIELab on chroma only, because L\* mostly measures the exposure, and runs a
separate check that two mapped families keep the palette's own luminance order.

- Colour enters as a **role name**, never as a hex.
- A family above `family_floor` is either mapped or carries an `unmatched`
  entry with a resolution: `light_only`, `out_of_camp`, `owner_decision` or
  `palette_change` (the last also needs `palette.py --check` green and an
  owner-taste line).
- **A lit pixel is a light colour and never a surface role.** A wall under a red
  beacon is not a red wall.
- A family present in one image only is a prop or a grade, not a zone material.
- An unmatched family is an owner question. The five roles and their contrast
  rules are the design, not a limitation, so nothing here ever rewrites
  `palette.json`.

## The scale rule

There is no perspective solver and there will not be one: a single frame carries
no metric depth, and a vanishing-point fit needs line pairs marked by eye plus
an unknown camera height. Every stud dimension is therefore a **range**, at
least `range_min_width` wide, and the board names one `scale_anchor` constant
that already exists in the project's blueprint. The script greps for it there.

## The exclusion rule

Characters in a reference are permitted **scale rulers** and forbidden
**geometry**. Four layers, because none of them alone is enough:

1. The mask box, applied before quantization, the histogram and the blob
   detector, so no number in the board is ever built on a body.
2. `characters` is a required answer. `"present"` with no mask is a
   `BOARD_FAIL unmasked`; a surviving `TODO` is a `BOARD_FAIL characters`.
3. A narrow character-term denylist over every declaration that can reach the
   build (`steal`, `unmatched` notes, `lights_declared`) and over `zone_facts`.
   Mask reasons, `do_not_steal` and `cannot_tell` are not scanned: naming the
   thing is exactly right there.
4. `forbidden` in `design-system.json` carries the entry, and the prop judge and
   the shot list already quote that list verbatim.

Stated plainly: **nothing detects a character in the pixels.** The answer is
required, not guessed. Anything that must feel alive is rung 2 of the
representation ladder, drawn from scratch, never a shape recovered from an image.

## Where each number lands

| Number | Lands in | Not in |
|---|---|---|
| footprint, opening, element ranges | the Luau blueprint, with the producing board key in the trailing comment | a builder literal |
| role per surface | the blueprint palette, by role name | a colour literal |
| light kind, count, position | the blueprint's effect data (`roblox-vfx`) | an eyeballed sample |
| a motif proven on two boards | `design-system.json` `motifs[]` | the board |
| the visual direction | the project style guide | the board |
| an unmatched family | the owner-taste file, as a question | `palette.json` |

The seam rule, `thickness_min` and the part budget outrank every board line: a
detail that cannot be built to the rules becomes a `do_not_steal` line, never a
violation.

## Commands

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/refboard.py" --init assets/refs/<zone> --zone <zone>
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/refboard.py" --measure assets/refs/<zone>/board.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/refboard.py" --sheet   assets/refs/<zone>/board.json
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/refboard.py" --check   assets/refs
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/refboard.py" --compare assets/refs/<zone>/board.json \
        --image <id> --shot docs/visual/<shot>.png
```

`--check assets/refs` is the gate step, and prints `REFBOARD_VALID:true (0
boards)` on a game that has no zones yet. The script needs Pillow and is
deliberately off the hook path; without it it exits 2 and nothing else in the
kit is affected.
