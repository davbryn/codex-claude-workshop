import random

from workshop.theatre.screens import IDLE_PAGES, ProjectDiffer, ScreenFeed


def test_differ_reports_real_changes_and_ignores_noise(tmp_path):
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("x = 1\n", encoding="utf-8")
    differ = ProjectDiffer(tmp_path)
    differ.baseline()
    (tmp_path / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "test_app.py").write_text("def test_add():\n    assert add(1, 2) == 3\n", encoding="utf-8")
    (tmp_path / ".venv" / "lib.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "conversation.md").write_text("## Codex - Turn 1\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\0\1\2")
    changes = {c.path: c for c in differ.changes()}
    assert set(changes) == {"app.py", "test_app.py"}
    assert ("del", "    return a - b") in changes["app.py"].lines
    assert ("add", "    return a + b") in changes["app.py"].lines
    assert changes["test_app.py"].created
    assert differ.changes() == []  # nothing new since the last scan
    (tmp_path / "app.py").unlink()
    gone = differ.changes()
    assert len(gone) == 1 and gone[0].deleted


def test_feed_modes():
    feed = ScreenFeed("Codex")
    feed.command("python -m pytest -q")
    feed.output("12 passed in 0.3s")
    assert feed.mode == "terminal" and list(feed.lines)[-1] == ("out", "12 passed in 0.3s")
    feed.narrate()
    feed.output("I'll now look at the parser.")  # narration isn't command output
    assert list(feed.lines)[-1] == ("out", "12 passed in 0.3s")
    feed.read("src/parser.py", ["import re", "def parse(x):"])
    assert feed.mode == "reader" and feed.title == "src/parser.py" and len(feed.lines) == 2
    feed.go_idle(random.Random(1))
    assert feed.mode == "idle" and feed.page in IDLE_PAGES["Codex"]


def test_idle_pages_are_parody_set_dressing_not_agent_quotes():
    for agent, pages in IDLE_PAGES.items():
        assert len(pages) >= 4
        for page in pages:
            text = " ".join(page.lines).lower()
            assert "gilfoyle:" not in text and "dinesh:" not in text  # never scripted lines "said" by the agents


def test_director_shows_files_only_inside_the_project(qapp, tmp_path):
    from workshop.agents.fake import FakeAdapter
    from workshop.orchestrator import Orchestrator
    from workshop.project import ensure_protocol_file, start_new_conversation
    from workshop.theatre.director import Director
    from workshop.theatre.sfx import SoundEffects
    from workshop.theatre.speech import NullSpeechEngine
    from workshop.ui.stage import StageWidget

    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "x", "Codex")
    (tmp_path / "parser.py").write_text("import re\n", encoding="utf-8")
    o = Orchestrator(tmp_path, {a: FakeAdapter(a) for a in ("Codex", "Claude")}, {})
    d = Director(o, StageWidget(), NullSpeechEngine(), SoundEffects(False))
    d._on_output_line("Claude", "[tool] Read: parser.py")
    assert d.screens["Claude"].mode == "reader" and d.screens["Claude"].title == "parser.py"
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    d._on_output_line("Codex", "exec")
    d._on_output_line("Codex", f'"powershell.exe" -Command "Get-Content {outside}"')
    assert d.screens["Codex"].mode == "terminal"  # the command shows; the outside file does not
    d.shutdown()


def test_prompt_echo_is_not_shown_as_command_output(qapp, tmp_path):
    from workshop.agents.fake import FakeAdapter
    from workshop.orchestrator import Orchestrator
    from workshop.project import ensure_protocol_file, start_new_conversation
    from workshop.theatre.director import Director
    from workshop.theatre.sfx import SoundEffects
    from workshop.theatre.speech import NullSpeechEngine
    from workshop.ui.stage import StageWidget

    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "x", "Codex")
    o = Orchestrator(tmp_path, {a: FakeAdapter(a) for a in ("Codex", "Claude")}, {})
    d = Director(o, StageWidget(), NullSpeechEngine(), SoundEffects(False))
    d.on_turn_started("Codex", 1)
    for line in ("OpenAI Codex v0.47", "user", "[CORE WORKSHOP RULES]", "The very last non-empty line…"):
        d._on_output_line("Codex", line)
    assert all(kind != "out" for kind, _ in d.screens["Codex"].lines)  # Codex echoing its prompt stays off screen
    d._on_output_line("Codex", "exec")
    d._on_output_line("Codex", '"powershell.exe" -Command "python -m pytest -q"')
    d._on_output_line("Codex", "3 passed in 0.02s")
    assert list(d.screens["Codex"].lines)[-1] == ("out", "3 passed in 0.02s")
    d.shutdown()
