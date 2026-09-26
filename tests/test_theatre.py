"""Tests for the Workshop Theatre's non-visual logic."""

import json
import sys

import pytest

from workshop import orchestrator as orch
from workshop.agents.demo_script import DEMO_PROMPT, DEMO_TURNS, demo_entry
from workshop.agents.fake import FakeAdapter
from workshop.config import Settings, load_personalities, load_personas, save_personality_preset
from workshop.conversation import ConversationTurn, get_control_signal, parse_conversation, read_conversation
from workshop.orchestrator import Orchestrator
from workshop.project import ensure_protocol_file, start_new_conversation
from workshop.theatre.avatar_state import DEFAULT_PERSONAS, STATES, AvatarModel, Persona
from workshop.theatre.reactions import ActivityTracker, asks_for_review, classify_entry
from workshop.theatre.speech import NullSpeechEngine, create_speech_engine
from workshop.theatre.stats import RunStats, completion_lines, summarise_conversation
from workshop.theatre.text import bubble_excerpt, clean_for_speech, sections, speech_text, strip_markdown


def turn(speaker: str, content: str, number: int = 1) -> ConversationTurn:
    return ConversationTurn(speaker, f"Turn {number}", number, content, None)


# --- reaction classifier ------------------------------------------------------

@pytest.mark.parametrize("text", [
    "I disagree with this approach.",
    "Honestly the wrapper is over-engineered.",
    "Codex is wrong about the cache.",
    "This is an unnecessary abstraction.",
])
def test_disagreement(text):
    r = classify_entry(turn("Claude", text))
    assert r.disagreement and r.primary_state() == "disagreeing"
    assert r.listener_state(rivalry=True) == "annoyed"
    assert r.listener_state(rivalry=False) == "confused"


def test_admission_and_concession():
    r = classify_entry(turn("Codex", "My mistake. Claude was right about the save path."))
    assert r.self_admission and r.concedes_other and r.primary_state() == "embarrassed"
    assert r.listener_state() == "smug"
    assert classify_entry(turn("Claude", "Good catch, you're right.")).concedes_other


def test_success_and_strong_success():
    assert classify_entry(turn("Codex", "Fixed it; the tests pass.")).primary_state() == "pleased"
    strong = classify_entry(turn("Claude", "All 12 tests pass."))
    assert strong.strong_success and strong.primary_state() == "celebrating" and strong.test_count == 12


def test_fixing_the_other_agents_bug_and_own_mistake():
    other = classify_entry(turn("Claude", "Codex's delete command crashed on index 99. I fixed it."))
    assert other.fixed_other_bug and other.listener_state() == "embarrassed"
    own = classify_entry(turn("Claude", "I also fixed my own earlier bug in the store."))
    assert own.fixed_own_mistake and not own.fixed_other_bug and own.primary_state() == "pleased"


def test_protocol_markers_and_neutral_text():
    assert classify_entry(turn("Codex", "Done.\n\nPROPOSE PROJECT COMPLETE\n\n@Claude")).proposes_completion
    assert classify_entry(turn("Claude", "Verified.\n\nPROJECT COMPLETE")).primary_state() == "celebrating"
    assert classify_entry(turn("Codex", "HUMAN DECISION NEEDED: tabs?")).primary_state() == "waiting"
    assert classify_entry(turn("Codex", "Renamed a variable.")).primary_state() == "idle"


def test_code_blocks_do_not_trigger_reactions():
    r = classify_entry(turn("Claude", "Updated docs.\n\n```\n# I disagree, this is over-engineered\n```"))
    assert not r.disagreement


def test_asks_for_review():
    assert asks_for_review(turn("Codex", "**Next**\n\nClaude, please review the parser.\n\n@Claude"))
    assert asks_for_review(turn("Codex", "PROPOSE PROJECT COMPLETE\n\n@Claude"))
    assert not asks_for_review(turn("Codex", "**Next**\n\nAdd the CLI.\n\n@Claude"))
    assert not asks_for_review(None)


# --- CLI activity parsing -------------------------------------------------------

