"""The episode plan: an ordered list of scenes, each pointing at real events in the log.

Scene kinds (plain dicts, so a writers' room can rewrite the same shape):

  title    {"title", "subtitle"}                                  opening title card
  card     {"title", "lines", "color"}                            a full-screen card (the brief, management)
  line     {"speaker", "text", "listener", "speaker_state", "moment", "handoff", "event"}   dialogue in the room
  screen   {"agent", "show": {"type": "diff"|"terminal"|"board", "events": [...]},
            "aside": {"speaker", "text", "event"} | None, "meanwhile": event_id | None}   his monitor, full size
  cutaway  {"agent", "event", "text"}                             the idle one's meanwhile bit
  finale   {"lines", "tagline"}                                   PROJECT COMPLETE

``plan_cut`` is an editor, not a writer: every spoken word is a line the agents
actually wrote (entries, asides, meanwhile bits). It scores each candidate beat,
keeps the dialogue backbone and the best of everything else until the running
time is used up, and opens cold on the best moment.
"""

from __future__ import annotations

import re

from ..conversation import AGENTS, ConversationTurn
from ..theatre.banter import petty_scoreboard
from ..theatre.cast import CHARACTER, MOMENTS
from ..theatre.reactions import classify_entry
from ..theatre.text import bubble_excerpt, score_sentence

DISCLAIMER_VERBATIM = "Cut from a real session. Every word was written by the agents themselves; the code, bugs and results are real."
DISCLAIMER_DRAMATISED = "Dramatised from a real session. The code, bugs and results are real; each character's lines were punched up by that agent itself."

MOMENT_SCORE = {"dinesh_catches": 10, "gilfoyle_catches": 10, "own_goal": 9, "both_wrong": 8, "concession": 7,
                "disagreement": 7, "same_solution": 6, "character_development": 6}
SPEECH_CPS = 13.0  # characters per second of speech, roughly, for estimating running time


def _turns(events: list[dict]) -> list[dict]:
    """Group events into turns: {agent, events: [...], entry: event|None}."""
    turns: list[dict] = []
    current = None
    for e in events:
        if e["kind"] == "turn_start":
            current = {"agent": e["agent"], "events": [], "entry": None}
            turns.append(current)
        elif e["kind"] == "entry" and turns:
            for t in reversed(turns):
                if t["agent"] == e["agent"] and t["entry"] is None:
                    t["entry"] = e
                    break
        elif current is not None and e["kind"] != "turn_end":
            current["events"].append(e)
    return turns


def diff_size(e: dict) -> int:
    return sum(1 for kind, _ in e.get("lines", []) if kind in ("add", "del"))


def _entry_turn(e: dict) -> ConversationTurn:
    return ConversationTurn(e["agent"], e.get("title", ""), 0, e.get("content", ""), e.get("handoff"))


def project_title(events: list[dict]) -> tuple[str, str]:
    brief = next((e.get("brief", "") for e in events if e["kind"] == "session" and e.get("brief")), "") or \
        next((e.get("content", "") for e in events if e["kind"] == "human"), "")
    # drop the "_2026-09-27 13:46_" stamp and any leading markdown
    lines = [ln for ln in brief.splitlines() if ln.strip() and not re.fullmatch(r"_[\d\- :]+_", ln.strip())]
    brief = " ".join(ln.strip().lstrip("#*- ").strip() for ln in lines)
    brief = re.sub(r"\s*@(Codex|Claude)\s*$", "", brief)
    first = re.split(r"[.:]\s", brief + " ", maxsplit=1)[0].strip().rstrip(".:")
    for prefix in ("Build a ", "Build an ", "Build ", "Create a ", "Create an ", "Write a ", "Write an ", "Make a "):
        if first.startswith(prefix):
            first = first[len(prefix):]
            break
    return (first[:1].upper() + first[1:])[:70] or "The Project", brief


def _aside_score(text: str, agent: str) -> float:
    """Asides that go after the other one score higher (score_sentence already likes names)."""
    other = CHARACTER["Claude" if agent == "Codex" else "Codex"]
    return score_sentence(text) + (1.5 if other.lower() in text.lower() else 0.0)


