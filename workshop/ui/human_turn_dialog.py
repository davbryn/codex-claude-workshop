from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from ..conversation import AGENTS


class HumanTurnDialog(QDialog):
    def __init__(self, default_agent: str = "Codex", reason: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Human Turn")
        self.resize(560, 360)

        intro = QLabel(
            "Your message is appended to conversation.md as a <b>Human — Intervention</b> "
            "entry, followed by a handoff to the agent you choose."
        )
        intro.setWordWrap(True)

        self.message = QPlainTextEdit()
        self.message.setPlaceholderText(
            "e.g. I think you're both overlooking persistence. Please resolve that before adding more UI work."
        )
        self.next_agent = QComboBox()
        self.next_agent.addItems(AGENTS)
        self.next_agent.setCurrentText(default_agent if default_agent in AGENTS else "Codex")
        self.resume = QCheckBox("Continue the workshop automatically after submitting")
        self.resume.setChecked(True)

        form = QFormLayout()
        form.addRow("Hand over to:", self.next_agent)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Submit")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        if reason:
            banner = QLabel(reason)
            banner.setWordWrap(True)
            banner.setStyleSheet("color: #f5c542; font-weight: bold;")
            layout.addWidget(banner)
        layout.addWidget(intro)
        layout.addWidget(self.message, 1)
        layout.addLayout(form)
        layout.addWidget(self.resume)
        layout.addWidget(buttons)
        self.message.setFocus()

    def _accept(self) -> None:
        if not self.message.toPlainText().strip():
            QMessageBox.warning(self, "Human Turn", "Please enter a message.")
            return
        self.accept()

    def values(self) -> tuple[str, str, bool]:
        return self.message.toPlainText().strip(), self.next_agent.currentText(), self.resume.isChecked()