def test_activity_from_claude_tool_lines():
    t = ActivityTracker()
    assert t.feed("[tool] Read: C:\\proj\\src\\parser.py").activity == "Reading parser.py…"
    edit = t.feed("[tool] Edit: /proj/src/parser.py")
    assert edit.activity == "Editing parser.py…" and edit.kind == "edit"
    t.feed("[tool] Write: /proj/tests/test_parser.py")
    assert t.files_edited == {"parser.py", "test_parser.py"}
    assert t.feed("[tool] Bash: python -m pytest -q").activity == "Running tests…"
    assert t.feed("[tool] Bash: git status").activity == "Checking git…"


def test_activity_from_codex_exec_lines():
    t = ActivityTracker()
    assert not t.feed("exec")
    cue = t.feed('"C:\\\\WINDOWS\\\\powershell.exe" -Command "python -m unittest -v test_greet"')
    assert cue.activity == "Running tests…" and cue.kind == "test"
    t.feed("exec")
    assert t.feed('"powershell.exe" -Command "Get-Content greet.py"').kind == "read"


@pytest.mark.parametrize("lines, passed, failed, ok", [
    (["===== 12 passed in 0.31s ====="], 12, 0, True),
    (["2 failed, 10 passed in 1.2s"], 10, 2, False),
    (["[tool result] 7 passed in 0.04s"], 7, 0, True),
    (["Ran 5 tests in 0.002s", "", "OK"], 5, 0, True),
    (["Tests:       1 failed, 4 passed, 5 total"], 4, 1, False),
    (["test result: ok. 9 passed; 0 failed; 0 ignored"], 9, 0, True),
])
def test_test_summaries(lines, passed, failed, ok):
    t = ActivityTracker()
    cues = [t.feed(line) for line in lines]
    cue = next(c for c in reversed(cues) if c.tests_passed is not None or c.tests_failed)
    assert (cue.tests_passed, cue.tests_failed or 0, cue.tests_ok) == (passed, failed, ok)


def test_errors_and_noise():
    t = ActivityTracker()
    assert t.feed("Traceback (most recent call last):").error
    assert not t.feed("(the outcome, including test results)")  # Codex prompt echo
    assert not t.feed("All tests pass, I think.")  # prose is not a test summary


# --- text extraction -------------------------------------------------------------

ENTRY = """**Thoughts**

Oh no. Codex has built *another* factory — see `src/app/factory.py`. I have concerns. 🎭

**Actions**

```python
class FactoryFactory: ...
```

**Result**

All 8 tests pass: `C:\\proj\\tests\\test_app.py` included.

**Next**

Codex, please justify the factory.

@Codex"""


def test_sections_and_markdown():
    s = sections(ENTRY)
    assert set(s) >= {"thoughts", "actions", "result", "next"}
    plain = strip_markdown(ENTRY)
    assert "class FactoryFactory" not in plain and "@Codex" not in plain and "*" not in plain


def test_bubble_excerpt_is_short_conversational_and_code_free():
    bubble = bubble_excerpt(ENTRY, limit=240)
    assert bubble.startswith("Oh no. Codex has built another factory")
    assert "class" not in bubble and len(bubble) <= 241


def test_speech_text_strips_code_paths_emoji_and_handoffs():
    speech = speech_text(ENTRY)
    assert "factory.py" in speech and "src/app" not in speech
    assert "🎭" not in speech and "@" not in speech and "FactoryFactory" not in speech
    assert "justify the factory" in speech
    assert len(speech) <= 300


def test_long_text_is_capped():
    long_entry = "**Thoughts**\n\n" + "This sentence is quite long indeed. " * 40
    assert len(speech_text(long_entry, limit=200)) <= 201
    assert len(bubble_excerpt(long_entry, limit=120)) <= 121


def test_clean_for_speech():
    assert clean_for_speech("@Claude — see /a/b/c.py ✨") == "Claude, see c.py"


# --- avatar state machine ------------------------------------------------------------

def test_every_state_produces_a_pose():
    for state in STATES:
        m = AvatarModel("Claude", seed=1)
        m.react(state, 2.0) if state not in ("idle", "waiting", "coding") else m.set_base(state)
        m.update(0.1)
        pose = m.pose()
        assert pose.state in STATES


