#!/usr/bin/env bash
# Stop hook: does not let the turn end on a red verification gate.
#
# tools/claude-verification-gate.sh fires on PostToolUse, so AFTER the subagent
# has already run; it cannot stop the subagent. This Stop hook is the real lock:
# `decision: "block"` on Stop keeps Claude working instead of closing the turn,
# so a red gate cannot sit quietly until the next prompt.
#
# Deliberately blocks ONCE per red gate (`reported` is set to true). Without that
# latch you run into the built-in emergency brake of 8 consecutive blocks, and
# that is a worse experience than a single clear reminder.

set -uo pipefail

payload=$(cat)

# The payload is passed as an argument, not via stdin: that way the Python code
# itself can come from a heredoc and stays free of shell expansion.
python3 - "$payload" <<'PY'
import json, os, sys

try:
    d = json.loads(sys.argv[1])
except Exception:
    raise SystemExit(0)

# Is Claude already continuing because of a Stop hook? Then do not stack.
if d.get("stop_hook_active"):
    raise SystemExit(0)

session = str(d.get("session_id") or "").strip()
if not session:
    raise SystemExit(0)

state_file = os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "roblox-gamedev-kit-gate", f"{session}.json")
if not os.path.exists(state_file):
    raise SystemExit(0)

try:
    state = json.load(open(state_file))
except Exception:
    raise SystemExit(0)

if state.get("state") != "FAIL" or state.get("reported"):
    raise SystemExit(0)

state["reported"] = True
json.dump(state, open(state_file, "w"))

print(json.dumps({"decision": "block", "reason": (
    "The verification gate is red after `{agent}`: {failed}. "
    "You cannot close this turn without repairing those steps or explicitly "
    "telling the owner that they are red and why."
).format(agent=state.get("agent", "a builder"),
         failed=state.get("failed", "unknown steps"))}))
PY

exit 0
