#!/usr/bin/env python3
"""PreToolUse hook on Edit|Write: refuses new text that repeats a known mistake.

The rules live in `.claude/known-bad.json` (module: tools/knownbad.py). Only what
the edit ADDS is checked: `new_string` of an Edit, `content` of a Write,
`new_source` of a NotebookEdit. Bash writes (heredocs, sed -i) pass this hook by
construction; the config guard catches their hits on the next run. Existing hits
in a file are the job of `tools/claude-config-guard.py`, not of this hook; an
Edit that removes a wrong line therefore simply goes through.

On a hit the hook prints JSON with `permissionDecision: "deny"` and exit 0.
Deliberately no exit 2: according to the hooks docs the turn then ends by
default, and the point is precisely that Claude reads the refusal and fixes the
mistake right away.

An error in this script itself never blocks: exit 1 (non-blocking) with one line
on stderr, so the error is visible without a bug of our own holding up every
edit; the guard still catches the hit on the next run.

    tools/check-denylist.py --self-test   # built-in cases, exit 1 on failure

The self-test runs against a temporary repo with its own fixture rules, so it
proves the decision logic without needing (or reading) the project's
`.claude/known-bad.json`; whether the project's rules are sound is the job of
`knownbad.load` on the real hook path and of the config guard.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import knownbad


def repo_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env).resolve() if env else Path(__file__).resolve().parent.parent


def reason(entry: dict, relpath: str, hit: str) -> str:
    return (
        f"DENYLIST ({entry['id']}) in {relpath}: `{hit.strip()}`. "
        f"Reason: {entry['reason']} Use: {entry['use']}. "
        f"Deliberate exception: put `guard:ignore {entry['id']}` in the file and write "
        "down why (lesson: .claude/rules/known-mistakes.md)."
    )


def decide(payload: dict, repo: Path, entries: list[dict]) -> str | None:
    """The refusal reason, or None if the edit may proceed."""
    tool = payload.get("tool_name")
    if tool not in ("Edit", "Write", "NotebookEdit"):
        return None
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = repo / path
    try:
        relpath = path.resolve().relative_to(repo).as_posix()
    except ValueError:
        return None  # outside the repo: none of this denylist's business
    if knownbad.is_exempt(relpath):
        return None
    field = {"Edit": "new_string", "Write": "content", "NotebookEdit": "new_source"}[tool]
    text = tool_input.get(field)
    if not isinstance(text, str) or not text:
        return None
    # On an Edit the rest of the file stays, so a marker in it counts. On a
    # Write `content` replaces the whole file: only the new text counts,
    # otherwise an old marker would approve a Write that removes it.
    existing = ""
    if tool == "Edit" and path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            existing = ""
    for entry in entries:
        if not knownbad.applies(entry, relpath):
            continue
        if knownbad.ignored(entry, existing) or knownbad.ignored(entry, text):
            continue
        hit = knownbad.first_match(entry, text)
        if hit is not None:
            return reason(entry, relpath, hit)
    return None


SELF_TEST_RULES = [
    {
        "id": "lighting-technology",
        "category": "feit",
        "pattern": "Lighting\\.Technology\\s*=[^=]|Enum\\.Technology\\.|\"Technology\"\\s*:",
        "reason": "fixture: Lighting.Technology is read-only.",
        "use": "Lighting.LightingStyle",
        "date": "2026-08-26",
        "source": "fixture",
        "paths": ["src/**", "tests/**", "tools/**", "default.project.json", ".claude/**", "CLAUDE.md"],
    },
    {
        "id": "model-pin",
        "category": "werkwijze",
        "pattern": "(?im)^\\s*model[:][ \\t]*\\S+|\\b(s[o]nnet|op[u]s|hai[k]u|fab[l]e)\\b",
        "reason": "fixture: no model pin in .claude/ or CLAUDE.md.",
        "use": "leave `model` out",
        "date": "2026-08-30",
        "source": "fixture",
        "paths": [".claude/**", "CLAUDE.md"],
    },
    {
        "id": "gate-count-drift",
        "category": "werkwijze",
        "pattern": "(?i)\\b(five|vijf|six|zes|seven|zeven|eight|acht)[ -]?(commands?|commando's?|steps?|stappen|stap)\\b",
        "reason": "fixture: the gate step count drifts.",
        "use": "refer to tools/gate.sh without a count",
        "date": "2026-08-30",
        "source": "fixture",
        "paths": [".claude/**", "CLAUDE.md", "tools/**"],
    },
]


def write_fixture_repo(root: Path) -> Path:
    """A throwaway repo with only the fixture denylist; returns its root."""
    denylist = root / knownbad.DENYLIST
    denylist.parent.mkdir(parents=True, exist_ok=True)
    denylist.write_text(json.dumps({"entries": SELF_TEST_RULES}, indent=2), encoding="utf-8")
    return root


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="denylist-self-test-") as tmp:
        repo = write_fixture_repo(Path(tmp).resolve())
        return run_self_test_cases(repo, knownbad.load(repo))


def run_self_test_cases(repo: Path, entries: list[dict]) -> int:
    inside = str(repo / "src" / "denylist-self-test.luau")
    agent = str(repo / ".claude" / "agents" / "denylist-self-test.md")
    cases = [
        ("Edit with Lighting.Technology in new_string", True,
         {"tool_name": "Edit", "tool_input": {"file_path": inside, "old_string": "x",
                                              "new_string": "Lighting.Technology = Enum.Technology.Future"}}),
        ("Edit that removes the mistake", False,
         {"tool_name": "Edit", "tool_input": {"file_path": inside, "old_string": "Lighting.Technology",
                                              "new_string": "Lighting.LightingStyle"}}),
        ("Write to docs/ (exempt)", False,
         {"tool_name": "Write", "tool_input": {"file_path": str(repo / "docs" / "status.md"),
                                               "content": "Lighting.Technology is fout"}}),
        ("Write with guard:ignore in the new text", False,
         {"tool_name": "Write", "tool_input": {"file_path": inside,
                                               "content": "-- guard:ignore lighting-technology\nLighting.Technology = 1"}}),
        ("Write of a model pin in an agent", True,
         {"tool_name": "Write", "tool_input": {"file_path": agent, "content": "---\nname: x\nmodel: sonnet\n---"}}),
        ("Write of a step count in an agent", True,
         {"tool_name": "Write", "tool_input": {"file_path": agent, "content": "run the five-command gate"}}),
        ("Write of a seven-step count in an agent", True,
         {"tool_name": "Write", "tool_input": {"file_path": agent, "content": "the seven-step gate"}}),
        ("Write outside the repo", False,
         {"tool_name": "Write", "tool_input": {"file_path": "/tmp/denylist-self-test.luau",
                                               "content": "Lighting.Technology = 1"}}),
        ("Read tool", False,
         {"tool_name": "Read", "tool_input": {"file_path": inside}}),
        ("Write that removes an existing guard:ignore marker", True,
         {"tool_name": "Write", "tool_input": {"file_path": str(repo / ".claude" / "rules" / "economy.md"),
                                               "content": "<!-- no marker anymore -->\nmodel: opus\n"}}),
        ("NotebookEdit with a wrong API in new_source", True,
         {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": str(repo / "src" / "x.ipynb"),
                                                      "new_source": "Lighting.Technology = 1"}}),
    ]
    failed = 0
    for label, expect_deny, payload in cases:
        why = decide(payload, repo, entries)
        if bool(why) != expect_deny:
            failed += 1
            print(f"FAIL {label}: expected {'deny' if expect_deny else 'allow'}, got {why or 'allow'}")
    if failed:
        print(f"DENYLIST SELF-TEST FAIL ({failed} of {len(cases)} cases)")
        return 1
    print(f"DENYLIST SELF-TEST PASS ({len(cases)} cases)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    try:
        payload = json.load(sys.stdin)
        repo = repo_root()
        why = decide(payload, repo, knownbad.load(repo))
    except Exception as exc:  # noqa: BLE001
        # Exit 1, not 0: a non-blocking error code makes Claude Code show the
        # stderr; on exit 0 it disappears. A broken regex must not silently
        # switch off the denylist.
        print(f"check-denylist: skipped ({exc})", file=sys.stderr)
        return 1
    if why:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": why,
        }}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
