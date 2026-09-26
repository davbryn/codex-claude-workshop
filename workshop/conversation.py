"""Parsing and appending for the shared ``conversation.md`` file.

The file is append-only Markdown. Each entry starts with a level-2 heading
naming the speaker::

    ## Codex — Turn 3
    ## Claude — Turn 2
    ## Human — Intervention

The *control signal* (who acts next) is always taken from the latest entry
only, so old handoffs further up the file are ignored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

AGENTS = ("Codex", "Claude")
SPEAKERS = AGENTS + ("Human",)

HUMAN_DECISION_MARKER = "HUMAN DECISION NEEDED:"
COMPLETE_MARKER = "PROJECT COMPLETE"
PROPOSE_COMPLETE_MARKER = "PROPOSE PROJECT COMPLETE"

# The separator is normally "—", but agents writing through a non-UTF-8 shell
# can mangle it (e.g. "## Codex ? Turn 6" or "## Codex â€” Turn 6"), so any
# short run of non-alphanumeric symbols between spaces is accepted too.
_HEADING_RE = re.compile(
    r"^#{2,3}\s+\**(Codex|Claude|Human)\**"
    r"(?:\s*[—–:\-]+\s*(.*?)|\s+[^A-Za-z0-9\s]{1,3}\s+(.*?))?\s*$",
    re.IGNORECASE,
)
_TURN_NUMBER_RE = re.compile(r"turn\s*#?\s*(\d+)", re.IGNORECASE)
_MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_-]*)")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")

DISAGREEMENT_PHRASES = (
    "i disagree",
    "codex is wrong",
    "claude is wrong",
    "unnecessary",
    "over-engineered",
    "overengineered",
    "over engineered",
    "bug",
    "however",
    "i don't think",
    "i do not think",
    "not convinced",
)


@dataclass
class ConversationTurn:
    speaker: str  # "Codex", "Claude" or "Human"
    title: str  # heading text after the speaker, e.g. "Turn 3"
    number: int | None
    content: str
    handoff: str | None  # "Codex" / "Claude" when the entry ends with a valid handoff


@dataclass
class ControlSignal:
    """What the latest entry says should happen next."""

    kind: str  # handoff | complete | human | missing | invalid | malformed | empty
    agent: str | None = None  # target agent for a handoff
    speaker: str | None = None  # who wrote the latest entry
    detail: str = ""


def normalise_agent(name: str) -> str | None:
    for agent in SPEAKERS:
        if agent.lower() == name.strip().lower():
            return agent
    return None


def parse_conversation(text: str) -> list[ConversationTurn]:
    """Split the conversation into speaker entries.

    Headings inside fenced code blocks are ignored. Text before the first
    speaker heading (the ``# Codex ↔ Claude`` title) is dropped.
    """
    turns: list[ConversationTurn] = []
    current: tuple[str, str] | None = None
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        if current is None:
            return
        content = _strip_separators("\n".join(body))
        speaker, title = current
        match = _TURN_NUMBER_RE.search(title)
        turns.append(
            ConversationTurn(
                speaker=speaker,
                title=title,
                number=int(match.group(1)) if match else None,
                content=content,
                handoff=_final_handoff(content),
            )
        )

    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING_RE.match(line)
        if heading:
            flush()
            title = heading.group(2) or heading.group(3) or ""
            current = (normalise_agent(heading.group(1)), title.strip())
            body = []
        elif current is not None:
            body.append(line)
    flush()
    return turns


def _strip_separators(content: str) -> str:
    lines = content.strip("\n").splitlines()
    while lines and lines[-1].strip() in ("", "---", "***", "___"):
        lines.pop()
    while lines and lines[0].strip() in ("", "---"):
        lines.pop(0)
    return "\n".join(lines).strip()


def _last_meaningful_line(content: str) -> str:
    for line in reversed(content.splitlines()):
        stripped = line.strip()
        if stripped and stripped not in ("---", "***", "___"):
            return stripped
    return ""


def _final_handoff(content: str) -> str | None:
    names = {normalise_agent(m) for m in _MENTION_RE.findall(_last_meaningful_line(content))}
    names.discard(None)
    names.discard("Human")
    return names.pop() if len(names) == 1 else None


def get_latest_turn(text_or_turns: str | list[ConversationTurn]) -> ConversationTurn | None:
    turns = parse_conversation(text_or_turns) if isinstance(text_or_turns, str) else text_or_turns
    return turns[-1] if turns else None


def get_control_signal(text: str) -> ControlSignal:
    """Decide what should happen next based only on the latest entry."""
    latest = get_latest_turn(text)
    if latest is None:
        return ControlSignal("empty", detail="The conversation has no entries yet.")
    return signal_for_turn(latest)


def signal_for_turn(turn: ConversationTurn) -> ControlSignal:
    speaker = turn.speaker
    if HUMAN_DECISION_MARKER.lower() in turn.content.lower():
        question = turn.content[turn.content.lower().index(HUMAN_DECISION_MARKER.lower()) :]
        return ControlSignal("human", speaker=speaker, detail=question.splitlines()[0].strip())

    declares_complete = has_marker(turn.content, COMPLETE_MARKER)
    last_line = _last_meaningful_line(turn.content)
    mentions = [m for m in _MENTION_RE.findall(last_line)]
    if mentions:
        known = {normalise_agent(m) for m in mentions} - {None, "Human"}
        unknown = [m for m in mentions if normalise_agent(m) not in AGENTS]
        if len(known) > 1:
            return ControlSignal(
                "malformed", speaker=speaker, detail=f"Both agents are tagged in the final line: {last_line!r}"
            )
        if len(known) == 1:
            target = known.pop()
            if target == speaker:
                return ControlSignal(
                    "malformed", speaker=speaker, detail=f"{speaker} handed off to itself (@{speaker})."
                )
            if declares_complete:
                return ControlSignal(
                    "malformed",
                    speaker=speaker,
                    detail=f"The entry says {COMPLETE_MARKER} but also hands off to @{target}.",
                )
            return ControlSignal("handoff", agent=target, speaker=speaker)
        return ControlSignal(
            "invalid", speaker=speaker, detail=f"Handoff to unknown agent: {', '.join('@' + m for m in unknown)}"
        )

    if declares_complete:
        return ControlSignal("complete", speaker=speaker)
    if has_marker(turn.content, PROPOSE_COMPLETE_MARKER):
        return ControlSignal(
            "missing",
            speaker=speaker,
            detail=f"It says {PROPOSE_COMPLETE_MARKER} but does not hand off to the other agent for review.",
        )
    return ControlSignal("missing", speaker=speaker, detail="The latest entry does not end with @Codex or @Claude.")


def _marker_text(line: str) -> str:
    """A line with Markdown emphasis/code and trailing punctuation stripped."""
    return line.strip().strip("*_`# ").rstrip(".!").strip("*_` ")


def has_marker(content: str, marker: str) -> bool:
    """True if ``marker`` appears as a whole line of its own (outside code fences).

    Control markers must be exact lines so prose such as "the project is not
    complete" or "don't write PROJECT COMPLETE yet" can never trigger them.
    """
    in_fence = False
    for line in content.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence and _marker_text(line) == marker:
            return True
    return False


def get_latest_handoff(text: str) -> str | None:
    signal = get_control_signal(text)
    return signal.agent if signal.kind == "handoff" else None


def completion_was_reviewed(turns: list[ConversationTurn]) -> bool:
    """PROJECT COMPLETE is only accepted from an agent answering the other agent's proposal.

    The previous *agent* entry (human interventions in between are allowed) must
    be by the other agent and contain the exact ``PROPOSE PROJECT COMPLETE`` line.
    """
    if not turns or turns[-1].speaker not in AGENTS:
        return False
    last = turns[-1]
    previous = next((t for t in reversed(turns[:-1]) if t.speaker in AGENTS), None)
    return (
        previous is not None
        and previous.speaker != last.speaker
        and has_marker(previous.content, PROPOSE_COMPLETE_MARKER)
    )


def validate_append(before: str, after: str, agent: str) -> str | None:
    """Check that an agent's turn only appended exactly one entry of its own.

    Returns a human-readable problem description, or None if the change is valid.
    Line-ending differences (CRLF/LF) and trailing whitespace at the old end of
    the file are tolerated; any other change to earlier text is not.
    """
    old = before.replace("\r\n", "\n").rstrip()
    new = after.replace("\r\n", "\n")
    if not new.startswith(old):
        new_stripped = new.rstrip()
        if old.startswith(new_stripped):
            kind = "truncated (earlier content was removed)"
        else:
            kind = "modified or replaced"
        old_lines, new_lines = old.splitlines(), new.splitlines()
        line = next(
            (i + 1 for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b),
            min(len(old_lines), len(new_lines)) + 1,
        )
        return (
            f"{agent} modified historical conversation content: conversation.md was {kind}, "
            f"first difference at line {line}. conversation.md is append-only; agents may only add a new "
            "entry at the end."
        )

    suffix = new[len(old):]
    preamble = []
    for text_line in suffix.splitlines():
        if _HEADING_RE.match(text_line):
            break
        preamble.append(text_line)
    stray = [t.strip() for t in preamble if t.strip() not in ("", "---", "***", "___")]
    added = parse_conversation(suffix)
    if not added:
        return f"{agent} changed conversation.md without appending a '## {agent} — Turn N' entry."
    if stray:
        return f"{agent} appended text outside its entry heading: {stray[0][:80]!r}"
    if len(added) > 1:
        who = ", ".join(t.speaker for t in added)
        return f"{agent} appended {len(added)} entries ({who}); exactly one entry of its own is allowed per turn."
    if added[0].speaker != agent:
        return f"{agent} appended an entry under the '## {added[0].speaker}' heading instead of its own."
    return None


def count_turns(turns: list[ConversationTurn], speaker: str) -> int:
    return sum(1 for t in turns if t.speaker == speaker)


def next_turn_number(text: str, agent: str) -> int:
    return count_turns(parse_conversation(text), agent) + 1


def extract_latest_speech(text: str, speaker: str, limit: int = 420) -> str | None:
    """A short, readable excerpt of the speaker's latest entry for a speech bubble.

    Prefers the **Thoughts** section (where personality tends to live), else
    the first real paragraph. Only ever returns text the speaker actually wrote.
    """
    turns = [t for t in parse_conversation(text) if t.speaker == speaker]
    if not turns:
        return None
    content = turns[-1].content
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]

    chosen = None
    for i, para in enumerate(paragraphs):
        if re.fullmatch(r"\**thoughts?\**:?", para.lower()) and i + 1 < len(paragraphs):
            chosen = paragraphs[i + 1]
            break
    if chosen is None:
        for para in paragraphs:
            if not re.fullmatch(r"\**[\w\s]+\**:?", para) and not para.startswith("@"):
                chosen = para
                break
    if chosen is None:
        chosen = content.strip()

    chosen = re.sub(r"\*\*(.+?)\*\*", r"\1", chosen)
    chosen = re.sub(r"\s+", " ", chosen).strip()
    if len(chosen) > limit:
        cut = chosen[:limit].rsplit(" ", 1)[0]
        chosen = cut.rstrip(",.;:") + "…"
    return chosen


def detect_disagreement(content: str) -> bool:
    lowered = content.lower()
    return any(re.search(r"\b" + re.escape(p) + r"\b", lowered) for p in DISAGREEMENT_PHRASES)


# --- writing -----------------------------------------------------------------

CONVERSATION_TITLE = "# Codex ↔ Claude"


def new_conversation_text(prompt: str, first_agent: str) -> str:
    return (
        f"{CONVERSATION_TITLE}\n\n"
        f"## Human — Project Start\n\n"
        f"_{datetime.now():%Y-%m-%d %H:%M}_\n\n"
        f"{prompt.strip()}\n\n"
        f"@{first_agent}\n\n"
        f"---\n"
    )


def human_turn_text(message: str, next_agent: str, title: str = "Intervention") -> str:
    return f"\n## Human — {title}\n\n{message.strip()}\n\n@{next_agent}\n\n---\n"


def append_human_turn(path: Path, message: str, next_agent: str, title: str = "Intervention") -> None:
    if next_agent not in AGENTS:
        raise ValueError(f"Unknown agent {next_agent!r}")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    prefix = "" if existing.endswith("\n") or not existing else "\n"
    if existing and not existing.rstrip().endswith("---"):
        prefix += "\n---\n"
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(prefix + human_turn_text(message, next_agent, title))


def read_conversation(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
