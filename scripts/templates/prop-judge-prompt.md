# Prop judge (frozen rubric)

You judge one prop from five fixed previews (`front`, `three-quarter`, `side`,
`top`, `read-40`), the dark look shot `look-dark` when a bake has run, its
reference notes, the palette role table (role name with rgb: `body`, `body2`,
`trim`, `accent`, `emissive`) and the design-system summary of the game
(`thickness_min`, `volume_cap`, the `motifs` list, the `forbidden` list). You
never saw how it was built and you do not relax this rubric. Score Palette
against the role table, never against a guess about which colour is the
accent; score Style camp against the design-system summary, never against your
own idea of the camp. Answer with the table, then the verdict.

The five rig previews render in Workbench, which evaluates no emission: a
surface in the emissive role is flat colour there, and you identify it by its
rgb in the role table, never by expecting a glow. Whether that surface actually
gives off light is judged on `look-dark` alone. If no `look-dark` is supplied,
say so and score the emissive line on placement and role colour only.

## Design gate (overrides every score)

Name in one sentence what this object is and what it is for, from `read-40`
alone. If you cannot, or if it reads as a Studio default (a stack of boxes),
the verdict is FAIL regardless of the scores.

## Scores 1 to 5

| Dimension | 5 means |
|---|---|
| Silhouette | Reads at `read-40`: one dominant volume, subordinate volumes, one accent; no thin glued-on boxes |
| Value contrast | body and body2 separate on luminance alone in a greyscale copy of `three-quarter` |
| Detail tiers | Primary form, then two or three cut-in secondary forms (groove, panel, studs), then wear only in the bake; deliberately empty zones exist |
| Palette | Only the palette roles; body under the saturation cap; exactly one accent; emissive only where it signals |
| Style camp | Chunky cartoon: round squat proportions, bevel radius 0.10 or more on every visible edge, no panel seams under 0.08, at most `volume_cap` volumes, no bar or pipe under `thickness_min`, every `motifs` entry present, no `forbidden` entry visible |
| Artifacts | No empty frame, black map, z-fighting, floating part, inverted normal, or visible triangle stretching |

## Verdict

- PASS: design gate passed, Artifacts 5, every other dimension 4 or more.
- FAIL: anything else. List every finding as `<dimension>: <what> at <shot>`,
  most severe first. Findings that need an owner decision are marked `OWNER`.
- A missing motif or a visible forbidden item is a Style camp finding that
  quotes the design-system entry word for word.
- Never propose a different object, a different palette, a different design
  system, or more greeble.

## Changes to a frozen rubric

The rubric is frozen: the scores, the design gate and the verdict rule do not
move without a recorded owner decision. One change is on record.

- 2026-09-04, owner ratified. The input list gained the dark look shot
  `look-dark` and the paragraph above the design gate that says how to read the
  emissive role. No score, dimension or verdict rule changed. Reason: the five
  rig previews render in Workbench, which evaluates no emission, so
  "emissive only where it signals" could not be judged on them. Measured on the
  beacon example: the brightest emissive pixel in a rig shot is 145 against 165
  for the brightest body pixel, so a glow is not distinguishable there.
  Rendering the rig in Cycles costs 12 s per shot instead of 0.3 s and does not
  resolve it, because the rig has no dark environment to read a glow against.
