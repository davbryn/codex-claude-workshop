from __future__ import annotations

import time

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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
from ..conversation import AGENTS
from ..orchestrator import Orchestrator
from ..theatre.director import Director
from ..theatre.sfx import SoundEffects
from ..theatre.speech import SpeechEngine, create_speech_engine
from ..theatre.stats import format_elapsed
from .avatar_paint import avatar_pixmap
from .conversation_view import ConversationView
from .human_turn_dialog import HumanTurnDialog
from .settings_dialog import SettingsDialog
from .stage import StageWidget
from .theme import ACCENTS

BANNER_STYLES = {
    "info": "background:#1d3346; color:#bfe3ff;",
    "warning": "background:#4a3b12; color:#ffe08a;",
    "error": "background:#4d1b1f; color:#ffc2c2;",
    "complete": "background:#123a44; color:#9ff0ff; font-size:13pt;",
}

STATE_TEXT = {
    orch.IDLE: "Idle",
    orch.RUNNING: "Running",
    orch.PAUSING: "Pausing after current turn…",
    orch.PAUSED: "⏸ PAUSED",
    orch.WAITING_HUMAN: "⚠ HUMAN INPUT REQUIRED",
    orch.NEEDS_ATTENTION: "⚠ Needs attention",
    orch.COMPLETE: "✓ PROJECT COMPLETE",
    orch.STOPPED: "■ Stopped",
}


def _chip(text: str = "", name: str = "chip") -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    return label


