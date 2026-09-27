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


DULL = re.compile(r"\b(?:no (?:new|additional|further) [\w ]{0,40}?(?:was|were) (?:needed|necessary|required)|remains? "
                  r"(?:intact|the|unchanged)|straight-line code)\b", re.I)


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
        from ..challenge import PROJECTS

        spun = by[("project", None)]
        project = next((label for label, brief in PROJECTS if brief == spun.get("rule")), spun["label"])
    lang = by.get(("language", None), {}).get("label", "")
    limit = by.get(("limit", None), {}).get("label", "")
    twist = by.get(("twist", None), {}).get("label", "")
    return {"project": project, "language": lang.split(",")[0].split(" (")[0], "limit": limit, "twist": twist,
            "skills": {a: by.get(("skill", a), {}).get("label", "") for a in AGENTS}}


def workaround_lines(entry: dict, limit: int = 150) -> list[str]:
    """Sentences where he explains how he got round the rules, in his own words."""
    out = []
    for s in sentences(strip_markdown(entry.get("content", ""))):
        s = " ".join(s.replace("`", "").split()).lstrip("-* ")
        if WORKAROUND.search(s) and 25 <= len(s) <= limit and not DULL.search(s):
            out.append(s)
    # punchy first: short, about the rule itself, and the kind of sentence the bubble scorer likes
    rule_words = re.compile(r"\b(loop|if|digit|vowel|import|rhyme|caps|lines?|rule|wheel|cheat\w*|legal\w*)\b", re.I)
    return sorted(out, key=lambda s: -(score_sentence(s) + 2.5 * bool(rule_words.search(s)) - len(s) / 60))


def punch(text: str, other: str) -> float:
    """How good a real line is for a clip: the bubble scorer, plus aiming at the other guy, minus length."""
    return score_sentence(text) + (1.5 if other.lower() in text.lower() else 0.0) - max(0, len(text) - 90) / 30


def _reaction_lines(spin: dict, reactions: dict) -> list[dict]:
    """Who reacts to a spin: both for the big ones; for a skill spin, only the funnier of the two."""
    order = [spin["who"], "Claude" if spin["who"] == "Codex" else "Codex"] if spin.get("who") else ["Claude", "Codex"]
    lines = [{"speaker": a, "text": reactions[(spin["index"], a)]} for a in order if (spin["index"], a) in reactions]
    if spin["wheel"] == "skill" and len(lines) == 2:
        lines = [max(lines, key=lambda x: punch(x["text"], CHARACTER["Claude" if x["speaker"] == "Codex" else "Codex"]))]
    return lines


