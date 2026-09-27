from workshop.episode.build import description, youtube_title
from workshop.episode.capture import EventLog, read_events
from workshop.episode.plan import DISCLAIMER_VERBATIM, plan_cut, plan_verbatim, project_title

BOARD = """# Kanban
## To do
## Doing
- Write encoder - Dinesh: finally, some real work
## Done
"""


def _events():
    ev = [
        {"kind": "session", "brief": ""},
        {"kind": "human", "title": "Project Start", "content": "_2026-09-27 13:46_\n\nBuild a tiny URL shortener: shorten and resolve."},
        {"kind": "turn_start", "agent": "Claude", "turn": 1},
        {"kind": "board", "agent": "Claude", "text": BOARD, "moved": ["Write encoder"]},
        {"kind": "aside", "agent": "Claude", "text": "Finally, some real work.", "card": "Write encoder"},
        {"kind": "diff", "agent": "Claude", "path": "short.py", "created": True, "deleted": False,
         "lines": [["add", "def encode(n):"], ["add", "    return ''"]]},
        {"kind": "command", "agent": "Claude", "command": "pytest -q", "kind_of": "testing"},
        {"kind": "tests", "agent": "Claude", "passed": 1, "failed": 1, "ok": False, "line": "1 failed, 1 passed"},
        {"kind": "bit", "agent": "Codex", "worker": "Claude", "bit": {"kind": "email", "title": "To Jared",
                                                                      "body": "He is typing.", "line": "Cc HR."}},
        {"kind": "entry", "agent": "Claude", "title": "Claude - Turn 1",
         "content": "I wrote the encoder. Gilfoyle, your turn to find nothing wrong with it.\n\n@Codex",
         "moment": None, "handoff": "Codex"},
        {"kind": "turn_end", "agent": "Claude", "exit_code": 0, "seconds": 30},
        {"kind": "complete"},
    ]
    for i, e in enumerate(ev):
        e["id"], e["t"] = i, float(i)
    return ev


def test_project_title_strips_stamp_and_verb():
    title, brief = project_title(_events())
    assert title == "Tiny URL shortener"
    assert brief.startswith("Build a tiny URL shortener")
    assert "2026" not in brief


def test_verbatim_plan_only_uses_logged_words():
    ev = _events()
    plan = plan_verbatim(ev, target_seconds=600)
    kinds = [s["kind"] for s in plan["scenes"]]
    assert kinds[0] == "title" and kinds[-1] == "finale"
    assert "cutaway" in kinds and "line" in kinds
    assert plan["disclaimer"] == DISCLAIMER_VERBATIM
    logged = " ".join(str(e) for e in ev)
    for s in plan["scenes"]:
        spoken = s.get("text") or (s.get("aside") or {}).get("text")
        if spoken and s["kind"] != "card":
            assert spoken.strip("“”…") in logged or all(w in logged for w in spoken.split()[:5])
    screens = [s for s in plan["scenes"] if s["kind"] == "screen"]
    assert {s["show"]["type"] for s in screens} >= {"diff", "terminal"}
    assert any(s.get("chapter", "").startswith("Dinesh, turn 1") for s in plan["scenes"])


def test_line_scene_carries_handoff():
    line = next(s for s in plan_verbatim(_events())["scenes"] if s["kind"] == "line")
    assert line["speaker"] == "Claude" and line["handoff"] == "Codex"


def test_description_chapters_start_at_zero_and_skip_short_ones():
    plan = {"title": "x", "logline": "Build x.", "disclaimer": "d"}
    text = description(plan, [(0.4, "Cold open"), (5.0, "too soon"), (20.0, "Dinesh, turn 1"), (75.0, "Gilfoyle, turn 1")],
                       [{"kind": "tests", "ok": True, "passed": 12}])
    assert "0:00 Cold open" in text and "too soon" not in text and "1:15 Gilfoyle, turn 1" in text
    assert "12 tests passing" in text and "not affiliated" in text


