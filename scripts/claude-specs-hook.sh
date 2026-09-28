#!/usr/bin/env bash
# PostToolUse hook: runs the specs as soon as something under src/ or tests/ is written.
#
# Why this exists next to the verification gate. That gate hangs off the `Agent`
# tool and only fires when `roblox-world-builder` or `luau-gameplay-engineer`
# returns. When the main session edits the Luau itself, which happens often (the
# whole phase 1 closing pass of 2026-08-29 went that way), nothing fires and only
# the prose in CLAUDE.md remains. Prose is advice, not enforcement; that is
# exactly the line tools/claude-verification-gate.sh draws in its own header.
#
# Why only the specs and not the whole gate: `tools/run-specs.sh` costs about
# 40 ms. `rojo build` and `luau-lsp analyze` cost seconds, and running those
# after every single Edit makes editing slow without catching anything the gate
# on the `Agent` tool or the manual gate would not also catch.
#
# Does not block the edit; it cannot, PostToolUse fires afterwards. The point is
# that a broken spec comes back in the SAME turn instead of whenever someone
# happens to think of it again. Exactly that "thinking of it again" left two
# specs broken for days on 2026-08-29.

set -uo pipefail

cat >/dev/null # the payload is not needed here; `if` in settings.json already filters

repo_root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$repo_root" || exit 0

# Same order as the gate: the rokit shims as a safety net at the END, so the hook
# picks up the same binaries as a manual run from the shell.
export PATH="$PATH:$HOME/.rokit/bin"

if [ ! -x "$repo_root/tools/run-specs.sh" ]; then
	# Fresh project without a specs runner: nothing to run, nothing to block.
	exit 0
fi

output=$("$repo_root/tools/run-specs.sh" 2>&1)
code=$?

if [ "$code" -eq 0 ]; then
	exit 0
fi

python3 -c '
import json, sys
print(json.dumps({"decision": "block", "reason": (
    "SPECS RED after an edit in src/ or tests/. Fix this now, in this turn, "
    "before building further.\n\n"
    "Mind the boundary: tools/run-specs.sh is not Jest but a shim with a "
    "limited matcher set (docs/studio-bridge.md). If it falls over with \"attempt to call a nil "
    "value\", a spec uses a feature the shim does not cover and that spec belongs "
    "under real Jest via the Studio Command Bar.\n\n"
    + sys.stdin.read().strip())}))
' <<<"$output"

exit 0
