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
    assert kinds[0] == "challenge_title" and kinds.count("wheel") == 5 and "rules" in kinds
    assert kinds[-2:] == ["demo", "finale"]
    wheel = plan["scenes"][1]
    assert [r["speaker"] for r in wheel["reactions"]] == ["Claude", "Codex"]  # Dinesh panics, Gilfoyle buttons
    violation = next(s for s in plan["scenes"] if s["kind"] == "violation")
    assert violation["agent"] == "Claude" and violation["new"] == 2
    cleared = next(s for s in plan["scenes"] if s["kind"] == "cleared")
    assert cleared["agent"] == "Codex" and cleared["fixed"] == 2
    trick = next(s for s in plan["scenes"] if s["kind"] == "confessional")
    assert "recursion is a workaround" in trick["text"]
    assert any("CLEAN" in line for line in plan["scenes"][-1]["lines"])
    assert plan["format"] == "challenge" and "Wheel of Destiny" in plan["logline"]
