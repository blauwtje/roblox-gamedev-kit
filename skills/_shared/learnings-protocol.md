# Learnings protocol (shared)

This file is not a skill and is never invoked on its own. It is the single home
of the protocol that every skill with a `references/learnings.md` follows for
that file. Change it here; never re-state it inside a `SKILL.md`.

`references/learnings.md` is the memory of the skill that owns it: what that
skill has already proved. It is not documentation: facts about the game belong
in the game repo's `docs/`, and visual direction in the project's style guide.

**Read.** At the start of every use of the skill, read its
`references/learnings.md` and apply what it says.

**Write.** At the end of a run, add an entry for every lesson that has
evidence. One confirmed mistake (verified against a primary source or a
measurement) or one explicit owner correction qualifies immediately. Writing a
lesson means: add one record to the project's `.claude/lessons.jsonl` and run
the lessons compiler (`${CLAUDE_PLUGIN_ROOT}/scripts/lessons-compile.py`); the
compiled views (`references/learnings.md`, the project's known-mistakes rule,
the project's `known-bad.json`) are never edited by hand — the config guard
fails on any divergence.

Route by kind. A **fact** goes to the owning skill's learnings; once it holds
for more than one skill it moves to the project's shared known-mistakes rule,
and a fact that rejects an API or setting also gets a denylist record so the
PreToolUse hook blocks the repeat. A **way of working** goes to the skill when
skill-specific and to the shared rule when shared. An owner verdict on
**taste** goes verbatim to the project's owner-taste file, never through the
compiler. Routing and promotion are record fields, not copies.

Not admissible: anything the project docs already state (link instead), and a
proposal that changes the visual direction (final report, "Proposals for the
owner"). No evidence means no entry.

**Format**, one line per lesson:

```
- [YYYY-MM-DD] <rule in the imperative> — bewijs: <meting | valkuil | ronde> — grens: <when it does not apply>
```

**Maintenance.** Update the existing record instead of duplicating it. The
ceiling is 30 lines per compiled view; above it, merge the oldest still-valid
lessons into the owning `SKILL.md` and archive their records. Delete a lesson
that turned out to be wrong by removing its record; give the reason in the
final report.

**Boundary.** Learnings never change the judge prompt, the style guide or the
rubric. **Boundary with auto-memory:** machine-local auto-memory is the channel
for session progress, never a lesson store; project lessons live in
`.claude/lessons.jsonl` and nowhere else.
