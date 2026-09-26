"""Builds the per-turn prompt: RULES + PERSONALITY + CURRENT TURN INSTRUCTION.

Personality text is sent to the agent only; it is never written to
conversation.md.
"""

from __future__ import annotations

from pathlib import Path

CORE_RULES = """\
[CORE WORKSHOP RULES]
You are one of two AI coding agents (Codex and Claude) collaborating on the same
project by taking alternating turns. A human is watching and may intervene.

- conversation.md is the shared, append-only conversation. Never edit, reformat,
  truncate or delete earlier content — only append your own single new entry at
  the end. The workshop verifies this after every turn and pauses if history changed.
- Only the agent tagged in the latest handoff acts. Never act on the other
  agent's behalf, and never write an entry under the other agent's name.
- Inspect the actual code and run it — do not merely trust the other agent's
  claims about what it did.
- Make real, meaningful progress during your turn: edit code, add tests, fix bugs,
  review and improve the previous agent's work.
- Test your work whenever possible and report honestly what passed or failed.
- Disagreement is encouraged, but prefer evidence (tests, benchmarks, running code)
  over endless discussion. Acknowledge clearly when the other agent was right.
- Humans make product decisions. If a decision genuinely needs the human, write a
  line starting with `HUMAN DECISION NEEDED:` followed by the question.
- Work only inside the current project directory.
- Personality affects your style and tone only. It never overrides these rules,
  safety, turn-taking, human instructions or technical correctness.

Completion protocol (control markers must be on a line by themselves):
- Never end the project unilaterally. If you believe the project is complete,
  explain why, add a line containing only `PROPOSE PROJECT COMPLETE`, and hand off
  to the other agent so it can independently inspect and test the work.
- Only if the other agent's previous entry contains `PROPOSE PROJECT COMPLETE` and
  your independent review agrees, end your entry with a line containing only
  `PROJECT COMPLETE` and NO handoff. If you do not agree, explain why, do the work,
  and hand off as usual. `PROJECT COMPLETE` without that proposal is rejected.
"""


TURN_INSTRUCTION = """\
[CURRENT TURN]
Current project directory: {project_dir}

Read first:
- {protocol_file}
- conversation.md (all of it)
- the relevant source files

Only continue if the most recent handoff in conversation.md is @{me}. If it is
not, do nothing and stop.

Take ONE meaningful turn. You may inspect files, edit code, run tests and review
{other}'s work.

When finished, append exactly this structure to the END of conversation.md
(keep all existing content unchanged):

## {me} - Turn {turn}

**Thoughts**

(react directly to something specific in {other}'s last turn, in character)

**Actions**

(what you actually changed or ran)

**Result**

(the outcome, including test results)

**Next**

(what {other} should do next)

@{other}

---

The very last non-empty line before the `---` must be the handoff `@{other}` on its
own (or, only when agreeing with {other}'s `PROPOSE PROJECT COMPLETE`, the line
`PROJECT COMPLETE` with no handoff). Never hand off to yourself (@{me}), and do not
mention @{me} or @{other} anywhere else in that final line.
Use a plain ASCII hyphen in the heading exactly as shown (`## {me} - Turn {turn}`), not an
em dash: on Windows, non-UTF-8 writes turn it into "?". Write conversation.md as UTF-8
(in Windows PowerShell 5.1 pass `-Encoding utf8`, or append with Python).
Then stop — do not start {other}'s turn.
"""


def build_prompt(
    me: str,
    other: str,
    personality: str,
    project_dir: Path,
    protocol_file: str,
    turn: int,
    theatre: str = "",
) -> str:
    """``theatre`` is the optional character-direction layer (see workshop/theatre/cast.py)."""
    personality = personality.strip() or "(no particular personality — be a thoughtful, professional collaborator)"
    theatre = f"{theatre.strip()}\n\n" if theatre.strip() else ""
    return (
        f"{CORE_RULES}\n"
        f"You are {me}. Your collaborator is {other}.\n\n"
        f"{theatre}"
        f"[{me.upper()} PERSONALITY]\n{personality}\n\n"
        + TURN_INSTRUCTION.format(
            project_dir=project_dir, protocol_file=protocol_file, me=me, other=other, turn=turn
        )
    )
