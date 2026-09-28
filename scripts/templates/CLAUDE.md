# CLAUDE.md

Roblox game built with the roblox-gamedev-kit plugin. This file keeps the
project rules short; method and working practice come from the plugin skills.

## Verification gate

`tools/gate.sh` runs exactly these steps, in this order; run it before calling
a Luau change done (the plugin hook runs it after every builder subagent):

```sh
true
```

## Rules

- Server-authoritative: every remote handler validates type, NaN/inf, range and
  ownership before mutation; `src/client` is display-only.
- `--!strict` with explicit types; one ModuleScript per system; pure rules in
  `src/shared` with a spec next to them.
- Names, currency, content: owner decisions; propose, build only after approval.
- Every number is derived from its source before it is written down, never after.
- Lessons: record in `.claude/lessons.jsonl` plus the plugin's lessons compiler;
  never edit the compiled views by hand.
