#!/usr/bin/env python3
"""Stop hook: does not let a turn end after a self-correction without a written lesson.

Why. Between 2026-08-24 and 2026-08-30 eleven mistakes were made again after a
correction, counted in a review of the session transcripts. The pattern was
always the same: the mistake was seen, fixed in the chat, and written down
nowhere. This hook reads back the session transcript and refuses once to close
the turn when the assistant corrected itself and touched no lesson file afterwards.

What it sees, and what not. Markers are fixed phrasings in the assistant's OWN
text ("mijn fout", "correctie:", "dat klopt niet", "was voorbarig", "my mistake",
"correction:", ...); text from the owner, tool output and subagent reports do not
count. A lesson is an Edit/Write/NotebookEdit on a lesson file, or a Bash command
that names such a path AND contains a write form (>>, tee, sed -i, write_text, mv,
cp; the learnings were written via heredocs so far). A bare
`git diff docs/status.md` or `cat` therefore does not count as a lesson. A marker
is "open" as long as no lesson write follows its position. Every open marker is
reported exactly once (latch per session), so the hook never runs into the
built-in limit of eight blocks and a deliberate "no lesson, because ..." to the
owner can simply pass.

Why Stop and not SubagentStop: a block on SubagentStop keeps the subagent
working, and the lesson files belong to the main session (learnings protocol).

    tools/require-lesson.py --self-test   # built-in cases, exit 1 on failure
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

MAX_TRANSCRIPT_BYTES = 100 * 1024 * 1024

MARKERS = [re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\bmijn fout\b",
    r"\bmy mistake\b",
    r"\bi was wrong\b",
    r"\bcorrectie:",
    r"\bcorrection:",
    r"\bdat klopt niet\b",
    r"\bklopt niet meer\b",
    r"\bwas voorbarig\b",
    r"\bverkeerd (?:gemeten|gemeld|geteld|gelezen)\b",
)]

LESSON_PATHS = [re.compile(pattern) for pattern in (
    r"\.claude/lessons\.jsonl",
    r"\.claude/rules/known-mistakes\.md",
    r"\.claude/known-bad\.json",
    r"\.claude/skills/[^/]+/references/learnings\.md",
    r"\.claude/skills/_shared/owner-taste\.md",
    r"docs/status\.md",
    r"docs/studio-bridge\.md",
    r"/memory/[^/]+\.md",
)]

WRITE_TOOLS = ("Edit", "Write", "NotebookEdit")

# A Bash call only counts as a lesson write with a write form in it; otherwise
# a read-only `git diff docs/status.md` would close every open marker.
BASH_WRITE = re.compile(r">>|>\s|\btee\b|\bsed -i\b|write_text|\.write\(|\bmv\b|\bcp\b")

REASON = (
    "LESSON MISSING. This session contains a self-correction without a lesson written "
    "afterwards: «{quote}». Write the lesson: add a record to .claude/lessons.jsonl and "
    "run python3 tools/lessons-compile.py (taste goes verbatim to "
    ".claude/skills/_shared/owner-taste.md; protocol: "
    ".claude/skills/_shared/learnings-protocol.md), or tell the owner in one sentence why "
    "there is no lesson. This reminder comes once per correction."
)


def state_path(session_id: str) -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / "roblox-gamedev-kit-gate" / f"{session_id}.lessons.json"


def scan(transcript: Path) -> tuple[list[tuple[int, str]], list[int]]:
    """Markers as (line position, text) and the line positions of lesson writes."""
    markers: list[tuple[int, str]] = []
    writes: list[int] = []
    position = 0
    with transcript.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            position += 1
            try:
                record = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            message = record.get("message")
            if not isinstance(message, dict):
                continue
            role = message.get("role") or record.get("type")
            if role != "assistant":
                continue
            content = message.get("content")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    for line in str(block.get("text", "")).splitlines():
                        if any(marker.search(line) for marker in MARKERS):
                            markers.append((position, line.strip()))
                elif block.get("type") == "tool_use":
                    tool_input = block.get("input") or {}
                    name = block.get("name")
                    if name in WRITE_TOOLS:
                        target = str(tool_input.get("file_path", ""))
                        if target and any(path.search(target) for path in LESSON_PATHS):
                            writes.append(position)
                    elif name == "Bash":
                        command = str(tool_input.get("command", ""))
                        if (any(path.search(command) for path in LESSON_PATHS)
                                and BASH_WRITE.search(command)):
                            writes.append(position)
    return markers, writes


def open_markers(markers: list[tuple[int, str]], writes: list[int]) -> list[tuple[int, str]]:
    """Markers without a later lesson write, oldest first."""
    last_write = max(writes) if writes else -1
    return [marker for marker in markers if marker[0] > last_write]


def load_state(path: Path) -> dict:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"reported": []}
    if not isinstance(state, dict) or not isinstance(state.get("reported"), list):
        return {"reported": []}
    return state


def decide(payload: dict, state_file: Path) -> dict | None:
    """The block response, or None if the turn may end."""
    if payload.get("stop_hook_active"):
        return None
    session = str(payload.get("session_id") or "").strip()
    transcript = payload.get("transcript_path")
    if not session or not isinstance(transcript, str):
        return None
    path = Path(transcript)
    if not path.is_file() or path.stat().st_size > MAX_TRANSCRIPT_BYTES:
        return None
    markers, writes = scan(path)
    pending = open_markers(markers, writes)
    if not pending:
        return None
    state = load_state(state_file)
    # Newest first, and exactly one unreported marker per Stop: that way every
    # open self-correction gets its reminder once across consecutive turns.
    for _, line in reversed(pending):
        digest = hashlib.sha1(line.encode("utf-8"), usedforsecurity=False).hexdigest()
        if digest in state["reported"]:
            continue
        state["reported"].append(digest)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state), encoding="utf-8")
        return {"decision": "block", "reason": REASON.format(quote=line[:200])}
    return None


def _record(role: str, content: list[dict]) -> str:
    return json.dumps({"type": role, "message": {"role": role, "content": content}})


def self_test() -> int:
    # The marker texts below are deliberately in Dutch: they must match MARKERS.
    marker = _record("assistant", [{"type": "text", "text": "Mijn fout: de telling was 55, niet 56."}])
    plain = _record("assistant", [{"type": "text", "text": "De telling is 55."}])
    owner = _record("user", [{"type": "text", "text": "dat klopt niet"}])
    edit = _record("assistant", [{"type": "tool_use", "name": "Edit", "input": {
        "file_path": "/repo/.claude/skills/visual-judge/references/learnings.md",
        "old_string": "a", "new_string": "b"}}])
    jsonl_edit = _record("assistant", [{"type": "tool_use", "name": "Edit", "input": {
        "file_path": "/repo/.claude/lessons.jsonl",
        "old_string": "a", "new_string": "b"}}])
    heredoc = _record("assistant", [{"type": "tool_use", "name": "Bash", "input": {
        "command": "cat >> .claude/rules/known-mistakes.md <<'EOF'\n- les\nEOF"}}])
    readonly_bash = _record("assistant", [{"type": "tool_use", "name": "Bash", "input": {
        "command": "git diff docs/status.md"}}])
    marker2 = _record("assistant", [{"type": "text", "text": "Correctie: de hoogte was 7.30, niet 5.70."}])
    # (label, transcript lines, stop_hook_active, clear latch first, expected block)
    cases = [
        ("marker without lesson", [marker], False, True, True),
        ("same marker, second call (latch)", [marker], False, False, False),
        ("marker followed by Edit on learnings.md", [marker, edit], False, True, False),
        ("marker followed by Edit on lessons.jsonl", [marker, jsonl_edit], False, True, False),
        ("no marker, only owner text", [plain, owner], False, True, False),
        ("stop_hook_active", [marker], True, True, False),
        ("marker followed by Bash heredoc to known-mistakes.md", [marker, heredoc], False, True, False),
        ("marker followed by read-only Bash on docs/status.md", [marker, readonly_bash], False, True, True),
    ]
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "latch.json"
        for index, (label, records, active, reset, expect_block) in enumerate(cases):
            transcript = Path(tmp) / f"case{index}.jsonl"
            transcript.write_text("\n".join(records) + "\n", encoding="utf-8")
            if reset:
                state_file.unlink(missing_ok=True)
            payload = {"session_id": "self-test", "stop_hook_active": active, "transcript_path": str(transcript)}
            result = decide(payload, state_file)
            if bool(result) != expect_block:
                failed += 1
                print(f"FAIL {label}: expected {'block' if expect_block else 'silent'}, got {result or 'silent'}")
        # Two open markers: every marker gets exactly one report across consecutive stops.
        state_file.unlink(missing_ok=True)
        transcript = Path(tmp) / "case-two-markers.jsonl"
        transcript.write_text(marker + "\n" + marker2 + "\n", encoding="utf-8")
        payload = {"session_id": "self-test", "stop_hook_active": False, "transcript_path": str(transcript)}
        first = decide(payload, state_file)
        second = decide(payload, state_file)
        third = decide(payload, state_file)
        if not (first and "Correctie" in first["reason"]
                and second and "Mijn fout" in second["reason"] and third is None):
            failed += 1
            print(f"FAIL two open markers in a row: got {first!r} / {second!r} / {third!r}")
    total = len(cases) + 1
    if failed:
        print(f"LESSON LATCH SELF-TEST FAIL ({failed} of {total} cases)")
        return 1
    print(f"LESSON LATCH SELF-TEST PASS ({total} cases)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    try:
        payload = json.load(sys.stdin)
        session = str(payload.get("session_id") or "").strip()
        result = decide(payload, state_path(session)) if session else None
    except Exception as exc:  # noqa: BLE001
        # Exit 1 is non-blocking and shows the stderr; exit 0 hides it.
        print(f"require-lesson: skipped ({exc})", file=sys.stderr)
        return 1
    if result:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
