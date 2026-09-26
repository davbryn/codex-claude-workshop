"""The Director: turns orchestrator events into stage performances.

Inputs are only public/observable: conversation.md entries, CLI output lines,
process states and orchestrator states. The Director never influences
orchestration (the one exception is the clearly labelled --demo auto-reply,
which uses the ordinary Human Turn API).
"""

from __future__ import annotations

import random
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from .. import orchestrator as orch
from ..conversation import AGENTS, ConversationTurn, parse_conversation
from ..orchestrator import Orchestrator, other_agent
from .banter import petty_scoreboard
from .cast import COMPLETE_FOOTER, COMPLETE_TAGLINE, MOMENTS, SMALL_LABELS, character, status_label
from .reactions import ActivityTracker, EntryReaction, asks_for_review, classify_entry
from ..kanban import moved_cards, new_asides, read_board
from .screens import ProjectDiffer, ScreenFeed, _read_text
from .sfx import SoundEffects
from .speech import SpeechEngine
from .stats import RunStats, completion_lines, summarise_conversation
from .text import bubble_excerpt, clean_for_speech, speech_text, strip_markdown

READ_TARGET = re.compile(r"^(?:cat|type|Get-Content|gc|less|more|head|tail)\s+(?:-\w+\s+\S+\s+)*[\"']?([^\s\"';|]+)", re.I)

WORRY_RX = re.compile(r"\b(?:stop|argu\w*|fight\w*|focus|enough|please|wrong|why|seriously|guys|bicker\w*)\b", re.I)

# Generic labels (kept for reference/tests); the stage shows the per-character ones from cast.py.
LABELS = {
    "starting": "⏳ STARTING",
    "reading": "📖 READING",
    "reviewing": "🔍 REVIEWING",
    "coding": "⚙ CODING",
    "testing": "🧪 RUNNING TESTS",
    "planning": "📝 PLANNING",
    "writing": "✍ WRITING UP",
    "waiting": "☕ WAITING",
    "sleeping": "💤 NAPPING",
    "paused": "⏸ PAUSED",
    "error": "⚠ ERROR",
    "complete": "✓ COMPLETE",
    "stopped": "■ STOPPED",
    "human": "👀 WAITING FOR YOU",
    "speaking": "💬 SPEAKING",
    "limited": "💸 OUT OF USAGE",
}

from ..agents.demo_script import DEMO_HUMAN_REPLY  # noqa: E402  (re-exported for callers/tests)


@dataclass
class Performance:
    turn: ConversationTurn
    previous: ConversationTurn | None
    bubble: str
    speech: str | None
    reaction: EntryReaction | None
    quick: bool = False
    spoken: bool = False  # the speech engine accepted the line
    delivered: bool = False  # the bubble is up


