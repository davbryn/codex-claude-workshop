from workshop.episode.build import description, youtube_title
from workshop.episode.capture import EventLog, read_events
from workshop.episode.plan import DISCLAIMER_VERBATIM, plan_verbatim, project_title

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
    plan = plan_verbatim(ev)
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
    assert {s["show"]["type"] for s in screens} >= {"board", "diff", "terminal"}
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
