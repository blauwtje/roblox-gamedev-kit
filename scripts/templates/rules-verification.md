---
paths:
  - "src/**"
  - "tests/**"
  - "tools/**"
---

# Verification in this project

- `tools/gate.sh` is the only source of the gate steps; CLAUDE.md shows the
  same block and check F of the plugin guard watches their equality.
- The plugin hooks run the gate after every builder subagent, the specs after
  every edit under `src/` or `tests/`, and the config guard after every edit
  under `.claude/`.
- Report honestly what was not run; a Studio-dependent check is called NOT RUN
  until a Studio session confirmed it.
