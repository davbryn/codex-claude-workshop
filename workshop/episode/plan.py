"""The episode plan: an ordered list of scenes, each pointing at real events in the log.

Scene kinds (plain dicts, so an LLM showrunner can produce the same shape):

  title    {"title", "subtitle"}                                  opening title card
  card     {"title", "lines", "color"}                            a full-screen card (the brief, management, acts)
  line     {"speaker", "text", "listener", "speaker_state", "moment"}   dialogue in the room
  screen   {"agent", "show": {"type": "diff"|"terminal"|"board", "events": [...]},
            "aside": {"speaker", "text"} | None, "meanwhile": event_id | None}   his monitor, full size
  cutaway  {"agent", "event", "text"}                             the idle one's meanwhile bit
  finale   {"lines", "tagline"}                                   PROJECT COMPLETE

``plan_verbatim`` builds a plan with no writing at all: every spoken word is a
line the agents actually wrote (entries, asides, meanwhile bits), only selected
and trimmed. It is also the fallback when the writers' room is unavailable.
"""

from __future__ import annotations

import re

from ..conversation import AGENTS, ConversationTurn
from ..theatre.banter import petty_scoreboard
from ..theatre.cast import CHARACTER, MOMENTS
from ..theatre.reactions import classify_entry
from ..theatre.text import bubble_excerpt

DISCLAIMER_VERBATIM = "Cut from a real session. Every word was written by the agents themselves; the code, bugs and results are real."
DISCLAIMER_DRAMATISED = "Dramatised from a real session. The code, bugs and results are real; the lines are theirs, punched up."


def _turns(events: list[dict]) -> list[dict]:
    """Group events into turns: {agent, events: [...], entry: event|None}."""
    turns: list[dict] = []
    current = None
    for e in events:
        if e["kind"] == "turn_start":
            current = {"agent": e["agent"], "events": [], "entry": None}
            turns.append(current)
        elif e["kind"] == "entry" and turns:
            # the entry is appended during the turn; attach it to the latest turn by that agent
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
    first = re.split(r"[.:]\s", brief + " ", maxsplit=1)[0].strip().rstrip(".:")
    for prefix in ("Build a ", "Build an ", "Build ", "Create a ", "Write a "):
        if first.startswith(prefix):
            first = first[len(prefix):]
            break
    return (first[:1].upper() + first[1:])[:70] or "The Project", brief


