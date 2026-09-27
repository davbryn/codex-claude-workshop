"""The shared kanban board (KANBAN.md), courtesy of management.

A small, forgiving Markdown format that agents edit with ordinary file tools::

    # Kanban
    ## To do
    - Split answers and allowed words (Gilfoyle) — "Dinesh 'suggested' it. So now it's mine."
    ## Doing
    ## Done
    ## Asides
    - Dinesh: He moved my card. Without asking. Again.

Cards may carry an owner in parentheses and an aside in quotes after a dash.
Asides are public, in-character one-liners the stage speaks aloud while an
agent works. The board is presentation and planning; conversation.md remains
the protocol and the source of truth.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

KANBAN_FILE = "KANBAN.md"
COLUMNS = ("To do", "Doing", "Done")
_COLUMN_ALIASES = {
    "to do": "To do", "todo": "To do", "backlog": "To do", "to-do": "To do",
    "doing": "Doing", "in progress": "Doing", "wip": "Doing", "in-progress": "Doing",
    "done": "Done", "complete": "Done", "completed": "Done",
}
_CARD = re.compile(r"^\s*[-*+]\s+(?:\[[ xX]\]\s*)?(?P<body>.+?)\s*$")
_ASIDE_QUOTE = re.compile(r"\s+(?:[—–-]{1,2}|\?|â€”)\s+[\"“](?P<aside>.+?)[\"”]\s*$")
_OWNER = re.compile(r"\s*\((?P<owner>[^()]{1,40})\)\s*$")
_ASIDE_LINE = re.compile(r"^\s*[-*+]\s+(?P<name>[A-Za-z][\w .'-]{0,30}?)\s*:\s+(?P<text>.+?)\s*$")

SEED = """# Kanban

<!-- Set up by management (Jared) so everyone can see progress at a glance. Please keep it current! -->

## To do
- Read the brief together (Gilfoyle, Dinesh) — "Synergy starts with a shared understanding! — Jared"

## Doing

## Done

## Asides
"""


@dataclass(frozen=True)
class Card:
    title: str
    column: str
    owner: str = ""
    aside: str = ""


@dataclass
class Board:
    columns: dict[str, list[Card]] = field(default_factory=lambda: {c: [] for c in COLUMNS})
    asides: list[tuple[str, str]] = field(default_factory=list)  # (name, text)

    def cards(self) -> list[Card]:
        return [c for col in COLUMNS for c in self.columns.get(col, [])]

    def __bool__(self) -> bool:
        return bool(self.cards() or self.asides)


def parse(text: str) -> Board:
    board = Board()
    section = None
    in_comment = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if "<!--" in line and "-->" not in line:
            in_comment = True
            continue
        if in_comment:
            in_comment = "-->" not in line
            continue
        heading = re.match(r"^\s*#{2,4}\s+(.+?)\s*#*\s*$", line)
        if heading:
            name = heading.group(1).strip().rstrip(":").lower()
            section = "asides" if name.startswith("aside") else _COLUMN_ALIASES.get(name)
            continue
        if section is None:
            continue
        if section == "asides":
            m = _ASIDE_LINE.match(line)
            if m:
                board.asides.append((m.group("name").strip(), _clean(m.group("text"))))
            continue
        m = _CARD.match(line)
        if not m:
            continue
        body, aside = m.group("body"), ""
        if q := _ASIDE_QUOTE.search(body):
            aside, body = _clean(q.group("aside")), body[: q.start()]
        owner = ""
        if o := _OWNER.search(body):
            owner, body = o.group("owner").strip(), body[: o.start()]
        title = body.strip().strip("*_`").strip()
        if title:
            board.columns[section].append(Card(title, section, owner, aside))
    return board


def _clean(text: str) -> str:
    # agents sometimes write "&gt;" for ">" in Markdown: show and speak the character, not the entity
    text = html.unescape(text.replace("**", "").replace("`", ""))
    return re.sub(r"\s+", " ", text).strip().strip("\"“”")[:200]


def read_board(project_dir: Path) -> Board | None:
    try:
        return parse((Path(project_dir) / KANBAN_FILE).read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return None


def ensure_board(project_dir: Path) -> Path:
    """Management sets up the board (once). Existing boards are never touched."""
    path = Path(project_dir) / KANBAN_FILE
    if not path.exists():
        path.write_text(SEED, encoding="utf-8")
    return path


@dataclass(frozen=True)
class Aside:
    speaker: str  # agent name ("Codex"/"Claude")
    text: str
    card: str = ""  # the card it was attached to, if any


def new_asides(old: Board | None, new: Board, names: dict[str, tuple[str, ...]]) -> list[Aside]:
    """Asides that appeared since ``old``, attributed to an agent by name or card owner.

    ``names`` maps agent -> accepted names (e.g. {"Codex": ("Codex", "Gilfoyle")}).
    Anything that can't be attributed is ignored (never guessed).
    """
    def who(name: str) -> str | None:
        low = name.strip().lower()
        for agent, aliases in names.items():
            if any(low == a.lower() for a in aliases):
                return agent
        return None

    before_cards = {(c.title, c.aside) for c in old.cards()} if old else set()
    before_lines = list(old.asides) if old else []
    found: list[Aside] = []
    for card in new.cards():
        if card.aside and (card.title, card.aside) not in before_cards:
            owners = [who(o) for o in re.split(r"\s*(?:,|/|&|\band\b)\s*", card.owner) if o]
            owners = [o for o in owners if o]
            if len(owners) == 1:
                found.append(Aside(owners[0], card.aside, card.title))
    remaining = list(before_lines)
    for name, text in new.asides:
        if (name, text) in remaining:
            remaining.remove((name, text))
            continue
        agent = who(name)
        if agent:
            found.append(Aside(agent, text))
    return found


def moved_cards(old: Board | None, new: Board) -> list[Card]:
    """Cards that are new or changed column since ``old`` (for highlighting)."""
    before = {c.title: c.column for c in old.cards()} if old else {}
    return [c for c in new.cards() if before.get(c.title) != c.column]


def prompt_block(me: str, other: str, me_name: str, other_name: str) -> str:
    return f"""[SHARED KANBAN BOARD]
Management has given you both a shared kanban board: {KANBAN_FILE} in the project root. The humans watch it
live, and your asides on it are read aloud while you work. (You are free to have opinions about this.)
- FIRST, before other work this turn: move (or add) the card(s) you're about to do into "## Doing", with your
  name as owner and a one-line in-character aside, like: `- Split the word lists ({me_name}) - "aside"`
  (plain ASCII hyphen before the quote; write the file as UTF-8).
- As you finish: move them to "## Done" with a short aside. Moving a card means deleting its line from the old
  column, not copying it. Add cards to "## To do" for work you think remains (owner optional).
- Optionally, while working (e.g. after a test run), append up to two lines under "## Asides" as
  `- {me_name}: your aside`.
- Asides: one line, under 120 characters, in character, and true to what is actually happening. Only write
  asides as yourself ({me_name}), never as {other_name}. Don't delete {other_name}'s cards or asides.
- Keep the headings (## To do / ## Doing / ## Done / ## Asides). Never put protocol markers or @handoffs in
  {KANBAN_FILE}. The board never replaces your conversation.md entry.
"""
