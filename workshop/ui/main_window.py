from __future__ import annotations

import time

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import orchestrator as orch
from ..config import Settings
from ..conversation import AGENTS, count_turns, extract_latest_speech, parse_conversation
from ..orchestrator import Orchestrator
from .agent_panel import AgentPanel
from .conversation_view import ConversationView
from .human_turn_dialog import HumanTurnDialog

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


class MainWindow(QMainWindow):
    def __init__(self, orchestrator: Orchestrator, settings: Settings, fake_agents: bool = False):
        super().__init__()
        self.orchestrator = orchestrator
        self.settings = settings
        self.fake_agents = fake_agents
        self.setWindowTitle(f"Codex ↔ Claude Workshop — {orchestrator.project_dir.name}")
        self.resize(1200, 900)
        if settings.window_geometry:
            self.restoreGeometry(QByteArray.fromHex(settings.window_geometry.encode()))

        # header
        title = QLabel("CODEX ↔ CLAUDE WORKSHOP")
        title.setObjectName("title")
        subtitle = QLabel(str(orchestrator.project_dir))
        subtitle.setObjectName("subtitle")
        subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header = QHBoxLayout()
        header.addWidget(title)
        if fake_agents:
            tag = QLabel("FAKE AGENTS")
            tag.setObjectName("modeTag")
            header.addWidget(tag)
        header.addStretch()
        header.addWidget(subtitle)

        # agent panels
        self.panels = {agent: AgentPanel(agent) for agent in AGENTS}
        panels = QHBoxLayout()
        panels.setSpacing(14)
        for agent in AGENTS:
            panels.addWidget(self.panels[agent], 1)
        panels_widget = QWidget()
        panels_widget.setLayout(panels)

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

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(panels_widget)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 420])

        # buttons
        self.pause_button = QPushButton("Pause")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("stopButton")
        self.human_button = QPushButton("Human Turn")
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
        layout.addLayout(header)
        layout.addWidget(self.banner)
        layout.addWidget(splitter, 1)
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

        o = orchestrator
        o.state_changed.connect(self._on_state)
        o.agent_state_changed.connect(lambda a, s: self.panels[a].set_state(s))
        o.conversation_changed.connect(self._on_conversation)
        o.agent_output.connect(self._on_output)
        o.message.connect(self._show_message)
        o.turn_started.connect(self._on_turn_started)
        o.disagreement.connect(lambda a: self.panels[a].set_disagreement(True))

        self._on_state(o.state)

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

    def _on_conversation(self, text: str) -> None:
        self.conversation.set_conversation(text)
        turns = parse_conversation(text)
        for agent, panel in self.panels.items():
            panel.set_turns(count_turns(turns, agent))
            speech = extract_latest_speech(text, agent)
            if self.orchestrator.current_agent == agent and (not turns or turns[-1].speaker != agent):
                panel.set_speech(None, working=True)
            elif speech:
                panel.set_speech(speech)

    def _on_output(self, agent: str, stream: str, line: str) -> None:
        view = self.outputs[agent]
        prefix = {"stderr": "[stderr] ", "system": "[workshop] "}.get(stream, "")
        view.appendPlainText(prefix + line)
        if stream != "system":
            self.panels[agent].set_live_output(line)

    def _on_turn_started(self, agent: str, turn: int) -> None:
        self.panels[agent].set_disagreement(False)
        self.panels[agent].set_speech(None, working=True)
        view = self.outputs[agent]
        view.appendPlainText(f"\n===== {agent} — Turn {turn} — {time.strftime('%H:%M:%S')} =====")

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
        self.settings.window_geometry = bytes(self.saveGeometry().toHex()).decode()
        self.settings.save()
        event.accept()
