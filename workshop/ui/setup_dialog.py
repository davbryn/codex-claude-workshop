from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings, load_personalities, save_personality_preset
from ..project import CONVERSATION_FILE, safety_warning

CUSTOM = "Custom"


@dataclass
class SetupResult:
    project_dir: Path
    prompt: str
    codex_personality: str
    claude_personality: str
    first_agent: str
    continue_existing: bool
    challenge: bool = False  # spin the Wheel of Destiny first


class SetupDialog(QDialog):
    def __init__(self, settings: Settings, fake_agents: bool = False, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.result_value: SetupResult | None = None
        self.setWindowTitle("Codex ↔ Claude Workshop — Setup")
        self.resize(820, 820)

        title = QLabel("CODEX ↔ CLAUDE WORKSHOP")
        title.setObjectName("title")

        # project directory
        self.project_edit = QLineEdit(settings.last_project_directory)
        self.project_edit.setPlaceholderText(r"C:\Dev\MyProject")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        project_row = QHBoxLayout()
        project_row.addWidget(self.project_edit, 1)
        project_row.addWidget(browse)

        self.prompt_edit = QPlainTextEdit(settings.last_prompt)
        self.prompt_edit.setPlaceholderText("Build a small NES-style virtual machine with a debugger…")

        # personalities
        self.presets = load_personalities()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([*self.presets.keys(), CUSTOM])
        save_preset = QPushButton("Save Preset…")
        save_preset.clicked.connect(self._save_preset)
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(save_preset)

        self.codex_edit = QPlainTextEdit()
        self.claude_edit = QPlainTextEdit()
        personalities = QGridLayout()
        personalities.addWidget(QLabel("Codex personality:"), 0, 0)
        personalities.addWidget(QLabel("Claude personality:"), 0, 1)
        personalities.addWidget(self.codex_edit, 1, 0)
        personalities.addWidget(self.claude_edit, 1, 1)

        if settings.codex_personality or settings.claude_personality:
            self.codex_edit.setPlainText(settings.codex_personality)
            self.claude_edit.setPlainText(settings.claude_personality)
            self._sync_combo_to_text(settings.last_preset)
        else:
            self.preset_combo.setCurrentText(settings.last_preset if settings.last_preset in self.presets else "Rivals")
            self._apply_preset(self.preset_combo.currentText())
        self.preset_combo.currentTextChanged.connect(self._apply_preset)
        self.codex_edit.textChanged.connect(lambda: self._sync_combo_to_text())
        self.claude_edit.textChanged.connect(lambda: self._sync_combo_to_text())

        # first agent
        self.first_codex = QRadioButton("Codex")
        self.first_claude = QRadioButton("Claude")
        (self.first_claude if settings.first_agent == "Claude" else self.first_codex).setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.first_codex)
        group.addButton(self.first_claude)
        first_row = QHBoxLayout()
        first_row.addWidget(QLabel("First turn:"))
        first_row.addWidget(self.first_codex)
        first_row.addWidget(self.first_claude)
        first_row.addStretch()

        # advanced CLI settings
        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("Advanced: agent commands ▸")
        self.advanced_toggle.setCheckable(True)
        self.advanced = QGroupBox()
        adv = QFormLayout(self.advanced)
        self.codex_cmd = QLineEdit(settings.codex_command)
        self.codex_args = QLineEdit(shlex.join(settings.codex_args))
        self.claude_cmd = QLineEdit(settings.claude_command)
        self.claude_args = QLineEdit(shlex.join(settings.claude_args))
        adv.addRow("Codex executable:", self.codex_cmd)
        adv.addRow("Codex extra args:", self.codex_args)
        adv.addRow("Claude executable:", self.claude_cmd)
        adv.addRow("Claude extra args:", self.claude_args)
        note = QLabel(
            "Codex runs as <code>codex exec … &lt;extra args&gt; -</code>; Claude as "
            "<code>claude -p --output-format stream-json --verbose &lt;extra args&gt;</code>. "
            "Prompts are sent on stdin."
            + ("<br><b>Fake-agent mode is on: these settings are ignored.</b>" if fake_agents else "")
        )
        note.setWordWrap(True)
        adv.addRow(note)
        self.advanced.setVisible(False)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)

        warning = QLabel(
            "⚠ Both agents run with permission to <b>edit files and run commands</b>. They start in the selected "
            "project directory and are instructed to work only there. Codex also uses its CLI sandbox, which limits "
            "its writes to the project and temp folders. Claude Code has no such OS-level boundary: its shell "
            "commands could reach files outside the project, depending on your Claude Code configuration. "
            "Use a directory you are happy for them to change."
            + ("<br><b>FAKE AGENTS:</b> no real Codex/Claude usage will be consumed." if fake_agents else "")
        )
        warning.setWordWrap(True)
        warning.setObjectName("warningText")

        start = QPushButton("Start Workshop")
        start.setObjectName("startButton")
        start.setDefault(True)
        start.clicked.connect(self._start)
        cancel = QPushButton("Quit")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(start)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(QLabel("Project directory:"))
        layout.addLayout(project_row)
        layout.addWidget(QLabel("What should they build?"))
        layout.addWidget(self.prompt_edit, 2)
        self.challenge_box = QCheckBox("🎡 Spin the Wheel of Destiny first (skill levels, language, a limitation, and a "
                                       "twist halfway). Leave the prompt empty and the wheel picks the project too.")
        layout.addWidget(self.challenge_box)
        layout.addLayout(preset_row)
        layout.addLayout(personalities, 3)
        layout.addLayout(first_row)
        layout.addWidget(self.advanced_toggle)
        layout.addWidget(self.advanced)
        layout.addWidget(warning)
        layout.addLayout(buttons)

    # -- presets ------------------------------------------------------------

    def _apply_preset(self, name: str) -> None:
        preset = self.presets.get(name)
        if preset is None:
            return
        for edit, text in ((self.codex_edit, preset["Codex"]), (self.claude_edit, preset["Claude"])):
            edit.blockSignals(True)
            edit.setPlainText(text)
            edit.blockSignals(False)

    def _sync_combo_to_text(self, preferred: str | None = None) -> None:
        codex, claude = self.codex_edit.toPlainText(), self.claude_edit.toPlainText()
        names = [preferred] if preferred else []
        names += list(self.presets)
        match = next(
            (n for n in names if n in self.presets and self.presets[n] == {"Codex": codex, "Claude": claude}),
            CUSTOM,
        )
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText(match)
        self.preset_combo.blockSignals(False)

    def _save_preset(self) -> None:
        current = self.preset_combo.currentText()
        name, ok = QInputDialog.getText(
            self, "Save Preset", "Preset name:", text="" if current == CUSTOM else current
        )
        name = name.strip()
        if not ok or not name:
            return
        if name == CUSTOM:
            QMessageBox.warning(self, "Save Preset", f"'{CUSTOM}' is reserved; choose another name.")
            return
        save_personality_preset(name, self.codex_edit.toPlainText(), self.claude_edit.toPlainText())
        self.presets = load_personalities()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems([*self.presets.keys(), CUSTOM])
        self.preset_combo.setCurrentText(name)
        self.preset_combo.blockSignals(False)

    # -- misc ---------------------------------------------------------------

    def _toggle_advanced(self, on: bool) -> None:
        self.advanced.setVisible(on)
        self.advanced_toggle.setText("Advanced: agent commands " + ("▾" if on else "▸"))

    def _browse(self) -> None:
        start = self.project_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Choose project directory", start)
        if chosen:
            self.project_edit.setText(str(Path(chosen)))

    def _start(self) -> None:
        raw = self.project_edit.text().strip().strip('"')
        if not raw:
            QMessageBox.warning(self, "Project directory", "Please choose a project directory.")
            return
        project = Path(raw).expanduser()
        if project.exists() and not project.is_dir():
            QMessageBox.warning(self, "Project directory", f"{project} is not a directory.")
            return
        if not project.exists():
            if (
                QMessageBox.question(self, "Project directory", f"{project} does not exist. Create it?")
                != QMessageBox.StandardButton.Yes
            ):
                return
            project.mkdir(parents=True)

        warning = safety_warning(project)
        if warning:
            answer = QMessageBox.warning(
                self,
                "Are you sure?",
                f"{warning}\n\nThe agents will be able to modify files and run commands anywhere inside it "
                "(and Claude Code's shell commands are not confined to it at all). "
                "It is strongly recommended to use a dedicated project folder.\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        continue_existing = False
        if (project / CONVERSATION_FILE).exists():
            box = QMessageBox(self)
            box.setWindowTitle("Existing workshop")
            box.setText(f"{CONVERSATION_FILE} already exists in this project.")
            box.setInformativeText(
                "Continue the existing workshop from its latest handoff, or start a new conversation? "
                "(Starting new keeps a timestamped backup of the old one.)"
            )
            cont = box.addButton("Continue existing workshop", QMessageBox.ButtonRole.AcceptRole)
            new = box.addButton("Start new conversation", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is cont:
                continue_existing = True
            elif box.clickedButton() is not new:
                return

        prompt = self.prompt_edit.toPlainText().strip()
        if not continue_existing and not prompt and not self.challenge_box.isChecked():
            QMessageBox.warning(self, "Project prompt", "Please describe what they should build.")
            return

        try:
            codex_args = shlex.split(self.codex_args.text())
            claude_args = shlex.split(self.claude_args.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Advanced settings", f"Could not parse extra args: {exc}")
            return

        first = "Claude" if self.first_claude.isChecked() else "Codex"
        s = self.settings
        s.last_project_directory = str(project)
        s.last_prompt = prompt
        s.first_agent = first
        s.last_preset = self.preset_combo.currentText()
        s.codex_personality = self.codex_edit.toPlainText()
        s.claude_personality = self.claude_edit.toPlainText()
        s.codex_command = self.codex_cmd.text().strip() or "codex"
        s.claude_command = self.claude_cmd.text().strip() or "claude"
        s.codex_args = codex_args
        s.claude_args = claude_args
        s.save()

        self.result_value = SetupResult(
            project_dir=project,
            prompt=prompt,
            codex_personality=s.codex_personality,
            claude_personality=s.claude_personality,
            first_agent=first,
            continue_existing=continue_existing,
            challenge=self.challenge_box.isChecked() and not continue_existing,
        )
        self.accept()