def test_youtube_title():
    assert youtube_title({"title": "tiny command-line URL shortener"}) == \
        "Gilfoyle & Dinesh Build Tiny Command-line URL Shortener"


def test_event_log_round_trip_and_ids_continue(tmp_path):
    path = tmp_path / "events.jsonl"
    log = EventLog(path)
    log.add("turn_start", agent="Codex", turn=1)
    log.add("entry", agent="Codex", content="ünïcode ✓")
    again = EventLog(path)
    again.add("complete")
    ev = read_events(path)
    assert [e["id"] for e in ev] == [0, 1, 2]
    assert ev[1]["content"] == "ünïcode ✓"
    assert ev[2]["t"] >= ev[1]["t"]


def test_cut_respects_the_budget_but_keeps_the_dialogue():
    ev = _events()
    short = plan_cut(ev, target_seconds=30)
    kinds = [s["kind"] for s in short["scenes"]]
    assert "line" in kinds and kinds[-1] == "finale"
    assert "terminal" in [s["show"]["type"] for s in short["scenes"] if s["kind"] == "screen"]  # failing tests always stay
    assert len(short["scenes"]) < len(plan_cut(ev, target_seconds=600)["scenes"])


# -- writers' room ---------------------------------------------------------------------------

from workshop.episode.writers import check_line, claims, corpus, parse_reply, punch_up, slots_for  # noqa: E402


def test_fact_check_rejects_invented_specifics():
    record = corpus(_events())
    assert check_line("Gilfoyle's encode(n) returns nothing. Magnificent.", "x", "line", record) is None
    assert "encode(7)" in check_line("encode(7) exploded.", "x", "line", record)
    assert "42" in check_line("All 42 tests failed.", "x", "line", record)
    assert "cache_layer.py" in check_line("He wrote cache_layer.py.", "x", "line", record)
    assert check_line("", "x", "line", record) == "empty"
    assert check_line("@Codex your turn", "x", "line", record)
    assert check_line("x" * 400, "x", "aside", record).startswith("too long")
    # numbers from the original line are allowed even if the log phrased them differently
    assert check_line("Four point six. 4.6 times slower.", "It was 4.6x slower", "line", record) is None


def test_claims_finds_code_numbers_and_files():
    found = claims("`short.py` has encode(0) and max_len 7 in camelCase")
    assert {"short.py", "encode(0)", "max_len", "7", "camelCase"} <= set(found)


def test_parse_reply_takes_the_first_json_object():
    assert parse_reply('Sure!\n{"s4": "Line  one", "s9a": "two"}\nthanks') == {"s4": "Line one", "s9a": "two"}
    assert parse_reply("no json") == {}


def test_each_agent_gets_only_his_own_lines():
    plan = plan_cut(_events(), target_seconds=600)
    dinesh = slots_for(plan, "Claude")
    gilfoyle = slots_for(plan, "Codex")
    assert dinesh and all(plan["scenes"][s["scene"]].get("speaker", plan["scenes"][s["scene"]].get("agent")) == "Claude"
                          or plan["scenes"][s["scene"]].get("aside", {}).get("speaker") == "Claude" for s in dinesh)
    assert [s["kind"] for s in gilfoyle] == ["cutaway"]


def test_punch_up_applies_checked_lines_and_labels_the_episode(monkeypatch):
    import workshop.episode.writers as writers

    ev = _events()
    plan = plan_cut(ev, target_seconds=600)
    line_slot = next(s for s in slots_for(plan, "Claude") if s["kind"] == "line")
    replies = {"Claude": '{"%s": "Gilfoyle, find nothing wrong with encode(n). I dare you."}' % line_slot["id"],
               "Codex": '{"%s": "Cc HR. And the 99 lawyers."}' % slots_for(plan, "Codex")[0]["id"]}
    monkeypatch.setattr(writers, "_run", lambda adapter, agent, prompt, tmp, t: (lambda: replies[agent]))
    out = punch_up(plan, ev, {"Codex": object(), "Claude": object()}, progress=lambda *_: None)
    scene = out["scenes"][line_slot["scene"]]
    assert scene["text"].startswith("Gilfoyle, find nothing") and scene["original_text"] and scene["rewritten_by"] == "Claude"
    cut = next(s for s in out["scenes"] if s["kind"] == "cutaway")
    assert cut["text"] == "Cc HR."  # "99" isn't in the record: rejected, original kept
    assert out["disclaimer"].startswith("Dramatised")
    assert plan["disclaimer"] == DISCLAIMER_VERBATIM  # the input plan is untouched


