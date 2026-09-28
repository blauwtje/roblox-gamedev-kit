---
name: roblox-vfx
description: Procedural visual effects (ParticleEmitter, Beam and Trail) via blueprint data and the project's world builders, particle textures via the project's own bake route and Open Cloud upload. Use for ambience, machine or prop effects. Not for light fixtures (roblox-hardsurface), not for UI effects (roblox-ui), never with downloaded or invented assets.
---

# Roblox VFX (method)

The enemy is an effect that hangs in the place as loose Studio handwork and
disappears on the next rebuild. Effect data belongs in the project's
blueprint, construction in the builders.

## Working method

1. **Verify every API before use** via the project's type definition file or
   an api-verifier dispatch; a member that is not there is one you do not
   use.
2. **Data first**: every emitter or beam gets a spec in the blueprint and a
   builder that builds it; the gate and the acceptance test see the effect
   emerge from the build.
3. **Mobile cost as a practice, not a number**: the lowest rate and lifetime
   that stay readable, emitters off when out of view, measure with the
   MicroProfiler instead of inventing threshold numbers.
4. **Textures through the project's own chain**: bake tooling or procedural
   generator, upload following the project's upload protocol (owner
   permission per upload, read the ids back, never invent them).
5. **Palette**: an effect colour is a palette role by name, taken from the
   zone board's `role_map`; a family that board left unmatched never becomes
   an effect colour, and a lit pixel in a reference is a light colour and
   never a surface role. No new accent without an owner decision.
6. **Flat entities**: a character, creature or signal that only needs to be
   seen, not walked around, is a drawn image on a ParticleEmitter or a
   BillboardGui before it is ever a mesh (rung 2 of the representation
   ladder in blender-hero-asset). The drawing is project-made and uploaded
   through step 4; no downloaded art, and never a shape recovered from a
   reference image. A fixture's hue, count and position come from the zone
   board's `lights_declared` entries and the measured blobs behind them,
   never from an eyeballed sample.

7. **Flat drawn shapes, no post**: an effect is a drawn flat shape, a speed
   line, a scribble, a splash, a coloured ground trail or one transparent
   coloured block, and no post-processing effect carries it, because a
   volumetric system and a screen filter both cost most on the platform the
   game has to run on (two chunky reference studies state it outright; the
   preflight assertion that Lighting gained no post-processing effect fails
   it).

## Rules against left-at-default effects

Each line is a rule, the reason, and the check that fails it.

- **Author every ParticleEmitter, no insert defaults**: `Rate`, `Texture` and
  the `Color`/`Size`/`Transparency` sequences are set per effect, never left
  at insert defaults (Rate 20, default sparkle, flat white, no authored
  sequences), because an unauthored emitter reads as unfinished; no
  `scripts/slop-scan.py` rule covers this yet, so a screenshot of the built
  effect is the check that fails it.
- **Juice on every reward**: a shake, particle burst or pop plays on the
  reward moment (pickup, level-up, purchase, milestone), never a silent
  payout, because a model leaves reward feedback out by default; no
  `scripts/slop-scan.py` rule covers this yet, so an owner look at the built
  effect is the check that fails it.

## Boundaries

- Server-authoritative stays leading: purely visual effects may be
  client-side (display-only), anything with gameplay meaning is server-side.
- No downloaded effect assets, no invented content or text.

## Learnings

`references/learnings.md` in the project layer; protocol in
`skills/_shared/learnings-protocol.md` (this plugin).