class Director(QObject):
    stats_changed = Signal()

    def __init__(self, orchestrator: Orchestrator, stage, speech: SpeechEngine, sfx: SoundEffects,
                 rivalry: bool = True, speech_enabled: bool = True, demo_auto_reply: float | None = None,
                 sleep_after: float = 150.0, parent: QObject | None = None):
        super().__init__(parent)
        self.o = orchestrator
        self.stage = stage
        self.speech = speech
        self.sfx = sfx
        self.rivalry = rivalry
        self.speech_enabled = speech_enabled
        self.muted = False
        self.demo_auto_reply = demo_auto_reply
        self.sleep_after = sleep_after
        self.stats = RunStats()
        self.trackers = {a: ActivityTracker() for a in AGENTS}
        self.last_kind = {a: None for a in AGENTS}
        self.turn_failed = {a: False for a in AGENTS}
        self.review_turn = {a: False for a in AGENTS}
        self.orch_state = {a: orch.A_WAITING for a in AGENTS}
        self.waiting_since = {a: time.monotonic() for a in AGENTS}
        self.status_text = {a: "" for a in AGENTS}
        self.popcorn = False
        self.queue: deque[Performance] = deque()
        self.current: Performance | None = None
        self._seen = 0
        self._initialised = False
        self._last_sfx: dict[str, float] = {}
        self._last_react: dict[tuple[str, str], float] = {}
        self._countdown = 0
        self._idle_callbacks: list = []
        self._voice_live = False
        self.comic_timing = True  # short reaction beats before/after lines (never more than ~1s)
        self.scoreboard = petty_scoreboard([])
        self._last_moment = -99.0
        self._last_small = -99.0
        self._after_beat = 0
        stage.level_source = self._voice_level
        # what's on their monitors: real diffs, commands and files while working; the web when idle
        self.screens = {a: ScreenFeed(a) for a in AGENTS}
        self._screen_rng = random.Random(11)
        for feed in self.screens.values():
            feed.go_idle(self._screen_rng)
        stage.screens = self.screens
        self.differ = ProjectDiffer(orchestrator.project_dir)
        # camera cuts: the working agent's monitor fills the stage; the room is for dialogue and reactions
        self.camera_cuts = True
        self._room_hold_until = 0.0
        self._last_cut = 0.0
        self._turn_began = 0.0
        self._diff_agent: str | None = None
        # management's kanban board, and the asides the agents write on it (spoken while they work)
        self.kanban = True
        self._board = read_board(orchestrator.project_dir)
        self._board_text = None
        self._mutters: deque = deque(maxlen=4)
        self._muttering: str | None = None
        self._mutter_live = False

        self._end_timer = QTimer(self)
        self._end_timer.setSingleShot(True)
        self._end_timer.timeout.connect(self._end_performance)
        self._gap_timer = QTimer(self)
        self._gap_timer.setSingleShot(True)
        self._gap_timer.timeout.connect(self._next_performance)
        self._ambient = QTimer(self)
        self._ambient.timeout.connect(self._ambient_tick)
        self._ambient.start(1000)
        # while someone is coding, the keyboard is audible now and then
        self._typing = QTimer(self)
        self._typing.timeout.connect(self._typing_tick)
        self._typing.start(1700)
        self._typing_rng = random.Random(5)
        self._diff_timer = QTimer(self)
        self._diff_timer.setInterval(1200)
        self._diff_timer.timeout.connect(self._poll_diffs)
        self._demo_timer = QTimer(self)
        self._demo_timer.timeout.connect(self._demo_tick)

        o = orchestrator
        o.conversation_changed.connect(self.on_conversation)
        o.agent_state_changed.connect(self.on_agent_state)
        o.agent_output.connect(self.on_output)
        o.turn_started.connect(self.on_turn_started)
        o.turn_finished.connect(self.on_turn_finished)
        o.state_changed.connect(self.on_state)
        speech.finished.connect(self._on_speech_finished)
        speech.started.connect(self._on_speech_started)
        speech.progress.connect(lambda agent, chars: self.stage.speech_progress(agent, chars))

    # -- settings -------------------------------------------------------------

    def set_speech(self, speech: SpeechEngine) -> None:
        """Swap the speech engine (e.g. system voices → Kokoro) without restarting."""
        for signal, slot in ((self.speech.finished, self._on_speech_finished),
                             (self.speech.started, self._on_speech_started)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self.speech = speech
        speech.finished.connect(self._on_speech_finished)
        speech.started.connect(self._on_speech_started)
        speech.progress.connect(lambda agent, chars: self.stage.speech_progress(agent, chars))

    def set_muted(self, muted: bool) -> None:
        self.muted = muted
        if muted:
            self.speech.stop()

    def speaking_allowed(self) -> bool:
        return self.speech_enabled and not self.muted and self.speech.available()

    def shutdown(self) -> None:
        for timer in (self._end_timer, self._gap_timer, self._ambient, self._demo_timer, self._typing):
            timer.stop()
        self.speech.stop()
        self.stage.stop()

    # -- conversation → performances -------------------------------------------

    def on_conversation(self, text: str) -> None:
        turns = parse_conversation(text)
        for agent in AGENTS:
            self.stage.set_turns(agent, sum(1 for t in turns if t.speaker == agent))
        if not self._initialised:
            self._initialised = True
            self._seen = len(turns)
            self.scoreboard = petty_scoreboard(turns)
            for agent in AGENTS:
                mine = [t for t in turns if t.speaker == agent]
                if mine:
                    self.stage.show_speech(agent, bubble_excerpt(mine[-1].content) or "…", mode="instant")
                else:
                    self.stage.show_status(agent, "Waiting for the first turn")
            if turns and len(turns) == 1 and turns[0].speaker == "Human":
                self._enqueue(Performance(turns[0], None, "", None, None))
            self.stats_changed.emit()
            return
        if len(turns) < self._seen:
            self._seen = len(turns)
            return
        new = turns[self._seen:]
        start = self._seen
        self._seen = len(turns)
        for offset, turn in enumerate(new):
            previous = turns[start + offset - 1] if start + offset > 0 else None
            if turn.speaker == "Human":
                self._enqueue(Performance(turn, previous, "", None, None))
            else:
                reaction = classify_entry(turn)
                self.stats.record_entry(turn, handed_off=bool(turn.handoff), disagreement=reaction.disagreement)
                self._enqueue(Performance(turn, previous, bubble_excerpt(turn.content) or "…",
                                          speech_text(turn.content) or None, reaction))
        self.scoreboard = petty_scoreboard(turns)
        popcorn = self.stats.disagreement_streak >= 3
        if popcorn and not self.popcorn:
            self.stage.badge("🍿 THIS IS GETTING GOOD", "center", "#ffe08a", 3.2)
        self.popcorn = popcorn
        if self.stats.handoff_streak and self.stats.handoff_streak % 10 == 0:
            self.stage.badge(f"🔁 PAIR PROGRAMMING STREAK ×{self.stats.handoff_streak}", "center", "#8fb8ff", 3.4)
        self.stats_changed.emit()

    def _enqueue(self, perf: Performance) -> None:
        self.queue.append(perf)
        # Never let a backlog build up: older queued entries play quickly and silently.
        while len(self.queue) > 2:
            stale = self.queue.popleft()
            stale.quick, stale.speech = True, None
            self._play(stale, instant=True)
        if self.current is None and not self._gap_timer.isActive():
            self._next_performance()

    def _next_performance(self) -> None:
        # Human cards don't occupy the stage's "current" slot, so keep going
        # until an agent performance is playing (or the queue is empty).
        while self.current is None and self.queue and not self._gap_timer.isActive():
            self._play(self.queue.popleft())
        if self.current is None and not self.queue and not self._gap_timer.isActive():
            self._next_mutter()
        if self.presentation_idle():
            callbacks, self._idle_callbacks = self._idle_callbacks, []
            for callback in callbacks:
                callback()

    def presentation_idle(self) -> bool:
        """True when no entry is being performed or waiting to be (used as a launch gate)."""
        return (self.current is None and not self.queue and not self._gap_timer.isActive()
                and not self._muttering and not self._mutters)

    def _after_idle(self, callback) -> None:
        if self.presentation_idle():
            callback()
        else:
            self._idle_callbacks.append(callback)

    def _play(self, perf: Performance, instant: bool = False) -> None:
        turn = perf.turn
        if turn.speaker == "Human":
            self._play_human(perf, instant)
            return
        agent, other = turn.speaker, other_agent(turn.speaker)
        m, om = self.stage.models[agent], self.stage.models[other]
        r = perf.reaction
        if instant:
            self.stage.show_speech(agent, perf.bubble, mode="instant")
            primary = r.primary_state() if r else "idle"
            if primary != "idle":
                m.react(primary)
            return

        # silence any aside first: stopping the voice emits "finished", which must not end this new line.
        # Asides still waiting get their moment right after this line (a sardonic tag), not dropped.
        self._interrupt_mutter()
        self.current = perf
        self._to_room()
        if om.base == "sleeping":
            om.set_base("waiting")
            om.react("surprised", 1.4)
        moment = r.moment() if r else None
        # Comic timing: a short silent beat before the line for the big moments.
        preroll = 0
        if self.comic_timing and self.rivalry and moment in ("dinesh_catches", "gilfoyle_catches", "both_wrong"):
            if moment == "dinesh_catches":
                m.react("gloating", None)  # Dinesh grins first…
                QTimer.singleShot(450, lambda: om.react("sideeye", 3.0))  # …Gilfoyle slowly looks over
            elif moment == "gilfoyle_catches":
                m.react("smug", None)  # the tiniest smile
                QTimer.singleShot(350, lambda: om.react("outraged", 2.6))
            else:
                m.react("embarrassed", None)
                om.react("stare", 2.5)
            m.look_at_other(2.0)
            preroll = 900
        self.stage.set_status(agent, self.orch_state[agent], status_label(agent, "speaking"))
        # Start synthesising the voice now, so the beat above hides its start-up latency.
        # The mouth only starts moving once audio is actually playing.
        self._voice_live = False
        perf.spoken = bool(perf.speech) and self.speaking_allowed() and self.speech.speak(agent, perf.speech)
        if perf.spoken:
            self._end_timer.start(int((len(perf.speech) / 9 + 8) * 1000))  # safety net
        if preroll:
            QTimer.singleShot(preroll, lambda perf=perf: self._deliver(perf))
        else:
            self._deliver(perf)

    def _deliver(self, perf: Performance) -> None:
        """Start the spoken/typed line for the current performance."""
        if self.current is not perf:
            return
        agent, other = perf.turn.speaker, other_agent(perf.turn.speaker)
        m, om = self.stage.models[agent], self.stage.models[other]
        r = perf.reaction
        perf.delivered = True
        self.stage.show_speech(agent, perf.bubble, mode="speech" if perf.spoken else "typewriter")
        if not perf.spoken or self._voice_live:
            m.set_talking(True)  # otherwise _on_speech_started opens the mouth when the audio begins
        if r and r.mentions_other:
            m.look_at_other(2.0)
        primary = r.primary_state() if r else "idle"
        if primary in ("disagreeing", "embarrassed", "confused", "celebrating", "pleased", "smug", "gloating"):
            m.react(primary, None)
        listener = r.listener_state(self.rivalry) if r else None
        if om.reaction not in ("sideeye", "outraged", "stare"):
            om.look_at_other(3.5, speed=1.6 if om.deadpan else None)
            if listener:
                om.react(listener)
        self._effects_at_start(agent, other, r)
        if not perf.spoken:
            seconds = max(2.4, min(7.0, len(perf.bubble) / 17 + 1.4))
            self._end_timer.start(int(seconds * 1000))

    def _play_human(self, perf: Performance, instant: bool) -> None:
        turn = perf.turn
        start = turn.title.lower() == "project start"
        body = strip_markdown(turn.content)
        body = " ".join(line for line in body.splitlines() if not line.strip().startswith("_20")).strip()
        if len(body) > 220:
            body = body[:219].rsplit(" ", 1)[0] + "…"
        footer = f"➜ over to {character(turn.handoff)} ({turn.handoff})" if turn.handoff else ""
        title = "📋 THE BRIEF (FROM MANAGEMENT)" if start else "👤 THE BOSS WALKS IN"
        if instant:
            return
        self._to_room()
        self.stage.show_card("human", title, [body], "#7bd88f", duration=5.5, footer=footer)
        stern = bool(WORRY_RX.search(body))
        for agent in AGENTS:
            m = self.stage.models[agent]
            if m.base == "sleeping":
                m.set_base("waiting")
            m.look_at_human(4.5)
            if start:
                continue
            # They both stop and look up. Dinesh worries; Gilfoyle is unimpressed.
            if m.deadpan:
                m.react("stare", 3.0)
            else:
                m.react("worried" if stern else "surprised", 3.0 if stern else 1.4)
        self._sfx("human")
        if start and self.kanban and self._board is not None:
            QTimer.singleShot(5900, self._show_kanban_arrival)
        if not start:
            # everyone stops for a moment; the next line (and the next launch) waits for it
            self._gap_timer.start(2600)

    def _show_kanban_arrival(self) -> None:
        """Management (Jared) has set up a kanban board. The characters' opinions follow, in their own words."""
        board = self._board
        todo = len(board.columns.get("To do", [])) if board else 0
        self.stage.show_card("human", "📌 MANAGEMENT HAS SET UP A KANBAN BOARD",
                             ["KANBAN.md  ·  To do / Doing / Done / Asides", f"{todo} card{'s' if todo != 1 else ''} waiting",
                              "“Please keep it current!” — Jared"], "#7bd88f", duration=5.0,
                             footer="Asides on the board are read aloud while they work")
        for agent in AGENTS:
            m = self.stage.models[agent]
            m.look_at_human(4.0)
            m.react("stare" if m.deadpan else "worried", 3.5)
        self._sfx("human")

    def _effects_at_start(self, agent: str, other: str, r: EntryReaction | None) -> None:
        if r is None:
            return
        now = time.monotonic()
        moment = r.moment() if self.rivalry else ("disagreement" if r.disagreement else None)
        # Big captions are rare: at most one every ~12s (disagreements are the most common, so they wait longest).
        cooldown = 25.0 if moment == "disagreement" else 12.0
        if moment and now - self._last_moment >= cooldown:
            self._last_moment = now
            text, colour = MOMENTS[moment]
            self.stage.badge(text, "center", colour, 3.4)
            sound = {"dinesh_catches": "yes", "gilfoyle_catches": "blast", "concession": "wahwah",
                     "own_goal": "wahwah", "disagreement": "zap", "both_wrong": "oops",
                     "character_development": "chime", "same_solution": "oops"}.get(moment)
            if sound:
                self._sfx(sound)
            if moment == "disagreement" and self.rivalry:
                self.stage.lightning(1.4)
                self.stage.shake(4)
        elif self.rivalry and now - self._last_small >= 20.0 and now - self._last_moment >= 6.0:
            # an occasional small label beside a head
            for who, state in ((agent, r.primary_state()), (other, r.listener_state(True) or "")):
                label = SMALL_LABELS.get((who, state))
                if label:
                    self._last_small = now
                    self.stage.badge(label, who, "#d9d2c3", 2.4)
                    break
        if r.fixed_other_bug and self.rivalry and moment not in ("dinesh_catches", "gilfoyle_catches"):
            self.stage.badge("GOOD CATCH", agent, "#7bd88f", 2.8)
            self._sfx("pop")
        if r.proposes_completion:
            self.stage.badge("PROPOSES: PROJECT COMPLETE", "center", "#8fd9ff", 3.2)
        # Dinesh celebrating too much → Gilfoyle simply stares at him.
        if agent == "Claude" and r.primary_state() in ("celebrating", "gloating") and self.rivalry:
            QTimer.singleShot(700, lambda: self.stage.models["Codex"].react("stare", 3.0))

    def _voice_level(self, agent: str) -> float | None:
        """Live loudness for the talking character (None → synthetic mouth)."""
        if self._voice_live and self.current and self.current.turn.speaker == agent:
            return self.speech.level()
        if self._mutter_live and self._muttering == agent:
            return self.speech.level()
        return None

    def _on_speech_started(self, agent: str) -> None:
        if self._muttering == agent and self.current is None:
            self._mutter_live = True
            self.stage.models[agent].set_talking(True)
            return
        if self.current and self.current.turn.speaker == agent:
            self._voice_live = True
            if self.current.delivered:  # the line is on screen: open the mouth with the audio
                self.stage.models[agent].set_talking(True)

    def _on_speech_finished(self, agent: str) -> None:
        if self._muttering == agent and self.current is None:
            self._end_mutter()
            return
        self._voice_live = False
        if self.current and self.current.turn.speaker == agent:
            self._end_performance()

    def _end_performance(self) -> None:
        self._end_timer.stop()
        self._voice_live = False
        perf, self.current = self.current, None
        if perf is None:
            return
        turn = perf.turn
        if turn.speaker in AGENTS:
            agent, other = turn.speaker, other_agent(turn.speaker)
            m = self.stage.models[agent]
            m.set_talking(False)
            self.stage.finish_speech_reveal(agent)
            r = perf.reaction
            primary = r.primary_state() if r else "idle"
            if m.reaction is not None and m.reaction_until is None:
                m.release()
            elif primary not in ("idle", "waiting"):
                m.react(primary)
            if primary == "celebrating" and not (r and r.declares_complete):
                self.stage.burst(agent)
            beat = 350
            if turn.handoff:
                # lob a crumpled sticky note across the room; the other one catches it
                m.gesture("point", 0.9)
                m.look_at_other(2.5)
                self.stage.handoff(agent, turn.handoff)
                self._sfx("handoff")
                receiver = self.stage.models[turn.handoff]
                jabbed = bool(r and (r.jab or r.caught_other_bug or r.disagreement)) and self.rivalry
                if jabbed and self.comic_timing:
                    # insult → small pause → the target turns and glowers → then his turn starts
                    reply = "sideeye" if receiver.deadpan else "glare"
                    QTimer.singleShot(250, lambda rv=receiver, s=reply: rv.react(s, 2.2))
                    beat = 950
                else:
                    receiver.look_at_other(2.0)
                QTimer.singleShot(720, lambda rv=receiver: (rv.gesture("catch", 0.7),
                                                            rv.hop(0.2, anticipation=False), rv.nudge_wobble(60)))
            self._restore_label(agent)
            self._apply_status(agent)
            self._gap_timer.start(beat)
            return
        self._gap_timer.start(350)

    # -- process / output --------------------------------------------------------

    def on_turn_started(self, agent: str, number: int) -> None:
        self.stage.set_active(agent)
        self.stage.on_air = True
        self.trackers[agent].reset()
        self.last_kind[agent] = None
        self.turn_failed[agent] = False
        turns = parse_conversation(self.o.conversation_text())
        self.review_turn[agent] = asks_for_review(turns[-1] if turns else None)
        other = other_agent(agent)
        self.stage.models[other].look_at_other(2.5)
        self.stage.set_activity(agent, "")
        self._diff_agent = agent
        try:
            self.differ.baseline()  # anything that changes from here on is this agent's doing
            self._poll_board(speak=False)  # edits made between turns aren't his to voice
        except OSError:
            pass
        self._diff_timer.start(max(1200, int(self.differ.last_scan_seconds * 8000)))
        feed = self.screens[agent]
        feed.command("# reading conversation.md")
        feed.narrate()  # the CLI echoes its prompt first: only real commands' output goes on screen
        self._turn_began = time.monotonic()
        self.stats_changed.emit()

    def on_turn_finished(self, agent: str, exit_code: int) -> None:
        self._poll_diffs()  # catch the last edits of the turn
        self._diff_timer.stop()
        self._diff_agent = None
        self._to_room()
        self.stage.set_active(None)
        self.stage.set_activity(agent, "")
        self.stage.on_air = self.o.is_busy()
        self.stats_changed.emit()

    def on_agent_state(self, agent: str, state: str) -> None:
        self.orch_state[agent] = state
        m = self.stage.models[agent]
        if state == orch.A_STARTING:
            m.set_base("thinking")
            self._set_status(agent, "Working…")
        elif state == orch.A_READING:
            m.set_base("reviewing" if self.review_turn[agent] else "reading")
        elif state == orch.A_WORKING:
            m.set_base(self._base_for_kind(agent, self.last_kind[agent] or "command"))
        elif state == orch.A_HANDING_OFF:
            m.set_base("coding")
        elif state == orch.A_WAITING:
            m.set_base("waiting")
            self.waiting_since[agent] = time.monotonic()
            if m.reaction == "error":
                m.clear_reaction()
            self._set_status(agent, f"Waiting for {other_agent(agent)}" if self.o.is_busy() else "Waiting")
        elif state == orch.A_PAUSED:
            m.set_base("idle")
        elif state == orch.A_ERROR:
            m.set_base("error")
            m.react("error")
            if not m.deadpan:
                self.stage.shake(4)
            self._sfx("buzz")
            self.stats.record_error()
            self.stage.badge("⚠ ERROR" if not m.deadpan else "⚠ ERROR. HE SEEMS FINE.", agent, "#ff8a80", 2.6)
            # the other one notices
            om = self.stage.models[other_agent(agent)]
            if self.rivalry and not om.talking:
                om.react("sideeye" if om.deadpan else "gloating", 2.4)
        elif state == orch.A_COMPLETE:
            m.set_base("complete")
        elif state == orch.A_LIMITED:
            m.set_base("sleeping")  # not a crash: he has simply run out
            om = self.stage.models[other_agent(agent)]
            if self.rivalry:
                om.react("stare" if om.deadpan else "gloating", 3.0)
        elif state == orch.A_STOPPED:
            m.set_base("idle")
        self._restore_label(agent)
        self.stats_changed.emit()

    def _base_for_kind(self, agent: str, kind: str | None) -> str:
        if kind == "read":
            return "reviewing" if self.review_turn[agent] else "reading"
        if kind == "plan":
            return "thinking"
        return "coding"

    def _restore_label(self, agent: str) -> None:
        state = self.orch_state[agent]
        labels = {key: status_label(agent, key) for key in LABELS}
        if self.current and self.current.turn.speaker == agent:
            label = labels["speaking"]
        elif self.o.state == orch.WAITING_HUMAN and not self.o.is_busy():
            label = labels["human"]
        elif state == orch.A_STARTING:
            label = labels["starting"]
        elif state in (orch.A_READING, orch.A_WORKING):
            kind = self.last_kind[agent]
            if kind == "test":
                label = labels["testing"]
            elif kind == "plan":
                label = labels["planning"]
            elif kind == "read" or (kind is None and state == orch.A_READING):
                label = labels["reviewing" if self.review_turn[agent] else "reading"]
            else:
                label = labels["coding"]
        elif state == orch.A_HANDING_OFF:
            label = labels["writing"]
        elif state == orch.A_WAITING:
            label = labels["sleeping"] if self.stage.models[agent].base == "sleeping" else labels["waiting"]
        else:
            label = {orch.A_PAUSED: labels["paused"], orch.A_ERROR: labels["error"],
                     orch.A_COMPLETE: labels["complete"], orch.A_STOPPED: labels["stopped"],
                     orch.A_LIMITED: labels["limited"]}.get(state, state)
        self.stage.set_status(agent, state, label)

    def _set_status(self, agent: str, text: str) -> None:
        self.status_text[agent] = text
        self._apply_status(agent)

    def _apply_status(self, agent: str) -> None:
        """Show the status pill unless this agent's speech is still being performed."""
        busy_speaking = (self.current and self.current.turn.speaker == agent) or any(
            p.turn.speaker == agent for p in self.queue)
        if busy_speaking:
            return
        if self.o.current_agent == agent and self.status_text[agent]:
            self.stage.show_status(agent, self.status_text[agent])

    def on_output(self, agent: str, stream: str, text: str) -> None:
        if stream == "system":
            return
        for line in text.splitlines() or [text]:
            self._on_output_line(agent, line)

    # -- the kanban board and its asides ------------------------------------------------

    def _poll_board(self, speak: bool = True) -> None:
        if not self.kanban:
            return
        path = self.o.project_dir / "KANBAN.md"
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
        agent = self._diff_agent
        if agent is None or not speak:
            return
        names = {a: (a, character(a)) for a in AGENTS}
        # only the agent whose turn it is can be editing the board: never voice lines "for" the other one
        asides = [a for a in new_asides(old, board, names) if a.speaker == agent]
        moved = [c.title for c in moved_cards(old, board)]
        if moved or asides:
            self.screens[agent].show_board(board, tuple(moved) + tuple(a.card for a in asides if a.card))
        for aside in asides[-3:]:
            self._mutters.append(aside)
        self._next_mutter()

    def _next_mutter(self) -> None:
        if self._muttering or not self._mutters or self.current is not None or self.queue:
            return
        aside = self._mutters.popleft()
        agent = aside.speaker
        self._muttering = agent
        text = aside.text
        if self.stage.shot_agent == agent:
            self.stage.set_caption(agent, text)
        else:
            self.stage.show_speech(agent, f"“{text}”", mode="typewriter")
        m = self.stage.models[agent]
        m.look_at_other(2.0) if self.rivalry and re.search(r"(?i)gilfoyle|dinesh|codex|claude", text) else None
        spoken = self.speaking_allowed() and self.speech.speak(agent, clean_for_speech(text))
        if not spoken:  # silent: animate the line for a reading-length beat
            m.set_talking(True)
            QTimer.singleShot(int(max(1.8, min(6.0, len(text) / 15)) * 1000), self._end_mutter)

    def _end_mutter(self) -> None:
        agent, self._muttering = self._muttering, None
        self._mutter_live = False
        if agent and self.current is None:
            self.stage.models[agent].set_talking(False)
        QTimer.singleShot(1500, lambda: self.stage.set_caption(None, ""))
        QTimer.singleShot(700, self._next_performance)  # more asides, or let the next agent start

    def _interrupt_mutter(self) -> None:
        while len(self._mutters) > 2:
            self._mutters.popleft()
        if self._muttering:
            agent = self._muttering
            self._muttering = None
            self._mutter_live = False
            self.speech.stop()
            self.stage.models[agent].set_talking(False)
        self.stage.set_caption(None, "")

    def _stop_mutter(self) -> None:
        self._mutters.clear()
        if self._muttering:
            agent = self._muttering
            self._muttering = None
            self._mutter_live = False
            self.speech.stop()
            self.stage.models[agent].set_talking(False)
        self.stage.set_caption(None, "")

    def _poll_diffs(self) -> None:
        self._poll_board()
        agent = self._diff_agent
        if agent is None:
            return
        try:
            changes = self.differ.changes()
        except OSError:
            return
        for change in changes[-6:]:
            self.screens[agent].show_diff(change)

    def _show_file(self, agent: str, path: str) -> None:
        """Put the file an agent is reading on its monitor (only files inside the project)."""
        root = self.o.project_dir.resolve()
        try:
            target = Path(path.strip().strip("\"'"))
            target = (target if target.is_absolute() else root / target).resolve()
            target.relative_to(root)
        except (ValueError, OSError):
            return
        lines = _read_text(target) if target.is_file() else None
        if lines:
            self.screens[agent].read(target.relative_to(root).as_posix(), lines[:400])

    def _feed_screen(self, agent: str, line: str, cue) -> None:
        feed = self.screens[agent]
        stripped = line.strip()
        if stripped in ("codex", "thinking") or (agent == "Claude" and stripped and not stripped.startswith("[")):
            feed.narrate()  # back to talking to itself, not command output
        if cue and cue.command:
            feed.command(cue.command)
            if cue.kind == "read":
                m = READ_TARGET.search(cue.command)
                if m:
                    self._show_file(agent, m.group(1))
        elif cue and cue.kind == "read" and cue.path:
            self._show_file(agent, cue.path)
        elif cue and cue.kind == "edit":
            QTimer.singleShot(250, self._poll_diffs)
        elif stripped and not stripped.startswith("[tool] "):
            feed.output(re.sub(r"^\[tool (?:result|error)\]\s*", "", stripped))

    def _on_output_line(self, agent: str, line: str) -> None:
        cue = self.trackers[agent].feed(line)
        self._feed_screen(agent, line, cue)
        self._update_shot()
        if not cue:
            return
        m = self.stage.models[agent]
        if cue.activity:
            self.last_kind[agent] = cue.kind
            self.stage.set_activity(agent, cue.activity)
            if self.orch_state[agent] in (orch.A_READING, orch.A_WORKING, orch.A_STARTING):
                m.set_base(self._base_for_kind(agent, cue.kind))
                self._set_status(agent, cue.activity)
            self._restore_label(agent)
            # working sounds: you can hear them work (never over someone speaking)
            if not any(mm.talking for mm in self.stage.models.values()):
                if cue.kind == "edit":
                    self._sfx("keys", 0.5)
                elif cue.kind == "test":
                    self._sfx("whir", 3.0)
                elif cue.kind in ("command", "read"):
                    self._sfx("tick", 0.8)
            if cue.kind == "edit":
                self.stats_changed.emit()
        if cue.tests_ok:
            self._to_room(3.0)  # cut to the room for the reaction
            self.stats.record_tests(cue.tests_passed, cue.tests_failed, True)
            count = f"{cue.tests_passed} " if cue.tests_passed else ""
            if self.turn_failed[agent]:
                self._react_once(agent, "surprised", 1.8)
                self.stage.badge(f"😮 {count}TESTS PASS NOW", agent, "#7dffc4", 3.0)
            else:
                self._react_once(agent, "pleased", 2.4)
                self.stage.badge(f"✓ {count}PASSED".replace("  ", " "), agent, "#7dffc4", 2.6)
            self.stage.burst(agent, 14)
            self._sfx("chime", 2.5)
            self.turn_failed[agent] = False
            self.stats_changed.emit()
        elif cue.tests_failed:
            self._to_room(3.0)  # cut to the room for the reaction
            self.stats.record_tests(cue.tests_passed, cue.tests_failed, False)
            self.turn_failed[agent] = True
            self._react_once(agent, "error", 2.2)
            self.stage.badge(f"✗ {cue.tests_failed} FAILED", agent, "#ff8a80", 2.6)
            self._sfx("oops", 2.5)
            if self.rivalry:  # the other one is watching
                om = self.stage.models[other_agent(agent)]
                self._react_once(om.agent, "sideeye" if om.deadpan else "smug", 2.4, cooldown=8.0)
            self.stats_changed.emit()
        elif cue.error:
            self._to_room(3.0)
            self._react_once(agent, "confused", 2.0, cooldown=6.0)

    def _react_once(self, agent: str, state: str, seconds: float, cooldown: float = 1.5) -> None:
        key = (agent, state)
        now = time.monotonic()
        if now - self._last_react.get(key, -99) < cooldown:
            return
        self._last_react[key] = now
        m = self.stage.models[agent]
        if not m.talking:
            m.react(state, seconds)

    # -- orchestrator states ---------------------------------------------------

    def on_state(self, state: str) -> None:
        stage = self.stage
        stage.paused = state in (orch.PAUSED,)
        if state != orch.USAGE_LIMIT:
            stage.hide_card("limit")
        if state != orch.WAITING_HUMAN:
            stage.hide_card("waiting")
            self._demo_timer.stop()
        if state == orch.RUNNING:
            stage.on_air = True
        elif state in (orch.STOPPED, orch.NEEDS_ATTENTION, orch.PAUSED, orch.COMPLETE):
            stage.on_air = self.o.is_busy()
        if state == orch.WAITING_HUMAN:
            self._after_idle(self._show_waiting)
        elif state == orch.USAGE_LIMIT:
            self._after_idle(self._show_limit)
        elif state == orch.COMPLETE:
            self._after_idle(self._celebrate)
        elif state in (orch.RUNNING, orch.PAUSED):
            for agent in AGENTS:
                stage.models[agent]._look_until = 0
        self.stats_changed.emit()

    def _show_waiting(self) -> None:
        if self.o.state != orch.WAITING_HUMAN:
            return
        stage = self.stage
        signal = self.o.last_signal
        question = signal.detail if signal else ""
        question = question.split(":", 1)[-1].strip() or question
        self._to_room()
        stage.show_card("waiting", "👀 THEY NEED A GROWN-UP", [question or "A human decision is needed."],
                        "#f5c542", footer="Answer with the Human Turn button")
        for agent in AGENTS:
            m = stage.models[agent]
            m.set_base("waiting")
            m.look_at_human(9999)
            m.react("stare" if m.deadpan else "worried", 2.5)
            self._restore_label(agent)
        self._sfx("alert")
        if self.demo_auto_reply:
            self._countdown = int(self.demo_auto_reply)
            self._demo_tick()
            self._demo_timer.start(1000)

    def _celebrate(self) -> None:
        if self.o.state != orch.COMPLETE:
            return
        stage = self.stage
        gil, din = stage.models["Codex"], stage.models["Claude"]
        for m in (gil, din):
            m.set_base("complete")
        # Dinesh celebrates like they landed on Mars…
        din.react("celebrating", 3.0)
        din.look_at_other(6.0)
        stage.confetti(110, only="Claude")
        stage.burst("Claude", 22)
        # …then goes for the high five. Gilfoyle eventually, barely, reciprocates.
        QTimer.singleShot(3000, lambda: din.react("highfive", 2.6))
        gil.react("pleased", 3.0)
        QTimer.singleShot(4300, lambda: (gil.look_at_other(2.0, speed=1.4), gil.react("highfive", 1.6)))
        QTimer.singleShot(6200, lambda: gil.react("smug", 3.0))
        self._sfx("yes")
        QTimer.singleShot(500, lambda: self._sfx("fanfare"))
        turns = parse_conversation(self.o.conversation_text())
        summary = summarise_conversation(turns)
        lines = completion_lines(summary, self.stats)
        board = petty_scoreboard(turns)
        lines.append("Bugs caught: " + " · ".join(f"{character(a)} {board[a].bugs_caught}" for a in AGENTS))
        self._to_room()
        stage.show_card("complete", "PROJECT COMPLETE", lines, "#f2c94c", footer=COMPLETE_FOOTER,
                        tagline=COMPLETE_TAGLINE)

    def _demo_tick(self) -> None:
        if self.o.state != orch.WAITING_HUMAN or self.o.is_busy():
            self._demo_timer.stop()
            return
        if self._countdown <= 0:
            self._demo_timer.stop()
            self.o.submit_human_turn(DEMO_HUMAN_REPLY, "Claude", title="Demo auto-reply")
            return
        self.stage.update_card_footer("waiting", f"Demo: the human answers automatically in {self._countdown}s "
                                                 "(or use Human Turn)")
        self._countdown -= 1

    def _typing_tick(self) -> None:
        agent = self.o.current_agent if self.o.is_busy() else None
        if agent is None or any(m.talking for m in self.stage.models.values()):
            return
        if self.stage.models[agent].base == "coding" and self._typing_rng.random() < 0.65:
            self._sfx("keys", 0.5)

    def _show_limit(self) -> None:
        limit = self.o.usage_limit
        if self.o.state != orch.USAGE_LIMIT or limit is None:
            return
        who = character(limit.agent)
        auto = self.o.limit_seconds_left() is not None
        lines = [f"{who} ({limit.agent}) hit his usage limit. Nothing crashed; the workshop is paused.",
                 f"It resets at {limit.reset_text()}." if limit.reset_at else "The CLI didn't say when it resets."]
        self._to_room()
        self.stage.show_card("limit", f"💸 {who.upper()} IS OUT OF USAGE", lines, "#f2c14e",
                             footer=self._limit_footer() if auto else "Press Resume once it has reset")
        self._sfx("wahwah")

    def _limit_footer(self) -> str:
        left = self.o.limit_seconds_left()
        if left is None:
            return "Press Resume once it has reset"
        h, rem = divmod(int(left), 3600)
        m, s = divmod(rem, 60)
        return f"Auto-resume in {h}:{m:02d}:{s:02d}  (or press Resume)"

    # -- camera ----------------------------------------------------------------------

    def _to_room(self, hold: float = 0.0) -> None:
        """Cut back to the room now (and stay there for ``hold`` seconds)."""
        if self.stage.shot_agent is not None:
            self._last_cut = time.monotonic()
        self.stage.set_shot(None)
        self._room_hold_until = max(self._room_hold_until, time.monotonic() + hold)

    def _update_shot(self) -> None:
        now = time.monotonic()
        agent = self.o.current_agent if self.o.is_busy() else None
        feed = self.screens.get(agent) if agent else None
        want = None
        if (self.camera_cuts and feed is not None and feed.mode in ("editor", "terminal", "reader")
                and self.current is None and not self.queue and not self._gap_timer.isActive()
                and not self.stage.cards and now >= self._room_hold_until
                and now - self._turn_began > 1.5):
            want = agent
        if want == self.stage.shot_agent:
            return
        if want is not None and now - self._last_cut < 2.5:
            return  # don't flicker between shots
        self._last_cut = now
        self.stage.set_shot(want)

    def _ambient_tick(self) -> None:
        self._update_shot()
        now_m = time.monotonic()
        for agent, feed in self.screens.items():
            working = self.o.is_busy() and self.o.current_agent == agent
            if feed.mode != "idle" and not working and now_m - feed.last_activity > 8:
                feed.go_idle(self._screen_rng)  # back to browsing
            elif feed.mode == "idle" and now_m - feed.page_since > 11:
                feed.go_idle(self._screen_rng)
        if self.o.state == orch.USAGE_LIMIT and "limit" in self.stage.cards:
            self.stage.update_card_footer("limit", self._limit_footer())
        now = time.monotonic()
        busy = self.o.is_busy()
        for agent in AGENTS:
            m = self.stage.models[agent]
            if (busy and self.o.current_agent != agent and self.orch_state[agent] == orch.A_WAITING
                    and m.base == "waiting" and now - self.waiting_since[agent] > self.sleep_after
                    and not m.talking and self.o.state != orch.WAITING_HUMAN):
                m.set_base("sleeping")
                self._restore_label(agent)
        self.stats_changed.emit()

    def _sfx(self, name: str, cooldown: float = 0.4) -> None:
        now = time.monotonic()
        if now - self._last_sfx.get(name, -99) < cooldown:
            return
        self._last_sfx[name] = now
        self.sfx.play(name)

    # -- status strip data ---------------------------------------------------------

    def files_edited(self) -> int | None:
        agent = self.o.current_agent
        if agent is None:
            return None
        count = len(self.trackers[agent].files_edited)
        return count or None
