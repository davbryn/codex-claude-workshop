"""Session capture: everything an episode can be cut from, as a timestamped event log.

Written to ``<project>/.workshop/episode/events.jsonl`` while the workshop runs
(headless or windowed). Only public, observable material is recorded: the
entries the agents append, the kanban board and its asides, the diffs of files
that changed on disk during a turn, the commands they ran and what came back,
test results, the idle agent's meanwhile bits, usage limits and completion.
The episode is built from this log afterwards, so it can be re-cut without
re-running the agents.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from ..conversation import AGENTS, parse_conversation
from ..kanban import moved_cards, new_asides, read_board
from ..theatre.cast import CHARACTER
from ..theatre.reactions import ActivityTracker, classify_entry
from ..theatre.screens import ProjectDiffer

EPISODE_DIR = Path(".workshop") / "episode"


def other_of(agent: str) -> str:
    return "Claude" if agent == "Codex" else "Codex"


class EventLog:
    """Append-only JSONL log with a monotonic session clock."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._start = time.monotonic()
        self._next_id = sum(1 for _ in self.path.open(encoding="utf-8")) if self.path.exists() else 0
        if self._next_id:
            last = read_events(self.path)[-1]
            self._start -= float(last.get("t", 0)) + 1.0  # continue the clock across restarts

    def add(self, kind: str, **data) -> int:
        event = {"id": self._next_id, "t": round(time.monotonic() - self._start, 2), "kind": kind, **data}
        self._next_id += 1
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event["id"]


def read_events(path: Path) -> list[dict]:
    events = []
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return events


