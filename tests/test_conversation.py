from pathlib import Path

from workshop.conversation import (
    append_human_turn,
    completion_was_reviewed,
    detect_disagreement,
    extract_latest_speech,
    get_control_signal,
    get_latest_handoff,
    new_conversation_text,
    next_turn_number,
    parse_conversation,
)

START = new_conversation_text("Build a NES-style VM.", "Codex")

CODEX_1 = """
## Codex — Turn 1

**Thoughts**

Claude hasn't had the chance to ruin anything yet, so I suppose I'll begin.

**Actions**

Created the VM. Claude should look at `@Codex`-style decorators later.

**Next**

Claude should inspect the memory model.

@Claude

---
"""

CLAUDE_1 = """
## Claude — Turn 1

**Thoughts**

I disagree with the address wrapper; it is unnecessary.

@Codex

---
"""


def test_detects_codex_handoff_from_human_start():
    signal = get_control_signal(START)
    assert signal.kind == "handoff" and signal.agent == "Codex" and signal.speaker == "Human"


def test_detects_claude_handoff():
    assert get_latest_handoff(START + CODEX_1) == "Claude"


def test_detects_codex_handoff_and_ignores_old_ones():
    text = START + CODEX_1 + CLAUDE_1
    assert get_latest_handoff(text) == "Codex"
    # The historical @Claude in Codex's turn must not win.
    assert get_control_signal(text).speaker == "Claude"


def test_handoff_tolerates_markdown_and_case():
    text = START + "\n## Claude — Turn 1\n\nDone.\n\n**@codex**\n\n---\n"
    assert get_latest_handoff(text) == "Codex"


def test_detects_project_complete():
    text = START + CODEX_1 + "\n## Claude — Turn 1\n\nReviewed and tested.\n\nPROJECT COMPLETE\n\n---\n"
    signal = get_control_signal(text)
    assert signal.kind == "complete" and signal.speaker == "Claude"


def test_completion_requires_review_of_proposal():
    proposal = (
        "\n## Codex — Turn 2\n\nI believe the project is complete. Please independently inspect.\n\n@Claude\n\n---\n"
    )
    agree = "\n## Claude — Turn 2\n\nAgreed after testing.\n\nPROJECT COMPLETE\n"
    assert completion_was_reviewed(parse_conversation(START + CODEX_1 + CLAUDE_1 + proposal + agree))
    unilateral = "\n## Codex — Turn 2\n\nAll done.\n\nPROJECT COMPLETE\n"
    assert not completion_was_reviewed(parse_conversation(START + CODEX_1 + CLAUDE_1 + unilateral))


def test_detects_human_decision_needed():
    text = START + "\n## Codex — Turn 1\n\nHUMAN DECISION NEEDED: SQLite or JSON files?\n\n@Claude\n"
    signal = get_control_signal(text)
    assert signal.kind == "human"
    assert "SQLite or JSON" in signal.detail


def test_old_human_decision_is_ignored():
    text = START + "\n## Codex — Turn 1\n\nHUMAN DECISION NEEDED: tabs?\n\n---\n"
    text += "\n## Human — Intervention\n\nSpaces.\n\n@Claude\n\n---\n"
    assert get_latest_handoff(text) == "Claude"


def test_missing_handoff():
    text = START + "\n## Codex — Turn 1\n\nI did stuff and forgot to hand over.\n\n---\n"
    assert get_control_signal(text).kind == "missing"


def test_invalid_handoff():
    signal = get_control_signal(START + "\n## Codex — Turn 1\n\nDone.\n\n@Bob\n")
    assert signal.kind == "invalid" and "@Bob" in signal.detail


def test_both_handoffs_is_malformed():
    signal = get_control_signal(START + "\n## Codex — Turn 1\n\nDone.\n\n@Claude @Codex\n")
    assert signal.kind == "malformed"


def test_empty_conversation():
    assert get_control_signal("# Codex ↔ Claude\n").kind == "empty"


def test_mangled_heading_separators_are_accepted():
    for heading in ("## Codex ? Turn 6", "## Codex â€” Turn 6", "## Codex - Turn 6", "## Codex: Turn 6"):
        turns = parse_conversation(START + f"\n{heading}\n\nAgreed.\n\nPROJECT COMPLETE\n")
        assert (turns[-1].speaker, turns[-1].number) == ("Codex", 6), heading


def test_other_headings_mentioning_agents_are_not_turns():
    text = START + "\n## Codex — Turn 1\n\n## Codex's plan\n\n## Claude is right\n\n@Claude\n"
    assert [t.speaker for t in parse_conversation(text)] == ["Human", "Codex"]


def test_headings_inside_code_fences_are_ignored():
    text = START + "\n## Codex — Turn 1\n\n```markdown\n## Claude — Turn 9\n@Codex\n```\n\n@Claude\n"
    turns = parse_conversation(text)
    assert [t.speaker for t in turns] == ["Human", "Codex"]
    assert turns[-1].handoff == "Claude"


def test_turn_numbers_and_next_number():
    text = START + CODEX_1 + CLAUDE_1
    turns = parse_conversation(text)
    assert [(t.speaker, t.number) for t in turns] == [("Human", None), ("Codex", 1), ("Claude", 1)]
    assert next_turn_number(text, "Codex") == 2


def test_append_human_turn(tmp_path: Path):
    path = tmp_path / "conversation.md"
    path.write_text(START + CODEX_1, encoding="utf-8")
    append_human_turn(path, "Please resolve persistence first.", "Claude")
    text = path.read_text(encoding="utf-8")
    assert text.startswith(START + CODEX_1)  # history untouched
    latest = parse_conversation(text)[-1]
    assert latest.speaker == "Human" and latest.title == "Intervention"
    assert get_latest_handoff(text) == "Claude"


def test_extract_latest_speech_prefers_thoughts():
    speech = extract_latest_speech(START + CODEX_1 + CLAUDE_1, "Codex")
    assert speech.startswith("Claude hasn't had the chance")
    assert extract_latest_speech(START, "Claude") is None


def test_extract_latest_speech_truncates():
    long = "word " * 300
    text = START + f"\n## Claude — Turn 1\n\n{long}\n\n@Codex\n"
    assert len(extract_latest_speech(text, "Claude", limit=100)) <= 101


def test_disagreement_detection():
    assert detect_disagreement("Honestly, I disagree with this.")
    assert detect_disagreement("This wrapper is over-engineered.")
    assert not detect_disagreement("Lovely work, all tests pass.")
