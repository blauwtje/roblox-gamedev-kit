---
description: Scaffold the roblox-gamedev-kit project layer in the current repo (gate template, CLAUDE.md with gate block, empty lessons source and denylist, rules template) and prove that guard and gate run green.
---

Scaffold the project layer of the roblox-gamedev-kit plugin in this project.
Work from the project root and never overwrite a file that already exists:
report it and skip it.

1. Copy from `${CLAUDE_PLUGIN_ROOT}/scripts/templates/`:
   - `gate.sh` to `tools/gate.sh` and make it executable (`chmod +x`);
   - `CLAUDE.md` to `CLAUDE.md` (project root);
   - `known-bad.json` to `.claude/known-bad.json`;
   - `rules-verification.md` to `.claude/rules/verification.md`;
   - `prop-judge-prompt.md` to `.claude/skills/visual-judge/references/prop-judge-prompt.md`;
   - `owner-taste.md` to `.claude/skills/_shared/owner-taste.md`;
   - and from `${CLAUDE_PLUGIN_ROOT}/scripts/blender/presets/`:
     `chunky-cartoon.json` to `assets/blender/palette.json`, then run
     `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/blender/palette.py" --check assets/blender/palette.json`
     and report the result verbatim;
   - and `chunky-cartoon-design.json` from the same presets directory to
     `assets/blender/design-system.json`, then set its `"palette"` value to
     `"palette.json"` (the copy next to it) and run
     `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/blender/palette.py" --check assets/blender/design-system.json`;
     report the result verbatim. The game edits the numbers, motifs and
     forbidden list there; every asset, the linter and the prop judge read it.
2. Create an empty lessons source: `.claude/lessons.jsonl` (empty file).
3. Wire the reference-board gate step. Resolve `${CLAUDE_PLUGIN_ROOT}` to its
   absolute path now and append the identical line to both the `STEPS` array
   in `tools/gate.sh` (inside the `GATE-STEPS-BEGIN/END` block) and the gate
   code block in `CLAUDE.md`, because check F compares the two line by line
   and `CLAUDE_PLUGIN_ROOT` is unset when the gate runs from a plain shell:

   ```
   python3 '<absolute plugin path>/scripts/refboard.py' --check assets/refs
   ```

   Use single quotes around the path so check F's `"([^"]+)"` extraction keeps
   working. Create no `assets/refs/` directory: a game has no zones on day one
   and the step prints `REFBOARD_VALID:true (0 boards)` and exits 0 until
   `refboard.py --init` makes the first board.

   Add the identical line for the AI-slop scanner to the same two places:

   ```
   python3 '<absolute plugin path>/scripts/slop-scan.py' src
   ```

   It exits 0 with no output until `src/` exists and gets Luau files.
4. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/lessons-compile.py"` so the
   views exist, then
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/claude-config-guard.py"` and
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/refboard.py" --selftest`; report
   both results verbatim.
5. Run `tools/gate.sh` and report the result verbatim; the template should be
   green until the game fills in its real steps.
6. Report: which files were created, which already existed and were skipped,
   and which steps the game now has to fill in itself (real gate steps, a
   blueprint/builders layout, a style guide once the visual direction exists,
   and a reference board per zone the owner supplies images for).