def plan_challenge(events: list[dict], project_dir: Path | None = None) -> dict:
    h = headline(events)
    spins = spins_of(events)
    opening = [x for x in spins if x["wheel"] != "twist"]
    reactions = {(e["index"], e["agent"]): e["line"] for e in events if e["kind"] == "spin_reaction"}
    scenes: list[dict] = []
    # -- cold open: the single best real line, then smash to the title
    candidates = [(punch(line, CHARACTER["Claude" if who == "Codex" else "Codex"]), who, line)
                  for (_i, who), line in reactions.items()]
    if candidates:
        _score, who, line = max(candidates)
        scenes.append({"kind": "confessional", "speaker": who, "text": line, "label": "", "chapter": "Cold open",
                       "cold_open": True})
    scenes.append({"kind": "challenge_title", "chapter": None if scenes else "The premise", **h})
    # -- the wheel
    for spin in opening:
        scenes.append({"kind": "wheel", "spin": spin["id"], "reactions": _reaction_lines(spin, reactions),
                       "chapter": "The Wheel of Destiny" if spin is opening[0] else None})
    scenes.append({"kind": "rules", **h})
    # the best meanwhile bits (what the waiting one got up to), at most three, never two in one turn
    bits = [e for e in events if e["kind"] == "bit" and e["bit"].get("line")]
    best_bits = sorted(bits, key=lambda e: -punch(e["bit"]["line"], CHARACTER[
        "Claude" if e["agent"] == "Codex" else "Codex"]))
    chosen_bits: list[dict] = []
    for b in best_bits:
        if len(chosen_bits) < 3 and all(abs(b["id"] - c["id"]) > 30 for c in chosen_bits):
            chosen_bits.append(b)
    chosen_ids = {b["id"] for b in chosen_bits}
    # -- the build: a montage that stops only for real moments
    prev_count = 0
    counts = {a: 0 for a in AGENTS}
    tests_so_far = ""
    first_fail = True
    for n, turn in enumerate(_turns(events), 1):
        agent = turn["agent"]
        other = "Claude" if agent == "Codex" else "Codex"
        evs = turn["events"]
        entry = turn["entry"]
        scenes.append({"kind": "turn_card", "agent": agent, "turn": n, "tests": tests_so_far,
                       "chapter": f"Turn {n}: {CHARACTER[agent]}"})
        for e in evs:
            if e["kind"] == "tests":
                tests_so_far = f"{e.get('passed') or 0} ✓" if e.get("ok") else f"{e.get('failed') or '?'} ✗"
        diffs = sorted((e for e in evs if e["kind"] == "diff" and diff_size(e) > 0), key=diff_size, reverse=True)
        asides = sorted((e for e in evs if e["kind"] == "aside" and e["agent"] == agent),
                        key=lambda e: -punch(e["text"], CHARACTER[other]))
        if diffs:
            best = asides[0] if asides else None
            scenes.append({"kind": "screen", "agent": agent, "show": {"type": "diff", "events": [diffs[0]["id"]]},
                           "aside": {"speaker": agent, "text": best["text"], "event": best["id"]} if best else None,
                           "meanwhile": next((e["id"] for e in evs if e["kind"] == "bit"), None), "fast": True})
        for b in (e for e in evs if e["id"] in chosen_ids):
            scenes.append({"kind": "cutaway", "agent": b["agent"], "event": b["id"], "text": b["bit"]["line"],
                           "best_bit": b is chosen_bits[0]})
        tricks = workaround_lines(entry) if entry else []
        if tricks and punch(tricks[0], CHARACTER[other]) > 0:
            scenes.append({"kind": "confessional", "speaker": agent, "text": tricks[0], "label": "THE WORKAROUND"})
        fails = [e for e in evs if e["kind"] == "tests" and not e.get("ok")]
        if fails and first_fail:
            first_fail = False
            cmds = [e for e in evs if e["kind"] == "command" and e["id"] < fails[0]["id"]][-1:]
            scenes.append({"kind": "screen", "agent": agent,
                           "show": {"type": "terminal", "events": [c["id"] for c in cmds] + [fails[0]["id"]]},
                           "aside": None, "meanwhile": None})
        # the referee checks when a turn ends; a twist spin (and a re-check under the new rules) may follow
        for e in evs:
            if e["kind"] == "rules_check" and not e.get("after_twist"):
                if e["count"] > prev_count and e["violations"]:
                    counts[agent] += e["count"] - prev_count
                    scenes.append({"kind": "violation", "agent": agent, "check": e["id"],
                                   "new": e["count"] - prev_count, "total": e["count"]})
                elif prev_count and e["count"] < prev_count:
                    scenes.append({"kind": "cleared", "agent": agent, "fixed": prev_count - e["count"],
                                   "total": e["count"]})
                prev_count = e["count"]
            elif e["kind"] == "spin" and e["wheel"] == "twist":
                scenes.append({"kind": "twist_intro", "chapter": "THE TWIST"})
                scenes.append({"kind": "wheel", "spin": e["id"], "reactions": _reaction_lines(e, reactions)})
            elif e["kind"] == "rules_check" and e.get("after_twist"):
                if e["count"] > prev_count and e["violations"]:
                    scenes.append({"kind": "violation", "agent": None, "check": e["id"], "twist": True,
                                   "new": e["count"] - prev_count, "total": e["count"]})
                prev_count = e["count"]
        if entry:
            r = classify_entry(_entry_turn(entry))
            text = bubble_excerpt(entry.get("content", ""), 150)
            if text and text not in tricks and (r.moment() or punch(text, CHARACTER[other]) >= 3):
                scenes.append({"kind": "line", "speaker": agent, "text": text, "speaker_state": r.primary_state(),
                               "listener": r.listener_state(True), "moment": r.moment(), "handoff": None,
                               "event": entry["id"]})
    # -- the demo, and the verdict
    demo = read_demo(project_dir) if project_dir else []
    if demo:
        scenes.append({"kind": "demo", "lines": demo, "chapter": "The demo"})
    checks = [e for e in events if e["kind"] == "rules_check"]
    final = checks[-1]["count"] if checks else None
    lines = finale_lines(events)
    lines.insert(0, f"{h['project']} · {h['language']} · {h['limit']}" + (f" · {h['twist']}" if h.get("twist") else ""))
    if final is not None:
        lines.append("Rule breaks caused: " + " · ".join(f"{CHARACTER[a]} {counts[a]}" for a in AGENTS))
        lines.append("Final rules check: CLEAN ✓" if final == 0 else f"Final rules check: {final} still broken 🚨")
    scenes.append({"kind": "finale", "lines": lines, "tagline": "Somehow." if not final else "Technically.",
                   "chapter": "The verdict"})
    title = f"{h['project']} in {h['language']}. {h['limit']}."
    return {"title": title, "project": h["project"], "logline": _logline(h), "format": "challenge",
            "headline": h, "disclaimer": "A real, unscripted session: every line is the agents' own; the code, "
                                         "rules checks and results are real.", "scenes": scenes}


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


