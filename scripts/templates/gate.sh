#!/usr/bin/env bash
# The verification gate of this project: one source of truth, executable.
# CLAUDE.md shows the same steps in the same code block; the plugin's config
# guard (check F) goes red as soon as the two lists differ.
# Fill in the steps for this game; elsewhere always refer to this script and
# name a step by its command, never by a count.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

# GATE-STEPS-BEGIN (check F compares this block line by line with CLAUDE.md)
STEPS=(
	"true"
)
# GATE-STEPS-END

failed=""
for step in "${STEPS[@]}"; do
	if bash -c "$step"; then
		echo "PASS $step"
	else
		echo "FAIL $step"
		failed="${failed:+$failed, }$step"
	fi
done

if [[ -n "$failed" ]]; then
	echo "GATE FAIL: $failed"
	exit 1
fi
echo "GATE PASS"
