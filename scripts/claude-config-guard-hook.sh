#!/usr/bin/env bash
# PostToolUse hook: runs the config guard as soon as a .claude/**/*.md file has
# been written.
#
# Deliberately does not block the edit; it cannot, since PostToolUse fires after
# the write has already happened. The point is that the finding comes back in
# the SAME turn, so drift is fixed right away instead of at an audit months later.

set -uo pipefail

cat >/dev/null # the hook payload is not needed here; `if` in settings.json already filters

repo_root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$repo_root" || exit 0

output=$(python3 "$(cd "$(dirname "$0")" && pwd)/claude-config-guard.py" --quiet 2>&1)
code=$?

if [ "$code" -eq 0 ]; then
	exit 0
fi

python3 -c '
import json, sys
print(json.dumps({"decision": "block", "reason": (
    "CONFIG GUARD FAIL after an edit in .claude/. "
    "A constant or skill structure has drifted from the source of truth "
    "(.claude/skills/roblox-hardsurface). Fix this now, in this turn.\n\n"
    + sys.stdin.read().strip())}))
' <<<"$output"

exit 0