# -- written scenes ----------------------------------------------------------------------------

from workshop.episode.scenes import script_text, to_plan, validate  # noqa: E402
from workshop.episode.facts import fact_sheet  # noqa: E402


def _script(**extra):
    base = {"title": "Encode Zero", "logline": "x", "runner": "y", "scenes": [
        {"name": "Cold open", "shots": [
            {"say": "Dinesh", "line": "Your encode(n) returns nothing.", "mood": "gloating"},
            {"react": "Gilfoyle", "mood": "stare", "seconds": 9},
            {"show": "E5", "highlight": "return ''", "caption": "Exhibit A"},
        ]},
        {"name": "Later", "shots": [
            {"say": "gilfoyle", "line": "All 42 tests failed.", "to": "camera"},   # invented number: cut
            {"say": "Gilfoyle", "line": "Cc HR.", "to": "camera"},
            {"say": "Jared", "line": "Guys?"},                                     # not a character: cut
            {"show": "E99"},                                                       # no such exhibit: dropped
            {"meanwhile": "E8"}, {"sting": "wahwah"}, {"sting": "airhorn"}, {"beat": "long"},
        ]},
    ]}
    base.update(extra)
    return base


def test_validate_cuts_invented_facts_and_unknown_things():
    log = []
    s = validate(_script(), _events(), log)
    first, second = s["scenes"]
    assert first["shots"][0] == {"say": "Claude", "line": "Your encode(n) returns nothing.", "mood": "gloating",
                                 "to": "other", "frame": "wide"}
    assert first["shots"][1]["seconds"] == 3.0  # clamped
    assert first["shots"][2] == {"show": 5, "highlight": "return ''", "caption": "Exhibit A"}
    says = [x for x in second["shots"] if "say" in x]
    assert [x["line"] for x in says] == ["Cc HR."] and says[0]["frame"] == "close"
    assert {"meanwhile": 8} in second["shots"] and {"sting": "wahwah"} in second["shots"]
    assert not any(x.get("sting") == "airhorn" for x in second["shots"])
    assert {"beat": 0.8} in second["shots"]
    assert any("42" in line for line in log)


def test_validate_rejects_scripts_with_too_little_left():
    assert validate({"scenes": [{"name": "a", "shots": [{"say": "Dinesh", "line": "Hi."}]}]}, _events()) is None
    assert validate({"nope": 1}, _events()) is None


def test_to_plan_puts_the_title_after_the_cold_open():
    plan = to_plan(validate(_script(), _events()), _events())
    kinds = [s["kind"] for s in plan["scenes"]]
    assert kinds == ["sketch", "title", "sketch", "finale"]
    assert plan["scenes"][0]["cold_open"] and plan["scenes"][0]["chapter"] == "Cold open"
    assert plan["project"] == "Tiny URL shortener" and plan["disclaimer"].startswith("Dramatised")
    assert "[L1] DINESH: Your encode(n)" in script_text(validate(_script(), _events()))


def test_fact_sheet_numbers_exhibits():
    sheet = fact_sheet(_events())
    assert "E5: Dinesh creates short.py" in sheet and "E7: Dinesh's test run FAILS" in sheet
    assert "E8: meanwhile Gilfoyle" in sheet and "TURN 1: DINESH" in sheet
