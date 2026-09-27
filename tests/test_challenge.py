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