def plan_short(plan: dict, events: list[dict]) -> dict:
    """A vertical, under-a-minute cut of a challenge episode: the hook, the two spins that matter, the twist or the
    best disaster, the thing working, the verdict."""
    by_id = {e["id"]: e for e in events}
    scenes = plan["scenes"]
    out: list[dict] = []

    def wheel_for(kind: str) -> dict | None:
        for sc in scenes:
            if sc["kind"] == "wheel" and by_id.get(sc["spin"], {}).get("wheel") == kind:
                best = sc["reactions"][:1]
                if len(sc["reactions"]) > 1:
                    best = [max(sc["reactions"], key=lambda r: punch(r["text"], CHARACTER[
                        "Claude" if r["speaker"] == "Codex" else "Codex"]))]
                return dict(sc, reactions=best, short=True)
        return None

    cold = next((sc for sc in scenes if sc.get("cold_open")), None)
    if cold:
        out.append(cold)
    for kind in ("language", "limit"):
        w = wheel_for(kind)
        if w:
            out.append(w)
    twist = wheel_for("twist")
    if twist:
        out.append({"kind": "twist_intro"})
        out.append(twist)
        fallout = next((sc for sc in scenes if sc["kind"] == "violation" and sc.get("twist")), None)
        if fallout:
            out.append(fallout)
    else:
        drama = next((sc for sc in scenes if sc["kind"] == "violation"), None) or \
            next((sc for sc in scenes if sc.get("label") == "THE WORKAROUND"), None)
        if drama:
            out.append(drama)
    bit = next((sc for sc in scenes if sc["kind"] == "cutaway" and sc.get("best_bit")), None)
    if bit:
        out.append(bit)
    demo = next((sc for sc in scenes if sc["kind"] == "demo"), None)
    if demo:
        out.append(dict(demo, lines=demo["lines"][:7]))
    finale = scenes[-1]
    out.append(dict(finale, short=True, lines=[x for x in finale["lines"] if "rules check" in x.lower()
                                                 or "tests passing" in x.lower()][:2]))
    return dict(plan, scenes=out, vertical=True)