def estimate_seconds(scene: dict) -> float:
    kind = scene["kind"]
    if kind == "title":
        return 5.5
    if kind == "card":
        return max(3.2, min(7.0, 2.2 + sum(len(x) for x in scene.get("lines", [])) / 45)) + 0.6
    if kind == "line":
        return len(scene["text"]) / SPEECH_CPS + 1.8 + (0.8 if scene.get("handoff") else 0)
    if kind == "cutaway":
        return 1.4 + max(3.5, len(scene.get("text", "")) / SPEECH_CPS + 1.2)
    if kind == "screen":
        aside = (scene.get("aside") or {}).get("text", "")
        base = {"diff": 6.0, "terminal": 6.5, "board": 4.0}[scene["show"]["type"]]
        return 0.7 + max(base, len(aside) / SPEECH_CPS + 1.2)
    if kind == "finale":
        return 12.5
    return 3.0


def plan_cut(events: list[dict], target_seconds: float = 210.0, cold_open: bool = True) -> dict:
    title, brief = project_title(events)
    fixed_head: list[dict] = [
        {"kind": "title", "title": title, "subtitle": "a Codex ↔ Claude workshop episode"},
        {"kind": "card", "title": "📋 THE BRIEF (FROM MANAGEMENT)", "lines": [brief[:260]], "color": "#7bd88f"},
    ]
    if any(e["kind"] == "board" for e in events):
        fixed_head.append({"kind": "card", "title": "📌 MANAGEMENT HAS SET UP A KANBAN BOARD",
                           "lines": ["“Please keep it current!” — Jared"], "color": "#7bd88f"})

    # Every beat is (order, score, scene). Score None = always kept.
    beats: list[tuple[tuple, float | None, dict]] = []
    turn_count = {a: 0 for a in AGENTS}
    for ti, turn in enumerate(_turns(events)):
        agent = turn["agent"]
        other = "Claude" if agent == "Codex" else "Codex"
        evs = turn["events"]
        turn_count[agent] += 1
        asides = sorted((e for e in evs if e["kind"] == "aside" and e["agent"] == agent),
                        key=lambda e: _aside_score(e["text"], agent), reverse=True)
        boards = [e for e in evs if e["kind"] == "board"]
        diffs = sorted((e for e in evs if e["kind"] == "diff" and diff_size(e) > 0), key=diff_size, reverse=True)
        failing = [e for e in evs if e["kind"] == "tests" and not e.get("ok")]
        bits = sorted((e for e in evs if e["kind"] == "bit" and e["agent"] == other),
                      key=lambda e: score_sentence(e["bit"].get("line", "") or e["bit"].get("title", "")), reverse=True)
        used_asides: list[dict] = []

        def take_aside():
            for a in asides:
                if a not in used_asides:
                    used_asides.append(a)
                    return {"speaker": agent, "text": a["text"], "event": a["id"]}
            return None

        meanwhile = bits[0]["id"] if bits else None
        # the work: the biggest real code change, captioned with his best aside
        if diffs:
            d = diffs[0]
            aside = take_aside()
            score = 3 + min(3.0, diff_size(d) / 20) + (_aside_score(aside["text"], agent) if aside else 0)
            beats.append(((ti, d["id"]), score, {"kind": "screen", "agent": agent,
                                                 "show": {"type": "diff", "events": [d["id"]]},
                                                 "aside": aside, "meanwhile": meanwhile}))
        # a failing test run is always worth seeing
        if failing:
            f = failing[0]
            cmds = [e for e in evs if e["kind"] == "command" and e["id"] < f["id"]][-1:]
            beats.append(((ti, f["id"]), 9.0, {"kind": "screen", "agent": agent,
                                               "show": {"type": "terminal", "events": [c["id"] for c in cmds] + [f["id"]]},
                                               "aside": None, "meanwhile": None}))
        # another aside, on the board (the kanban is part of the joke)
        aside = take_aside()
        if aside and boards:
            board = min(boards, key=lambda b: abs(b["id"] - aside["event"]))
            beats.append(((ti, aside["event"]), _aside_score(aside["text"], agent),
                          {"kind": "screen", "agent": agent, "show": {"type": "board", "events": [board["id"]]},
                           "aside": aside, "meanwhile": None}))
        # the idle one, meanwhile
        if bits:
            b = bits[0]
            text = b["bit"].get("line", "")
            beats.append(((ti, b["id"]), 4 + score_sentence(text or b["bit"].get("title", "")),
                          {"kind": "cutaway", "agent": b["agent"], "event": b["id"], "text": text}))
        # the entry, in the room: the backbone, always kept
        entry = turn["entry"]
        if entry:
            r = classify_entry(_entry_turn(entry))
            text = bubble_excerpt(entry.get("content", ""), 220)
            if text:
                moment = r.moment()
                beats.append(((ti, 10 ** 9), None, {
                    "kind": "line", "speaker": agent, "text": text, "speaker_state": r.primary_state(),
                    "listener": r.listener_state(True), "moment": moment, "handoff": entry.get("handoff"),
                    "event": entry["id"], "_score": MOMENT_SCORE.get(moment, 3) + score_sentence(text) / 3,
                    "_turn": (agent, turn_count[agent])}))
    for e in events:
        if e["kind"] == "human" and e.get("title", "").lower() not in ("project start", ""):
            ti = sum(1 for t in _turns(events) if t["entry"] and t["entry"]["id"] < e["id"])
            beats.append(((ti, -1), None, {"kind": "card", "title": "👤 THE BOSS WALKS IN",
                                           "lines": [e.get("content", "")[:220]], "color": "#7bd88f"}))

    finale = {"kind": "finale", "lines": finale_lines(events), "tagline": "Somehow."}
    lines = [s for _, score, s in beats if s["kind"] == "line"]
    best = max(lines, key=lambda s: s["_score"], default=None)
    opener = []
    if cold_open and best is not None and best["_score"] >= 7:
        opener = [dict(best, handoff=None, cold_open=True)]
    budget = target_seconds - sum(estimate_seconds(s) for s in fixed_head + opener + [finale])
    budget -= sum(estimate_seconds(s) for _, score, s in beats if score is None)
    kept = {id(s) for _, score, s in beats if score is None}
    for _, score, s in sorted((b for b in beats if b[1] is not None), key=lambda b: b[1], reverse=True):
        cost = estimate_seconds(s)
        if cost <= budget or score >= 9:  # a failing test run or a great line earns its place regardless
            kept.add(id(s))
            budget -= cost
    story = [s for _, _, s in sorted(beats, key=lambda b: b[0]) if id(s) in kept]

    # chapters: the first scene of each turn that made the cut
    seen: set = set()
    for i, s in enumerate(story):
        turn = next((x.get("_turn") for x in story[i:] if x["kind"] == "line"), None)
        if turn and turn not in seen:
            seen.add(turn)
            line = next(x for x in story[i:] if x["kind"] == "line")
            label = f"{CHARACTER[turn[0]]}, turn {turn[1]}"
            if line.get("moment") in MOMENTS:
                label += ": " + MOMENTS[line["moment"]][0].lstrip("⚔ ").capitalize()
            s["chapter"] = label
    scenes = opener + fixed_head + story + [finale]
    scenes[0]["chapter"] = "Cold open"
    finale["chapter"] = "Project complete"
    for s in scenes:
        s.pop("_score", None)
        s.pop("_turn", None)
    return {"title": title, "logline": brief[:200], "disclaimer": DISCLAIMER_VERBATIM, "scenes": scenes,
            "estimated_seconds": round(sum(estimate_seconds(s) for s in scenes))}


