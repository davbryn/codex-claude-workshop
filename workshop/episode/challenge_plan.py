"""A Wheel of Destiny episode: premise, spins and reactions, the build as a story, the demo, the verdict.

Nothing here is written for the characters. The laughs come from what really
happened: their own reactions to the wheel, the rules checker catching them,
the workarounds they came up with (in their own words), and the thing working
(or not) at the end.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..conversation import AGENTS
from ..theatre.cast import CHARACTER
from ..theatre.text import score_sentence, sentences, strip_markdown
from .plan import _entry_turn, _turns, diff_size, finale_lines
from ..theatre.reactions import classify_entry
from ..theatre.text import bubble_excerpt

WORKAROUND = re.compile(
    r"\b(workaround|work around|instead of|since (?:we|i) can'?t|can'?t use|no loops?|no if|without (?:a |any )?"
    r"(?:loop|if|digit|import)|recurs\w*|goto|trick|hack\w*|loophole|cheat\w*|legal(?:ly)?|"
    r"the rules?|the wheel|conjur\w*|smuggl\w*|abus\w*)\b", re.I)


def spins_of(events: list[dict]) -> list[dict]:
    return [e for e in events if e["kind"] == "spin"]


def result(spin: dict) -> dict:
    return spin["slices"][spin["result"]]


def headline(events: list[dict]) -> dict:
    """The episode's premise: what, in what, under what rule, by whom."""
    spins = spins_of(events)
    by = {(s["wheel"], s.get("who")): result(s) for s in spins}
    from .plan import project_title

    project, _brief = project_title(events)
    project = project.split("\n")[0]
    if ("project", None) in by:
        project = by[("project", None)]["label"]
    lang = by.get(("language", None), {}).get("label", "")
    limit = by.get(("limit", None), {}).get("label", "")
    return {"project": project, "language": lang.split(",")[0], "limit": limit,
            "skills": {a: by.get(("skill", a), {}).get("label", "") for a in AGENTS}}


def workaround_lines(entry: dict, limit: int = 150) -> list[str]:
    """Sentences where he explains how he got round the rules, in his own words."""
    out = []
    for s in sentences(strip_markdown(entry.get("content", ""))):
        s = " ".join(s.replace("`", "").split()).lstrip("-* ")
        if WORKAROUND.search(s) and 25 <= len(s) <= limit:
            out.append(s)
    # punchy first: short, about the rule itself, and the kind of sentence the bubble scorer likes
    rule_words = re.compile(r"\b(loop|if|digit|vowel|import|rhyme|caps|lines?|rule|wheel|cheat\w*|legal\w*)\b", re.I)
    return sorted(out, key=lambda s: -(score_sentence(s) + 2.5 * bool(rule_words.search(s)) - len(s) / 60))


