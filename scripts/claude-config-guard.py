#!/usr/bin/env python3
"""Guard against drift in .claude/: contradictory constants and broken skills.

Six checks, all deterministic, no dependencies beyond tools/knownbad.py:

CHECK A: constants
    `.claude/skills/roblox-hardsurface/SKILL.md` (plus its
    `references/style-guide.md`) is the only source of truth for the build
    numbers. This check reads those numbers from it and fails as soon as another
    `.claude/**/*.md` file names a different value for the same constant. Since
    2026-08-31 the style guide itself is also a check target: the two files of
    the skill must not contradict each other (this is how `MAX_LIGHT_BRIGHTNESS`
    sat at 1.2 in the table against 6 in the guide, unnoticed).

    This exists because it really went wrong once: an essay in
    `roblox-world-builder` named doors of 8-9 studs and a seam gap of 0.05,
    while the skill prescribes 10-stud doors and `SEAM_OVERLAP = 0.1`. That is
    not reliably found by hand; with a grep it is.

CHECK B: structure
    Every skill with a references/learnings.md follows the shared learnings
    protocol and must actually refer to it (the list is derived, not pinned),
    and every SKILL.md stays within the form Anthropic prescribes (<= 500 lines,
    references at most one level deep, frontmatter with name and description).

CHECK D: budgets
    The Part and light budgets also live in `src/shared/StationBlueprint.luau`,
    the only place the builders and the acceptance test really read. This check
    ties those to the skill and watches that the shadow sub-limit stays strictly
    below the light budget.

CHECK E: denylist
    `.claude/known-bad.json` (module tools/knownbad.py) lists known wrong APIs,
    settings and phrasings. Check A watches numbers; a lesson is often a name
    ("Future lighting", `model:`), and until 2026-08-30 that could be fixed in
    one file while another file kept repeating it. The PreToolUse hook
    tools/check-denylist.py refuses new text; this check reports existing text.

CHECK F: the gate steps
    tools/gate.sh is the only executable source of the verification gate and
    CLAUDE.md shows the same code block. This check keeps those two equal line
    by line and demands that the runner agent refers to the script instead of
    repeating its own list; a copied list is exactly how the number of steps
    could drift.

CHECK G: settings.json and the hook scripts
    `.claude/settings.json` must parse as JSON and every `command` in the hooks
    block must, after substitution of `$CLAUDE_PROJECT_DIR`, point to an
    existing, executable file. Until 2026-08-31 this was a manual step in
    `.claude/rules/claude-config.md`; a typo in a hook path then failed silently
    only at the moment the hook should have fired.

CHECK H: lessons source and views
    The lesson views (per-skill learnings.md, known-mistakes.md, known-bad.json)
    are compiled from `.claude/lessons.jsonl` by `tools/lessons-compile.py`; a
    hand edit of a view or a forgotten compile makes source and view unequal.
    This check runs the compiler in `--check` and goes red on every difference
    (since 2026-09-01, checkpoint lessons-as-data).

Usage:
    python3 tools/claude-config-guard.py          # report on stdout, exit 1 on findings
    python3 tools/claude-config-guard.py --quiet  # findings only

Escape hatch: put `<!-- guard:ignore NAME -->` in a file to allow a deliberate
deviation from that one constant there. Add why.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import knownbad

REPO = Path(os.environ["CLAUDE_PROJECT_DIR"]).resolve() if os.environ.get("CLAUDE_PROJECT_DIR") else Path.cwd()
CLAUDE_DIR = REPO / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"

HARDSURFACE = SKILLS_DIR / "roblox-hardsurface" / "SKILL.md"
STYLE_GUIDE = SKILLS_DIR / "roblox-hardsurface" / "references" / "style-guide.md"
SHARED_PROTOCOL = SKILLS_DIR / "_shared" / "learnings-protocol.md"
SHARED_REF = ".claude/skills/_shared/learnings-protocol.md"

SKILL_MAX_LINES = 500
CLAUDE_MD_MAX_LINES = 200

NUMBER = r"-?\d+(?:\.\d+)?"

# Number words the style guide uses; the guide writes "twee tinten", not "2".
DUTCH_NUMBERS = {
    "een": 1, "één": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5,
    "zes": 6, "zeven": 7, "acht": 8, "negen": 9, "tien": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
}


def as_number(raw: str) -> float | None:
    """Number from a string, or from a Dutch/English number word."""
    raw = raw.strip().strip("`*")
    if raw.lower() in DUTCH_NUMBERS:
        return float(DUTCH_NUMBERS[raw.lower()])
    try:
        return float(raw)
    except ValueError:
        return None


def fmt(value: float) -> str:
    return f"{value:g}"


class Finding:
    def __init__(self, check: str, path: Path, line: int, message: str) -> None:
        self.check = check
        self.path = path
        self.line = line
        self.message = message

    def __str__(self) -> str:
        where = self.path.relative_to(REPO)
        return f"[{self.check}] {where}:{self.line}: {self.message}"


# --------------------------------------------------------------------------
# CHECK A: constants
# --------------------------------------------------------------------------

def extract_identifier_constants() -> tuple[dict[str, float], list[Finding]]:
    """Reads SCREAMING_SNAKE constants from the source of truth.

    Two locations in the same file: the table under "Constants already
    decided" (where a row can put two constants next to two values) and loose
    `NAME = value` in the running text (that is where the seam rule lives).
    """
    findings: list[Finding] = []
    constants: dict[str, float] = {}
    origins: dict[str, int] = {}

    text = HARDSURFACE.read_text(encoding="utf-8")

    def record(name: str, value: float, line: int) -> None:
        if name in constants and constants[name] != value:
            findings.append(Finding(
                "A", HARDSURFACE, line,
                f"the source contradicts itself about `{name}`: "
                f"{fmt(constants[name])} on line {origins[name]}, here {fmt(value)}"))
            return
        constants[name] = value
        origins[name] = line

    for lineno, line in enumerate(text.splitlines(), start=1):
        # Table row: | `A` / `B` | 1 / 2 | where used |
        if line.startswith("|") and line.count("|") >= 3:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2:
                names = re.findall(r"`([A-Z][A-Z0-9_]{2,})`", cells[0])
                values = re.findall(NUMBER, cells[1])
                if names and len(names) == len(values):
                    # strict=True: the lengths were already found equal above,
                    # and if that ever changes this should fail hard instead
                    # of silently dropping the last constant.
                    for name, raw in zip(names, values, strict=True):
                        number = as_number(raw)
                        if number is not None:
                            record(name, number, lineno)
                elif len(names) == 1 and len(values) == 1:
                    number = as_number(values[0])
                    if number is not None:
                        record(names[0], number, lineno)

        # Running text: `SEAM_OVERLAP = 0.1`
        for name, raw in re.findall(rf"`?\b([A-Z][A-Z0-9_]{{2,}})\b`?\s*=\s*({NUMBER})", line):
            number = as_number(raw)
            if number is not None:
                record(name, number, lineno)

    return constants, findings


def check_identifier_constants(constants: dict[str, float]) -> list[Finding]:
    """Searches every other .claude/**/*.md for a deviating value for the same name.

    The name -> number coupling is deliberately tight: the number must follow
    the name directly, possibly with `=`, `:`, a bracket or a short connector
    word in between. Without that tightness the scan picks up the first number
    further along the sentence, and then reports
    `SEAM_OVERLAP, evidence: measurement (67 candidates)` as 67.
    """
    findings: list[Finding] = []
    connector = r"(?:=|:|van|is|op|naar|to|of)?"

    # The style guide is deliberately a check target too: it should carry the
    # same numbers as the table in SKILL.md, and until 2026-08-31 a difference
    # between those two could go unnoticed.
    for path in sorted(CLAUDE_DIR.rglob("*.md")):
        if path == HARDSURFACE:
            continue
        text = path.read_text(encoding="utf-8")
        ignored = set(re.findall(r"<!--\s*guard:ignore\s+([A-Za-z0-9_]+)\s*-->", text))

        for lineno, line in enumerate(text.splitlines(), start=1):
            for name, expected in constants.items():
                if name in ignored or name not in line:
                    continue
                pattern = rf"`?\b{re.escape(name)}\b`?\s*{connector}\s*\(?\s*({NUMBER})"
                for raw in re.findall(pattern, line):
                    found = as_number(raw)
                    if found is None or found == expected:
                        continue
                    findings.append(Finding(
                        "A", path, lineno,
                        f"`{name}` = {fmt(found)}, but roblox-hardsurface/SKILL.md "
                        f"says {fmt(expected)}"))
    return findings


# Concepts the source pins down in plain language instead of as an identifier.
# Each concept: where the value comes from, and how we recognise it elsewhere.
# These patterns are heuristic; they are tested against the current content of
# .claude/ and deliberately kept narrow. A false alarm should be dismissed with
# `guard:ignore`, not by stretching the pattern.
CONCEPTS = [
    {
        "name": "DOOR_WIDTH_STUDS",
        # Since 2026-09-02 the constants table lives in the project layer
        # (style guide), no longer in the plugin's SKILL.md.
        "source": STYLE_GUIDE,
        # Alternation: the old source line ("doors 10 wide") and the one
        # re-derived from StationBlueprint.WALLS on 2026-08-31 ("doorways 10-14
        # wide"), so the guard stays green at the moment the table line changes.
        "source_pattern": (
            rf"doors?\s+({NUMBER})\s+wide"
            rf"|doorways\s+({NUMBER})[–—-]({NUMBER})\s+wide"
        ),
        "range": True,
        "probes": [
            # Width claims only (wide/breed): since the judge prompt also names
            # door heights in studs, a bare "N studs" is ambiguous.
            (
                rf"\bd(?:oorway|oor|eur)\w*s?\b[^\n]{{0,40}}?"
                rf"({NUMBER})(?:\s*[–—-]\s*({NUMBER}))?\s*(?:studs?\s+)?(?:wide|breed)"
            ),
        ],
        "label": "door width in studs",
    },
    {
        "name": "BEVEL_RADIUS_MIN",
        "source": STYLE_GUIDE,
        "source_pattern": rf"[Bb]evelradius\s+vanaf\s+({NUMBER})",
        "probes": [
            rf"bevel\w*[^\d\n]{{0,20}}?(?:vanaf|from|min\w*)\s*({NUMBER})",
        ],
        "label": "minimum bevel radius",
    },
    {
        "name": "BEVEL_SEGMENTS",
        "source": STYLE_GUIDE,
        "source_pattern": rf"met\s+({NUMBER})\s+tot\s+({NUMBER})\s+segmenten",
        "range": True,
        "probes": [
            rf"segments?[^\d\n]{{0,8}}?({NUMBER})\s*(?:tot|to|[–—-])\s*({NUMBER})",
        ],
        "label": "number of bevel segments",
    },
    {
        "name": "PROP_TINTS",
        "source": STYLE_GUIDE,
        "source_pattern": r"[Pp]recies\s+(\w+)\s+tinten",
        "probes": [
            # The surrounding brackets are not style: without them a single
            # stray comma silently turns this one pattern into two.
            (
                r"(\w+)\s*(?:[–—-]\s*(\w+)\s*)?(?:desaturated\s+)?"
                r"(?:colou?rs?|tinten|tints)[^\n]{0,30}?accent"
            ),
        ],
        "label": "number of tints per prop (besides the accent)",
    },
    {
        "name": "MAX_ACCENTS_PER_STATION",
        "source": STYLE_GUIDE,
        "source_pattern": r"[Mm]aximaal\s+(\w+)\s+accentkleuren",
        "probes": [
            r"(\w+)\s+accentkleuren",
        ],
        "label": "number of accent colours per station",
    },
]


def check_concepts() -> list[Finding]:
    findings: list[Finding] = []

    for concept in CONCEPTS:
        source: Path = concept["source"]
        match = re.search(concept["source_pattern"], source.read_text(encoding="utf-8"))
        if not match:
            findings.append(Finding(
                "A", source, 0,
                f"could no longer find the source value for {concept['name']} ({concept['label']}); "
                "has the phrasing in the source changed? Update the "
                "pattern in tools/claude-config-guard.py"))
            continue

        expected = [as_number(g) for g in match.groups() if g]
        if any(v is None for v in expected) or not expected:
            continue
        is_range = bool(concept.get("range")) or len(expected) > 1

        for path in sorted(CLAUDE_DIR.rglob("*.md")):
            if path == source:
                continue
            text = path.read_text(encoding="utf-8")
            if concept["name"] in set(
                    re.findall(r"<!--\s*guard:ignore\s+([A-Za-z0-9_]+)\s*-->", text)):
                continue

            for lineno, line in enumerate(text.splitlines(), start=1):
                for probe in concept["probes"]:
                    for raw in re.finditer(probe, line):
                        found = [as_number(g) for g in raw.groups() if g]
                        if any(v is None for v in found) or not found:
                            continue
                        if is_range:
                            ok = found == expected or (
                                len(found) == 1 and expected[0] <= found[0] <= expected[-1])
                        else:
                            ok = len(found) == 1 and found[0] == expected[0]
                        if ok:
                            continue
                        findings.append(Finding(
                            "A", path, lineno,
                            f"{concept['label']} appears here as "
                            f"{'-'.join(fmt(v) for v in found)}, but "
                            f"{source.relative_to(REPO)} says "
                            f"{'-'.join(fmt(v) for v in expected)} "
                            f"({concept['name']})"))
    return findings


# --------------------------------------------------------------------------
# CHECK B: structure
# --------------------------------------------------------------------------

def skills_with_learnings() -> list[str]:
    # Derived, not pinned: every skill directory with a references/learnings.md
    # follows the shared protocol. A list of names drifted with every new skill
    # (same class as the gate-count lesson in known-mistakes).
    return sorted(path.parent.parent.name for path in SKILLS_DIR.glob("*/references/learnings.md"))


def check_structure() -> list[Finding]:
    findings: list[Finding] = []

    if skills_with_learnings() and not SHARED_PROTOCOL.exists():
        findings.append(Finding(
            "B", SHARED_PROTOCOL, 0,
            "the shared learnings protocol is missing, while the skills with a "
            "references/learnings.md refer to it (in a plugin project a "
            "reference to the plugin's protocol is enough)"))

    for skill in skills_with_learnings():
        skill_md = SKILLS_DIR / skill / "SKILL.md"
        if not skill_md.exists():
            findings.append(Finding("B", skill_md, 0, "SKILL.md is missing"))
            continue
        if "learnings-protocol.md" not in skill_md.read_text(encoding="utf-8"):
            findings.append(Finding(
                "B", skill_md, 0,
                f"does not refer to `{SHARED_REF}`, while that is the only place "
                "where the learnings protocol belongs"))

    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        lines = text.splitlines()

        if len(lines) > SKILL_MAX_LINES:
            findings.append(Finding(
                "B", skill_md, len(lines),
                f"{len(lines)} lines; the limit is {SKILL_MAX_LINES}. Move "
                "detail to references/"))

        if not text.startswith("---"):
            findings.append(Finding("B", skill_md, 1, "no frontmatter"))
        else:
            frontmatter = text.split("---", 2)[1]
            for field in ("name", "description"):
                if not re.search(rf"^{field}:", frontmatter, re.MULTILINE):
                    findings.append(Finding(
                        "B", skill_md, 1, f"frontmatter is missing `{field}:`"))

        # References at most one level deep (Anthropic's skill checklist).
        for lineno, line in enumerate(lines, start=1):
            for ref in re.findall(r"`([A-Za-z0-9_.\-]+/[A-Za-z0-9_./\-]+\.md)`", line):
                if ref.startswith((".claude/", "docs/")):
                    continue
                # Plugin path: the shared protocol lives in the kit under skills/_shared/.
                if ref.startswith("skills/_shared/"):
                    continue
                if ref.count("/") > 1:
                    findings.append(Finding(
                        "B", skill_md, lineno,
                        f"reference `{ref}` is more than one level deep"))

    # CLAUDE.md loads in every session; above the documented limit compliance
    # drops (memory docs: "target under 200 lines"). The owner aims for 100.
    claude_md = REPO / "CLAUDE.md"
    if claude_md.exists():
        count = len(claude_md.read_text(encoding="utf-8").splitlines())
        if count > CLAUDE_MD_MAX_LINES:
            findings.append(Finding(
                "B", claude_md, count,
                f"{count} lines; the limit is {CLAUDE_MD_MAX_LINES} (aim under 100). "
                "Move to .claude/rules/*.md with `paths`"))

    # A rule without `paths` loads in every session, including where it has no
    # business. Deliberately global: put `<!-- guard:ignore RULE_PATHS -->` in it with the reason.
    for rule in sorted((CLAUDE_DIR / "rules").glob("*.md")):
        text = rule.read_text(encoding="utf-8")
        if "guard:ignore RULE_PATHS" in text:
            continue
        frontmatter = text.split("---", 2)[1] if text.startswith("---") else ""
        if not re.search(r"^paths:", frontmatter, re.MULTILINE):
            findings.append(Finding(
                "B", rule, 1,
                "rule without `paths:` frontmatter loads in every session; scope it, or put "
                "`<!-- guard:ignore RULE_PATHS -->` in it with the reason"))
    return findings


# --------------------------------------------------------------------------
# CHECK D: budgets against the Luau source
#
# Check A watches drift WITHIN .claude/. The budgets also live in
# `src/shared/StationBlueprint.luau`, and that is the only place the builders
# and the acceptance test actually read. A skill that says 16 while the
# blueprint does 20 is an agent applying the wrong limit without anything
# failing. This check ties the two together, and additionally watches the ratio
# between the light budget and the sub-limit on shadows: a sub-limit that is not strictly smaller than the total prices nothing.

BLUEPRINT = REPO / "src" / "shared" / "StationBlueprint.luau"

BUDGET_NAMES = ("PART_BUDGET", "LIGHT_BUDGET", "SHADOW_LIGHT_BUDGET")


def check_budgets(constants: dict[str, float]) -> list[Finding]:
    findings: list[Finding] = []

    if not BLUEPRINT.exists():
        findings.append(Finding("D", BLUEPRINT, 0, "the Luau source is missing"))
        return findings

    text = BLUEPRINT.read_text(encoding="utf-8")
    blueprint: dict[str, tuple[float, int]] = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = re.match(
            rf"\s*StationBlueprint\.([A-Z][A-Z0-9_]{{2,}})\s*=\s*({NUMBER})\s*$", line)
        if match:
            number = as_number(match.group(2))
            if number is not None:
                blueprint[match.group(1)] = (number, lineno)

    for name in BUDGET_NAMES:
        if name not in blueprint:
            findings.append(Finding(
                "D", BLUEPRINT, 0,
                f"`{name}` is not in the Luau source; the skills cannot rely on it"))

    # Every constant that both the SKILL table and the blueprint name must carry
    # the same value. Until 2026-08-31 this only held for the three budgets,
    # which is how `MAX_LIGHT_BRIGHTNESS` could stay at 1.2 while the source
    # said 6.
    for name, (value, lineno) in sorted(blueprint.items()):
        if name in constants and constants[name] != value:
            findings.append(Finding(
                "D", BLUEPRINT, lineno,
                f"`{name}` is {fmt(value)} in the Luau source but "
                f"{fmt(constants[name])} in {HARDSURFACE.relative_to(REPO)}"))

    if "LIGHT_BUDGET" in blueprint and "SHADOW_LIGHT_BUDGET" in blueprint:
        total, _ = blueprint["LIGHT_BUDGET"]
        shadow, shadow_line = blueprint["SHADOW_LIGHT_BUDGET"]
        if shadow >= total:
            findings.append(Finding(
                "D", BLUEPRINT, shadow_line,
                f"SHADOW_LIGHT_BUDGET ({fmt(shadow)}) must be strictly smaller than "
                f"LIGHT_BUDGET ({fmt(total)}); otherwise the sub-limit is no limit"))

    return findings


# --------------------------------------------------------------------------
# CHECK E: denylist
#
# The rules live in .claude/known-bad.json; the module tools/knownbad.py reads,
# validates and matches them, the same code as the PreToolUse hook. Only files
# that fall under a rule's `paths` and are not exempt are scanned (the lesson
# files and docs/ may name the wrong thing in order to explain it).

SKIP_DIRS = {".git", "ServerPackages", "DevPackages", "Packages", "node_modules", "__pycache__"}
SKIP_FILES = {"sourcemap.json"}


def repo_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in sorted(REPO.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO)
        if any(part in SKIP_DIRS for part in rel.parts) or rel.name in SKIP_FILES:
            continue
        files.append((path, rel.as_posix()))
    return files


def check_denylist() -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    try:
        entries = knownbad.load(REPO)
    except (OSError, ValueError, re.error) as exc:
        return [Finding("E", REPO / knownbad.DENYLIST, 0, f"denylist unreadable: {exc}")], 0

    files = repo_files()
    for entry in entries:
        for path, rel in files:
            if knownbad.is_exempt(rel) or not knownbad.applies(entry, rel):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if knownbad.ignored(entry, text):
                continue
            for lineno, hit in knownbad.matches(entry, text):
                findings.append(Finding(
                    "E", path, lineno,
                    f"denylist `{entry['id']}`: `{hit.strip()}`; use {entry['use']}"))
    return findings, len(entries)


# --------------------------------------------------------------------------
# CHECK F: the gate steps

GATE_SCRIPT = REPO / "tools" / "gate.sh"
def gate_steps_from_script() -> list[str]:
    match = re.search(r"# GATE-STEPS-BEGIN.*?\n(.*?)# GATE-STEPS-END",
                      GATE_SCRIPT.read_text(encoding="utf-8"), re.DOTALL)
    return re.findall(r'"([^"]+)"', match.group(1)) if match else []


def gate_blocks_from_claude_md() -> list[list[str]]:
    """All ```sh blocks that start with the first gate step from tools/gate.sh.

    Generic: the first step comes from the GATE-STEPS block itself, not from a
    hard-coded project step; there should be exactly one."""
    claude_md = REPO / "CLAUDE.md"
    if not claude_md.exists():
        return []
    steps = gate_steps_from_script()
    if not steps:
        return []
    text = claude_md.read_text(encoding="utf-8")
    first_step = re.escape(steps[0])
    return [
        [line.strip() for line in match.group(1).splitlines() if line.strip()]
        for match in re.finditer(rf"```sh\n({first_step}[^`]*?)```", text, re.DOTALL)
    ]


def check_gate_steps() -> list[Finding]:
    if not GATE_SCRIPT.exists():
        return [Finding("F", GATE_SCRIPT, 0,
                        "tools/gate.sh is missing while CLAUDE.md and the hook refer to it")]
    findings: list[Finding] = []
    script = gate_steps_from_script()
    blocks = gate_blocks_from_claude_md()
    if not script:
        findings.append(Finding("F", GATE_SCRIPT, 0,
                                "no GATE-STEPS block found; has the marker changed?"))
    if not blocks:
        findings.append(Finding("F", REPO / "CLAUDE.md", 0,
                                "no gate code block found that starts with the first step from "
                                "tools/gate.sh"))
    elif len(blocks) > 1:
        findings.append(Finding("F", REPO / "CLAUDE.md", 0,
                                f"{len(blocks)} gate code blocks; there should be exactly one, "
                                "otherwise a duplicate block drifts unseen"))
    claude = blocks[0] if blocks else []
    if script and claude and script != claude:
        findings.append(Finding("F", GATE_SCRIPT, 0,
                                f"steps differ from CLAUDE.md: script {script} versus CLAUDE.md {claude}"))
    return findings


# --------------------------------------------------------------------------
# CHECK G: settings.json and the hook scripts

SETTINGS = CLAUDE_DIR / "settings.json"


def hook_commands(settings: dict) -> list[tuple[str, str]]:
    """All (event, command) pairs from the hooks block, tolerant of shape errors.

    A shape error (hooks not a dict, entry not a dict) is not a finding here:
    Claude Code itself ignores such blocks too, and the JSON parse in
    `check_settings` is the hard boundary.
    """
    pairs: list[tuple[str, str]] = []
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return pairs
    for event, entries in hooks.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks") or []:
                command = hook.get("command") if isinstance(hook, dict) else None
                if isinstance(command, str) and command:
                    pairs.append((str(event), command))
    return pairs


def check_settings() -> tuple[list[Finding], int]:
    """settings.json parses, and every hook command exists and is executable."""
    if not SETTINGS.exists():
        # In a plugin project the hooks come from the plugin's hooks/hooks.json;
        # a settings.json of its own is then optional.
        return [], 0
    try:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Finding("G", SETTINGS, 0, f"does not parse as JSON: {exc}")], 0

    findings: list[Finding] = []
    commands = hook_commands(settings)
    for event, command in commands:
        script = Path(command.replace("$CLAUDE_PROJECT_DIR", str(REPO)))
        if not script.is_absolute():
            # A bare shell command ("python3 ...") is not a file reference.
            continue
        if not script.is_file():
            findings.append(Finding(
                "G", SETTINGS, 0,
                f"hook `{event}` points to a missing script: {command}"))
        elif not os.access(script, os.X_OK):
            findings.append(Finding(
                "G", SETTINGS, 0,
                f"hook script of `{event}` is not executable: {command}"))
    return findings, len(commands)


