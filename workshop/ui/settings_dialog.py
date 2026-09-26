"""Compact Settings dialog: The Cast, Appearance, Audio, Personality."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import Settings, load_personalities
from ..theatre.cast import HOSTILITY_LEVELS, display_name
from ..theatre.speech import SpeechEngine

CUSTOM = "Custom"


def _slider(value: float, lo: int, hi: int) -> QSlider:
    s = QSlider(Qt.Orientation.Horizontal)
    s.setRange(lo, hi)
    s.setValue(int(round(value)))
    return s


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, speech: SpeechEngine, personalities: dict[str, str], parent=None,
                 sfx=None):
        super().__init__(parent)
        self.settings = settings
        self.speech = speech
        self.setWindowTitle("Workshop Settings")
        self.resize(640, 520)
        tabs = QTabWidget()

        # The Cast
        cast = QWidget()
        cform = QFormLayout(cast)
        self.cast_on = QCheckBox("Codex plays GILFOYLE, Claude plays DINESH (Silicon Valley cast)")
        self.cast_on.setChecked(settings.cast_enabled)
        cform.addRow(self.cast_on)
        self.hostility = QComboBox()
        self.hostility.addItems(list(HOSTILITY_LEVELS))
        self.hostility.setCurrentText(settings.hostility if settings.hostility in HOSTILITY_LEVELS
                                      else "Gilfoyle & Dinesh")
        cform.addRow("Hostility:", self.hostility)
        self.scoreboard = QCheckBox("Show the PETTY SCOREBOARD (deliberately unserious)")
        self.scoreboard.setChecked(settings.petty_scoreboard)
        cform.addRow(self.scoreboard)
        self.kanban = QCheckBox("Shared kanban board from management (KANBAN.md); their asides on it are read aloud")
        self.kanban.setChecked(settings.kanban_enabled)
        cform.addRow(self.kanban)
        self.timing = QCheckBox("Comic timing: short reaction beats between lines (under a second)")
        self.timing.setChecked(settings.comic_timing)
        cform.addRow(self.timing)
        cast_note = QLabel("The cast is a presentation layer. Every turn prompt tells Codex it is Gilfoyle and "
                           "Claude it is Dinesh, asks them to react to each other and bans assistant-speak, and "
                           "feeds a few factual callbacks from this session's public conversation. The protocol, "
                           "headings, handoffs and conversation.md are unchanged. \"Nuclear\" is ruder but must "
                           "stay technically productive.")
        cast_note.setWordWrap(True)
        cast_note.setObjectName("subtitle")
        cform.addRow(cast_note)
        tabs.addTab(cast, "The Cast")

        # Appearance
        appearance = QWidget()
        form = QFormLayout(appearance)
        self.animations = QCheckBox("Animate the characters")
        self.animations.setChecked(settings.animations)
        self.reduced = QCheckBox("Reduce motion (no bobbing, bouncing, shaking or particles)")
        self.reduced.setChecked(settings.reduced_motion)
        self.typewriter = QCheckBox("Typewriter effect in speech bubbles")
        self.typewriter.setChecked(settings.typewriter)
        self.theatre = QCheckBox("Start in Theatre Mode (F11)")
        self.theatre.setChecked(settings.theatre_mode)
        self.rivalry = QCheckBox("Rivalry: glares, side-eye, gloating and the occasional caption")
        self.rivalry.setChecked(settings.rivalry_mode)
        self.cuts = QCheckBox("Camera cuts: while an agent works, show his monitor full-size (readable code)")
        self.cuts.setChecked(settings.camera_cuts)
        for w in (self.animations, self.reduced, self.typewriter, self.theatre, self.rivalry, self.cuts):
            form.addRow(w)
        note = QLabel("All reactions are theatre, driven by public conversation text and observable CLI "
                      "events. They never affect the orchestration.")
        note.setWordWrap(True)
        note.setObjectName("subtitle")
        form.addRow(note)
        tabs.addTab(appearance, "Appearance")

        # Audio
        audio = QWidget()
        grid = QFormLayout(audio)
        self.speech_on = QCheckBox("Read new entries aloud (local text-to-speech)")
        self.speech_on.setChecked(settings.speech_enabled)
        grid.addRow(self.speech_on)
        from ..theatre.neural_tts import models_present

        self.engine = QComboBox()
        self.engine.addItem("Automatic (best available)", "auto")
        if models_present():
            self.engine.addItem("Kokoro neural voices (local, most natural)", "neural")
        self.engine.addItem("Windows system voices", "system")
        index = self.engine.findData(settings.speech_engine)
        self.engine.setCurrentIndex(max(0, index))
        grid.addRow("Voice engine:", self.engine)
        voices = speech.available_voices()
        self.voice = {}
        for agent, current in (("Codex", settings.codex_voice), ("Claude", settings.claude_voice)):
            combo = QComboBox()
            for voice in voices:
                combo.addItem(speech.voice_label(voice), voice)
            if not voices:
                combo.addItem("(no voices available)", "")
            combo.setEnabled(bool(voices))
            chosen = current if current in voices else speech.voice_for(agent)
            if chosen in voices:
                combo.setCurrentIndex(combo.findData(chosen))
            test = QPushButton("▶ Test")
            test.setEnabled(bool(voices))
            test.clicked.connect(lambda _=False, a=agent: self._test_voice(a))
            row = QHBoxLayout()
            row.addWidget(combo, 1)
            row.addWidget(test)
            holder = QWidget()
            holder.setLayout(row)
            grid.addRow(f"{display_name(agent)} voice:", holder)
            self.voice[agent] = combo
        self.rate = _slider(settings.speech_rate * 100, -60, 60)
        self.volume = _slider(settings.speech_volume * 100, 0, 100)
        grid.addRow("Speech rate:", self.rate)
        grid.addRow("Speech volume:", self.volume)
        self.sfx_on = QCheckBox("Sound effects (handoff, test chime, error buzz, fanfare…)")
        self.sfx_on.setChecked(settings.sfx_enabled)
        self.sfx_volume = _slider(settings.sfx_volume * 100, 0, 100)
        grid.addRow(self.sfx_on)
        self.sfx = sfx
        test_sfx = QPushButton("▶ Test")
        test_sfx.setEnabled(bool(sfx and sfx.available))
        test_sfx.clicked.connect(self._test_sfx)
        sfx_row = QHBoxLayout()
        sfx_row.addWidget(self.sfx_volume, 1)
        sfx_row.addWidget(test_sfx)
        sfx_holder = QWidget()
        sfx_holder.setLayout(sfx_row)
        grid.addRow("Effects volume:", sfx_holder)
        hint = "" if models_present() else (
            "<br>For much more natural voices, download the Kokoro model (~340 MB): "
            "<code>python -m workshop.theatre.neural_tts --download</code>")
        engine = QLabel(f"Active engine: {speech.name}" + ("" if speech.available() else " — unavailable; "
                        "the characters still animate their talking") + hint)
        engine.setObjectName("subtitle")
        engine.setWordWrap(True)
        grid.addRow(engine)
        tabs.addTab(audio, "Audio")

        # Personality
        personality = QWidget()
        pl = QGridLayout(personality)
        self.presets = load_personalities()
        self.preset = QComboBox()
        self.preset.addItems([*self.presets.keys(), CUSTOM])
        self.codex_text = QPlainTextEdit(personalities.get("Codex", ""))
        self.claude_text = QPlainTextEdit(personalities.get("Claude", ""))
        self.preset.setCurrentText(next((n for n, p in self.presets.items()
                                         if p == {"Codex": self.codex_text.toPlainText(),
                                                  "Claude": self.claude_text.toPlainText()}), CUSTOM))
        self.preset.currentTextChanged.connect(self._apply_preset)
        pl.addWidget(QLabel("Preset:"), 0, 0)
        pl.addWidget(self.preset, 0, 1)
        pl.addWidget(QLabel(f"{display_name('Codex')} personality:"), 1, 0, 1, 2)
        pl.addWidget(self.codex_text, 2, 0, 1, 2)
        pl.addWidget(QLabel(f"{display_name('Claude')} personality:"), 3, 0, 1, 2)
        pl.addWidget(self.claude_text, 4, 0, 1, 2)
        hint = QLabel("Changes apply from the next agent turn. Personality shapes tone only.")
        hint.setObjectName("subtitle")
        pl.addWidget(hint, 5, 0, 1, 2)
        tabs.addTab(personality, "Personality")

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _apply_preset(self, name: str) -> None:
        if name in self.presets:
            self.codex_text.setPlainText(self.presets[name]["Codex"])
            self.claude_text.setPlainText(self.presets[name]["Claude"])

    def _test_voice(self, agent: str) -> None:
        self.speech.set_voice(agent, self.voice[agent].currentData())
        self.speech.set_rate(self.rate.value() / 100)
        self.speech.set_volume(self.volume.value() / 100)
        line = {"Codex": "This is my voice. I didn't choose it to please you. It is, however, correct.",
                "Claude": "Okay, this voice is great. Way better than Gilfoyle's. Objectively. I checked."}[agent]
        self.speech.speak(agent, line)

    def _test_sfx(self) -> None:
        if self.sfx:
            was = self.sfx.enabled
            self.sfx.enabled = True
            self.sfx.set_volume(self.sfx_volume.value() / 100)
            self.sfx.play("yes")
            self.sfx.enabled = was

    def _accept(self) -> None:
        s = self.settings
        s.animations = self.animations.isChecked()
        s.reduced_motion = self.reduced.isChecked()
        s.typewriter = self.typewriter.isChecked()
        s.theatre_mode = self.theatre.isChecked()
        s.rivalry_mode = self.rivalry.isChecked()
        s.camera_cuts = self.cuts.isChecked()
        s.speech_enabled = self.speech_on.isChecked()
        new_engine = self.engine.currentData()
        if new_engine != s.speech_engine:
            s.speech_engine = new_engine
            s.codex_voice = s.claude_voice = ""  # voice ids differ between engines
        elif self.voice["Codex"].isEnabled():
            s.codex_voice = self.voice["Codex"].currentData()
            s.claude_voice = self.voice["Claude"].currentData()
        s.speech_rate = self.rate.value() / 100
        s.speech_volume = self.volume.value() / 100
        s.sfx_enabled = self.sfx_on.isChecked()
        s.sfx_volume = self.sfx_volume.value() / 100
        s.cast_enabled = self.cast_on.isChecked()
        s.hostility = self.hostility.currentText()
        s.petty_scoreboard = self.scoreboard.isChecked()
        s.comic_timing = self.timing.isChecked()
        s.kanban_enabled = self.kanban.isChecked()
        if self.preset.currentText() != CUSTOM:
            s.last_preset = self.preset.currentText()
        s.codex_personality = self.codex_text.toPlainText()
        s.claude_personality = self.claude_text.toPlainText()
        self.accept()

    def personalities(self) -> dict[str, str]:
        return {"Codex": self.codex_text.toPlainText(), "Claude": self.claude_text.toPlainText()}
