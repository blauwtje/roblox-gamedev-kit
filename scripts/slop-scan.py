#!/usr/bin/env python3
"""PreToolUse hook (`--hook`), gate (`<dir-or-file>`) and `--self-test` for Luau AI-slop tells.

Rules: slop-rules.json. `guard:ignore <id>` in a file skips that rule; `absent` rules are gate-only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import knownbad

RULES_PATH = Path(__file__).resolve().parent / "slop-rules.json"
FIXTURES = Path(__file__).resolve().parent / "slop-scan-fixtures"
REQUIRED = ("id", "pattern", "reason", "use", "source", "paths")
ADDED_TEXT_FIELD = {"Edit": "new_string", "Write": "content", "NotebookEdit": "new_source"}


def load_rules(path: Path = RULES_PATH) -> list[dict]:
    """Reads and validates the rule set; a broken rule is an error, not silence."""
    rules = json.loads(path.read_text(encoding="utf-8")).get("rules")
    if not isinstance(rules, list):
        raise ValueError(f"{path}: `rules` is missing")
    seen: set[str] = set()
    for rule in rules:
        missing = [key for key in REQUIRED if key not in rule]
        if missing:
            raise ValueError(f"{path}: rule {rule.get('id', '?')} is missing {', '.join(missing)}")
        if rule["id"] in seen:
            raise ValueError(f"{path}: id {rule['id']} appears twice")
        seen.add(rule["id"])
        rule["_regex"] = re.compile(rule["pattern"])
        rule["_absent"] = re.compile(rule["absent"]) if rule.get("absent") else None
        rule["_paths"] = [knownbad.glob_to_regex(p) for p in rule["paths"]]
    return rules


def reason(rule: dict, relpath: str, hit: str) -> str:
    return (f"SLOP ({rule['id']}) in {relpath}: `{hit.strip()}`. Reason: {rule['reason']} "
            f"Use: {rule['use']}. Deliberate exception: put `guard:ignore {rule['id']}` in the file.")


def relative_to_src(raw: str, project: str | None) -> str | None:
    """The path past the first `src` segment inside `project` (anywhere without one), or None."""
    path, base = Path(raw).resolve(), Path(project or "/").resolve()
    parts = path.relative_to(base).parts if path.is_relative_to(base) else ()
    return "/".join(parts[parts.index("src") + 1 :]) if "src" in parts else None


def decide_hook(payload: dict, rules: list[dict], project: str | None) -> str | None:
    """The refusal reason for a PreToolUse payload, or None if the edit may proceed."""
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    text = tool_input.get(ADDED_TEXT_FIELD.get(tool, ""))
    if not (isinstance(raw, str) and raw and isinstance(text, str) and text):
        return None
    relpath = relative_to_src(raw, project)
    if relpath is None or knownbad.is_exempt(relpath):
        return None  # outside the game's src/, or a knownbad-exempt path
    existing = ""
    if tool == "Edit" and Path(raw).is_file():
        try:
            existing = Path(raw).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            existing = ""  # unreadable: only the added text can carry guard:ignore
    for rule in rules:
        skip = rule["_absent"] is not None or knownbad.ignored(rule, existing + "\n" + text)
        hit = None if skip or not knownbad.applies(rule, relpath) else knownbad.first_match(rule, text)
        if hit:
            return reason(rule, relpath, hit)
    return None


def scan_target(target: Path, rules: list[dict]) -> list[tuple[str, str, int]]:
    """(rule id, relpath, line) for every gate hit under target (a file or a directory)."""
    root = target if target.is_dir() else target.parent
    files = [target] if target.is_file() else sorted(p for p in target.rglob("*") if p.is_file())
    hits: list[tuple[str, str, int]] = []
    for path in files:
        relpath = path.resolve().relative_to(root.resolve()).as_posix()
        applicable = [rule for rule in rules if knownbad.applies(rule, relpath)]
        text = path.read_text(encoding="utf-8") if applicable else ""  # skips a binary .rbxm
        for rule in applicable:
            if knownbad.ignored(rule, text) or (rule["_absent"] and rule["_absent"].search(text)):
                continue
            hits.extend((rule["id"], relpath, line) for line, _ in knownbad.matches(rule, text))
    return hits


HOOK_DENY = ("wait(1)", "spawn(f)", "delay(1, f)", "workspace:FindPartOnRayWithIgnoreList(ray, {})",
             "humanoid:LoadAnimation(anim)", "label.Font = Enum.Font.GothamBold",
             'label.Text = "Done ✅"', 'label.Text = "⭐ Star"', "label.Text = `Coins \U0001fa99 {n}`")
HOOK_ALLOW = ("task.wait(1)", "task.spawn(function() end)", "task.delay(1, function() end)",
              "obj:Connect(onTouch)", "local function myspawn() end\nmyspawn()", "my_spawn(f)",
              "self.wait(1)", "timer:wait(1)", "Thread.spawn(f)", "Promise.delay(1):andThen(f)",
              "-- use task.wait, never wait()", "animator:LoadAnimation(anim)", 'label.Text = "★ 5 ✓"',
              "label.Font = Enum.Font.BuilderSans", "-- guard:ignore deprecated-wait\nwait(1)",
              "function ProcessReceipt(r) end")  # the last is an `absent` rule: gate only


def self_test() -> int:
    rules = load_rules()
    hits = scan_target(FIXTURES, rules)  # clean*.luau must stay silent, the rest must hit every rule
    clean_hits = [hit for hit in hits if hit[1].startswith("clean")]
    dirty_ids = {hit[0] for hit in hits if not hit[1].startswith("clean")}
    failures = [f"clean fixtures got hits: {clean_hits}"] if clean_hits else []
    failures += [f"rule {rule['id']} never hits the dirty fixtures" for rule in rules if rule["id"] not in dirty_ids]

    def edit(path: str, text: str) -> dict:
        return {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": "x", "new_string": text}}

    cases = [(edit("/repo/src/x.luau", text), None, True) for text in HOOK_DENY]
    cases += [(edit("/repo/src/x.luau", text), None, False) for text in HOOK_ALLOW]
    with tempfile.TemporaryDirectory() as tmp:
        marked = Path(tmp) / "src" / "marked.luau"  # guard:ignore in the existing file, not the edit
        marked.parent.mkdir()
        marked.write_text("-- guard:ignore deprecated-wait\n", encoding="utf-8")
        cases += [
            (edit(str(marked), "wait(1)"), None, False),
            (edit("/home/me/resrc/tools/a.lua", "wait(1)"), None, False),
            (edit("/home/me/src/game/tools/a.lua", "wait(1)"), "/home/me/src/game", False),
        ]
        verdicts = [(payload, deny, decide_hook(payload, rules, project)) for payload, project, deny in cases]
    failures += [f"{payload['tool_input']}: expected {'deny' if deny else 'allow'}, got {why or 'allow'}"
                 for payload, deny, why in verdicts if bool(why) != deny]
    for failure in failures:
        print(f"FAIL {failure}")
    print(f"SLOP-SCAN SELF-TEST {'FAIL' if failures else 'PASS'} ({len(failures)} failure(s), {len(rules)} rules)")
    return 1 if failures else 0


def main() -> int:
    argv = sys.argv[1:]
    if "--self-test" in argv:
        return self_test()
    rules = load_rules()
    if "--hook" in argv:
        why = decide_hook(json.load(sys.stdin), rules, os.environ.get("CLAUDE_PROJECT_DIR"))
        if why:
            decision = {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": why}
            print(json.dumps({"hookSpecificOutput": decision}))
        return 0
    if not argv:
        print("usage: slop-scan.py <dir-or-file> | --hook | --self-test", file=sys.stderr)
        return 2
    hits = scan_target(Path(argv[0]), rules)
    for rule_id, relpath, line in hits:
        print(f"SLOP {rule_id} {relpath}:{line}")
    return 1 if hits else 0


if __name__ == "__main__":
    raise SystemExit(main())
