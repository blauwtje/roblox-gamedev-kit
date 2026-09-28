---
name: visual-judge
description: Adversarial screenshot critique loop on a procedural world. Edit-mode preview in Studio, scripted preflight, coplanar sweep, an independent judge agent that scores fixed camera shots against a rubric it may not relax, fixes in the data/builder layer, repeat until PASS or a stop condition. Use after every verified world change or on owner request. Not for gameplay or economy, not during a playtest, and never as a replacement for the owner playtest gate.
---

# Visual judge (loop method)

The enemy is "it will probably look fine" from an agent that cannot look.
The overcorrection is an endless loop against a bar the platform cannot
reach. This loop gives the builder eyes (Studio screenshots via the MCP
bridge), an impartial critic with a frozen prompt, and hard stop conditions.

## Project layer (per game)

- `references/judge-prompt.md`: the rubric and verdict rules, owner-frozen;
  the orchestrator passes it verbatim and may only add the shot list, the
  report path and the previous round's findings.
- `references/shot-list.md`: static part (subject, test question, measured
  deviations, mandatory list) plus a generated block that a script derives
  from the blueprint; `--check` before every round.
- Preflight, preview and sweep scripts under the project's `tools/`.
- For a zone with a reference board, each shot-list row names the board key
  and the measured number it must answer, and the measured-deviations slot
  carries the `refboard.py --compare` delta table under its own header line
  saying it is a measured delta and not a similarity score. The judge never
  receives the concept art and `judge-prompt.md` stays frozen; a finding that
  asks for something on a `do_not_steal` line is answered by quoting it.

## The loop

1. **Preview** built from the real builders (never handwork in Studio).
2. **Preflight sweep**: scripted, expectations derived per run (mesh scale,
   Lighting against the Rojo source, place defaults, counts against the
   headless build). Every FAIL blocks the round.
3. **Coplanar sweep**: fix every candidate z-fight plane first; otherwise the
   judge finds them anyway and that costs a full cycle.
4. **Judge round**: one fresh `general-purpose` agent (never a fork: it
   inherits the builder's reasoning and is not independent) with the prompt,
   the list, the report path and the previous findings. **Delta round after
   a fix pass**: only the shots of affected zones plus the mandatory list; a
   full round starts a series and is the only candidate for a final verdict.
5. **Triage**: fixable / owner decision / beyond platform reach. Test all
   stop conditions here after every round; if one applies, stop immediately.
6. **Fix round**: batched per subsystem, gate after every batch, at most one
   subsystem directly after a measured regression. Data first, then
   builders, then the spec that should have caught it; a geometric fix is
   only done once the shot list (generator) and judge prompt describe the
   new state.
7. **Log**: exactly one table row per round in the judge log; prose belongs
   in the round report.
8. **Learnings** following `skills/_shared/learnings-protocol.md`.

## Verdicts and stop conditions

- Verdicts: `PASS`, `FAIL`, and `KLAAR-BEHOUDENS-OWNER` (done pending owner:
  design gate PASS, nothing blocking, artifact dimension at maximum, and
  every open severe finding demonstrably requires an owner decision, an
  asset pass or a platform feature).
- Stop at the first of: final verdict; the round maximum (default five
  rounds, the owner may choose otherwise at invocation); three consecutive
  FAIL rounds (see the divergence step below); two rounds without an
  accepted fix; everything open is owner/platform; owner interrupts.
- Divergence step after three consecutive FAIL rounds: stop patching the
  current form. Build two structurally different candidate directions (a
  different silhouette, layout or material logic, not a tweak of the same
  form), render both from the same shot list, and present them side by side
  with one line of rationale each and the finding they answer. Wait for the
  owner's pick before any further round; the pick goes verbatim into the
  owner-taste file. Measured on the bench and the dining hall: rounds 4 to
  15 against one form kept landing on "too simple" or "too empty", so the
  cheap move is a second direction, not a fourth patch.
- Never relax the rubric to reach PASS, and never declare the loop done on
  your own screenshots.

## Prop mode (before a Studio import)

One prop, judged from the five rig previews `render_rig` wrote, the dark look
shot `previews/look-dark.png` once a bake has run, plus `refs/NOTES.md`. One
fresh `general-purpose` agent gets the project's copy of
`prop-judge-prompt.md` verbatim (template in `scripts/templates/` of this
plugin), those paths, the notes and the design-system summary (the
`thickness_min`, `volume_cap`, `motifs` and `forbidden` entries of
`assets/blender/design-system.json`, pasted as JSON); nothing else.

The dark shot is not decoration. The five rig previews render in Workbench,
which evaluates no emission, so an emissive surface is flat colour in every one
of them and a judge asked whether a signal glows can only guess. Measured on
beacon round 3: the brightest emissive pixel was luminance 145 against 165 for
the brightest body pixel. Rendering the rig in Cycles does not fix it either
(measured: 12 s instead of 0.3 s, and the emissive still 63 below the lit body,
because the three-point rig outshines it); the dark look shot is where emission
reads. PASS lets the asset go
to the owner; FAIL goes back to `blender-hero-asset` with the findings, at
most three prop rounds. The world loop above stays untouched.

## Learnings

`references/learnings.md` in the project layer; protocol in
`skills/_shared/learnings-protocol.md` (this plugin). Owner verdicts go
verbatim into the project's owner-taste file.