plan_verbatim = plan_cut  # the old name


def finale_lines(events: list[dict]) -> list[str]:
    turns = sum(1 for e in events if e["kind"] == "entry")
    counts = {a: sum(1 for e in events if e["kind"] == "entry" and e["agent"] == a) for a in AGENTS}
    lines = [f"{turns} turns ({' · '.join(f'{CHARACTER[a]} {n}' for a, n in counts.items())})"]
    tests = [e for e in events if e["kind"] == "tests" and e.get("ok") and e.get("passed")]
    if tests:
        lines.append(f"{tests[-1]['passed']} tests passing at the end")
    fails = sum(1 for e in events if e["kind"] == "tests" and not e.get("ok"))
    if fails:
        lines.append(f"{fails} failing test run{'s' if fails != 1 else ''} along the way")
    asides = sum(1 for e in events if e["kind"] == "aside")
    if asides:
        lines.append(f"{asides} kanban asides · {sum(1 for e in events if e['kind'] == 'bit')} things done while waiting")
    entries = [_entry_turn(e) for e in events if e["kind"] == "entry"]
    if entries:
        board = petty_scoreboard(entries)
        lines.append("Bugs caught: " + " · ".join(f"{CHARACTER[a]} {board[a].bugs_caught}" for a in AGENTS))
    return lines
