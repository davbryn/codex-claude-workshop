"""The referee.

The orchestrator is the only thing that decides when an agent runs. Agents
never poll the conversation themselves. After every agent process exits,
conversation.md is re-read and the latest entry decides what happens next.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from .agents.base import AgentAdapter, AgentProcess, AgentUnavailable
from .conversation import (
    AGENTS,
    ControlSignal,
    append_human_turn,
    completion_was_reviewed,
    detect_disagreement,
    next_turn_number,
    parse_conversation,
    get_control_signal,
    read_conversation,
    validate_append,
)
from .limits import UsageLimit, detect_usage_limit
from .project import CONVERSATION_FILE, PROTOCOL_FILE
from .prompts import build_prompt

# Overall orchestrator states
IDLE = "idle"
RUNNING = "running"
PAUSING = "pausing"  # pause requested; current turn still finishing
PAUSED = "paused"
WAITING_HUMAN = "waiting_human"
NEEDS_ATTENTION = "needs_attention"  # error / malformed conversation
COMPLETE = "complete"
USAGE_LIMIT = "usage_limit"  # an agent ran out of usage; paused until it resets
STOPPED = "stopped"

# Per-agent display states
A_WAITING = "WAITING"
A_STARTING = "STARTING"
A_READING = "READING"
A_WORKING = "WORKING"
A_HANDING_OFF = "HANDING OFF"
A_ERROR = "ERROR"
A_PAUSED = "PAUSED"
A_COMPLETE = "COMPLETE"
A_STOPPED = "STOPPED"
A_LIMITED = "OUT OF USAGE"


def other_agent(agent: str) -> str:
    return "Claude" if agent == "Codex" else "Codex"


class Orchestrator(QObject):
    state_changed = Signal(str)
    agent_state_changed = Signal(str, str)  # agent, state
    conversation_changed = Signal(str)  # full text
    agent_output = Signal(str, str, str)  # agent, stream, text
    message = Signal(str, str)  # level (info/warning/error), text
    turn_started = Signal(str, int)
    turn_finished = Signal(str, int)  # agent, exit code
    disagreement = Signal(str)  # agent whose latest entry sounds argumentative

    def __init__(
        self,
        project_dir: Path,
        adapters: dict[str, AgentAdapter],
        personalities: dict[str, str] | None = None,
        protocol_file: str = PROTOCOL_FILE,
        poll_ms: int = 700,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        # resolve() expands Windows 8.3 short names (C:\Users\ABCDEF~1), which
        # agents' permission checks may not match against their working directory.
        self.project_dir = Path(project_dir).resolve()
        self.conversation_path = self.project_dir / CONVERSATION_FILE
        self.adapters = adapters
        self.personalities = personalities or {}
        self.protocol_file = protocol_file

        self.state = IDLE
        self.paused = False
        self.stopped = False
        self.current_agent: str | None = None
        self.running_process: AgentProcess | None = None
        self.turn_number = 0  # total agent turns launched this session
        self.usage_limit: UsageLimit | None = None
        self._auto_resumed = False  # one automatic retry per usage-limit episode
        self._turn_log: list[str] = []
        self._limit_timer = QTimer(self)
        self._limit_timer.setSingleShot(True)
        self._limit_timer.timeout.connect(self._auto_resume_after_limit)
        self.turn_started_at: float | None = None
        self.last_signal: ControlSignal | None = None
        self.last_error: str = ""
        self.agent_states = {a: A_WAITING for a in AGENTS}
        self._last_text = ""
        # Optional pacing hook (e.g. "let the presentation finish speaking").
        # It can only *delay* a launch, never skip or reorder one, and gives up
        # after launch_gate_max seconds so it can never stall the workshop.
        self.launch_gate: Callable[[], bool] | None = None
        # Optional character direction for each prompt (agent, conversation text) -> str. Presentation only.
        self.prompt_theatre: Callable[[str, str], str] | None = None
        self.launch_gate_max = 25.0
        self._gate_timer = QTimer(self)
        self._gate_timer.setSingleShot(True)
        self._gate_timer.timeout.connect(self._retry_gated_launch)
        self._gate_waited = 0.0

        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(lambda _p: self._check_file())
        self._poll = QTimer(self)
        self._poll.setInterval(poll_ms)
        self._poll.timeout.connect(self._check_file)

    # -- public API ---------------------------------------------------------

    def start(self) -> None:
        self.paused = False
        self.stopped = False
        if self.conversation_path.exists():
            self._watcher.addPath(str(self.conversation_path))
        self._poll.start()
        self._check_file(force=True)
        self._advance()

    def pause(self) -> None:
        self._limit_timer.stop()
        self.paused = True
        if self.is_busy():
            self._set_state(PAUSING)
            self.message.emit("info", "Pausing after the current turn finishes.")
        elif self.state not in (COMPLETE, STOPPED):
            self._set_state(PAUSED)
            self._mark_idle_agents(A_PAUSED)

    def resume(self) -> None:
        self._limit_timer.stop()
        self.usage_limit = None
        self.paused = False
        self.stopped = False
        if self.is_busy():
            self._set_state(RUNNING)
            return
        self._advance()

    def stop(self) -> None:
        self._gate_timer.stop()
        self._limit_timer.stop()
        self.stopped = True
        self.paused = False
        if self.running_process is not None:
            self.message.emit("warning", f"Stopping {self.current_agent}: terminating its process.")
            self.running_process.kill()
        self._set_state(STOPPED)
        self._mark_idle_agents(A_STOPPED)

    def submit_human_turn(self, message: str, next_agent: str, resume: bool = True, title: str = "Intervention") -> None:
        if self.is_busy():
            raise RuntimeError("Cannot add a human turn while an agent is running. Pause first.")
        append_human_turn(self.conversation_path, message, next_agent, title)
        self._check_file(force=True)
        if resume:
            self.resume()
        else:
            self.paused = True
            self._set_state(PAUSED)
            self._mark_idle_agents(A_PAUSED)

    def is_busy(self) -> bool:
        return self.running_process is not None

    def shutdown(self) -> None:
        self._poll.stop()
        if self.running_process is not None:
            self.stopped = True
            self.running_process.kill()

    def conversation_text(self) -> str:
        return self._last_text

    # -- core loop ----------------------------------------------------------

    def _advance(self) -> None:
        if self.is_busy() or self.stopped or self._gate_timer.isActive():
            return
        text = self._check_file(force=True)
        signal = get_control_signal(text)
        self.last_signal = signal

        if signal.kind == "handoff":
            if self.paused:
                self._set_state(PAUSED)
                self._mark_idle_agents(A_PAUSED)
            elif self.launch_gate and self._gate_waited < self.launch_gate_max and not self.launch_gate():
                self._gate_timer.start(250)
            else:
                self._gate_waited = 0.0
                self._launch(signal.agent)
            return

        if signal.kind == "complete":
            turns = parse_conversation(text)
            if completion_was_reviewed(turns):
                for agent in AGENTS:
                    self._set_agent_state(agent, A_COMPLETE)
                self._set_state(COMPLETE)
            else:
                self._needs_attention(
                    f"{signal.speaker} declared PROJECT COMPLETE without the other agent reviewing a "
                    "completion proposal. Use Human Turn to decide what happens next."
                )
            return

        if signal.kind == "human":
            self._set_state(WAITING_HUMAN)
            self._mark_idle_agents(A_WAITING)
            self.message.emit("warning", f"⚠ HUMAN INPUT REQUIRED — {signal.detail}")
            return

        # missing / invalid / malformed / empty: never guess who goes next.
        if signal.speaker in AGENTS:
            self._set_agent_state(signal.speaker, A_ERROR)
        if signal.kind == "missing" and signal.speaker in AGENTS:
            text = f"{signal.speaker} completed without a valid handoff. {signal.detail}"
        elif signal.kind in ("invalid", "malformed"):
            text = f"Malformed handoff in {signal.speaker}'s latest entry: {signal.detail}"
        else:
            text = signal.detail
        self._needs_attention(text)

    def _retry_gated_launch(self) -> None:
        self._gate_waited += 0.25
        self._advance()  # re-reads conversation.md, re-checks pause/stop

    def _launch(self, agent: str) -> None:
        adapter = self.adapters[agent]
        other = other_agent(agent)
        text = self._last_text
        turn = next_turn_number(text, agent)
        theatre = ""
        if self.prompt_theatre is not None:
            try:  # presentation only: a failure here must never block a turn
                theatre = self.prompt_theatre(agent, text)
            except Exception:
                theatre = ""
        prompt = build_prompt(
            agent, other, self.personalities.get(agent, ""), self.project_dir, self.protocol_file, turn, theatre,
            getattr(adapter, "environment_note", ""),
        )
        self.current_agent = agent
        self._turn_log = []
        self._set_agent_state(agent, A_STARTING)
        self._set_agent_state(other, A_WAITING)
        try:
            process = adapter.prepare_turn(self.project_dir, prompt, self)
        except AgentUnavailable as exc:
            self._set_agent_state(agent, A_ERROR)
            self.current_agent = None
            self._needs_attention(str(exc), level="error")
            return

        self.running_process = process
        self.turn_number += 1
        self.turn_started_at = time.monotonic()
        process.output.connect(lambda stream, line, a=agent: self._on_output(a, stream, line))
        process.finished.connect(
            lambda code, crashed, a=agent, p=process, before=text: self._on_finished(a, p, before, code, crashed)
        )
        self._set_state(PAUSING if self.paused else RUNNING)
        self.turn_started.emit(agent, turn)
        process.start()

    def _on_output(self, agent: str, stream: str, line: str) -> None:
        if len(self._turn_log) < 20000:
            self._turn_log.append(f"[{stream}] {line}" if stream != "stdout" else line)
        self.agent_output.emit(agent, stream, line)
        if stream == "system" or self.agent_states.get(agent) == A_HANDING_OFF:
            return
        elapsed = time.monotonic() - (self.turn_started_at or 0)
        self._set_agent_state(agent, A_WORKING if elapsed > 3 else A_READING)

    def _on_finished(self, agent: str, process: AgentProcess, text_before: str, exit_code: int, crashed: bool):
        if process is not self.running_process:
            return
        self.running_process = None
        self.current_agent = None
        self.turn_started_at = None
        process.deleteLater()
        text = self._check_file(force=True)
        self._write_turn_log(agent, exit_code)
        self.turn_finished.emit(agent, exit_code)

        if self.stopped:
            self._set_agent_state(agent, A_STOPPED)
            self.message.emit("warning", f"{agent}'s turn was terminated. Files and conversation were kept.")
            return

        if exit_code != 0 or crashed or text == text_before:
            limit = detect_usage_limit(agent, self._turn_log + list(process.stderr_tail))
            if limit is not None:
                self._usage_limited(limit)
                return

        if exit_code != 0 or crashed:
            self._set_agent_state(agent, A_ERROR)
            stderr = "\n".join(process.stderr_tail[-15:]).strip()
            self._needs_attention(
                f"{agent.upper()} ERROR\nExit code: {exit_code}" + (f"\n\nstderr:\n{stderr}" if stderr else ""),
                level="error",
            )
            return

        if text == text_before:
            self._set_agent_state(agent, A_ERROR)
            self._needs_attention(f"{agent} completed without updating conversation.md.")
            return

        problem = validate_append(text_before, text, agent)
        if problem:
            self._set_agent_state(agent, A_ERROR)
            backup = self._save_pre_turn_backup(text_before, agent)
            note = f"\n\nThe conversation as it was before this turn was saved to {backup.name}." if backup else ""
            self._needs_attention(problem + note, level="error")
            return

        latest = parse_conversation(text)[-1]
        if detect_disagreement(latest.content):
            self.disagreement.emit(agent)

        self._auto_resumed = False  # a successful turn ends any usage-limit episode
        self._set_agent_state(agent, A_PAUSED if self.paused else A_WAITING)
        self._advance()

    # -- usage limits -----------------------------------------------------------

    def _usage_limited(self, limit: UsageLimit) -> None:
        """Pause cleanly (not an error) and, once per episode, resume shortly after the reset."""
        self.usage_limit = limit
        self.paused = True
        self._set_agent_state(limit.agent, A_LIMITED)
        auto = limit.reset_at is not None and not self._auto_resumed
        if auto:
            delay = max(5.0, limit.reset_at + 60 - time.time())
            self._limit_timer.start(int(min(delay, 8 * 86400) * 1000))
        self._set_state(USAGE_LIMIT)
        when = f"It resets at {limit.reset_text()}" if limit.reset_at else "The reset time wasn't given"
        then = ("; the workshop will resume automatically a minute after that." if auto else
                ". Press Resume when it has reset." if not self._auto_resumed else
                ". It was still limited after the automatic retry, so press Resume when it has reset.")
        self.message.emit("warning", f"{limit.agent.upper()} HIT ITS USAGE LIMIT. {when}{then}\n({limit.evidence})")

    def _auto_resume_after_limit(self) -> None:
        self._limit_timer.stop()
        if self.state != USAGE_LIMIT or self.is_busy():
            return
        self._auto_resumed = True
        self.message.emit("info", f"Usage should have reset: resuming {self.usage_limit.agent if self.usage_limit else ''}.")
        self.usage_limit = None
        self.paused = False
        self._advance()

    def limit_seconds_left(self) -> float | None:
        if self.state != USAGE_LIMIT or not self._limit_timer.isActive():
            return None
        return self._limit_timer.remainingTime() / 1000.0

    # -- helpers ------------------------------------------------------------

    def _write_turn_log(self, agent: str, exit_code: int) -> None:
        """Keep each turn's raw CLI output next to the project, so failures can be read after the window closes."""
        try:
            logs = self.project_dir / ".workshop" / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            name = f"{time.strftime('%Y%m%d-%H%M%S')}-{agent.lower()}-exit{exit_code}.log"
            (logs / name).write_text("\n".join(self._turn_log) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _save_pre_turn_backup(self, text: str, agent: str) -> Path | None:
        path = self.project_dir / f"conversation.before-{agent.lower()}-{time.strftime('%Y%m%d-%H%M%S')}.bak.md"
        try:
            path.write_text(text, encoding="utf-8", newline="")
        except OSError:
            return None
        return path

    def _needs_attention(self, text: str, level: str = "warning") -> None:
        self.last_error = text
        self.paused = True
        self._set_state(NEEDS_ATTENTION)
        self.message.emit(level, text)

    def _check_file(self, force: bool = False) -> str:
        text = read_conversation(self.conversation_path)
        path = str(self.conversation_path)
        if self.conversation_path.exists() and path not in self._watcher.files():
            self._watcher.addPath(path)  # editors/agents may replace the file
        if text != self._last_text or force:
            changed = text != self._last_text
            self._last_text = text
            if changed or force:
                self.conversation_changed.emit(text)
            if changed and self.current_agent:
                latest = parse_conversation(text)
                if latest and latest[-1].speaker == self.current_agent:
                    self._set_agent_state(self.current_agent, A_HANDING_OFF)
        return text

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.state_changed.emit(state)

    def _set_agent_state(self, agent: str, state: str) -> None:
        if self.agent_states.get(agent) != state:
            self.agent_states[agent] = state
            self.agent_state_changed.emit(agent, state)

    def _mark_idle_agents(self, state: str) -> None:
        for agent in AGENTS:
            if agent != self.current_agent and self.agent_states[agent] not in (A_ERROR, A_COMPLETE):
                self._set_agent_state(agent, state)