def test_layering_talking_reaction_base():
    m = AvatarModel("Codex", seed=1)
    m.set_base("coding")
    assert m.effective_state() == "coding"
    m.react("disagreeing", None)
    m.set_talking(True)
    assert m.effective_state() == "talking" and m.expression_state() == "disagreeing"
    m.set_talking(False)
    m.release(after=1.0)
    m.update(0.5)
    assert m.effective_state() == "disagreeing"
    m.update(0.6)
    assert m.effective_state() == "coding"


def test_talking_moves_the_mouth_and_reduced_motion_is_still():
    m = AvatarModel("Claude", seed=2)
    m.set_talking(True)
    openings = set()
    for _ in range(30):
        m.update(0.03)
        openings.add(round(m.pose().mouth_open, 2))
    assert len(openings) > 5
    m.motion = 0.0
    m.set_talking(False)
    m.react("celebrating")
    m.update(0.2)
    pose = m.pose()
    assert pose.bob == 0 and pose.shake == 0 and pose.tilt == 0


def test_persona_changes_expression():
    confident = AvatarModel("Codex", Persona("confident", 0.3, 0.5))
    confident.react("pleased", None)
    confident.update(1.5)  # expressions ease in rather than snapping
    assert confident.pose().mouth == "smug"
    dramatic = AvatarModel("Claude", Persona("dramatic", 0.8, 1.0))
    dramatic.react("disagreeing", None)
    dramatic.update(1.5)
    assert dramatic.pose().brow_angle > confident.pose().brow_angle


def test_reactions_expire():
    m = AvatarModel("Codex", seed=3)
    m.react("surprised", 0.5)
    m.update(0.6)
    assert m.reaction is None


# --- stats -------------------------------------------------------------------------

def test_stats_are_factual():
    text = start_text() + "".join(demo_entry(t, i // 2 + 1) for i, t in enumerate(DEMO_TURNS[:3]))
    summary = summarise_conversation(parse_conversation(text))
    assert summary.turns == {"Codex": 2, "Claude": 1}
    assert summary.disagreements >= 1 and summary.corrections >= 1
    stats = RunStats()
    lines = completion_lines(summary, stats)
    assert not any("tests passing" in line for line in lines)  # nothing captured → nothing claimed
    stats.record_tests(9, 0, True)
    assert any("9 tests passing" in line for line in completion_lines(summary, stats))


def test_streaks():
    stats = RunStats()
    for i in range(3):
        stats.record_entry(turn("Codex", "x"), handed_off=True, disagreement=True)
    assert stats.handoff_streak == 3 and stats.disagreement_streak == 3
    stats.record_entry(turn("Claude", "x"), handed_off=False, disagreement=False)
    assert stats.handoff_streak == 0 and stats.disagreement_streak == 0 and stats.best_streak == 3


def start_text() -> str:
    from workshop.conversation import new_conversation_text

    return new_conversation_text(DEMO_PROMPT, "Codex")


# --- speech fallback ----------------------------------------------------------------

def test_speech_disabled_by_environment_falls_back(qapp):
    engine = create_speech_engine()  # WORKSHOP_NO_AUDIO=1 in conftest
    assert isinstance(engine, NullSpeechEngine)
    assert not engine.available() and engine.speak("Codex", "hello") is False
    assert engine.available_voices() == []


def test_speech_falls_back_when_no_engine_is_installed(qapp, monkeypatch):
    monkeypatch.delenv("WORKSHOP_NO_AUDIO", raising=False)
    monkeypatch.setitem(sys.modules, "kokoro_onnx", None)  # neural engine missing
    monkeypatch.setitem(sys.modules, "PySide6.QtTextToSpeech", None)  # system voices missing
    assert isinstance(create_speech_engine(), NullSpeechEngine)


def test_system_preference_skips_neural_engine(qapp, monkeypatch):
    monkeypatch.delenv("WORKSHOP_NO_AUDIO", raising=False)
    monkeypatch.setitem(sys.modules, "PySide6.QtTextToSpeech", None)
    engine = create_speech_engine(preference="system")
    assert "Kokoro" not in engine.name


def test_neural_streaming_helpers():
    from workshop.theatre.neural_tts import split_for_streaming, voice_label

    chunks = split_for_streaming(
        "I disagree, strongly and at length, with the notion that a global list is architecture. "
        "It is not. Todos vanish on exit!")
    assert chunks[0].endswith(",") and len(chunks[0]) < 60  # first chunk short → audio starts fast
    assert " ".join(chunks).replace("  ", " ").startswith("I disagree")
    assert voice_label("am_michael") == "Michael (American male)"
    assert voice_label("bf_emma") == "Emma (British female)"


# --- settings & presets ----------------------------------------------------------------

def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings(speech_muted=True, codex_voice="Microsoft Mark", speech_rate=0.3, theatre_mode=True)
    s.save(path)
    loaded = Settings.load(path)
    assert (loaded.speech_muted, loaded.codex_voice, loaded.speech_rate, loaded.theatre_mode) == (
        True, "Microsoft Mark", 0.3, True)


def test_old_settings_files_still_load(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"codex_command": "codex", "unknown_future_key": 1}), encoding="utf-8")
    loaded = Settings.load(path)
    assert loaded.animations and loaded.sfx_enabled