class MainWindow(QMainWindow):
    def __init__(self, orchestrator: Orchestrator, settings: Settings, fake_agents: bool = False, demo: bool = False,
                 speech: SpeechEngine | None = None, sfx: SoundEffects | None = None,
                 demo_auto_reply: float | None = None, pace: bool = False):
        super().__init__()
        self.orchestrator = orchestrator
        self.settings = settings
        self.fake_agents = fake_agents
        self.setWindowTitle(f"Codex ↔ Claude Workshop — {orchestrator.project_dir.name}")
        self.setWindowIcon(QIcon(avatar_pixmap("Codex", 64)))
        self.resize(1320, 940)
        if settings.window_geometry:
            self.restoreGeometry(QByteArray.fromHex(settings.window_geometry.encode()))

        # header
        title = QLabel(
            f'<span style="color:{ACCENTS["Codex"]}">CODEX</span>'
            f' <span style="color:#6f7887">↔</span> '
            f'<span style="color:{ACCENTS["Claude"]}">CLAUDE</span>'
            f' <span style="color:#e8ecf2">WORKSHOP</span>'
        )
        title.setObjectName("title")
        subtitle = QLabel(str(orchestrator.project_dir))
        subtitle.setObjectName("subtitle")
        subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.header = QWidget()
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        header.addWidget(title)
        if demo or fake_agents:
            tag = QLabel("DEMO" if demo else "FAKE AGENTS")
            tag.setObjectName("modeTag")
            header.addWidget(tag)
        header.addStretch()
        header.addWidget(subtitle)

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
        self.director.set_muted(settings.speech_muted)
        if pace:  # let a character finish its line before the next agent starts
            orchestrator.launch_gate = self.director.presentation_idle

        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.banner.hide()

        # conversation + raw output
        self.conversation = ConversationView()
        self.outputs = {}
        self.tabs = QTabWidget()
        self.tabs.addTab(self.conversation, "Conversation")
        for agent in AGENTS:
            view = QPlainTextEdit()
            view.setObjectName("rawOutput")
            view.setReadOnly(True)
            view.setMaximumBlockCount(20000)
            view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            self.outputs[agent] = view
            self.tabs.addTab(view, f"{agent} Output (raw CLI)")

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.stage)
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([520, 330])

        # status strip
        self.strip = QFrame()
        self.strip.setObjectName("statusStrip")
        strip = QHBoxLayout(self.strip)
        strip.setContentsMargins(10, 4, 6, 4)
        strip.setSpacing(8)
        self.chip_turn = _chip()
        self.chip_time = _chip()
        self.chip_agents = {a: _chip() for a in AGENTS}
        self.chip_files = _chip()
        self.chip_tests = _chip()
        self.chip_popcorn = _chip("🍿", "popcorn")
        self.chip_popcorn.setToolTip("Three disagreements in a row. Grab a snack.")
        for w in (self.chip_turn, self.chip_time, *self.chip_agents.values(), self.chip_files, self.chip_tests,
                  self.chip_popcorn):
            strip.addWidget(w)
        strip.addStretch()
        self.mute_button = QToolButton()
        self.mute_button.setCheckable(True)
        self.mute_button.setObjectName("toggle")
        self.mute_button.toggled.connect(self._toggle_mute)
        self.sfx_button = QToolButton()
        self.sfx_button.setCheckable(True)
        self.sfx_button.setObjectName("toggle")
        self.sfx_button.toggled.connect(self._toggle_sfx)
        self.theatre_button = QToolButton()
        self.theatre_button.setCheckable(True)
        self.theatre_button.setObjectName("toggle")
        self.theatre_button.setText("🎭 Theatre")
        self.theatre_button.setToolTip("Theatre Mode (F11): big stage, compact conversation")
        self.theatre_button.toggled.connect(self.set_theatre_mode)
        settings_button = QToolButton()
        settings_button.setObjectName("toggle")
        settings_button.setText("⚙ Settings")
        settings_button.clicked.connect(self._open_settings)
        for b in (self.mute_button, self.sfx_button, self.theatre_button, settings_button):
            strip.addWidget(b)
        self.mute_button.setChecked(settings.speech_muted)
        self.sfx_button.setChecked(not settings.sfx_enabled)
        self._refresh_audio_buttons()

        # buttons
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("stopButton")
        self.human_button = QPushButton("👤 Human Turn")
        open_project = QPushButton("Open Project")
        open_conversation = QPushButton("Open Conversation")
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button.clicked.connect(self._stop)
        self.human_button.clicked.connect(self._human_turn)
        open_project.clicked.connect(lambda: self._open(orchestrator.project_dir))
        open_conversation.clicked.connect(lambda: self._open(orchestrator.conversation_path))
        buttons = QHBoxLayout()
        for b in (self.pause_button, self.stop_button, self.human_button):
            buttons.addWidget(b)
        buttons.addStretch()
        buttons.addWidget(open_project)
        buttons.addWidget(open_conversation)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        layout.addWidget(self.header)
        layout.addWidget(self.banner)
        layout.addWidget(self.splitter, 1)
        layout.addWidget(self.strip)
        layout.addLayout(buttons)
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
        dialog = SettingsDialog(self.settings, self.speech, o.personalities, self)
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
        self.stage.set_motion(s.animations, s.reduced_motion, s.typewriter)
        for agent, persona in load_personas(s.last_preset).items():
            self.stage.set_persona(agent, persona)
        self.sfx_button.setChecked(not s.sfx_enabled)
        self._refresh_audio_buttons()
        s.save()

    # -- theatre mode ----------------------------------------------------------

    def set_theatre_mode(self, on: bool) -> None:
        self.settings.theatre_mode = on
        self.header.setVisible(not on)
        for i in range(1, self.tabs.count()):
            self.tabs.setTabVisible(i, not on)
        self.tabs.tabBar().setVisible(not on)
        if on:
            self.tabs.setCurrentIndex(0)
        total = max(1, sum(self.splitter.sizes()))
        self.splitter.setSizes([int(total * 0.84), int(total * 0.16)] if on else [int(total * 0.6), int(total * 0.4)])

    # -- orchestrator events ------------------------------------------------

    def _on_state(self, state: str) -> None:
        self.state_label.setText(STATE_TEXT.get(state, state))
        self._update_clock()
        busy = self.orchestrator.is_busy()
        if state == orch.PAUSING:
            self.pause_button.setText("Cancel Pause")
        elif state in (orch.RUNNING, orch.IDLE):
            self.pause_button.setText("Pause")
        else:
            self.pause_button.setText("Resume")
        self.pause_button.setEnabled(state != orch.COMPLETE)
        self.stop_button.setEnabled(state not in (orch.STOPPED, orch.COMPLETE))
        self.human_button.setEnabled(not busy)
        self.human_button.setToolTip(
            "Available once the current agent turn finishes (use Pause to stop after this turn)." if busy else ""
        )
        if state == orch.COMPLETE:
            self._show_message("complete", "✓ PROJECT COMPLETE — both agents agreed the work is done.")
        elif state == orch.PAUSED:
            self._show_message("info", "⏸ PAUSED — press Resume to continue, or take a Human Turn.")
        elif state == orch.STOPPED:
            self._show_message("warning", "■ STOPPED — no further turns will run. Files and conversation are kept.")
        elif state == orch.RUNNING:
            self.banner.hide()

    def _on_output(self, agent: str, stream: str, line: str) -> None:
        prefix = {"stderr": "[stderr] ", "system": "[workshop] "}.get(stream, "")
        self.outputs[agent].appendPlainText(prefix + line)

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
            self.elapsed_label.setText(f"{o.current_agent} working — {elapsed // 60:d}:{elapsed % 60:02d}")
        else:
            self.elapsed_label.setText(f"Agent turns this session: {o.turn_number}")
        self._update_strip()

    def _update_strip(self) -> None:
        d = self.director
        total = sum(v.turns for v in self.stage.views.values())
        self.chip_turn.setText(f"TURN {total}")
        self.chip_time.setText(f"⏱ {format_elapsed(d.stats.elapsed())}")
        for agent, chip in self.chip_agents.items():
            view = self.stage.views[agent]
            chip.setText(f'<span style="color:{ACCENTS[agent]}; font-weight:700">{agent}</span>&nbsp; {view.label}')
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
        for agent in AGENTS:  # the human walks into the room
            self.stage.models[agent].look_at_human(6.0)
        self.stage.wake()
        dialog = HumanTurnDialog(default, reason, self)
        if dialog.exec():
            message, next_agent, resume = dialog.values()
            o.submit_human_turn(message, next_agent, resume)

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
