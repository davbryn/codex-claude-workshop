"""Offscreen tests for the theatre layer wired into the real main window."""

from PySide6.QtCore import QTimer

from workshop import orchestrator as orch
from workshop.agents.fake import FakeAdapter
from workshop.config import Settings
from workshop.orchestrator import Orchestrator
from workshop.project import ensure_protocol_file, start_new_conversation
from workshop.theatre.speech import SpeechEngine
from workshop.ui.main_window import MainWindow


class RecordingSpeech(SpeechEngine):
    """A speech engine that 'speaks' instantly and records what it was asked to say."""

    name = "recording"

    def __init__(self):
        super().__init__()
        self.calls = []

    def available(self):
        return True

    def available_voices(self):
        return ["Voice A", "Voice B"]

    def speak(self, agent, text):
        self.calls.append((agent, text))
        self.started.emit(agent)
        QTimer.singleShot(50, lambda: self.finished.emit(agent))
        return True


def make_window(tmp_path, speech=None, pace=False, **settings_kw):
    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "Build a to-do app.", "Codex")
    adapters = {a: FakeAdapter(a, delay=0.05, complete_after=2) for a in ("Codex", "Claude")}
    o = Orchestrator(tmp_path, adapters, {}, poll_ms=50)
    settings = Settings(**settings_kw)
    settings.save = lambda *a, **k: None
    w = MainWindow(o, settings, fake_agents=True, speech=speech, pace=pace)
    return o, w


def test_entries_are_spoken_and_mute_silences_them(qapp, wait, tmp_path):
    speech = RecordingSpeech()
    o, w = make_window(tmp_path, speech=speech, pace=True)
    w.show()
    o.start()
    assert wait(lambda: any(a == "Codex" for a, _ in speech.calls))
    agent, text = speech.calls[0]
    assert "ruin anything" in text and "@" not in text  # public text, cleaned for speech
    w.mute_button.click()
    assert w.director.muted and "🔇" in w.mute_button.text()
    before = len(speech.calls)
    assert wait(lambda: w.stage.views["Claude"].turns >= 1)
    assert wait(lambda: w.director.presentation_idle(), timeout=15)
    assert len(speech.calls) == before  # muted: nothing new spoken, but the bubble still shows
    assert w.stage.views["Claude"].bubble.text()
    w.mute_button.click()
    assert not w.director.muted
    o.stop()
    assert wait(lambda: not o.is_busy())
    w.close()


def test_no_speech_engine_still_animates_talking(qapp, wait, tmp_path):
    o, w = make_window(tmp_path)  # WORKSHOP_NO_AUDIO → silent engine
    assert not w.speech.available()
    o.start()
    assert wait(lambda: w.stage.models["Codex"].talking)  # timer-driven talking
    assert wait(lambda: not w.stage.models["Codex"].talking, timeout=15)
    o.stop()
    assert wait(lambda: not o.is_busy())
    w.close()


def test_theatre_mode_hides_diagnostics_but_keeps_conversation(qapp, tmp_path):
    o, w = make_window(tmp_path)
    w.show()
    w.theatre_button.setChecked(True)
    assert not w.header.isVisible()
    assert not w.tabs.isTabVisible(1) and not w.tabs.isTabVisible(2)
    assert w.tabs.currentIndex() == 0 and w.settings.theatre_mode
    w.theatre_button.setChecked(False)
    assert w.header.isVisible() and w.tabs.isTabVisible(1)
    w.close()


def test_completion_celebration_and_waiting_card(qapp, wait, tmp_path):
    o, w = make_window(tmp_path)
    o.start()
    assert wait(lambda: o.state == orch.COMPLETE, timeout=40)
    assert wait(lambda: "complete" in w.stage.cards, timeout=20)
    card = w.stage.cards["complete"]
    assert card.title.endswith("PROJECT COMPLETE") and card.tagline == "Somehow."
    assert any("agent turns" in line for line in card.lines)
    assert all(v.state == orch.A_COMPLETE for v in w.stage.views.values())
    w.close()


def test_status_strip_shows_factual_state(qapp, wait, tmp_path):
    o, w = make_window(tmp_path)
    o.start()
    assert wait(lambda: w.stage.views["Codex"].turns >= 1)
    w._update_strip()
    assert w.chip_turn.text().startswith("TURN ")
    assert "Gilfoyle" in w.chip_agents["Codex"].text()
    assert w.chip_tests.isHidden()  # the normal fake agents print no test summaries
    o.stop()
    assert wait(lambda: not o.is_busy())
    w.close()
