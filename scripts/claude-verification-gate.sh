#!/usr/bin/env bash
# Verification gate as a PostToolUse hook on the `Agent` tool.
#
# Why a hook and not a rule in CLAUDE.md: prose is advice, not enforcement. The
# official docs draw that line explicitly ("use permissions or hooks for ...
# anything that must never happen"). This hook runs tools/gate.sh, so the main
# session cannot skip the gate.
#
# Why PostToolUse on `Agent` and not SubagentStop: SubagentStop delivers its
# `reason` TO THE SUBAGENT (which then keeps running), and that is exactly the
# architecture we do not want; the builders deliberately do not run the gate
# themselves. PostToolUse on `Agent` delivers to the PARENT. The hooks docs say
# this literally: "To inject context into the parent session after a subagent
# returns, use a PostToolUse hook on the Agent tool instead."
#
# Mind the limit of this mechanism: PostToolUse fires AFTER the subagent has
# already run. It cannot stop the subagent; it makes a red gate impossible to
# miss. The real lock is in the Stop hook (tools/claude-gate-latch.sh), which
# does not let the turn end on a red gate.
#
# Verified on Claude Code 2.1.247 (2026-08-27), not assumed:
#   - the tool is called `Agent` (`Task` fires too, as a backwards alias);
#   - `permissionDecision` does NOT exist for PostToolUse; `decision: "block"`
#     does, and that text lands verbatim in the main session;
#   - exit code 2 blocks nothing here: the tool has already run.

set -uo pipefail

payload=$(cat)

repo_root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$repo_root" || exit 0

# The rokit shims as a safety net at the END, not the front: a hook inherits the
# session environment, and the gate should pick up exactly the same binaries as
# a manual run from the shell. Putting them first lets the hook silently use a
# different toolchain than the owner sees, and that makes a green gate unreliable.
export PATH="$PATH:$HOME/.rokit/bin"

# Only these two agents deliver Luau that has to pass the gate.
BUILDER_AGENTS="roblox-world-builder luau-gameplay-engineer"

read -r agent status resolved_model session_id <<EOF
$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("- - - -"); sys.exit(0)
ti = d.get("tool_input") or {}
tr = d.get("tool_response")
tr = tr if isinstance(tr, dict) else {}
def clean(v):
    v = str(v or "-").strip()
    return v.replace(" ", "_") or "-"
print(clean(ti.get("subagent_type")), clean(tr.get("status")),
      clean(tr.get("resolvedModel")), clean(d.get("session_id")))
')
EOF

# Not a builder? Exit quietly. The gate must not add noise to Explore/judge rounds.
case " $BUILDER_AGENTS " in
	*" $agent "*) ;;
	*) exit 0 ;;
esac

# A subagent that went to the background reports `async_launched` and is not
# done yet. Running the gate now would measure work that does not exist yet.
if [ "$status" != "completed" ]; then
	exit 0
fi

log_dir=$(mktemp -d "${TMPDIR:-/tmp}/sr-gate.XXXXXX")
trap 'rm -rf "$log_dir"' EXIT

# The steps themselves live in tools/gate.sh: one source, which CLAUDE.md also
# shows and whose equality check F of the config guard watches. This script
# only translates the result into hook JSON and the state file.
report="$log_dir/report.txt"
gate_output="$("$repo_root/tools/gate.sh" --quiet 2>&1)"
gate_code=$?
printf '%s\n' "$gate_output" >"$report"
failed_steps="$(printf '%s\n' "$gate_output" | sed -n 's/^GATE FAIL: //p')"
# Do not rely on the text line alone: if gate.sh itself cannot run (missing,
# not executable, syntax error), there is no FAIL line and an empty
# failed_steps would pass as green. The exit code decides.
if [ "$gate_code" -ne 0 ] && [ -z "$failed_steps" ]; then
	failed_steps="tools/gate.sh (exit $gate_code)"
fi

# State file for the Stop latch. Per session, so parallel sessions do not
# overwrite each other.
state_dir="${TMPDIR:-/tmp}/roblox-gamedev-kit-gate"
mkdir -p "$state_dir"
state_file="$state_dir/$session_id.json"

python3 - "$agent" "$resolved_model" "$failed_steps" "$report" "$state_file" <<'PY'
import json, os, sys

agent, model, failed, report_path, state_file = sys.argv[1:6]
model = model if model and model != "-" else "unknown model"

if not failed:
    # Green: no block, but do report the model line. That line is the source
    # for the `Model` column in docs/visual/judge-log.md.
    json.dump({"state": "PASS", "agent": agent, "model": model, "reported": True},
              open(state_file, "w"))
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            f"GATE PASS: all steps green after `{agent}` (run on {model}). "
            "Jest-Lua specs: NOT RUN (Studio only). "
            f"For a visual-judge round, record `{model}` in the Model column of "
            "docs/visual/judge-log.md."
        )}}))
    raise SystemExit(0)

detail = open(report_path).read().strip() if os.path.exists(report_path) else ""
reason = (
    f"GATE FAIL after `{agent}` (run on {model}). Failed steps: {failed}.\n"
    "The verification gate was run automatically by the PostToolUse hook on the "
    "Agent tool; this is not optional advice. Fix these errors before calling "
    "this work done or committing anything. Jest-Lua specs: NOT RUN.\n"
    f"{detail}"
)
json.dump({"state": "FAIL", "agent": agent, "model": model,
           "failed": failed, "reported": False}, open(state_file, "w"))
print(json.dumps({"decision": "block", "reason": reason}))
PY

exit 0