def test_presets_and_personas():
    presets = load_personalities()
    assert {"Rivals", "Professional", "Odd Couple", "Chaos", "Professor & Cowboy"} <= set(presets)
    assert "best programmer in the room" in presets["Rivals"]["Codex"]
    personas = load_personas("Rivals")
    assert personas["Codex"].animation_style == "confident" and personas["Claude"].reaction_strength > 0.8
    assert load_personas("No such preset") == DEFAULT_PERSONAS


def test_saving_a_preset_keeps_its_persona(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"Mine": {"Codex": "a", "Claude": "b", "persona": {"Codex": {"idle_energy": 0.9}}}}))
    save_personality_preset("Mine", "c", "d", path)
    data = json.loads(path.read_text())
    assert data["Mine"]["Codex"] == "c" and data["Mine"]["persona"]["Codex"]["idle_energy"] == 0.9
    assert load_personas("Mine", path)["Codex"].idle_energy == 0.9


# --- demo scenario ----------------------------------------------------------------------

def test_demo_script_covers_every_beat():
    reactions = [classify_entry(turn(t.agent, demo_entry(t, 1))) for t in DEMO_TURNS]
    assert any(r.success for r in reactions)
    assert any(r.disagreement for r in reactions)
    assert any(r.admits_mistake for r in reactions)
    assert any(r.fixed_other_bug for r in reactions)
    assert any(r.fixed_own_mistake for r in reactions)
    assert any(r.human_needed for r in reactions)
    assert reactions[-2].proposes_completion and reactions[-1].declares_complete
    agents = [t.agent for t in DEMO_TURNS]
    assert all(a != b for a, b in zip(agents, agents[1:]))  # strictly alternating
    failing = [line for t in DEMO_TURNS for line in t.steps if "failed" in line]
    assert failing, "the demo should show a failing test run"


def test_demo_runs_to_completion_through_the_real_protocol(qapp, wait, tmp_path):
    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, DEMO_PROMPT, "Codex")
    adapters = {a: FakeAdapter(a, delay=0.01, behavior="demo") for a in ("Codex", "Claude")}
    o = Orchestrator(tmp_path, adapters, {}, poll_ms=50)
    o.start()
    assert wait(lambda: o.state == orch.WAITING_HUMAN and not o.is_busy(), timeout=40)
    assert "hide completed items" in o.last_signal.detail
    o.submit_human_turn("Hide them; add --all.", "Claude", title="Demo auto-reply")
    assert wait(lambda: o.state == orch.COMPLETE and not o.is_busy(), timeout=40)
    text = read_conversation(tmp_path / "conversation.md")
    speakers = [t.speaker for t in parse_conversation(text)]
    assert speakers.count("Codex") == 4 and speakers.count("Claude") == 4 and speakers.count("Human") == 2
    assert get_control_signal(text).kind == "complete"


def test_launch_gate_delays_but_never_blocks(qapp, wait, tmp_path):
    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "x", "Codex")
    o = Orchestrator(tmp_path, {a: FakeAdapter(a, delay=0.01) for a in ("Codex", "Claude")}, {}, poll_ms=50)
    o.launch_gate = lambda: False  # a presentation that never finishes
    o.launch_gate_max = 0.5
    o.start()
    assert not o.is_busy()  # gated: nothing launched yet
    assert wait(lambda: o.current_agent == "Codex", timeout=5)  # …but it gives up and launches
    o.stop()
    assert wait(lambda: not o.is_busy())
