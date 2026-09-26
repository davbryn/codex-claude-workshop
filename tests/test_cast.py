"""The Silicon Valley cast layer: prompts, callbacks, scoreboard, moments, animation style."""

import json

from workshop import orchestrator as orch
from workshop.agents.demo_script import DEMO_FIRST_AGENT, DEMO_PROMPT, DEMO_TURNS, demo_entry
from workshop.agents.fake import FakeAdapter
from workshop.config import THEME_VERSION, Settings
from workshop.conversation import ConversationTurn, new_conversation_text, parse_conversation
from workshop.orchestrator import Orchestrator
from workshop.project import ensure_protocol_file, start_new_conversation
from workshop.prompts import build_prompt
from workshop.theatre.avatar_state import AvatarModel
from workshop.theatre.banter import callbacks_for, extract_callbacks, make_prompt_theatre, petty_scoreboard
from workshop.theatre.cast import BANNED_PHRASES, HOSTILITY_LEVELS, PERSONALITY, status_label, theatre_block
from workshop.theatre.reactions import classify_entry
from workshop.theatre.text import bubble_excerpt, score_sentence


def turn(speaker, content, number=1):
    return ConversationTurn(speaker, f"Turn {number}", number, content, None)


def demo_turns():
    text = new_conversation_text(DEMO_PROMPT, DEMO_FIRST_AGENT)
    text += "".join(demo_entry(t, i // 2 + 1) for i, t in enumerate(DEMO_TURNS))
    return parse_conversation(text)


# --- prompts --------------------------------------------------------------------------

def test_every_prompt_states_the_identity_mapping_prominently(tmp_path):
    codex = theatre_block("Codex")
    claude = theatre_block("Claude")
    assert "For the theatrical collaboration layer, you are GILFOYLE.\nThe other agent, Claude, is DINESH." in codex
    assert "For the theatrical collaboration layer, you are DINESH.\nThe other agent, Codex, is GILFOYLE." in claude
    for block in (codex, claude):
        for step in ("Read", "React directly", "Respond in character", "real engineering work", "Hand over"):
            assert step.lower() in block.lower()
        assert all(phrase in block for phrase in BANNED_PHRASES)
        assert "do NOT invent a bug" in block
    prompt = build_prompt("Codex", "Claude", PERSONALITY["Codex"], tmp_path, "AGENT_README.md", 3, codex)
    rules, cast, persona, current = (prompt.index("[CORE WORKSHOP RULES]"), prompt.index("you are GILFOYLE"),
                                     prompt.index("[CODEX PERSONALITY]"), prompt.index("[CURRENT TURN]"))
    assert rules < cast < persona < current
    assert "## Codex - Turn 3" in prompt and "@Claude" in prompt  # protocol untouched


def test_hostility_levels_and_callbacks_in_prompt():
    assert HOSTILITY_LEVELS[-2] == "Gilfoyle & Dinesh" and "Nuclear" in HOSTILITY_LEVELS
    assert "NUCLEAR" in theatre_block("Claude", "Nuclear") and "productive" in theatre_block("Claude", "Nuclear")
    assert "GILFOYLE & DINESH" in theatre_block("Claude", "nonsense")  # unknown → default
    block = theatre_block("Claude", callbacks=["Dinesh caught a Gilfoyle bug — turn 3"])
    assert "- Dinesh caught a Gilfoyle bug — turn 3" in block and "never let them change technical" in block


def test_prompt_theatre_follows_live_settings():
    settings = Settings()
    build = make_prompt_theatre(settings)
    text = demo_entry(DEMO_TURNS[0], 1)
    assert "you are GILFOYLE" in build("Codex", text)
    settings.hostility = "Civil"
    assert "CIVIL" in build("Codex", text)
    settings.cast_enabled = False
    assert build("Codex", text) == ""


def test_orchestrator_sends_theatre_and_survives_a_broken_one(qapp, wait, tmp_path):
    ensure_protocol_file(tmp_path)
    start_new_conversation(tmp_path, "x", "Codex")
    o = Orchestrator(tmp_path, {a: FakeAdapter(a, delay=0.01) for a in ("Codex", "Claude")}, {}, poll_ms=50)
    calls = []

    def theatre(agent, text):
        calls.append(agent)
        raise ValueError("presentation bug")

    o.prompt_theatre = theatre
    o.start()
    assert wait(lambda: o.current_agent == "Claude", timeout=10)  # Codex's turn ran regardless
    assert calls[:2] == ["Codex", "Claude"]
    o.stop()
    assert wait(lambda: not o.is_busy())


# --- callbacks & the petty scoreboard ------------------------------------------------------

def test_callbacks_are_factual_and_small():
    callbacks = extract_callbacks(demo_turns())
    texts = [c.text() for c in callbacks]
    assert any(t.startswith("Dinesh caught a Gilfoyle bug — turn 3") and "encode(0)" in t for t in texts)
    assert any(t.startswith("Gilfoyle won an argument with Dinesh by evidence — turn 5") for t in texts)
    assert not any(t.startswith("Dinesh won an argument") for t in texts)  # a bug concession isn't an argument
    for agent in ("Codex", "Claude"):
        picked = callbacks_for(agent, callbacks)
        assert 0 < len(picked) <= 4 and all(p in texts for p in picked)


def test_petty_scoreboard_counts_only_derivable_events():
    board = petty_scoreboard(demo_turns())
    assert board["Claude"].bugs_caught == 1 and board["Codex"].bugs_caught == 0
    assert board["Codex"].arguments_won == 1 and board["Claude"].arguments_won == 0
    assert board["Claude"].concessions_received == 1 and board["Codex"].concessions_received == 1
    assert petty_scoreboard([])["Codex"].bugs_caught == 0


# --- classifier & bubbles ----------------------------------------------------------------------

def test_character_names_count_as_the_other_agent():
    caught = classify_entry(turn("Claude", "Gilfoyle's parser crashes on empty input. I fixed it."))
    assert caught.caught_other_bug and caught.fixed_other_bug and caught.moment() == "dinesh_catches"
    assert caught.primary_state() == "gloating" and caught.listener_state() == "sideeye"
    smug = classify_entry(turn("Codex", "Dinesh's retry loop has a race condition. I fixed it."))
    assert smug.moment() == "gilfoyle_catches" and smug.listener_state() == "outraged"
    conceded = classify_entry(turn("Codex", "Unfortunately Dinesh found an actual race condition. I've fixed it."))
    assert conceded.concedes_other and conceded.self_admission and not conceded.caught_other_bug
    assert conceded.moment() == "concession"


def test_real_world_catch_said_to_his_face():
    # from a real session: the catch is phrased "Dinesh, your X printed …", with a side concession
    text = ("Dinesh, your claim that privacy was enforced structurally ran into argparse, which printed the "
            "rejected password directly to stderr. The original 28 tests passed while it did this. You were "
            "right about the PowerShell BOM.")
    r = classify_entry(turn("Codex", text))
    assert r.caught_other_bug and not r.concedes_other
    assert r.moment() == "gilfoyle_catches" and r.primary_state() == "smug" and r.listener_state() == "outraged"


def test_more_real_world_phrasings():
    catch = classify_entry(turn("Codex", "Dinesh, your calendar cap is correct. Your detector survived a year suffix "
                                         "and was defeated by punctuation approaching from the left."))
    assert catch.moment() == "gilfoyle_catches"
    grudging = classify_entry(turn("Claude", "Fine. The argparse thing was real. I re-probed your fix and it holds."))
    assert grudging.concedes_other and grudging.moment() == "concession"


def test_catch_plus_confession_is_both_wrong():
    text = ("Gilfoyle, you locked the front door against ! and left the space bar holding the back door open. "
            "Before you enjoy this, here's my own confession: my first fix introduced a quadratic regex.")
    r = classify_entry(turn("Claude", text))
    assert r.caught_other_bug and r.self_admission and r.moment() == "both_wrong"


def test_that_makes_it_your_bug():
    r = classify_entry(turn("Claude", "Gilfoyle, a typo like Bob:1_0 silently gives Bob a weight of 10. That shipped in "
                                      "Turn 1, which makes it your bug."))
    assert r.caught_other_bug and r.moment() == "dinesh_catches"


def test_third_person_catch():
    r = classify_entry(turn("Codex", "Dinesh was right about the example. His proposed cumulative bound, however, "
                                     "does not survive deliberately changing groups."))
    assert r.caught_other_bug and r.moment() == "gilfoyle_catches"


def test_markdown_emphasis_does_not_hide_reactions():
    r = classify_entry(turn("Claude", "Your cap holds. I *do* disagree with your rule for the fairness fix. "
                                      "**Gilfoyle** was right about the cap."))
    assert r.disagreement and r.concedes_other
    assert classify_entry(turn("Claude", "my_helper_function works.")).primary_state() != "disagreeing"


def test_inline_code_punctuation_does_not_split_sentences():
    entry = "**Thoughts**\n\nIt was still calling `Summer2024!` \"strong\", which Gilfoyle walked past like it was a Hooli billboard."
    assert bubble_excerpt(entry).startswith("It was still calling Summer2024! \"strong\"")


def test_rare_moments():
    same = classify_entry(turn("Codex", "Dinesh and I independently arrived at the same fix. Disturbing."))
    assert same.moment() == "same_solution"
    regression = classify_entry(turn("Claude", "My previous fix broke the export. Fixed it again."))
    assert regression.moment() == "character_development"
    assert classify_entry(turn("Codex", "Renamed a variable.")).moment() is None


def test_bubble_prefers_the_jab_over_boilerplate():
    entry = ("**Thoughts**\n\nI read the files and ran the suite. Dinesh added a factory for a list comprehension. "
             "It has one product.\n\n**Actions**\n\nDeleted `factory.py`.\n\n**Result**\n\nAll 12 tests pass.\n\n"
             "**Next**\n\nYour turn.\n\n@Claude")
    bubble = bubble_excerpt(entry)
    assert bubble.startswith("Dinesh added a factory") and "It has one product." in bubble
    assert score_sentence("Dinesh, you are wrong again.") > score_sentence("I ran the tests.")


# --- animation philosophy -----------------------------------------------------------------------

def _motion(model, state):
    model.react(state, 3.0)
    peak = 0.0
    for _ in range(40):
        model.update(0.05)
        pose = model.pose()
        peak = max(peak, abs(pose.bob) + abs(pose.tilt) + abs(pose.shake))
    return peak


def test_gilfoyle_is_under_animated_and_dinesh_is_not():
    gilfoyle, dinesh = AvatarModel("Codex", seed=1), AvatarModel("Claude", other_side=-1, seed=1)
    assert gilfoyle.deadpan and not dinesh.deadpan
    assert _motion(dinesh, "celebrating") > 3 * max(0.5, _motion(gilfoyle, "celebrating"))
    gilfoyle.react("smug", None)
    gilfoyle.update(2.0)
    pose = gilfoyle.pose()
    assert pose.mouth == "smug" and pose.mouth_open < 0.1  # a tiny smile, not a grin
    dinesh.react("gloating", None)
    dinesh.update(2.0)
    assert dinesh.pose().mouth == "grin" and "yes" in dinesh.pose().props


def test_sideeye_is_a_slow_look():
    m = AvatarModel("Codex", seed=2)
    m.update(0.5)
    m.react("sideeye", 3.0)
    m.update(0.2)
    assert 0.05 < m.look_x < 0.6  # still travelling…
    m.update(2.0)
    assert m.look_x > 0.8  # …but it gets there


# --- settings, labels, sounds, rendering --------------------------------------------------------

def test_old_settings_migrate_to_the_cast(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"last_preset": "Rivals", "codex_voice": "af_bella", "codex_personality": "x"}))
    s = Settings.load(path)
    assert s.last_preset == "Gilfoyle & Dinesh" and s.codex_voice == "" and s.theme_version == THEME_VERSION
    assert "GILFOYLE" in s.codex_personality and s.cast_enabled
    path.write_text(json.dumps({"last_preset": "Chaos", "codex_voice": "am_echo", "theme_version": THEME_VERSION}))
    kept = Settings.load(path)
    assert kept.last_preset == "Chaos" and kept.codex_voice == "am_echo"


