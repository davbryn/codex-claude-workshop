from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ..config import ASSETS_DIR
from ..orchestrator import (
    A_COMPLETE,
    A_ERROR,
    A_HANDING_OFF,
    A_PAUSED,
    A_READING,
    A_STARTING,
    A_STOPPED,
    A_WAITING,
    A_WORKING,
)

ACCENTS = {"Codex": "#39d98a", "Claude": "#f0915f"}
INITIALS = {"Codex": "CX", "Claude": "CL"}

STATE_LABELS = {
    A_WAITING: "○ WAITING",
    A_STARTING: "💭 STARTING",
    A_READING: "👀 READING",
    A_WORKING: "⚙ WORKING",
    A_HANDING_OFF: "✍ HANDING OFF",
    A_ERROR: "⚠ ERROR",
    A_PAUSED: "⏸ PAUSED",
    A_COMPLETE: "✓ COMPLETE",
    A_STOPPED: "■ STOPPED",
}
ACTIVE_STATES = {A_STARTING, A_READING, A_WORKING, A_HANDING_OFF}

AVATAR_SIZE = 132


def load_avatar(agent: str, size: int = AVATAR_SIZE) -> QPixmap:
    """Load assets/<agent>.png, falling back to a generated initials badge."""
    path = Path(ASSETS_DIR) / f"{agent.lower()}.png"
    pixmap = QPixmap(str(path)) if path.exists() else QPixmap()
    if not pixmap.isNull():
        return pixmap.scaled(
            size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(ACCENTS.get(agent, "#888")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(QRectF(4, 4, size - 8, size - 8))
    painter.setPen(QColor("#111"))
    painter.setFont(QFont("Segoe UI", size // 4, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, INITIALS.get(agent, agent[:2].upper()))
    painter.end()
    return pixmap


class AgentPanel(QFrame):
    def __init__(self, agent: str, parent=None):
        super().__init__(parent)
        self.agent = agent
        self.accent = ACCENTS.get(agent, "#888")
        self.state = A_WAITING
        self.turns = 0
        self._tick = 0
        self.setObjectName("agentPanel")

        self.name_label = QLabel(agent.upper())
        self.name_label.setObjectName("agentName")
        self.name_label.setStyleSheet(f"color: {self.accent};")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.avatar = QLabel()
        self.avatar.setPixmap(load_avatar(agent))
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedHeight(AVATAR_SIZE + 8)

        self.state_label = QLabel()
        self.state_label.setObjectName("agentState")
        self.turn_label = QLabel()
        self.turn_label.setObjectName("agentTurns")
        status_row = QHBoxLayout()
        status_row.addStretch()
        status_row.addWidget(self.state_label)
        status_row.addSpacing(18)
        status_row.addWidget(self.turn_label)
        status_row.addStretch()

        self.badge = QLabel("⚔ TECHNICAL DISAGREEMENT")
        self.badge.setObjectName("disagreeBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.hide()

        self.bubble = QLabel()
        self.bubble.setObjectName("speechBubble")
        self.bubble.setWordWrap(True)
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.bubble.setMinimumHeight(96)

        self.live_label = QLabel()
        self.live_label.setObjectName("liveOutput")
        self.live_label.setToolTip("Latest raw CLI output (not part of the conversation)")
        self.live_label.setMinimumWidth(10)
        self.live_label.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)
        layout.addWidget(self.name_label)
        layout.addWidget(self.avatar)
        layout.addLayout(status_row)
        layout.addWidget(self.badge)
        layout.addWidget(self.bubble, 1)
        layout.addWidget(self.live_label)

        self._timer = QTimer(self)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._animate)

        self.set_speech(None)
        self.set_state(A_WAITING)
        self.set_turns(0)

    # -- public -------------------------------------------------------------

    def set_state(self, state: str) -> None:
        self.state = state
        active = state in ACTIVE_STATES
        if active and not self._timer.isActive():
            self._tick = 0
            self._timer.start()
        elif not active:
            self._timer.stop()
            self.live_label.hide()
        self._render_state()
        colour = {A_ERROR: "#ff5d5d", A_COMPLETE: "#8fd9ff"}.get(state, self.accent if active else "#3a414c")
        width = 3 if active or state in (A_ERROR, A_COMPLETE) else 1
        self.setStyleSheet(f"#agentPanel {{ border: {width}px solid {colour}; }}")
        if state == A_STARTING:
            self.set_speech(None, working=True)

    def set_turns(self, turns: int) -> None:
        self.turns = turns
        self.turn_label.setText(f"Turns: {turns}")

    def set_speech(self, text: str | None, working: bool = False) -> None:
        if text:
            self.bubble.setText(text)
            self.bubble.setProperty("placeholder", False)
        else:
            self.bubble.setText("Working…" if working else "…")
            self.bubble.setProperty("placeholder", True)
        self.bubble.style().unpolish(self.bubble)
        self.bubble.style().polish(self.bubble)

    def set_live_output(self, line: str) -> None:
        if self.state not in ACTIVE_STATES:
            return
        line = " ".join(line.split())
        if not line:
            return
        metrics = self.live_label.fontMetrics()
        width = max(self.live_label.width() - 8, 120)
        self.live_label.setText(metrics.elidedText("▸ " + line, Qt.TextElideMode.ElideRight, width))
        self.live_label.show()

    def set_disagreement(self, on: bool) -> None:
        self.badge.setVisible(on)

    # -- internals ----------------------------------------------------------

    def _render_state(self) -> None:
        text = STATE_LABELS.get(self.state, self.state)
        if self.state in ACTIVE_STATES:
            text += "." * (self._tick % 4)
        self.state_label.setText(text)
        colour = {A_ERROR: "#ff5d5d", A_COMPLETE: "#8fd9ff", A_PAUSED: "#f5c542", A_STOPPED: "#aaa"}.get(
            self.state, self.accent if self.state in ACTIVE_STATES else "#8b93a1"
        )
        self.state_label.setStyleSheet(f"color: {colour};")

    def _animate(self) -> None:
        self._tick += 1
        self._render_state()