def plan_verbatim(events: list[dict], max_screens_per_turn: int = 2) -> dict:
    title, brief = project_title(events)
    scenes: list[dict] = [
        {"kind": "title", "title": title, "subtitle": "a Codex ↔ Claude workshop episode", "chapter": "Cold open"},
        {"kind": "card", "title": "📋 THE BRIEF (FROM MANAGEMENT)", "lines": [brief[:260]], "color": "#7bd88f"},
    ]
    if any(e["kind"] == "board" for e in events):
        scenes.append({"kind": "card", "title": "📌 MANAGEMENT HAS SET UP A KANBAN BOARD",
                       "lines": ["“Please keep it current!” — Jared"], "color": "#7bd88f"})
    turn_count = {a: 0 for a in AGENTS}
    for turn in _turns(events):
        agent = turn["agent"]
        evs = turn["events"]
        turn_count[agent] += 1
        first_scene = len(scenes)
        asides = [e for e in evs if e["kind"] == "aside" and e["agent"] == agent]
        boards = [e for e in evs if e["kind"] == "board"]
        diffs = sorted((e for e in evs if e["kind"] == "diff" and diff_size(e) > 0), key=diff_size, reverse=True)
        tests = [e for e in evs if e["kind"] == "tests"]
        bits = [e for e in evs if e["kind"] == "bit"]
        screens = 0
        # 1. the first board move, with his opening aside
        if boards and asides:
            scenes.append({"kind": "screen", "agent": agent, "show": {"type": "board", "events": [boards[0]["id"]]},
                           "aside": {"speaker": agent, "text": asides[0]["text"]},
                           "meanwhile": bits[0]["id"] if bits else None})
            screens += 1
        # 2. the biggest real code change, typed out, with a mid-turn aside if there is one
        if diffs and screens < max_screens_per_turn:
            mid = asides[1]["text"] if len(asides) > 2 else None
            scenes.append({"kind": "screen", "agent": agent, "show": {"type": "diff", "events": [diffs[0]["id"]]},
                           "aside": {"speaker": agent, "text": mid} if mid else None,
                           "meanwhile": bits[0]["id"] if bits else None})
            screens += 1
        # 3. a failing test run is always worth seeing
        failing = [e for e in tests if not e.get("ok")]
        if failing:
            cmds = [e for e in evs if e["kind"] == "command" and e["id"] < failing[0]["id"]][-1:]
            scenes.append({"kind": "screen", "agent": agent,
                           "show": {"type": "terminal", "events": [c["id"] for c in cmds] + [failing[0]["id"]]},
                           "aside": None, "meanwhile": None})
        # 4. the idle one, meanwhile
        if bits:
            b = bits[0]
            scenes.append({"kind": "cutaway", "agent": b["agent"], "event": b["id"], "text": b["bit"].get("line", "")})
        # 5. his closing aside, on the board
        if len(asides) > 1 and len(boards) > 1:
            scenes.append({"kind": "screen", "agent": agent, "show": {"type": "board", "events": [boards[-1]["id"]]},
                           "aside": {"speaker": agent, "text": asides[-1]["text"]}, "meanwhile": None})
        # 6. the entry, in the room
        entry = turn["entry"]
        if entry:
            r = classify_entry(_entry_turn(entry))
            text = bubble_excerpt(entry.get("content", ""), 220)
            if text:
                scenes.append({"kind": "line", "speaker": agent, "text": text,
                               "speaker_state": r.primary_state(), "listener": r.listener_state(True),
                               "moment": r.moment(), "handoff": entry.get("handoff"), "event": entry["id"]})
        if len(scenes) > first_scene:
            label = f"{CHARACTER[agent]}, turn {turn_count[agent]}"
            moment = next((s.get("moment") for s in scenes[first_scene:] if s.get("moment")), None)
            if moment in MOMENTS:
                label += f": {MOMENTS[moment][0].lstrip('⚔ ').capitalize()}"
            scenes[first_scene]["chapter"] = label
    for e in events:
        if e["kind"] == "human" and e.get("title", "").lower() not in ("project start", ""):
            scenes.append({"kind": "card", "title": "👤 THE BOSS WALKS IN", "lines": [e.get("content", "")[:220]],
                           "color": "#7bd88f", "_after": e["id"]})
    scenes = _order(scenes, events)
    scenes.append({"kind": "finale", "lines": finale_lines(events), "tagline": "Somehow.", "chapter": "Project complete"})
    return {"title": title, "logline": brief[:200], "disclaimer": DISCLAIMER_VERBATIM, "scenes": scenes}


def _order(scenes: list[dict], events: list[dict]) -> list[dict]:
    """Human cards were appended last; slot each in after the scene preceding it in time."""
    humans = [s for s in scenes if "_after" in s]
    rest = [s for s in scenes if "_after" not in s]
    if not humans:
        return rest
    by_id = {e["id"]: e for e in events}
    out: list[dict] = []
    for scene in rest:
        out.append(scene)
    for h in humans:
        after = h.pop("_after")
        # insert before the first line scene whose entry comes after the human turn
        entries_after = [e["id"] for e in events if e["kind"] == "entry" and e["id"] > after]
        target = entries_after[0] if entries_after else None
        index = len(out)
        if target is not None:
            speaker = by_id[target]["agent"]
            for i, s in enumerate(out):
                if s["kind"] == "line" and s["speaker"] == speaker and i > 2:
                    # the first line by that speaker after the human event (approximate by order)
                    pos = sum(1 for e in events if e["kind"] == "entry" and e["id"] < target)
                    count = sum(1 for x in out[: i + 1] if x["kind"] == "line")
                    if count > pos:
                        index = i
                        while index > 0 and out[index - 1]["kind"] in ("screen", "cutaway"):
                            index -= 1
                        break
        out.insert(index, h)
    return out


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
