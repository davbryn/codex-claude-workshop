"""The fact sheet: what really happened in a session, as numbered exhibits a writer can cite.

Writers never see the raw log. They get the story turn by turn (who did what, who
caught whose bug, who conceded) and exhibits they can put on screen: real diffs,
real failing test runs, real errors, the meanwhile bits and the kanban asides.
Every exhibit keeps its event id, so a scene that shows ``E57`` shows exactly that.
"""

from __future__ import annotations

from ..theatre.cast import CHARACTER
from ..theatre.text import strip_markdown
from .plan import _entry_turn, _turns, diff_size, project_title

MAX_ENTRY = 900
MAX_SHEET = 30000


def exhibits(events: list[dict]) -> dict[int, dict]:
    """Events that can be shown on screen, by id."""
    out = {}
    for e in events:
        if e["kind"] == "diff" and diff_size(e) > 0:
            out[e["id"]] = e
        elif e["kind"] in ("tests", "error_output", "bit", "command"):
            out[e["id"]] = e
    return out


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _describe(e: dict) -> str:
    k = e["kind"]
    who = CHARACTER.get(e.get("agent", ""), "")
    if k == "diff":
        adds = [t for kind, t in e.get("lines", []) if kind == "add" and t.strip()]
        dels = [t for kind, t in e.get("lines", []) if kind == "del" and t.strip()]
        verb = "creates" if e.get("created") else "deletes" if e.get("deleted") else "edits"
        head = f"{who} {verb} {e['path']} (+{len(adds)} -{len(dels)})"
        sample = " | ".join(_clip(t.strip(), 70) for t in adds[:6])
        return head + (f": {sample}" if sample else "")
    if k == "tests":
        return f"{who}'s test run {'PASSES' if e.get('ok') else 'FAILS'}: {_clip(e.get('line', ''), 120)}"
    if k == "error_output":
        return f"error on {who}'s screen: {_clip(e.get('line', ''), 140)}"
    if k == "command":
        return f"{who} runs: {_clip(e.get('command', ''), 100)}"
    if k == "bit":
        b = e.get("bit", {})
        return (f"meanwhile {who} (waiting) makes a {b.get('kind')}: '{_clip(str(b.get('title', '')), 80)}': "
                f"{_clip(str(b.get('body', '')), 160)} / mutters: '{_clip(str(b.get('line', '')), 100)}'")
    return k


def fact_sheet(events: list[dict]) -> str:
    from ..theatre.reactions import classify_entry

    title, brief = project_title(events)
    rows = [f"PROJECT: {title}", f"THE BRIEF (from management): {brief}", ""]
    if any(e["kind"] == "board" for e in events):
        rows.append("Management (Jared) set up a shared kanban board and asked them to keep it current. "
                    "They move cards and leave asides on it.")
    for i, turn in enumerate(_turns(events), 1):
        agent = turn["agent"]
        rows.append(f"\n=== TURN {i}: {CHARACTER[agent].upper()} ===")
        for e in turn["events"]:
            if e["kind"] == "aside" and e["agent"] == agent:
                rows.append(f"  aside on the kanban: '{e['text']}'")
            elif e["kind"] in ("diff", "tests", "error_output", "bit") and (e["kind"] != "diff" or diff_size(e) > 0):
                rows.append(f"  E{e['id']}: {_describe(e)}")
        entry = turn["entry"]
        if entry:
            r = classify_entry(_entry_turn(entry))
            moment = r.moment()
            if moment:
                rows.append(f"  story beat: {moment.replace('_', ' ')}")
            body = _clip(strip_markdown(entry.get("content", "")), MAX_ENTRY)
            rows.append(f"  what {CHARACTER[agent]} wrote at the end of his turn (E{entry['id']}): {body}")
    for e in events:
        if e["kind"] == "human" and e.get("title", "").lower() not in ("project start", ""):
            rows.append(f"\nMANAGEMENT (E{e['id']}): {_clip(e.get('content', ''), 300)}")
    tests = [e for e in events if e["kind"] == "tests" and e.get("ok") and e.get("passed")]
    if tests:
        rows.append(f"\nEND: PROJECT COMPLETE, {tests[-1]['passed']} tests passing.")
    else:
        rows.append("\nEND: PROJECT COMPLETE.")
    sheet = "\n".join(rows)
    return sheet if len(sheet) <= MAX_SHEET else sheet[:MAX_SHEET] + "\n…(truncated)"
