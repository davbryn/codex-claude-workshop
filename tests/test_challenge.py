import random

from workshop import challenge as c


def _spins(language: str, limit: str) -> list[dict]:
    lang = next(i for i, L in enumerate(c.LANGUAGES) if L[0] == language)
    lim = next(i for i, s in enumerate(c.LIMITS) if s.key == limit)
    langs = [c.Slice(L[0], L[1], "") for L in c.LANGUAGES]
    return [c.Spin("language", None, langs, lang).as_event(), c.Spin("limit", None, c.LIMITS, lim).as_event()]


def _check(tmp_path, files: dict, language="python", limit="no_loops"):
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return c.check(tmp_path, _spins(language, limit))


def test_spin_all_covers_every_wheel_with_near_misses():
    spins = c.spin_all(random.Random(1), project=True)
    assert [s.wheel for s in spins] == ["project", "skill", "skill", "language", "limit"]
    assert [s.who for s in spins if s.wheel == "skill"] == ["Codex", "Claude"]
    for s in spins:
        assert s.result not in s.near_misses and 0 <= s.result < len(s.slices)
    text = c.brief("", spins)
    assert "WHEEL OF DESTINY" in text and "DEMO.md" in text and spins[-1].slice.label in text


def test_no_loops_ignores_comments_and_strings(tmp_path):
    v = _check(tmp_path, {"a.py": "# for every habit\nprint('while you wait')\nfor x in y:\n    pass\n"})
    assert [(x.rule, x.line) for x in v] == [("no_loops", 3)]


def test_no_if_and_case_insensitive_languages(tmp_path):
    v = _check(tmp_path, {"a.vbs": "If x Then\n' if in a comment\nWScript.Echo \"else\"\n"}, "vbscript", "no_if")
    assert [x.line for x in v] == [1]


def test_no_digits_counts_comments_too(tmp_path):
    v = _check(tmp_path, {"a.py": "x = len('ab')\n# day 1\n"}, limit="no_digits")
    assert [x.line for x in v] == [2]


def test_short_lines_and_tiny(tmp_path):
    v = _check(tmp_path, {"a.py": "x = 1\n" + "y = '" + "a" * 50 + "'\n"}, limit="short_lines")
    assert [x.line for x in v] == [2]
    v = _check(tmp_path, {"b.py": "x = 1\n" * 101}, limit="tiny")
    assert any(x.rule == "tiny" for x in v)


def test_no_vowels_in_defined_names(tmp_path):
    v = _check(tmp_path, {"a.py": "def strk(dys):\n    return dys\n\ndef streak(days):\n    pass\ncnt = 3\ncount = 4\n"},
               limit="no_vowels")
    assert [x.line for x in v] == [4, 7]


def test_shouting_strings(tmp_path):
    v = _check(tmp_path, {"a.py": "print('DONE')\nprint(\"done\")\n"}, limit="shouting")
    assert [x.line for x in v] == [2]


def test_rhyming_couplets(tmp_path):
    good = "# the streak is long\n# the code is strong\nx = 1\n"
    bad = "# the streak is long\n# the code is fine\nx = 1\n# alone\n"
    assert _check(tmp_path, {"a.py": good}, limit="rhyme") == []
    assert [x.line for x in _check(tmp_path, {"a.py": bad}, limit="rhyme")] == [2, 4]


def test_wrong_language_and_imports(tmp_path):
    v = _check(tmp_path, {"a.py": "import os\nx = 1\n", "helper.js": "WScript.Echo(1)"}, limit="no_imports")
    assert {(x.rule, x.path) for x in v} == {("no_imports", "a.py"), ("wrong language", "helper.js")}


def test_report_text():
    assert "clean" in c.report([], [])
    text = c.report([c.Violation("no_loops", "a.py", 3, "for x in y:")], [])
    assert "1 violation" in text and "a.py:3" in text


def test_reaction_prompt_lists_every_spin():
    spins = c.spin_all(random.Random(2), project=True)
    text = c.reaction_prompt("Codex", spins)
    assert "skill level for Dinesh" in text and "the language" in text and "the project" in text
    assert text.count("\n1. ") == 1 and "5. " in text


def _challenge_events(tmp_path):
    from workshop.episode.capture import EventLog, read_events

    log = EventLog(tmp_path / "events.jsonl")
    spins = c.spin_all(random.Random(3), project=True)
    log.add("human", title="Project Start", content=c.brief("", spins))
    for i, s in enumerate(spins):
        log.add("spin", index=i, **s.as_event())
    log.add("spin_reaction", index=0, agent="Claude", line="Oh no.")
    log.add("spin_reaction", index=0, agent="Codex", line="Good.")
    log.add("turn_start", agent="Claude", turn=1)
    log.add("diff", agent="Claude", path="game.py", created=True, deleted=False, lines=[["add", "x = 1"]])
    log.add("entry", agent="Claude", title="Claude - Turn 1", content=(
        "There are no loops, because recursion is a workaround the wheel can't stop. It works.\n\n@Codex"),
        moment=None, handoff="Codex")
    log.add("turn_end", agent="Claude", exit_code=0, seconds=10)
    log.add("rules_check", agent="Claude", count=2, violations=[{"rule": "no_loops", "path": "game.py", "line": 3,
                                                                "text": "for x in y:"}])
    log.add("turn_start", agent="Codex", turn=1)
    log.add("entry", agent="Codex", title="Codex - Turn 1", content="Fixed his loops. You're welcome.\n\n@Claude",
            moment=None, handoff="Claude")
    log.add("turn_end", agent="Codex", exit_code=0, seconds=10)
    log.add("rules_check", agent="Codex", count=0, violations=[])
    log.add("complete")
    return read_events(tmp_path / "events.jsonl")