class SessionCapture(QObject):
    """Listens to the orchestrator and records the session.

    ``side_bits``: an optional SideBits to drive (headless mode) — in the windowed
    app the Director drives them and we just record what they produce.
    """

    def __init__(self, orchestrator, side_bits=None, drive_bits: bool = False, scripted_bits: dict | None = None,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.o = orchestrator
        root = Path(orchestrator.project_dir)
        self.log = EventLog(root / EPISODE_DIR / "events.jsonl")
        self.differ = ProjectDiffer(root)
        self.trackers = {a: ActivityTracker() for a in AGENTS}
        self._agent: str | None = None
        self._turn_began = 0.0
        self._seen_entries = len(parse_conversation(orchestrator.conversation_text() or ""))
        self._board = read_board(root)
        self._board_text = None
        self._bits = side_bits
        self._drive_bits = drive_bits and side_bits is not None
        self._bits_this_turn = 0
        self._next_bit_at = float("inf")
        self._recent_kinds = {a: [] for a in AGENTS}
        self._rng = random.Random(7)
        self._scripted = scripted_bits  # demo only: {agent-turn index: bit}
        if side_bits is not None:
            side_bits.ready.connect(self._on_bit)
        self._poll = QTimer(self)
        self._poll.setInterval(1500)
        self._poll.timeout.connect(self._tick)
        o = orchestrator
        o.turn_started.connect(self._on_turn_started)
        o.turn_finished.connect(self._on_turn_finished)
        o.agent_output.connect(self._on_output)
        o.conversation_changed.connect(self._on_conversation)
        o.state_changed.connect(self._on_state)
        self.log.add("session", project=str(root), brief=self._brief())

    def _brief(self) -> str:
        turns = parse_conversation(self.o.conversation_text() or "")
        start = next((t for t in turns if t.speaker == "Human"), None)
        return start.content.strip()[:2000] if start else ""

    # -- turns -------------------------------------------------------------------------

    def _on_turn_started(self, agent: str, number: int) -> None:
        self._agent = agent
        self._turn_began = time.monotonic()
        self.trackers[agent].reset()
        try:
            self.differ.baseline()
        except OSError:
            pass
        self._poll_board(record=False)
        self._bits_this_turn = 0
        self._next_bit_at = self._turn_began + 20
        self.log.add("turn_start", agent=agent, turn=number)
        self._poll.start()
        if self._scripted:
            index = sum(1 for t in parse_conversation(self.o.conversation_text() or "") if t.speaker in AGENTS)
            bit = self._scripted.get(index)
            if bit:
                idle = other_of(agent)
                QTimer.singleShot(2500, lambda b=dict(bit), a=idle: self._on_bit(a, b))

    def _on_turn_finished(self, agent: str, exit_code: int) -> None:
        self._tick()
        self._poll.stop()
        self.log.add("turn_end", agent=agent, exit_code=exit_code,
                     seconds=round(time.monotonic() - self._turn_began, 1))
        self._agent = None

    def _tick(self) -> None:
        agent = self._agent
        if agent is None:
            return
        try:
            for change in self.differ.changes():
                self.log.add("diff", agent=agent, path=change.path, created=change.created, deleted=change.deleted,
                             lines=[list(pair) for pair in change.lines])
        except OSError:
            pass
        self._poll_board(record=True)
        self._maybe_request_bit()

    # -- output -------------------------------------------------------------------------

    def _on_output(self, agent: str, stream: str, text: str) -> None:
        if stream == "system":
            return
        for line in text.splitlines() or [text]:
            cue = self.trackers[agent].feed(line)
            if not cue:
                continue
            if cue.command:
                self.log.add("command", agent=agent, command=cue.command[:300], kind_of=cue.kind)
            if cue.tests_ok or cue.tests_failed:
                self.log.add("tests", agent=agent, passed=cue.tests_passed, failed=cue.tests_failed or 0,
                             ok=bool(cue.tests_ok), line=line.strip()[:200])
            elif cue.error:
                self.log.add("error_output", agent=agent, line=line.strip()[:200])

    # -- the board -----------------------------------------------------------------------

    def _poll_board(self, record: bool) -> None:
        path = Path(self.o.project_dir) / "KANBAN.md"
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return
        if text == self._board_text:
            return
        self._board_text = text
        board = read_board(self.o.project_dir)
        if board is None:
            return
        old, self._board = self._board, board
        if not record or self._agent is None:
            return
        names = {a: (a, CHARACTER[a]) for a in AGENTS}
        asides = [a for a in new_asides(old, board, names) if a.speaker == self._agent]
        moved = [c.title for c in moved_cards(old, board)]
        self.log.add("board", agent=self._agent, text=text[:6000], moved=moved)
        for aside in asides:
            self.log.add("aside", agent=aside.speaker, text=aside.text, card=aside.card)

    # -- meanwhile -------------------------------------------------------------------------

    def _maybe_request_bit(self) -> None:
        if not self._drive_bits or self._agent is None or self._bits_this_turn >= 3:
            return
        now = time.monotonic()
        if now < self._next_bit_at:
            return
        idle = other_of(self._agent)
        if self._bits.busy(idle):
            return
        context = f"- He is working on the shared project; this turn has run for {int(now - self._turn_began)}s."
        if self._board:
            doing = self._board.columns.get("Doing", [])
            if doing:
                context += "\n- Kanban, Doing: " + "; ".join(f"'{c.title}'" for c in doing[:3])
        if self._bits.request(idle, context, self._recent_kinds[idle]):
            self._bits_this_turn += 1
            self._next_bit_at = now + 75

    def _on_bit(self, agent: str, bit: dict) -> None:
        self._recent_kinds[agent] = (self._recent_kinds[agent] + [bit.get("kind", "")])[-4:]
        clean = {k: v for k, v in bit.items() if not k.startswith("_")}
        self.log.add("bit", agent=agent, worker=self._agent, bit=clean)

    # -- conversation & state ---------------------------------------------------------------

    def _on_conversation(self, text: str) -> None:
        turns = parse_conversation(text)
        for turn in turns[self._seen_entries:]:
            if turn.speaker in AGENTS:
                r = classify_entry(turn)
                self.log.add("entry", agent=turn.speaker, title=turn.title, content=turn.content[:12000],
                             moment=r.moment(), handoff=turn.handoff)
            else:
                self.log.add("human", title=turn.title, content=turn.content[:2000])
        self._seen_entries = max(self._seen_entries, len(turns))

    def _on_state(self, state: str) -> None:
        from .. import orchestrator as orch

        if state == orch.COMPLETE:
            self.log.add("complete")
        elif state == orch.USAGE_LIMIT and self.o.usage_limit:
            self.log.add("usage_limit", agent=self.o.usage_limit.agent)
        elif state == orch.WAITING_HUMAN:
            self.log.add("human_needed", detail=getattr(self.o.last_signal, "detail", ""))
