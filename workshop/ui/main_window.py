from __future__ import annotations

import time

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import orchestrator as orch
from ..config import Settings, load_personas
from ..conversation import AGENTS, parse_conversation
from ..orchestrator import Orchestrator, other_agent
from ..theatre.banter import make_prompt_theatre
from ..theatre.cast import ACCENT, CHARACTER, display_name
from ..theatre.director import Director
from ..theatre.sfx import SoundEffects
from ..theatre.speech import SpeechEngine, create_speech_engine
from ..theatre.stats import format_elapsed
from .avatar_paint import portrait_pixmap
from .conversation_view import ConversationView
from .dashboard import FilesPanel, RecentOutputPanel, ScoreboardPanel, StatusPanel
from .human_turn_dialog import HumanTurnDialog
from .settings_dialog import SettingsDialog
from .stage import StageWidget
from .theme import ACCENTS

BANNER_STYLES = {
    "info": "background:#1d2a36; color:#bfe3ff;",
    "warning": "background:#4a3b12; color:#ffe08a;",
    "error": "background:#4d1b1f; color:#ffc2c2;",
    "complete": "background:#2d2610; color:#f7dd8a; font-size:13pt;",
}

STATE_TEXT = {
    orch.IDLE: "Idle",
    orch.RUNNING: "Running",
    orch.PAUSING: "Pausing after current turn…",
    orch.PAUSED: "⏸ PAUSED",
    orch.WAITING_HUMAN: "⚠ HUMAN INPUT REQUIRED",
    orch.NEEDS_ATTENTION: "⚠ Needs attention",
    orch.COMPLETE: "✓ PROJECT COMPLETE",
    orch.USAGE_LIMIT: "💸 OUT OF USAGE (paused)",
    orch.STOPPED: "■ Stopped",
}


def _chip(text: str = "", name: str = "chip") -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    return label


def _icon_button(text: str, tip: str, checkable: bool = False) -> QToolButton:
    b = QToolButton()
    b.setObjectName("toggle")
    b.setText(text)
    b.setToolTip(tip)
    b.setCheckable(checkable)
    return b


