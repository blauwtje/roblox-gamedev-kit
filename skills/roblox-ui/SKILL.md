---
name: roblox-ui
description: Interface construction (HUD, menus, feeds and buttons) via the project's Studio MCP UI route (with a mandatory design brief where the bridge requires one), 9-slice panels, and the UI section of the project style guide as style source. Use for every screen or HUD request. Not for 3D signage in the world (roblox-hardsurface), not for the gameplay logic behind the UI, never with downloaded art or invented text.
---

# Roblox UI (method)

The enemy is an interface that originates as loose Studio handwork and whose
source nobody can find again. Structure comes from code or a documented
bridge route, styling follows the style guide, text content is an owner
decision.

## Working method

1. **Start with the bridge's UI route** (design brief mandatory where the
   MCP server requires it) and record the brief in the report.
2. **Style source**: the UI section of the project style guide (fonts,
   outlines, wayfinding without words). Icons and logo are owner assets; a
   programmatic SVG-to-PNG route is an alternative to be tested, not a done
   deal. No chat image tools, no downloads.
3. **9-slice for scalable panels**: `ImageLabel`/`ImageButton` with
   `ScaleType = Enum.ScaleType.Slice` and a fitting `SliceCenter`; textures
   from the project's own bake or generator route, uploaded following the
   project's upload protocol. Verify every further API before use.
4. **Display-only client**: UI shows state; every action goes through the
   existing remote contracts and is validated server-side. Do not invent
   names, prices or text: the UI shows what the catalogs supply.
5. **Verify visibly**: a UI change is only done after a screenshot or an
   owner look; the gate only proves compilation.

## Screen rules from the co-op reference corpus

Each line is one rule plus its reason and the check that fails it. The number
in brackets is how many of the eighteen co-op reference studies state it in an
observation section; a rule under two was not admitted.

- **Corners and edges, centre clear** [14]: HUD elements sit in the screen
  corners and along the edges and the centre stays free, because the centre is
  where the player looks at the world; an element in the centre is a design
  brief finding. No element count is prescribed: only one study states one and
  three others exceed it.
- **The world carries it first** [8]: prefer a physical in-world display over a
  screen overlay wherever the world can carry the information, because an
  overlay is the same information without a place; every overlay element must
  say in the brief why the world could not carry it.
- **Gauges, not bare numbers** [5]: pair a vital with a bar, a dot row or a
  segmented column rather than a bare number, because a shape reads at a glance
  and a number has to be parsed; a vital with no gauge is a brief finding.
- **Prompts sit on their object** [3]: an action prompt sits beside or above
  the object it acts on, one per object, because a prompt in a central list
  makes the player map words to things; a spec assertion that every prompt is
  parented to the object it acts on fails it.

## Rules against the code-only look

Each line is a rule, the reason, and the check that fails it. Where
`scripts/slop-rules.json` already has a matching id, `scripts/slop-scan.py`
enforces it at scan time; where it does not, the check is a design-brief or
screenshot finding.

- **Image panels, not code shapes**: panels, buttons and frames are uploaded
  9-slice images (`ImageLabel`/`ImageButton` with `ScaleType.Slice`), never a
  `Frame` + `UICorner` + `UIGradient` + `UIStroke` stack or a purple-to-blue
  "glass" gradient, because that stack is the default shape a model draws
  when it has no image tool; `scripts/slop-scan.py` fails this on the
  `ui-gradient` rule.
- **Own icons, not emoji**: icons are an own set in one style, uploaded as
  decals, never an emoji character in a string, because emoji is the
  cheapest icon a model can type; `scripts/slop-scan.py` fails this on the
  `emoji-string` rule.
- **One theme font, not Gotham**: text uses one chosen display font plus one
  body font set in a theme module, never `Enum.Font.Gotham`, because Gotham
  is the tutorial default; `scripts/slop-scan.py` fails this on the
  `font-gotham` rule.
- **Scale sizes with aspect constraints, tested on phone and console**: every
  panel uses `Scale` sizing plus a `UIAspectRatioConstraint`, tested on
  phone, tablet and console, because an `Offset`-only size only works on the
  one screen it was pictured on; no `scripts/slop-scan.py` rule covers this
  yet, so a screenshot on each form factor is the check that fails it.
- **Hover, press and click-sound feedback**: every button tweens on hover
  and press and plays a click sound, because feedback is not in the prompt
  and a model leaves it out by default; no `scripts/slop-scan.py` rule
  covers this yet, so an owner look at the built screen is the check that
  fails it.
- **No purchase prompt on join**: a `PromptPurchase`/`PromptGamePassPurchase`
  call is gated behind a player action, never fired from `PlayerAdded` or
  another on-join handler, because a prompt before any action reads as spam;
  no `scripts/slop-scan.py` rule covers this yet, so a spec assertion that no
  purchase prompt fires from the join handler is the check that fails it.
- **No text-wall tutorial**: the first mechanic is taught through doing,
  never a long, read-heavy popup shown before play starts, because a wall of
  text on join is a model's default explainer; no `scripts/slop-scan.py`
  rule covers this yet, so an owner look at the join flow is the check that
  fails it.
- **Designed first 60 seconds**: where to go and what to press is decided
  and built, never a bare spawn with no guidance, because a silent spawn
  leaves a new player lost; no `scripts/slop-scan.py` rule covers this yet,
  so an owner playtest of the first 60 seconds is the check that fails it.

## Boundaries

- Mobile first: generous touch targets, no effects that vanish on a phone.
- No model or alias in configuration, no invented asset ids.

## Learnings

`references/learnings.md` in the project layer; protocol in
`skills/_shared/learnings-protocol.md` (this plugin).
