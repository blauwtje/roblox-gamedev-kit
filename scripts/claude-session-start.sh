#!/usr/bin/env bash
# SessionStart hook: one line of context saying where the known mistakes live and
# that the denylist is active. Rules with `paths` only load once a matching file
# is read; this line makes sure every session knows the list exists.
# stdout of a SessionStart hook lands as text in the context (hooks docs).

set -uo pipefail

cat >/dev/null # the payload is not needed here

repo_root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$repo_root" || exit 0

python3 - <<'PY'
import json
from pathlib import Path

# Broken input must not make this line disappear silently: then every session
# misses exactly the signal that something is broken, and the denylist hook
# fails later.
try:
    lessons = sum(1 for line in Path(".claude/rules/known-mistakes.md").read_text(encoding="utf-8").splitlines()
                  if line.startswith("- ["))
    rules = len(json.loads(Path(".claude/known-bad.json").read_text(encoding="utf-8"))["entries"])
except (OSError, ValueError, KeyError, TypeError) as exc:
    print("Known mistakes: could not read .claude/rules/known-mistakes.md or .claude/known-bad.json "
          f"({exc}); fix that first, otherwise the denylist hook fails too.")
else:
    print(f"Known mistakes: .claude/rules/known-mistakes.md ({lessons} lessons). "
          f"Denylist .claude/known-bad.json ({rules} rules) refuses an Edit or Write that repeats one; "
          "exception: guard:ignore <id>.")
PY

exit 0