class MainWindow(QMainWindow):
    def __init__(self, orchestrator: Orchestrator, settings: Settings, fake_agents: bool = False, demo: bool = False,
                 speech: SpeechEngine | None = None, sfx: SoundEffects | None = None,
                 demo_auto_reply: float | None = None, pace: bool = False):
        super().__init__()
        self.orchestrator = orchestrator
        self.settings = settings
        self.fake_agents = fake_agents
        self._pending_message: tuple[str, str] | None = None
        self.setWindowTitle(f"Codex ↔ Claude Workshop — {orchestrator.project_dir.name}")
        self.setWindowIcon(QIcon(portrait_pixmap("Codex", 64)))
        self.resize(1440, 1000)
        if settings.window_geometry:
            self.restoreGeometry(QByteArray.fromHex(settings.window_geometry.encode()))
        # the cast's character direction goes into every real turn prompt (presentation only)
        orchestrator.prompt_theatre = make_prompt_theatre(settings)

        # header bar
        title = QLabel(
            f'<span style="color:{ACCENTS["Codex"]}">CODEX</span>'
            f' <span style="color:#8b8378">↔</span> '
            f'<span style="color:{ACCENTS["Claude"]}">CLAUDE</span>'
            f' <span style="color:#efe8dc">WORKSHOP</span>'
        )
        title.setObjectName("title")
        logo = QLabel()
        logo.setPixmap(portrait_pixmap("Codex", 30, background=True))
        self.project_label = QLabel(f"Project: {orchestrator.project_dir.name}")
        self.project_label.setObjectName("headerDim")
        self.project_label.setToolTip(str(orchestrator.project_dir))
        self.header_turn = QLabel()
        self.header_turn.setObjectName("headerDim")
        self.header_clock = QLabel()
        self.header_clock.setObjectName("headerDim")
        self.live = QLabel()
        self.live.setObjectName("live")
        self.header = QFrame()
        self.header.setObjectName("headerBar")
        header = QHBoxLayout(self.header)
        header.setContentsMargins(10, 4, 8, 4)
        header.setSpacing(12)
        header.addWidget(logo)
        header.addWidget(title)
        if demo or fake_agents:
            tag = QLabel("DEMO EPISODE" if demo else "FAKE AGENTS")
            tag.setObjectName("modeTag")
            header.addWidget(tag)
        for w in (self.project_label, self.header_turn, self.header_clock):
            header.addWidget(_chip("|", "sep"))
            header.addWidget(w)
        header.addStretch()
        header.addWidget(self.live)
        self.mute_button = _icon_button("🔊", "Mute/unmute voices (Ctrl+M)", checkable=True)
        self.mute_button.toggled.connect(self._toggle_mute)
        self.sfx_button = _icon_button("🔔", "Sound effects on/off", checkable=True)
        self.sfx_button.toggled.connect(self._toggle_sfx)
        self.theatre_button = _icon_button("🎭 Theatre", "Theatre Mode (F11): big stage, compact conversation",
                                           checkable=True)
        self.theatre_button.toggled.connect(self.set_theatre_mode)
        settings_button = _icon_button("⚙", "Settings: the cast, hostility, voices, animation")
        settings_button.clicked.connect(self._open_settings)
        for b in (self.mute_button, self.sfx_button, self.theatre_button, settings_button):
            header.addWidget(b)

        # stage + theatre
        self.stage = StageWidget(load_personas(settings.last_preset))
        self.stage.set_motion(settings.animations, settings.reduced_motion, settings.typewriter)
        self.panels = self.stage.views  # per-agent state/bubble/turns (kept for tests & tooling)
        self.speech = speech or create_speech_engine(self, settings.speech_engine)
        self._engine_pref = settings.speech_engine
        self.sfx = sfx or SoundEffects(settings.sfx_enabled, settings.sfx_volume, self)
        self._apply_audio_settings()
        self.director = Director(orchestrator, self.stage, self.speech, self.sfx, rivalry=settings.rivalry_mode,
                                 speech_enabled=settings.speech_enabled, demo_auto_reply=demo_auto_reply,
                                 sleep_after=40.0 if demo else 150.0, parent=self)
        self.director.comic_timing = settings.comic_timing
        self.director.camera_cuts = settings.camera_cuts
        self.director.kanban = settings.kanban_enabled
        self.director.side_bits = settings.side_bits_enabled
        self.director.set_muted(settings.speech_muted)
        if pace:  # let a character finish its line before the next agent starts
            orchestrator.launch_gate = self.director.presentation_idle

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.banner.hide()

        # status chips (inside the CURRENT STATUS panel)
        self.chip_turn = _chip()
        self.chip_time = _chip()
        self.chip_agents = {a: _chip() for a in AGENTS}
        self.chip_files = _chip()
        self.chip_tests = _chip()
        self.chip_popcorn = _chip("🍿", "popcorn")
        self.chip_popcorn.setToolTip("Three disagreements in a row. Grab a snack.")

        # dashboard row
        self.scoreboard = ScoreboardPanel()
        self.status_panel = StatusPanel([self.chip_turn, self.chip_time, self.chip_tests, self.chip_popcorn])
        for chip in (*self.chip_agents.values(), self.chip_files):
            self.status_panel.agent_row.addWidget(chip)
        self.status_panel.agent_row.addStretch()
        self.recent = RecentOutputPanel()
        self.dashboard = QWidget()
        dash = QHBoxLayout(self.dashboard)
        dash.setContentsMargins(0, 0, 0, 0)
        dash.setSpacing(8)
        dash.addWidget(self.scoreboard, 4)
        dash.addWidget(self.status_panel, 4)
        dash.addWidget(self.recent, 5)
        self.scoreboard.setVisible(settings.petty_scoreboard)
        self.dashboard.setMaximumHeight(178)
        self.stage.show_on_air = False

        # conversation + raw output, and the project files
        self.conversation = ConversationView()
        self.outputs = {}
        self.tabs = QTabWidget()
        self.tabs.addTab(self.conversation, "CONVERSATION")
        for agent in AGENTS:
            view = QPlainTextEdit()
            view.setObjectName("rawOutput")
            view.setReadOnly(True)
            view.setMaximumBlockCount(20000)
            view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.outputs[agent] = view
            self.tabs.addTab(view, f"{display_name(agent)} output (raw CLI)")
        self.files = FilesPanel(orchestrator.project_dir)
        self.lower = QSplitter(Qt.Orientation.Horizontal)
        self.lower.addWidget(self.tabs)
        self.lower.addWidget(self.files)
        self.lower.setStretchFactor(0, 5)
        self.lower.setStretchFactor(1, 1)
        self.lower.setSizes([1100, 260])

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)
        bottom_layout.addWidget(self.dashboard)
        bottom_layout.addWidget(self.lower, 1)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.stage)
        self.splitter.addWidget(bottom)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setSizes([540, 460])

        # controls
        self.pause_button = QPushButton("⏸  Pause Workshop")
        self.pause_button.setObjectName("pauseButton")
        self.stop_button = QPushButton("■  Stop")
        self.stop_button.setObjectName("stopButton")
        self.human_button = QPushButton("👤  Human Turn")
        open_project = QPushButton("Open Project")
        open_conversation = QPushButton("Open Conversation")
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button.clicked.connect(self._stop)
        self.human_button.clicked.connect(self._human_turn)
        open_project.clicked.connect(lambda: self._open(orchestrator.project_dir))
        open_conversation.clicked.connect(lambda: self._open(orchestrator.conversation_path))
        self.message = QLineEdit()
        self.message.setObjectName("messageBox")
        self.message.setPlaceholderText("Type your message to both agents…  (delivered as a Human Turn)")
        self.message.returnPressed.connect(self._send_message)
        send = QToolButton()
        send.setObjectName("sendButton")
        send.setText("➤")
        send.setToolTip("Send as a Human Turn. If an agent is working, the workshop pauses after its turn "
                        "and your message is delivered then.")
        send.clicked.connect(self._send_message)
        controls = QHBoxLayout()
        for b in (self.pause_button, self.human_button, self.stop_button):
            controls.addWidget(b)
        controls.addSpacing(8)
        controls.addWidget(open_project)
        controls.addWidget(open_conversation)
        controls.addSpacing(12)
        controls.addWidget(self.message, 1)
        controls.addWidget(send)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(self.header)
        layout.addWidget(self.banner)
        layout.addWidget(self.splitter, 1)
        layout.addLayout(controls)
        self.setCentralWidget(central)

        self.state_label = QLabel()
        self.elapsed_label = QLabel()
        self.statusBar().addWidget(self.state_label, 1)
        self.statusBar().addPermanentWidget(self.elapsed_label)
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._update_clock)
        self._clock.start()

        for seq in ("F11", "Ctrl+T"):
            QShortcut(QKeySequence(seq), self, activated=self.theatre_button.toggle)
        QShortcut(QKeySequence("Ctrl+M"), self, activated=self.mute_button.toggle)

        o = orchestrator
        o.state_changed.connect(self._on_state)
        o.conversation_changed.connect(self.conversation.set_conversation)
        o.agent_output.connect(self._on_output)
        o.message.connect(self._show_message)
        o.turn_started.connect(self._on_turn_started)
        self.director.stats_changed.connect(self._update_strip)

        self.mute_button.setChecked(settings.speech_muted)
        self.sfx_button.setChecked(not settings.sfx_enabled)
        self._refresh_audio_buttons()
        self._on_state(o.state)
        self._update_strip()
        if settings.theatre_mode:
            self.theatre_button.setChecked(True)

    # -- audio ----------------------------------------------------------------

    def _apply_audio_settings(self) -> None:
        s = self.settings
        self.speech.set_rate(s.speech_rate)
        self.speech.set_volume(s.speech_volume)
        if s.codex_voice:
            self.speech.set_voice("Codex", s.codex_voice)
        if s.claude_voice:
            self.speech.set_voice("Claude", s.claude_voice)
        self.sfx.enabled = s.sfx_enabled
        self.sfx.set_volume(s.sfx_volume)

    def _toggle_mute(self, muted: bool) -> None:
        self.settings.speech_muted = muted
        self.director.set_muted(muted)
        self._refresh_audio_buttons()

    def _toggle_sfx(self, off: bool) -> None:
        self.settings.sfx_enabled = not off
        self.sfx.enabled = not off
        self._refresh_audio_buttons()

    def _refresh_audio_buttons(self) -> None:
        voices = self.speech.available() and self.settings.speech_enabled
        self.mute_button.setText("🔇 Voices" if (self.mute_button.isChecked() or not voices) else "🔊 Voices")
        self.mute_button.setToolTip(
            "Mute/unmute voices (Ctrl+M)" if voices else "Voices are off or no local speech engine is available")
        self.sfx_button.setText("🔕 Sounds" if self.sfx_button.isChecked() else "🔔 Sounds")

    def _open_settings(self) -> None:
        o = self.orchestrator
        dialog = SettingsDialog(self.settings, self.speech, o.personalities, self, sfx=self.sfx)
        if not dialog.exec():
            return
        s = self.settings
        o.personalities = dialog.personalities()
        if s.speech_engine != self._engine_pref:
            self._engine_pref = s.speech_engine
            old = self.speech
            self.speech = create_speech_engine(self, s.speech_engine)
            self.director.set_speech(self.speech)
            old.stop()
            old.deleteLater()
        self._apply_audio_settings()
        self.director.speech_enabled = s.speech_enabled
        self.director.rivalry = s.rivalry_mode
        self.director.comic_timing = s.comic_timing
        self.director.camera_cuts = s.camera_cuts
        self.director.kanban = s.kanban_enabled
        self.director.side_bits = s.side_bits_enabled
        if not s.camera_cuts:
            self.stage.set_shot(None)
        self.stage.set_motion(s.animations, s.reduced_motion, s.typewriter)
        for agent, persona in load_personas(s.last_preset).items():
            self.stage.set_persona(agent, persona)
        self.sfx_button.setChecked(not s.sfx_enabled)
        self.scoreboard.setVisible(s.petty_scoreboard and not s.theatre_mode)
        self._refresh_audio_buttons()
        s.save()

    # -- theatre mode ----------------------------------------------------------

    def set_theatre_mode(self, on: bool) -> None:
        self.settings.theatre_mode = on
        self.header.setVisible(not on)
        self.stage.show_on_air = on
        self.stage.update()
        self.dashboard.setVisible(not on)
        self.files.setVisible(not on)
        for i in range(1, self.tabs.count()):
            self.tabs.setTabVisible(i, not on)
        self.tabs.tabBar().setVisible(not on)
        if on:
            self.tabs.setCurrentIndex(0)
        total = max(1, sum(self.splitter.sizes()))
        self.splitter.setSizes([int(total * 0.8), int(total * 0.2)] if on else [int(total * 0.55), int(total * 0.45)])

    # -- orchestrator events ------------------------------------------------

    def _on_state(self, state: str) -> None:
        self.state_label.setText(STATE_TEXT.get(state, state))
        self._update_clock()
        busy = self.orchestrator.is_busy()
        if state == orch.PAUSING:
            self.pause_button.setText("Cancel Pause")
        elif state in (orch.RUNNING, orch.IDLE):
            self.pause_button.setText("⏸  Pause Workshop")
        elif state == orch.COMPLETE:
            self.pause_button.setText("✓  Complete")
        elif state == orch.USAGE_LIMIT:
            self.pause_button.setText("▶  Resume now")
        else:
            self.pause_button.setText("▶  Resume")
        self.pause_button.setEnabled(state != orch.COMPLETE)
        self.stop_button.setEnabled(state not in (orch.STOPPED, orch.COMPLETE))
        self.human_button.setEnabled(not busy)
        self.human_button.setToolTip(
            "Available once the current agent turn finishes (use Pause to stop after this turn)." if busy else ""
        )
        if state == orch.COMPLETE:
            self._show_message("complete", "✓ PROJECT COMPLETE — both agents agreed the work is done. Somehow.")
        elif state == orch.PAUSED:
            self._show_message("info", "⏸ PAUSED — press Resume to continue, or take a Human Turn.")
        elif state == orch.STOPPED:
            self._show_message("warning", "■ STOPPED — no further turns will run. Files and conversation are kept.")
        elif state == orch.RUNNING:
            self.banner.hide()
        if self._pending_message and not busy and state in (orch.PAUSED, orch.WAITING_HUMAN, orch.NEEDS_ATTENTION,
                                                             orch.COMPLETE, orch.IDLE, orch.USAGE_LIMIT):
            QTimer.singleShot(0, self._deliver_pending)

    def _on_output(self, agent: str, stream: str, line: str) -> None:
        prefix = {"stderr": "[stderr] ", "system": "[workshop] "}.get(stream, "")
        self.outputs[agent].appendPlainText(prefix + line)
        if stream != "system":
            for part in line.splitlines() or [line]:
                self.recent.add(agent, part)

    def _on_turn_started(self, agent: str, turn: int) -> None:
        self.outputs[agent].appendPlainText(f"\n===== {agent} — Turn {turn} — {time.strftime('%H:%M:%S')} =====")

    def _show_message(self, level: str, text: str) -> None:
        self.banner.setText(text)
        self.banner.setStyleSheet(BANNER_STYLES.get(level, BANNER_STYLES["info"]))
        self.banner.show()
        if level == "error":
            self.statusBar().showMessage("Error — see the banner and the raw output tab.", 8000)

    def _update_clock(self) -> None:
        o = self.orchestrator
        if o.is_busy() and o.turn_started_at:
            elapsed = int(time.monotonic() - o.turn_started_at)
            self.elapsed_label.setText(f"{display_name(o.current_agent)} working — {elapsed // 60:d}:{elapsed % 60:02d}")
        else:
            self.elapsed_label.setText(f"Agent turns this session: {o.turn_number}")
        self._update_strip()

    def _update_strip(self) -> None:
        d = self.director
        o = self.orchestrator
        total = sum(v.turns for v in self.stage.views.values())
        elapsed = format_elapsed(d.stats.elapsed())
        self.chip_turn.setText(f"TURN {total}")
        self.chip_time.setText(f"⏱ {elapsed}")
        self.header_turn.setText(f"Turn {total}")
        self.header_clock.setText(elapsed)
        live = o.is_busy() or o.state == orch.RUNNING
        self.live.setText(f'<span style="color:{"#39d98a" if live else "#6b645b"}">●</span> '
                          f'{"LIVE" if live else STATE_TEXT.get(o.state, o.state).upper()}')
        for agent, chip in self.chip_agents.items():
            view = self.stage.views[agent]
            chip.setText(f'<span style="color:{ACCENTS[agent]}; font-weight:700">{CHARACTER[agent]}</span>'
                         f'&nbsp; {view.label}')
        files = d.files_edited()
        self.chip_files.setVisible(bool(files))
        if files:
            self.chip_files.setText(f"✎ {files} file{'s' if files != 1 else ''} edited this turn")
        if d.stats.last_test_count or d.stats.test_runs_passed or d.stats.test_runs_failed:
            text = f"🧪 {d.stats.last_test_count} passing" if d.stats.last_test_count else "🧪 tests"
            text += f" · {d.stats.test_runs_passed}✓ {d.stats.test_runs_failed}✗ runs"
            self.chip_tests.setText(text)
            self.chip_tests.show()
        else:
            self.chip_tests.hide()
        self.chip_popcorn.setVisible(d.popcorn)
        agent = o.current_agent if o.is_busy() else None
        if agent:
            activity = self.stage.views[agent].activity
            self.status_panel.set_working(f"{display_name(agent)} is working…" + (f"  {activity}" if activity else ""),
                                          ACCENT[agent], True)
        else:
            self.status_panel.set_working(STATE_TEXT.get(o.state, o.state), "#8b8378", False)
        self.scoreboard.set_scores(d.scoreboard)

    # -- buttons ------------------------------------------------------------

    def _toggle_pause(self) -> None:
        if self.orchestrator.state in (orch.RUNNING, orch.IDLE):
            self.orchestrator.pause()
        else:
            self.orchestrator.resume()

    def _stop(self) -> None:
        o = self.orchestrator
        if o.is_busy():
            answer = QMessageBox.question(
                self,
                "Stop workshop",
                f"{o.current_agent} is in the middle of a turn. Stopping will terminate its process "
                "(any partial file changes stay as they are).\n\nStop now?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        o.stop()

    def _human_turn(self) -> None:
        o = self.orchestrator
        if o.is_busy():
            QMessageBox.information(self, "Human Turn", "Wait for the current agent turn to finish (or Pause).")
            return
        signal = o.last_signal
        default = signal.agent if signal and signal.agent else "Codex"
        reason = ""
        if o.state == orch.WAITING_HUMAN and signal:
            reason = signal.detail
        elif o.state == orch.NEEDS_ATTENTION:
            reason = o.last_error.splitlines()[0] if o.last_error else ""
        for agent in AGENTS:  # the boss walks into the room
            self.stage.models[agent].look_at_human(6.0)
        self.stage.wake()
        dialog = HumanTurnDialog(default, reason, self)
        if dialog.exec():
            message, next_agent, resume = dialog.values()
            o.submit_human_turn(message, next_agent, resume)

    def _next_agent_for_message(self) -> str:
        o = self.orchestrator
        signal = o.last_signal
        if signal and signal.agent in AGENTS:
            return signal.agent
        turns = [t for t in parse_conversation(o.conversation_text()) if t.speaker in AGENTS]
        return other_agent(turns[-1].speaker) if turns else "Codex"

    def _send_message(self) -> None:
        text = self.message.text().strip()
        if not text:
            return
        o = self.orchestrator
        if o.state == orch.STOPPED:
            QMessageBox.information(self, "Message", "The workshop is stopped. Use Human Turn to restart it.")
            return
        self.message.clear()
        if o.is_busy():
            self._pending_message = (text, "")
            if o.state == orch.RUNNING:
                o.pause()
            self._show_message("info", f"✉ Message queued. {display_name(o.current_agent)} finishes this turn "
                                       "first; then both of them get your message.")
            for agent in AGENTS:
                self.stage.models[agent].look_at_human(3.0)
            return
        o.submit_human_turn(text, self._next_agent_for_message(), resume=True)

    def _deliver_pending(self) -> None:
        o = self.orchestrator
        if not self._pending_message or o.is_busy() or o.state == orch.STOPPED:
            return
        text, _ = self._pending_message
        self._pending_message = None
        o.submit_human_turn(text, self._next_agent_for_message(), resume=True)

    def _open(self, path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event) -> None:
        o = self.orchestrator
        if o.is_busy():
            answer = QMessageBox.question(
                self, "Quit", f"{o.current_agent} is still working. Quit and terminate its process?"
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        o.shutdown()
        self.director.shutdown()
        self._clock.stop()
        self.settings.window_geometry = bytes(self.saveGeometry().toHex()).decode()
        self.settings.save()
        event.accept()