def plan_challenge(events: list[dict], project_dir: Path | None = None) -> dict:
    h = headline(events)
    spins = spins_of(events)
    reactions = {(e["index"], e["agent"]): e["line"] for e in events if e["kind"] == "spin_reaction"}
    scenes: list[dict] = [{"kind": "challenge_title", "chapter": "The premise", **h}]
    # -- the wheel
    for spin in spins:
        order = list(AGENTS)
        if spin.get("who"):  # the one it landed on reacts first
            order = [spin["who"], "Claude" if spin["who"] == "Codex" else "Codex"]
        else:
            order = ["Claude", "Codex"]  # Dinesh panics, Gilfoyle buttons
        lines = [{"speaker": a, "text": reactions[(spin["index"], a)]} for a in order if (spin["index"], a) in reactions]
        scenes.append({"kind": "wheel", "spin": spin["id"], "reactions": lines,
                       "chapter": "The Wheel of Destiny" if spin is spins[0] else None})
    scenes.append({"kind": "rules", **h})
    # -- the build
    checks = [e for e in events if e["kind"] == "rules_check"]
    prev_count = 0
    counts = {a: 0 for a in AGENTS}
    tests_so_far = ""
    for n, turn in enumerate(_turns(events), 1):
        agent = turn["agent"]
        evs = turn["events"]
        entry = turn["entry"]
        scenes.append({"kind": "turn_card", "agent": agent, "turn": n, "tests": tests_so_far,
                       "chapter": f"Turn {n}: {CHARACTER[agent]}"})
        for e in evs:
            if e["kind"] == "tests":
                tests_so_far = f"{e.get('passed') or 0} ✓" if e.get("ok") else f"{e.get('failed') or '?'} ✗"
        diffs = sorted((e for e in evs if e["kind"] == "diff" and diff_size(e) > 0), key=diff_size, reverse=True)
        tricks = workaround_lines(entry) if entry else []
        if diffs:
            scenes.append({"kind": "screen", "agent": agent, "show": {"type": "diff", "events": [diffs[0]["id"]]},
                           "aside": None, "meanwhile": next((e["id"] for e in evs if e["kind"] == "bit"), None)})
        if tricks:  # the workaround, explained by the guy who did it, to camera
            scenes.append({"kind": "confessional", "speaker": agent, "text": tricks[0], "label": "THE WORKAROUND"})
        fails = [e for e in evs if e["kind"] == "tests" and not e.get("ok")]
        if fails:
            cmds = [e for e in evs if e["kind"] == "command" and e["id"] < fails[0]["id"]][-1:]
            scenes.append({"kind": "screen", "agent": agent,
                           "show": {"type": "terminal", "events": [c["id"] for c in cmds] + [fails[0]["id"]]},
                           "aside": None, "meanwhile": None})
        # the referee checks the moment a turn ends, so the check is among this turn's events
        check = next((e for e in reversed(evs) if e["kind"] == "rules_check"), None)
        if check is not None:
            if check["count"] > prev_count and check["violations"]:
                counts[agent] += check["count"] - prev_count
                scenes.append({"kind": "violation", "agent": agent, "check": check["id"],
                               "new": check["count"] - prev_count, "total": check["count"]})
            elif prev_count and check["count"] < prev_count:
                scenes.append({"kind": "cleared", "agent": agent, "fixed": prev_count - check["count"],
                               "total": check["count"]})
            prev_count = check["count"]
        if entry:
            r = classify_entry(_entry_turn(entry))
            text = bubble_excerpt(entry.get("content", ""), 160)
            if text and text not in tricks:
                scenes.append({"kind": "line", "speaker": agent, "text": text, "speaker_state": r.primary_state(),
                               "listener": r.listener_state(True), "moment": r.moment(), "handoff": None,
                               "event": entry["id"]})
    # -- the demo, and the verdict
    demo = read_demo(project_dir) if project_dir else []
    if demo:
        scenes.append({"kind": "demo", "lines": demo, "chapter": "The demo"})
    final = checks[-1]["count"] if checks else None
    lines = finale_lines(events)
    lines.insert(0, f"{h['project']} · {h['language']} · {h['limit']}")
    if final is not None:
        lines.append("Rules violations caused: " + " · ".join(f"{CHARACTER[a]} {counts[a]}" for a in AGENTS))
        lines.append("Final rules check: CLEAN ✓" if final == 0 else f"Final rules check: {final} still broken 🚨")
    scenes.append({"kind": "finale", "lines": lines, "tagline": "Somehow." if not final else "Technically.",
                   "chapter": "The verdict"})
    title = f"{h['project']} in {h['language']}. {h['limit']}."
    return {"title": title, "project": h["project"], "logline": _logline(h), "format": "challenge",
            "disclaimer": "A real, unscripted session: every line is the agents' own; the code, rules checks and "
                          "results are real.", "scenes": scenes}


def _logline(h: dict) -> str:
    return (f"The Wheel of Destiny picked the project ({h['project']}), the language ({h['language']}) and the rule "
            f"({h['limit']}). Gilfoyle codes as a {h['skills'].get('Codex')}, Dinesh as a {h['skills'].get('Claude')}. "
            "Two AI agents, no humans. Can they ship it?")


def read_demo(project_dir: Path, max_lines: int = 22) -> list[str]:
    """DEMO.md's terminal session: code-fenced lines, or the whole file if there are no fences."""
    path = Path(project_dir) / "DEMO.md"
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    fenced = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
    body = "\n".join(fenced) if fenced else text
    lines = [ln.rstrip() for ln in body.splitlines() if ln.strip()]
    return lines[:max_lines]
