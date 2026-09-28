#!/usr/bin/env python3
"""Shared module for the denylist of known mistakes (`.claude/known-bad.json`).

Two readers:

- `tools/check-denylist.py`: PreToolUse hook on Edit|Write. Refuses NEW text
  that repeats a rule.
- `tools/claude-config-guard.py` (check E): reports EXISTING text that repeats
  a rule.

Every rule belongs to a lesson in `.claude/rules/known-mistakes.md`. Deliberate
exception per file: the text `guard:ignore <id>` (in Markdown as an HTML
comment, in Luau as `-- guard:ignore <id>`). Files that carry the lesson itself
(the lesson files, docs/, these scripts) are always exempt: they must be able to
name the wrong thing in order to explain why it is wrong.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DENYLIST = ".claude/known-bad.json"
REQUIRED = ("id", "category", "pattern", "reason", "use", "date", "source", "paths")
CATEGORIES = ("feit", "werkwijze")

EXEMPT = (
    ".claude/known-bad.json",
    ".claude/lessons.jsonl",
    ".claude/rules/known-mistakes.md",
    ".claude/skills/_shared/learnings-protocol.md",
    ".claude/skills/_shared/owner-taste.md",
    ".claude/skills/*/references/learnings.md",
    ".claude/skills/*/references/owner-taste.md",
    "docs/**",
    "tools/knownbad.py",
    "tools/check-denylist.py",
    "tools/claude-config-guard.py",
    "tools/require-lesson.py",
)


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """`**` also spans directory separators, `*` and `?` do not; the rest is literal."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


_EXEMPT_RX = [glob_to_regex(p) for p in EXEMPT]


def load(repo: Path) -> list[dict]:
    """Reads and validates the denylist; a broken rule is an error, not silence."""
    data = json.loads((repo / DENYLIST).read_text(encoding="utf-8"))
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"{DENYLIST}: `entries` is missing")
    # Empty is valid: a fresh project starts without lessons (init-project).
    seen: set[str] = set()
    for entry in entries:
        missing = [key for key in REQUIRED if key not in entry]
        if missing:
            raise ValueError(f"{DENYLIST}: rule {entry.get('id', '?')} is missing {', '.join(missing)}")
        if entry["category"] not in CATEGORIES:
            raise ValueError(f"{DENYLIST}: rule {entry['id']} has category {entry['category']!r}")
        if entry["id"] in seen:
            raise ValueError(f"{DENYLIST}: id {entry['id']} appears twice")
        seen.add(entry["id"])
        entry["_regex"] = re.compile(entry["pattern"])
        entry["_paths"] = [glob_to_regex(p) for p in entry["paths"]]
    return entries


def is_exempt(relpath: str) -> bool:
    return any(rx.match(relpath) for rx in _EXEMPT_RX)


def applies(entry: dict, relpath: str) -> bool:
    return any(rx.match(relpath) for rx in entry["_paths"])


def ignored(entry: dict, text: str) -> bool:
    return f"guard:ignore {entry['id']}" in text


def first_match(entry: dict, text: str) -> str | None:
    """The first hit, or None; enough for a yes/no decision."""
    match = entry["_regex"].search(text)
    return match.group(0) if match else None


def matches(entry: dict, text: str) -> list[tuple[int, str]]:
    """All hits as (line number from 1, matched text); linear in the text."""
    found: list[tuple[int, str]] = []
    line = 1
    cursor = 0
    for match in entry["_regex"].finditer(text):
        line += text.count("\n", cursor, match.start())
        cursor = match.start()
        found.append((line, match.group(0)))
    return found