def test_status_labels_are_factual_with_flavour():
    assert "JUDGING" in status_label("Codex", "reviewing") and "BUGS" in status_label("Claude", "reviewing")
    assert "TESTS" in status_label("Codex", "testing") and "TESTS" in status_label("Claude", "testing")


def test_new_sound_effects_exist():
    from workshop.theatre import sfx

    effects = sfx._effects()
    assert {"yes", "blast", "wahwah"} <= set(effects) and set(sfx._effects_names()) == set(effects)
    assert 0.9 < len(effects["blast"]) / sfx.RATE < 1.3  # about one second of grindcore


def test_stage_paints_the_set_characters_and_cards(qapp):
    from workshop.ui.stage import StageWidget

    stage = StageWidget()
    for w, h in ((1400, 560), (700, 320)):
        stage.resize(w, h)
        stage.show_speech("Codex", "You made a service locator for three functions, Dinesh.", mode="instant")
        stage.show_speech("Claude", "IT'S CALLED DECOUPLING.", mode="instant")
        stage.models["Claude"].react("gloating", 2.0)
        stage.badge("DINESH WILL NEVER LET THIS GO", "center", "#6f9dff")
        stage.show_card("complete", "PROJECT COMPLETE", ["8 agent turns"], "#f2c94c", tagline="Somehow.")
        stage.confetti(20, only="Claude")
        image = stage.grab()
        assert not image.isNull() and image.width() == w
        stage.hide_card("complete")
    stage.stop()