def test_challenge_plan_tells_the_story(tmp_path):
    from workshop.episode.challenge_plan import plan_challenge

    (tmp_path / "DEMO.md").write_text("```\n> python game.py\nYou win!\n```\n", encoding="utf-8")
    plan = plan_challenge(_challenge_events(tmp_path), tmp_path)
    kinds = [s["kind"] for s in plan["scenes"]]
    assert kinds[:2] == ["confessional", "challenge_title"] and plan["scenes"][0]["cold_open"]
    assert kinds.count("wheel") == 5 and "rules" in kinds
    assert kinds[-2:] == ["demo", "finale"]
    wheel = plan["scenes"][2]
    assert [r["speaker"] for r in wheel["reactions"]] == ["Claude", "Codex"]  # Dinesh panics, Gilfoyle buttons
    violation = next(s for s in plan["scenes"] if s["kind"] == "violation")
    assert violation["agent"] == "Claude" and violation["new"] == 2
    cleared = next(s for s in plan["scenes"] if s["kind"] == "cleared")
    assert cleared["agent"] == "Codex" and cleared["fixed"] == 2
    trick = next(s for s in plan["scenes"] if s.get("label") == "THE WORKAROUND")
    assert "recursion is a workaround" in trick["text"]
    assert any("CLEAN" in line for line in plan["scenes"][-1]["lines"])
    assert plan["format"] == "challenge" and "Wheel of Destiny" in plan["logline"]


def test_twist_adds_a_limitation_that_the_checker_enforces(tmp_path):
    spins = c.spin_all(random.Random(3))
    spins[-1] = c.Spin("limit", None, c.LIMITS, [x.key for x in c.LIMITS].index("no_loops"))
    lang = [s for s in spins if s.wheel == "language"][0]
    lang.slices[:] = [c.Slice("python", "Python", "")]
    lang.result = 0
    twist_slices = c.twist_slices(spins)
    assert all(x.key != "limit:no_loops" for x in twist_slices)
    assert any(x.key.startswith("jared:") for x in twist_slices) and twist_slices[-1].key == "swap"
    digits = next(i for i, x in enumerate(twist_slices) if x.key == "limit:no_digits")
    twist = c.Spin("twist", None, twist_slices, digits)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert c.check(tmp_path, spins) == []
    assert [v.rule for v in c.check(tmp_path, spins + [twist])] == ["no_digits"]
    assert "SECOND LIMITATION" in c.rules_text(spins + [twist])


def test_skill_swap_and_jared():
    spins = c.spin_all(random.Random(5))
    before = c.skills(spins)
    swapped = c.skills(spins + [c.Spin("twist", None, [c.SWAP], 0)])
    assert swapped["Codex"] == before["Claude"] and swapped["Claude"] == before["Codex"]
    jared = c.Spin("twist", None, c.JARED, 1)
    assert "JARED'S FEATURE REQUEST" in c.rules_text(spins + [jared])


def test_trivial_limits_never_win():
    for seed in range(60):
        spins = c.spin_all(random.Random(seed))
        lang = [s for s in spins if s.wheel == "language"][0].slice.key
        assert not c.trivial(spins[-1].slice.key, lang)


def test_music_bed_is_quiet_tileable_and_faded():
    import numpy as np

    from workshop.episode.music import RATE, bed

    x = bed(7.5)
    assert len(x) == int(7.5 * RATE) and float(np.abs(x).max()) <= 0.91
    assert abs(float(x[0])) < 1e-3 and abs(float(x[-1])) < 1e-2  # fades in and out
    assert len(bed(0)) == 0


def test_short_plan_hook_spins_twist_demo_verdict(tmp_path):
    from workshop.episode.capture import EventLog, read_events
    from workshop.episode.challenge_plan import plan_challenge, plan_short

    events = _challenge_events(tmp_path)
    log = EventLog(tmp_path / "events.jsonl")
    spins = [e for e in events if e["kind"] == "spin"]
    twist = c.Spin("twist", None, c.JARED, 0)
    log.add("spin", index=len(spins), **twist.as_event())
    log.add("spin_reaction", index=len(spins), agent="Claude", line="Blockchain?! Jared, NO.")
    (tmp_path / "DEMO.md").write_text("> run\n" + "\n".join(f"line {i}" for i in range(20)), encoding="utf-8")
    events = read_events(tmp_path / "events.jsonl")
    full = plan_challenge(events, tmp_path)
    short = plan_short(full, events)
    kinds = [s["kind"] for s in short["scenes"]]
    assert kinds[0] == "confessional" and kinds[-1] == "finale" and short["vertical"]
    assert kinds.count("wheel") == 3 and "twist_intro" in kinds  # language, limit, twist
    assert all(len(s["reactions"]) <= 1 for s in short["scenes"] if s["kind"] == "wheel")
    assert len(next(s for s in short["scenes"] if s["kind"] == "demo")["lines"]) <= 7
    assert full["headline"]["twist"] == "Put It On The Blockchain"


def test_viral_titles():
    from workshop.episode.build import short_title, youtube_title

    plan = {"format": "challenge", "project": "Hangman", "title": "x",
            "headline": {"project": "Hangman", "language": "Windows Batch", "limit": "No Loops", "twist": ""}}
    assert youtube_title(plan) == "I Made Two AIs Build Hangman in Windows Batch With NO Loops"
    plan["headline"]["twist"] = "Klingon Mode"
    assert youtube_title(plan).endswith("Then the Wheel Added Klingon Mode")
    assert "#shorts" in short_title(plan)


def test_reaction_prompt_handles_the_twist():
    spins = c.spin_all(random.Random(2))
    twist = c.spin_twist(spins, random.Random(3))
    assert "TWIST WHEEL" in c.reaction_prompt("Claude", [twist])
