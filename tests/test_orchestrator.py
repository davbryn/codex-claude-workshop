"""Orchestrator state tests using fake agents running as real child processes."""

from pathlib import Path

import pytest

from workshop import orchestrator as orch
from workshop.agents.base import AgentAdapter
from workshop.agents.fake import FakeAdapter
from workshop.conversation import parse_conversation, read_conversation
from workshop.orchestrator import Orchestrator
from workshop.project import ensure_protocol_file, start_new_conversation


def make(tmp_path: Path, first="Codex", codex="normal", claude="normal", complete_after=2) -> Orchestrator:
    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "Build a tiny calculator.", first)
    adapters = {
        "Codex": FakeAdapter("Codex", delay=0.05, behavior=codex, complete_after=complete_after),
        "Claude": FakeAdapter("Claude", delay=0.05, behavior=claude, complete_after=complete_after),
    }
    o = Orchestrator(tmp_path, adapters, {"Codex": "dry", "Claude": "dramatic"}, poll_ms=50)
    o.events = []
    o.turn_started.connect(lambda agent, n: o.events.append(("start", agent, n)))
    o.messages = []
    o.message.connect(lambda level, text: o.messages.append((level, text)))
    return o


def speakers(tmp_path: Path) -> list[str]:
    return [t.speaker for t in parse_conversation(read_conversation(tmp_path / "conversation.md"))]


def settled(o: Orchestrator, *states):
    return lambda: o.state in states and not o.is_busy()


def test_full_alternation_to_completion(qapp, wait, tmp_path):
    o = make(tmp_path)
    o.start()
    assert wait(settled(o, orch.COMPLETE, orch.NEEDS_ATTENTION))
    assert o.state == orch.COMPLETE, o.messages
    # Codex 1, Claude 1, Codex 2 proposes completion, Claude 2 agrees.
    assert speakers(tmp_path) == ["Human", "Codex", "Claude", "Codex", "Claude"]
    assert [e[1:] for e in o.events] == [("Codex", 1), ("Claude", 1), ("Codex", 2), ("Claude", 2)]
    assert o.agent_states == {"Codex": orch.A_COMPLETE, "Claude": orch.A_COMPLETE}


def test_claude_can_go_first(qapp, wait, tmp_path):
    o = make(tmp_path, first="Claude", complete_after=99)
    o.start()
    assert wait(lambda: len(o.events) >= 2)
    o.stop()
    assert [e[1] for e in o.events[:2]] == ["Claude", "Codex"]


def test_pause_finishes_turn_then_resume_continues(qapp, wait, tmp_path):
    o = make(tmp_path, complete_after=99)
    o.start()
    assert o.is_busy() and o.current_agent == "Codex"
    o.pause()
    assert o.state == orch.PAUSING
    assert wait(settled(o, orch.PAUSED))
    # Codex's turn completed, but Claude was not launched.
    assert speakers(tmp_path) == ["Human", "Codex"]
    assert len(o.events) == 1

    o.resume()
    assert o.is_busy() and o.current_agent == "Claude"
    assert wait(lambda: len(speakers(tmp_path)) >= 3)
    o.stop()
    assert wait(lambda: not o.is_busy())


def test_stop_kills_running_agent_and_keeps_files(qapp, wait, tmp_path):
    o = make(tmp_path, codex="slow")
    o.start()
    assert wait(lambda: o.agent_states["Codex"] in (orch.A_READING, orch.A_WORKING))
    before = read_conversation(tmp_path / "conversation.md")
    o.stop()
    assert o.state == orch.STOPPED
    assert wait(lambda: not o.is_busy(), timeout=10)
    assert read_conversation(tmp_path / "conversation.md") == before
    assert (tmp_path / "AGENT_README.md").exists()
    assert len(o.events) == 1


def test_missing_handoff_pauses(qapp, wait, tmp_path):
    o = make(tmp_path, codex="no-handoff")
    o.start()
    assert wait(settled(o, orch.NEEDS_ATTENTION))
    assert "Codex completed without a valid handoff" in o.messages[-1][1]
    assert len(o.events) == 1


def test_no_write_is_reported(qapp, wait, tmp_path):
    o = make(tmp_path, codex="no-write")
    o.start()
    assert wait(settled(o, orch.NEEDS_ATTENTION))
    assert "without updating conversation.md" in o.messages[-1][1]
    assert o.agent_states["Codex"] == orch.A_ERROR


def test_agent_error_does_not_pass_turn(qapp, wait, tmp_path):
    o = make(tmp_path, codex="fail")
    o.start()
    assert wait(settled(o, orch.NEEDS_ATTENTION))
    level, text = o.messages[-1]
    assert level == "error"
    assert "CODEX ERROR" in text and "Exit code: 1" in text and "simulated crash" in text
    assert o.agent_states["Codex"] == orch.A_ERROR
    assert [e[1] for e in o.events] == ["Codex"]  # Claude never started


def test_human_decision_needed_waits_then_human_turn_resumes(qapp, wait, tmp_path):
    o = make(tmp_path, codex="human", complete_after=99)
    o.start()
    assert wait(settled(o, orch.WAITING_HUMAN))
    assert "HUMAN INPUT REQUIRED" in o.messages[-1][1]

    o.submit_human_turn("Spaces, obviously.", "Claude")
    assert o.current_agent == "Claude"
    assert wait(lambda: speakers(tmp_path)[-1] == "Claude")
    assert speakers(tmp_path)[-2] == "Human"
    o.stop()
    assert wait(lambda: not o.is_busy())


def test_human_turn_rejected_while_running(qapp, wait, tmp_path):
    o = make(tmp_path, codex="slow")
    o.start()
    with pytest.raises(RuntimeError):
        o.submit_human_turn("hello", "Claude")
    o.stop()
    assert wait(lambda: not o.is_busy(), timeout=10)


def test_human_turn_without_resume_stays_paused(qapp, wait, tmp_path):
    o = make(tmp_path)
    o.pause()
    o.start()  # start clears pause
    o.pause()
    assert wait(settled(o, orch.PAUSED))
    o.submit_human_turn("Codex again please.", "Codex", resume=False)
    assert o.state == orch.PAUSED and not o.is_busy()


def test_unavailable_executable_is_reported(qapp, wait, tmp_path):
    class Missing(AgentAdapter):
        name = "Codex"

        def build_launch(self, project_dir, prompt):
            self.command = "definitely-not-a-real-codex-binary"
            self.resolve_executable()

    o = make(tmp_path)
    o.adapters["Codex"] = Missing()
    o.start()
    assert o.state == orch.NEEDS_ATTENTION
    assert "Codex executable not found" in o.messages[-1][1]


def test_prompt_contains_rules_personality_and_turn(tmp_path):
    from workshop.prompts import build_prompt

    prompt = build_prompt("Claude", "Codex", "Terrible puns.", tmp_path, "AGENT_README.md", 4)
    assert prompt.index("[CORE WORKSHOP RULES]") < prompt.index("Terrible puns.") < prompt.index("[CURRENT TURN]")
    assert "## Claude — Turn 4" in prompt and "@Codex" in prompt
