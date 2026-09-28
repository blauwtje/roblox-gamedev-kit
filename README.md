# roblox-gamedev-kit

Reusable Claude Code plugin for building Roblox games: skills as method,
agents as working practice, hooks as the deterministic backbone, and a lessons
protocol that lets a mistake happen only once.

## Loading

```sh
git clone https://github.com/blauwtje/roblox-gamedev-kit.git
claude --plugin-dir /path/to/roblox-gamedev-kit
```

- The plugin loads per session; there is nothing to install.
- An edit to a `SKILL.md` takes effect immediately in the running session;
  for changes to `hooks/`, `agents/` and `.mcp.json` run `/reload-plugins`
  or restart the session.
- Deliberately no skills-dir install (`~/.claude/skills/`): that loads in
  every project, and this plugin carries hooks that belong only in a Roblox
  project layer.
- `plugin.json` carries `version` and `author`:
  `claude plugin validate --strict` counts their absence as an error. The
  version does not affect the local workflow (edits keep working directly);
  bump it on a meaningful change, without ceremony.

## Project layer convention (stays per game in the game repo)

The plugin carries the method; each game carries its own data. These stay in
the game repo:

| Project layer | Example path in the game repo |
|---|---|
| Style guide and owner decisions | `.claude/skills/roblox-hardsurface/references/style-guide.md`, `_shared/owner-taste.md` |
| Lessons source and views | `.claude/lessons.jsonl` plus the compiled views |
| Constants and blueprint | `src/shared/StationBlueprint.luau` (or its equivalent) |
| Shot list and judge artifacts | `.claude/skills/visual-judge/references/shot-list.md`, `docs/visual/` |
| Reference boards | `assets/refs/<zone>/board.json` plus the owner's images and the generated `sheet.png` |
| Denylist contents | `.claude/known-bad.json` (started empty per game) |
| The gate | `tools/gate.sh`, the contract: one script, the game fills in the steps |

Hooks in this plugin call scripts via `${CLAUDE_PLUGIN_ROOT}/scripts/` and
project data via `${CLAUDE_PROJECT_DIR}`; the gate hook runs
`${CLAUDE_PROJECT_DIR}/tools/gate.sh`, never a step list of its own.

**Deliberately no `.mcp.json` in the plugin**: the MCP configuration (Studio
bridge, Blender bridge) is machine- and project-bound and stays in project or
user config.

## Flow-back protocol

A lesson or working practice that turns out to apply to more than one game
moves from the project layer into this plugin (same route as the lessons
protocol in `skills/_shared/learnings-protocol.md`: promotion is a deliberate
move, not a copy). Project-specific lessons stay in the game repo.

## Blender toolkit (`scripts/blender/`)

The prop pipeline ships with the plugin: palette as data with presets and a
validator, `Builder` with cut-in detail helpers, a fixed five-angle preview
rig, a guarded Cycles bake, a headless acceptance check and an end-to-end
selfcheck. A game imports it from `${CLAUDE_PLUGIN_ROOT}/scripts/blender` and
keeps only its `palette.json` and per-asset `build.py`. Details and the API
table: `scripts/blender/README.md`.

## Reference boards (`scripts/refboard.py`)

An owner drops reference images in `assets/refs/<zone>/` in the game repo and a
board turns them into data a builder can be held to: `--init` writes the
skeleton, `--measure` writes a digest-sealed block of measurements (value
structure, surface colour families fitted to palette roles in CIELab, lit
blobs), `--check` re-measures and validates every hand-written declaration,
`--sheet` draws the annotated proof, `--compare` prints a measured delta
between a board and a Studio shot. Character regions and generator watermarks
are masked out before any measurement runs. Method lives here; every image and
every board lives in the game repo. Protocol:
`skills/_shared/reference-board.md`.

This is the kit's only script with a third-party dependency (Pillow). It is
therefore deliberately off the hook and guard path and runs as a gate step
(`--check assets/refs`); without Pillow it exits 2 with
`REFBOARD_ERROR: Pillow required` and nothing else in the kit is affected.

## Verification

```sh
claude plugin validate . --strict
python3 scripts/lessons-compile.py --self-test
python3 scripts/check-denylist.py --self-test
python3 scripts/slop-scan.py --self-test
python3 scripts/blender/palette.py --check scripts/blender/presets/chunky-cartoon.json
python3 scripts/blender/palette.py --check scripts/blender/presets/chunky-horror.json
python3 scripts/blender/palette.py --check scripts/blender/presets/chunky-cartoon-design.json
python3 scripts/blender/palette.py --check scripts/blender/presets/chunky-horror-design.json
python3 scripts/refboard.py --selftest
python3 scripts/blender/review_build.py --selftest
blender -b --python scripts/blender/check_asset.py -- --selftest
blender -b --python scripts/blender/selfcheck.py
```

After a migration or trial run, check with `/context` in a session which
instruction files actually load.

## Starting a new game

```sh
cd <fresh project> && claude --plugin-dir /path/to/roblox-gamedev-kit
```

In that session run `/roblox-gamedev-kit:init-project`, then inspect
`/context`. On a fresh project the guard skips checks A and D until the game
has a constants source.

## Plugin platform notes

Confirmed against `code.claude.com/docs/en/plugins-reference` and the local
CLI: only `name` is required in `plugin.json`; component directories in the
plugin root (`skills/`, `agents/`, `hooks/hooks.json`, `commands/`,
`scripts/`, `bin/`); `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PROJECT_DIR}` and
`${CLAUDE_PLUGIN_DATA}` (machine-local, not for lessons); a `CLAUDE.md` in
the plugin root does not load; plugin agents do not support `hooks`,
`mcpServers` or `permissionMode` in frontmatter. The only thing left
unconfirmed is the exact version fallback without a `version` field.
