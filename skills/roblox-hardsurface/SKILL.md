---
name: roblox-hardsurface
description: Model hard-surface world geometry and props from procedural Parts in strict Luau, using the box vocabulary, the seam/proud-trim rule, budget discipline and the fixed recipe shapes (blueprint as data, builders as construction, spec as proof). Use for every world geometry, furniture, trim or decor request. Not for gameplay logic, remotes, UI or Blender mesh work (blender-hero-asset).
---

# Roblox hard-surface (method)

The enemy is the blockout that stays a blockout: flat unbroken faces,
coplanar seams, one grey, light everywhere. The overcorrection is greeble
past the part budget or inventing content the owner has not approved.

## Project layer (per game, in the game repo)

This skill carries the method; each game carries its own data and numbers:

- **Style guide** with the visual direction and the "measured and rejected"
  list.
- **Blueprint module** (pure data: rooms, walls, anchors, palettes, budgets;
  only `Vector3`/`CFrame`/`Color3`) plus **builders** that turn it into
  Instances, and **specs** that test the data.
- **Constants table** (seam overlap, trim depth, budgets, human scale) in the
  project copy of this skill or the style guide; a guard enforces equality
  with the Luau source. Never repeat those numbers from memory.
- **Reference board** per zone the owner gave images for:
  `assets/refs/<zone>/board.json`. Surface colours come from the roles that
  board mapped, never from a colour literal in a builder. Protocol in
  `skills/_shared/reference-board.md`.

## Box vocabulary (the pattern)

- `Box = { center: Vector3, size: Vector3 }` with helpers for min/max, the
  inner face per side, a box from three `NumberRange`s (along the wall, up,
  through the wall), a "proud" range in front of a face, and span
  subtraction for door openings.
- Three building blocks: a colliding `solidBox`, a non-colliding `decorBox`,
  and a `neonBox` (Neon, no shadows, decor).

## The seam rule (never violate)

Two visible faces never share a plane. Anything that touches something sinks
the project's seam overlap into it; trim and frames stand proud by the trim
depth. A coplanar sweep on the Edit-mode preview finds violations; run it
after every geometry change.

## Zone rules from the co-op reference corpus

Each line is one rule plus its reason and the check that fails it. The number
in brackets is how many of the eighteen co-op reference studies state it in an
observation section; a rule under two was not admitted.

- **One hue per zone** [8]: give a zone one dominant hue and keep the step
  between two zones larger than any step inside one zone, because a player who
  cannot name a zone from its colour falls back on reading a sign; a spec
  assertion over the blueprint palette table fails it.
- **Work floors stay readable** [6]: a room where players work reads without a
  carried light and its shadows are coloured rather than black, because
  darkness that hides a task is a cost and not a mood; a task surface in black
  shadow is a blocking judge finding.
- **No words in the world** [6]: no room label, no direction word and no
  sentence, with text allowed only on a control the player operates and on a
  joke prop, because a world that needs words has already failed at silhouette
  and light; the build check lists every text string in the built tree and each
  one must name its control or its joke.
- **Light points at the destination** [6]: in a zone lit by one or two dominant
  sources the strongest light aims at the place the player goes next and the
  fix for a shot whose brightest surface is elsewhere is aiming rather than
  another lamp, because light is read before signage; it does not apply to
  evenly lit zones, where the same studies hand wayfinding to landmarks.
- **The goal is the tallest silhouette** [2]: the goal of a zone is its tallest
  object and carries a shape no dressing in that zone repeats, because a
  landmark that shares its shape with dressing stops being a landmark; a spec
  assertion that its top clears every wall top in the room box fails it.
- **A state is a recolour** [3]: signal a change of state by recolouring light
  that is already there instead of adding a prop or a sign, because the
  recolour costs no geometry and reads across the whole room at once; the judge
  delta round on the state shots fails it.

## Working method for a prop or a zone

0. Reference images enter only through the zone's board: read it, and have
   `refboard.py --check` green, before the first blueprint number. A picture
   you looked at but wrote no board line for is not a source.
1. Read the builder you are extending and the blueprint for the numbers that
   already exist; grep the type definition file for every API you have not
   yet seen in `src/`.
2. Placement data as a typed table in the blueprint (position, size,
   per-instance yaw or variant) with a comment on the line behind it; never
   `math.random`, never manual work in Studio: the same blueprint yields the
   same model. The only allowed form of variation is a seeded catalog: the
   seed is data in the blueprint, the draw is a pure LCG or
   `Random.new(seed)` in shared code, `partCount(seed)` is predictable, and
   the spec runs over a seed range (measured 2026-09-02: `Random` can be
   absent from a Lune test bundle; a pure LCG keeps spec and builder on one
   sequence). A value taken from a board carries its producing board key in
   that trailing comment.
3. Build in the matching builder; collision only on what a player touches;
   thin strips and Neon without shadows.
4. Seam rule on every contact; thin decor at least 0.3 studs thick (thinner
   shimmers at a distance). The seam rule, the thickness floor and the part
   budget outrank every board line: a detail from an image that cannot be
   built to the rules becomes a `do_not_steal` line, never a violation.
5. Count the parts and report the new total against the budget.
6. Assert the data in a spec (inside the room box, clear of the walking
   route, no forbidden overlap) and keep the acceptance test green.
7. Deliver the proof to the main session: the verification gate runs there
   via the hook as soon as you return; a subagent never runs it itself and
   ends with `VERIFICATION NOT RUN`.

## Learnings

`references/learnings.md` in the project layer is this skill's memory. Read
`skills/_shared/learnings-protocol.md` (this plugin) at the start of a run
and follow it when writing. Owner verdicts on delivered work go verbatim
into the project's owner-taste file.
