"""Offscreen end-to-end test of the main window driven by fake agents."""

from workshop import orchestrator as orch
from workshop.agents.fake import FakeAdapter
from workshop.config import Settings
from workshop.conversation import parse_conversation, read_conversation
from workshop.orchestrator import Orchestrator
from workshop.project import ensure_protocol_file, start_new_conversation
from workshop.ui.human_turn_dialog import HumanTurnDialog
from workshop.ui.main_window import MainWindow
from workshop.ui.setup_dialog import SetupDialog


def test_main_window_full_flow(qapp, wait, tmp_path):
    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "Build a to-do app.", "Codex")
    adapters = {a: FakeAdapter(a, delay=0.2, complete_after=3) for a in ("Codex", "Claude")}
    o = Orchestrator(tmp_path, adapters, {}, poll_ms=50)
    settings = Settings()
    settings.save = lambda *a, **k: None  # don't touch the real config dir
    w = MainWindow(o, settings, fake_agents=True)
    w.show()
    o.start()

    codex, claude = w.panels["Codex"], w.panels["Claude"]
    assert codex.state == orch.A_STARTING and codex.bubble.text() == "Working…"
    assert not w.human_button.isEnabled()

    # Codex hands off to Claude; Claude starts.
    assert wait(lambda: o.current_agent == "Claude")
    assert codex.turns == 1 and "ruin anything" in codex.bubble.text()
    assert "GILFOYLE (Codex)  •  Turn 1" in w.conversation.toPlainText()
    assert "[fake Codex]" in w.outputs["Codex"].toPlainText()

    # Pause: Claude finishes, Codex does not start.
    w.pause_button.click()
    assert w.pause_button.text() == "Cancel Pause"
    assert wait(lambda: o.state == orch.PAUSED)
    assert "Resume" in w.pause_button.text() and w.human_button.isEnabled()
    assert "PAUSED" in w.banner.text()
    n = len(parse_conversation(read_conversation(o.conversation_path)))

    # Human intervention, then continue.
    dialog = HumanTurnDialog("Codex", parent=w)
    dialog.message.setPlainText("Please add persistence before more UI.")
    dialog.next_agent.setCurrentText("Codex")
    message, agent, resume = dialog.values()
    o.submit_human_turn(message, agent, resume)
    turns = parse_conversation(read_conversation(o.conversation_path))
    assert turns[n].speaker == "Human" and "persistence" in turns[n].content

    assert wait(lambda: o.state == orch.COMPLETE, timeout=40)
    assert "PROJECT COMPLETE" in w.banner.text()
    assert codex.state == claude.state == orch.A_COMPLETE
    assert not w.pause_button.isEnabled() and not w.stop_button.isEnabled()
    text = w.conversation.toPlainText()
    assert "YOU  •  Intervention" in text and "PROJECT COMPLETE" in text
    w.close()


def test_error_is_visible(qapp, wait, tmp_path):
    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "x", "Claude")
    adapters = {
        "Codex": FakeAdapter("Codex", delay=0.05),
        "Claude": FakeAdapter("Claude", delay=0.05, behavior="fail"),
    }
    o = Orchestrator(tmp_path, adapters, {}, poll_ms=50)
    settings = Settings()
    settings.save = lambda *a, **k: None
    w = MainWindow(o, settings, fake_agents=True)
    o.start()
    assert wait(lambda: o.state == orch.NEEDS_ATTENTION)
    assert "CLAUDE ERROR" in w.banner.text() and "Exit code: 1" in w.banner.text()
    assert "simulated crash" in w.outputs["Claude"].toPlainText()
    assert w.panels["Claude"].state == orch.A_ERROR
    w.close()


def test_setup_dialog_builds(qapp):
    settings = Settings()
    settings.save = lambda *a, **k: None
    d = SetupDialog(settings, fake_agents=True)
    assert d.preset_combo.count() >= 6  # 5 presets + Custom
    d.preset_combo.setCurrentText("Professional")
    assert "senior engineer" in d.codex_edit.toPlainText()
    d.codex_edit.setPlainText("something else")
    assert d.preset_combo.currentText() == "Custom"