# --------------------------------------------------------------------------

# CHECK H: lessons source and views
LESSONS_SOURCE = CLAUDE_DIR / "lessons.jsonl"
LESSONS_COMPILER = Path(__file__).resolve().parent / "lessons-compile.py"


def check_lessons_source() -> list[Finding]:
    if not LESSONS_SOURCE.exists() or not LESSONS_COMPILER.exists():
        return [Finding("H", LESSONS_SOURCE, 0,
                        "lessons source or compiler is missing; the lesson views are then unguarded")]
    uitkomst = subprocess.run(
        [sys.executable, str(LESSONS_COMPILER), "--check"],
        capture_output=True, text=True, check=False)
    if uitkomst.returncode == 0:
        return []
    detail = (uitkomst.stderr or uitkomst.stdout).strip().splitlines()
    return [Finding("H", LESSONS_SOURCE, 0,
                    detail[0] if detail else "lessons-compile --check failed without output")]


def main() -> int:
    quiet = "--quiet" in sys.argv

    # Generic plugin variant: checks A and D require a project layer with a
    # constants source (hardsurface skill copy plus style guide plus blueprint);
    # a fresh project without that layer skips them instead of failing.
    findings: list[Finding] = []
    constants: dict = {}
    if HARDSURFACE.exists() and STYLE_GUIDE.exists():
        constants, findings = extract_identifier_constants()
        findings += check_identifier_constants(constants)
        findings += check_concepts()
        findings += check_budgets(constants)
    elif not quiet:
        print("checks A/D skipped: no project constants source "
              "(hardsurface skill copy or style guide is missing)")
    findings += check_structure()
    denylist_findings, denylist_count = check_denylist()
    findings += denylist_findings
    findings += check_gate_steps()
    settings_findings, hook_command_count = check_settings()
    findings += settings_findings
    findings += check_lessons_source()

    if not quiet:
        print(f"Source: {HARDSURFACE.relative_to(REPO)} + {STYLE_GUIDE.relative_to(REPO)}")
        print(f"Constants read: {len(constants)} "
              f"({', '.join(sorted(constants))})")
        print(f"Concepts checked: {len(CONCEPTS)}")
        print(f"Denylist rules: {denylist_count}")
        print(f"Hook commands checked: {hook_command_count}")
        print(f"Files scanned: {len(list(CLAUDE_DIR.rglob('*.md')))}")
        print()

    if not findings:
        print("CONFIG GUARD PASS: no contradictory constants, skills structurally in order")
        return 0

    print(f"CONFIG GUARD FAIL: {len(findings)} finding(s):")
    for finding in findings:
        print(f"  {finding}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
