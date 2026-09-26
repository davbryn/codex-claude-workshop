from workshop.kanban import SEED, ensure_board, moved_cards, new_asides, parse

NAMES = {"Codex": ("Codex", "Gilfoyle"), "Claude": ("Claude", "Dinesh")}


def test_seed_board_is_managements_and_says_nothing_itself(tmp_path):
    path = ensure_board(tmp_path)
    board = parse(path.read_text(encoding="utf-8"))
    assert [c.title for c in board.columns["To do"]] == ["Read the brief together"]
    assert new_asides(None, board, NAMES) == []  # Jared's note is shared-owner: nobody is made to "say" it
    path.write_text("custom", encoding="utf-8")
    ensure_board(tmp_path)
    assert path.read_text(encoding="utf-8") == "custom"  # an existing board is never replaced


def test_forgiving_parse():
    text = """# Kanban
## TODO
* [ ] Split word lists (Gilfoyle) - "Dinesh suggested it. So now it's mine."
## In progress
- **Colour detection** (Dinesh) — “Windows, my old nemesis.”
## Completed
- [x] Scoring
## Asides
- Gilfoyle: The board has more process than the code.
"""
    board = parse(text)
    assert [c.title for c in board.columns["To do"]] == ["Split word lists"]
    doing = board.columns["Doing"][0]
    assert (doing.title, doing.owner, doing.aside) == ("Colour detection", "Dinesh", "Windows, my old nemesis.")
    assert board.columns["Done"][0].title == "Scoring"
    assert board.asides == [("Gilfoyle", "The board has more process than the code.")]


def test_new_asides_and_moves():
    before = parse(SEED)
    after = parse(SEED.replace("## Doing\n", '## Doing\n- Split word lists (Gilfoyle) — "Mine now."\n')
                  .replace("## Asides\n", "## Asides\n- Dinesh: He moved my card.\n- Somebody: unattributable\n"))
    asides = new_asides(before, after, NAMES)
    assert [(a.speaker, a.text) for a in asides] == [("Codex", "Mine now."), ("Claude", "He moved my card.")]
    assert [c.title for c in moved_cards(before, after)] == ["Split word lists"]
    assert new_asides(after, after, NAMES) == []  # nothing new, nothing said twice


def test_director_only_voices_the_working_agents_asides(qapp, tmp_path):
    from workshop.agents.fake import FakeAdapter
    from workshop.orchestrator import Orchestrator
    from workshop.project import ensure_protocol_file, start_new_conversation
    from workshop.theatre.director import Director
    from workshop.theatre.sfx import SoundEffects
    from workshop.theatre.speech import NullSpeechEngine
    from workshop.ui.stage import StageWidget

    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "x", "Codex")
    path = ensure_board(tmp_path)
    o = Orchestrator(tmp_path, {a: FakeAdapter(a) for a in ("Codex", "Claude")}, {})
    stage = StageWidget()
    d = Director(o, stage, NullSpeechEngine(), SoundEffects(False))
    d.on_turn_started("Codex", 1)
    path.write_text(SEED.replace("## Asides\n", "## Asides\n- Gilfoyle: I have been assigned a card.\n"
                                              "- Dinesh: (written by Gilfoyle, pretending)\n"), encoding="utf-8")
    d._poll_board()
    assert d._muttering == "Codex" and stage.models["Codex"].talking
    assert all(a.speaker == "Codex" for a in d._mutters)  # the impersonated line is dropped
    assert d.screens["Codex"].mode == "kanban"
    d._end_mutter()
    d.shutdown()


def test_an_aside_being_cut_off_does_not_end_the_next_line(qapp, tmp_path):
    from workshop.agents.fake import FakeAdapter
    from workshop.conversation import ConversationTurn
    from workshop.orchestrator import Orchestrator
    from workshop.project import ensure_protocol_file, start_new_conversation
    from workshop.theatre.director import Director, Performance
    from workshop.theatre.reactions import classify_entry
    from workshop.theatre.sfx import SoundEffects
    from workshop.theatre.speech import SpeechEngine
    from workshop.ui.stage import StageWidget

    class Voice(SpeechEngine):  # like Kokoro: stop() reports the interrupted speaker as finished
        speaking = None

        def available(self):
            return True

        def speak(self, agent, text):
            self.stop()
            self.speaking = agent
            return True

        def stop(self):
            if self.speaking:
                agent, self.speaking = self.speaking, None
                self.finished.emit(agent)

    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "x", "Codex")
    o = Orchestrator(tmp_path, {a: FakeAdapter(a) for a in ("Codex", "Claude")}, {})
    d = Director(o, StageWidget(), Voice(), SoundEffects(False))
    d.on_turn_started("Claude", 1)
    (tmp_path / "KANBAN.md").write_text(SEED.replace("## Asides\n", "## Asides\n- Dinesh: Six tests, all green.\n"),
                                        encoding="utf-8")
    d._poll_board()
    assert d._muttering == "Claude"
    entry = ConversationTurn("Claude", "Turn 1", 1, "**Thoughts**\n\nGilfoyle, the scorer is right.\n\n@Codex", "Codex")
    d._play(Performance(entry, None, "Gilfoyle, the scorer is right.", "Gilfoyle, the scorer is right.",
                        classify_entry(entry)))
    assert d.current is not None and d.current.turn is entry  # the line is still being performed
    d.shutdown()
