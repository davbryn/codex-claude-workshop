"""Banter memory and the Petty Scoreboard.

Both are derived ONLY from public entries in conversation.md, using the same
deterministic classifier as the stage reactions. Callbacks are short factual
notes ("Dinesh caught a Gilfoyle bug — turn 5: …") fed into the *personality*
part of later prompts; they never touch technical or orchestration state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..conversation import AGENTS, ConversationTurn
from .cast import CHARACTER
from .reactions import (
    DISAGREE_RX,
    EVIDENCE_RX,
    FOUND_BUG_RX,
    JAB_RX,
    SELF_ADMIT_RX,
    EntryReaction,
    classify_entry,
)
from .text import sentences, strip_code

ABSTRACTION_RX = re.compile(
    r"\b(?:factory|factories|abstract(?:ion|ions)?|interface|plugin|registry|framework|kubernetes|microservice|"
    r"service locator|dependency injection|base class|singleton|strategy pattern|adapter layer|lru cache|cache)\b",
    re.I,
)


@dataclass(frozen=True)
class Callback:
    turn: int  # index of the entry in the conversation (1-based, agent entries only)
    kind: str  # caught_bug | own_goal | concession | won_argument | mocked_abstraction | disagreement
    actor: str  # agent who did the thing
    target: str  # the other agent
    quote: str = ""

    def text(self) -> str:
        a, b = CHARACTER[self.actor], CHARACTER[self.target]
        head = {
            "caught_bug": f"{a} caught a {b} bug",
            "own_goal": f"{a} admitted his own mistake",
            "concession": f"{a} conceded {b} was right",
            "won_argument": f"{a} won an argument with {b} by evidence",
            "mocked_abstraction": f"{a} mocked {b}'s abstraction",
            "disagreement": f"{a} disagreed with {b}",
        }[self.kind]
        quote = f': "{self.quote}"' if self.quote else ""
        return f"{head} — turn {self.turn}{quote}"


def _quote(content: str, pattern: re.Pattern, limit: int = 110) -> str:
    for sentence in sentences(strip_code(content)):
        if pattern.search(sentence):
            return sentence if len(sentence) <= limit else sentence[: limit - 1].rsplit(" ", 1)[0] + "…"
    return ""


def extract_callbacks(turns: list[ConversationTurn]) -> list[Callback]:
    out: list[Callback] = []
    number = 0
    previous: tuple[ConversationTurn, EntryReaction] | None = None
    for turn in turns:
        if turn.speaker not in AGENTS:
            continue
        number += 1
        me = turn.speaker
        other = "Claude" if me == "Codex" else "Codex"
        r = classify_entry(turn)
        content = turn.content
        if r.caught_other_bug:
            out.append(Callback(number, "caught_bug", me, other, _quote(content, FOUND_BUG_RX) or
                                _quote(content, re.compile(r"bug|crash|broke|fails", re.I))))
        if r.self_admission:
            out.append(Callback(number, "own_goal", me, other, _quote(content, SELF_ADMIT_RX)))
        if r.concedes_other:
            out.append(Callback(number, "concession", me, other))
            # an argument is "won by evidence" when the other side argued, and this concession cites evidence
            argued = previous is not None and previous[0].speaker == other and previous[1].disagreement
            if argued and not r.disagreement and (r.evidence or previous[1].evidence):
                out.append(Callback(number, "won_argument", other, me, _quote(content, EVIDENCE_RX)))
        if r.disagreement and r.mentions_other and ABSTRACTION_RX.search(strip_code(content)):
            out.append(Callback(number, "mocked_abstraction", me, other, _quote(content, ABSTRACTION_RX)))
        elif r.disagreement:
            out.append(Callback(number, "disagreement", me, other, _quote(content, DISAGREE_RX)))
        previous = (turn, r)
    return out


def callbacks_for(agent: str, callbacks: list[Callback], limit: int = 4) -> list[str]:
    """A small, relevant subset for ``agent``'s next prompt: its ammunition first, then its sore points."""
    ammo = [c for c in callbacks if c.actor == agent and c.kind in ("caught_bug", "won_argument", "mocked_abstraction")]
    ammo += [c for c in callbacks if c.actor != agent and c.kind in ("own_goal", "concession")]
    sore = [c for c in callbacks if c.target == agent and c.kind in ("caught_bug", "won_argument")]
    picked: list[Callback] = []
    for c in sorted(ammo, key=lambda c: -c.turn)[:limit - 1] + sorted(sore, key=lambda c: -c.turn)[:1]:
        if c not in picked:
            picked.append(c)
    return [c.text() for c in sorted(picked, key=lambda c: c.turn)[:limit]]


# --- the Petty Scoreboard ----------------------------------------------------------

SCORE_ROWS = (
    ("bugs_caught", "Bugs caught"),
    ("arguments_won", "Arguments won by evidence"),
    ("concessions_received", "Grudging concessions received"),
    ("own_goals", "Own goals"),
)


@dataclass
class PettyScore:
    bugs_caught: int = 0
    arguments_won: int = 0
    concessions_received: int = 0
    own_goals: int = 0
    jabs: int = 0
    extra: dict = field(default_factory=dict)


def petty_scoreboard(turns: list[ConversationTurn]) -> dict[str, PettyScore]:
    """Only factual, derivable events. Deliberately unserious; not a model leaderboard."""
    board = {a: PettyScore() for a in AGENTS}
    for c in extract_callbacks(turns):
        if c.kind == "caught_bug":
            board[c.actor].bugs_caught += 1
        elif c.kind == "won_argument":
            board[c.actor].arguments_won += 1
        elif c.kind == "concession":
            board[c.target].concessions_received += 1
        elif c.kind == "own_goal":
            board[c.actor].own_goals += 1
    for turn in turns:
        if turn.speaker in AGENTS and classify_entry(turn).jab:
            board[turn.speaker].jabs += 1
    return board


__all__ = ["Callback", "extract_callbacks", "callbacks_for", "petty_scoreboard", "PettyScore", "SCORE_ROWS",
           "JAB_RX"]


def make_prompt_theatre(settings):
    """``Orchestrator.prompt_theatre`` factory: reads the live settings on every turn."""
    from ..conversation import parse_conversation
    from .cast import theatre_block

    def build(agent: str, conversation_text: str) -> str:
        from ..kanban import prompt_block
        from .cast import CHARACTER

        other = "Claude" if agent == "Codex" else "Codex"
        cast = getattr(settings, "cast_enabled", True)
        parts = []
        if cast:
            callbacks = callbacks_for(agent, extract_callbacks(parse_conversation(conversation_text)))
            parts.append(theatre_block(agent, getattr(settings, "hostility", ""), callbacks))
        if getattr(settings, "kanban_enabled", False):
            me_name = CHARACTER[agent] if cast else agent
            other_name = CHARACTER[other] if cast else other
            parts.append(prompt_block(agent, other, me_name, other_name))
        return "\n\n".join(parts)

    return build
