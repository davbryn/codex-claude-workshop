"""Written episodes: scenes with setups, reactions and buttons, not a string of monologues.

1. The head writer (one CLI call) turns the fact sheet into a short script: a
   cold open, then scenes that follow what really happened. Each scene is a list
   of shots: lines, silent reaction close-ups, talking-head confessionals, beats,
   the real code or test run on screen (with the guilty line highlighted), the
   meanwhile bits, stings and captions.
2. The table read: Codex then rewrites only Gilfoyle's lines, and Claude only
   Dinesh's, so each character's final wording is his own agent's.
3. Every line is fact-checked against the session log (writers.check_line). A
   draft line that fails is cut; a table-read rewrite that fails keeps the draft.

The result is a plan (see plan.py) whose story scenes are ``sketch`` scenes.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from ..theatre.avatar_state import STATES
from ..theatre.cast import CHARACTER
from .facts import exhibits, fact_sheet
from .plan import DISCLAIMER_DRAMATISED, finale_lines, project_title
from .writers import _run, check_line, corpus, parse_reply

NAMES = {"gilfoyle": "Codex", "dinesh": "Claude"}
MOODS = tuple(s for s in STATES if s not in ("sleeping", "talking", "coding", "reading", "complete", "waiting"))
STINGS = ("wahwah", "yes", "blast", "oops", "zap", "chime", "buzz", "alert")
MAX_LINE = 120

HEAD_WRITER = """You are the head writer of a short comedy series in the style of HBO's Silicon Valley. In each episode
Gilfoyle (played by the Codex agent) and Dinesh (played by the Claude agent) build a real project together. The
session below REALLY HAPPENED; write this episode from it.

THE CHARACTERS
- Gilfoyle: deadpan, contemptuous, economical. Never excited. Satanist sysadmin energy. When he's wrong he admits
  it in as few words as possible and makes it sound like a threat. His silences are jokes.
- Dinesh: insecure, boastful, petty, desperate to win. Over-explains. Milks every rare victory far too long and is
  punished for it. Gets defensive fast.
- They hold each other in mutual contempt that is, very secretly, respect. Jared (management) is offscreen: they
  can mention him or his kanban board, he never speaks.

THIS IS BANTER, NOT A REPORT
They are two coworkers who can't stand each other, trapped at adjacent desks. Every line is aimed AT the other guy:
an attack, a defence, a comeback, a one-up. Nobody explains, summarises or narrates what they are doing. The tech is
the ammunition, not the subject: the real bug is what they hit each other with.

  REPORT (never):  "He's going to test for off-by-one errors in the cache."
  BANTER (always): "This jackass keeps submitting spaces, not tabs. For Christ's sake. DINESH. STOP BEING AN ASS."

  REPORT (never):  DINESH: "Your validator lets the same day in twice."
  BANTER (always): DINESH: "You let the same day in TWICE. Your validator is a bouncer with no eyes."
                   GILFOYLE: "And it still turned you away."

  REPORT (never):  GILFOYLE: "I found an issue with the date parsing."
  BANTER (always): GILFOYLE: "Your date parser accepted February 30th. That's not a date. That's a cry for help."
                   DINESH: "It's lenient parsing, it's a feature!"
                   GILFOYLE: "So is scurvy."
  (These examples are about other sessions. Write about THIS one.)

HOW TO MAKE IT FUNNY
- Answer the last line. Each line is a direct response to the one before it: interrupt, twist it, throw it back.
- Escalate. Each exchange gets pettier and more personal until someone lands the kill shot, then cut.
- Say the specific real thing (the actual input, value, file, error) inside the insult. Specific is funny; vague is not.
- Swear like the show when it helps the rhythm: ass, jackass, dick, damn, hell, shit, "Jesus Christ". No slurs, no
  attacks on real people, nothing about race or religion beyond Gilfoyle's LaVeyan Satanism.
- SHOUTING IN CAPS is allowed for Dinesh losing it, sparingly.
- Short. Most lines under 60 characters. An interrupted line can end with "—" and the next one cuts in.
- A silent reaction close-up after a kill shot IS a joke (Gilfoyle's dead stare, Dinesh's face falling). Use them.
- Confessionals ("to": "camera") only when the character says something he'd never say to the other guy's face,
  and it must be a joke. Never use one to explain the plot.
- When a bug is caught, SHOW the real exhibit with the guilty line highlighted, then cut to the guilty face.
- Establish a running gag early and pay it off in the last scene.
- NEVER REPEAT. No line, fact or joke appears twice. The cold open is not re-told later: the story scenes pick up
  from before it or after it. A caption never restates the line before it. No "you were right" more than once.
- Vary who wins. Gilfoyle is not always right; Dinesh occasionally lands one and is then immediately punished.

TRUTH RULES (strict)
- Everything that happens must be in the fact sheet. No invented bugs, numbers, file names, test counts or outcomes.
  Exaggerate feelings, never facts. Only Gilfoyle and Dinesh speak.
- Only cite exhibits that exist (E-numbers below). "highlight" must be text that appears in that exhibit.

STRUCTURE
- Scene 1 is a COLD OPEN: 3-6 shots, the funniest real moment or a tease of it, ending on a laugh. (The title plays after it.)
- Then 4-6 scenes that follow the real order of events. The last scene is the finish.
- 25-35 spoken lines in total (about two and a half minutes). Cut anything that is not a joke or needed for one.

SHOT TYPES (a scene is a list of these)
  {{"say": "Gilfoyle"|"Dinesh", "line": "...", "mood": "<mood>", "to": "other"|"camera", "frame": "wide"|"close"}}
  {{"react": "Gilfoyle"|"Dinesh", "mood": "<mood>", "seconds": 1.2}}       silent close-up reaction
  {{"beat": 0.8}}                                                           awkward silence, both in frame
  {{"show": "E57", "highlight": "exact text from the exhibit", "caption": "short label"}}  real code/test run on screen
  {{"meanwhile": "E80"}}                                                    cut to what the other one did while waiting
  {{"sting": "{stings}"}}                                                  one sound effect
  {{"caption": "BIG ON-SCREEN TEXT"}}                                       at most one per scene, under 30 characters
Moods: {moods}

Reply with ONLY a JSON object:
{{"title": "episode title, under 60 characters", "logline": "one sentence", "runner": "the running gag",
  "scenes": [{{"name": "...", "shots": [...]}}, ...]}}
Do not use tools, do not read or write files.

THE FACT SHEET
{facts}"""

TABLE_READ = """You are {me} (the {agent} agent) at the table read for a comedy episode in the style of HBO's Silicon Valley,
written from a real coding session you took part in with {other}. Below is the script. Rewrite ONLY {me}'s lines
(ids marked {tag}) to be funnier and more {me}: {voice}.
This is BANTER, not a report: every line is aimed at {other}, answers the line before it, and uses the real
technical detail as ammunition (the actual input, file, error), never as an explanation. Swearing like the show
(ass, jackass, dick, damn, hell, shit) is fine when it helps the rhythm; no slurs.
- Keep each line's job in the scene (the setup stays a setup, the button stays a button) and keep it short;
  a line may not grow by more than a few words. Shorter is usually funnier.
- Don't invent facts: no new numbers, file names, bugs or events beyond what the script and facts say.
- If a line is already right, leave it out of your reply.
- Never touch {other}'s lines.
Reply with ONLY a JSON object mapping line ids to new lines, e.g. {{"L7": "..."}}. Do not use tools.

THE SCRIPT
{script}

FACTS (what really happened)
{facts}"""

VOICE = {"Codex": "deadpan, dry, contemptuous, economical; never excited; admissions sound like threats",
         "Claude": "defensive, excitable, petty, over-explains, milks every win and gets punished for it"}


# -- validation --------------------------------------------------------------------------------

def _who(name) -> str | None:
    return NAMES.get(str(name or "").strip().lower())


def _exhibit_id(value, known: dict) -> int | None:
    m = re.fullmatch(r"E?(\d+)", str(value or "").strip(), re.I)
    return int(m.group(1)) if m and int(m.group(1)) in known else None


def _exhibit_text(e: dict) -> str:
    if e["kind"] == "diff":
        return "\n".join(t for _, t in e.get("lines", []))
    if e["kind"] == "bit":
        return " ".join(str(v) for v in e.get("bit", {}).values())
    return str(e.get("line") or e.get("command") or "")


_STOP = {"the", "a", "an", "and", "or", "to", "of", "it", "is", "in", "on", "that", "this", "you", "your", "i", "my",
         "he", "his", "me", "we", "for", "was", "with", "be", "just", "so", "but", "not", "no", "yes", "oh"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in _STOP and len(w) > 2}


def _repeats(line: str, said: list[set[str]], threshold: float = 0.6) -> str | None:
    """Why ``line`` is a rerun of something already said, or None."""
    words = _words(line)
    if len(words) < 2:
        return None
    for earlier in said:
        if earlier and len(words & earlier) / len(words) >= threshold:
            return "repeats an earlier line"
    return None


def validate(script: dict, events: list[dict], log: list[str] | None = None) -> dict | None:
    """A clean script (bad shots dropped, lines fact-checked), or None if nothing usable is left."""
    log = log if log is not None else []
    known = exhibits(events)
    record = corpus(events)
    scenes = []
    said: list[set[str]] = []
    for sc in script.get("scenes", []) if isinstance(script, dict) else []:
        shots = []
        for shot in sc.get("shots", []) if isinstance(sc, dict) else []:
            if not isinstance(shot, dict):
                continue
            if "say" in shot:
                who, line = _who(shot.get("say")), " ".join(str(shot.get("line", "")).split())
                if not who or not line:
                    continue
                problem = check_line(line, "", "line", record, limit=MAX_LINE) or _repeats(line, said)
                if problem:
                    log.append(f"cut draft line ({problem}): {CHARACTER[who]}: {line}")
                    continue
                said.append(_words(line))
                mood = shot.get("mood") if shot.get("mood") in MOODS else None
                shots.append({"say": who, "line": line, "mood": mood,
                              "to": "camera" if shot.get("to") == "camera" else "other",
                              "frame": "close" if shot.get("frame") == "close" or shot.get("to") == "camera" else "wide"})
            elif "react" in shot:
                who = _who(shot.get("react"))
                if who:
                    seconds = shot.get("seconds", 1.2)
                    seconds = max(0.6, min(3.0, float(seconds))) if isinstance(seconds, (int, float)) else 1.2
                    shots.append({"react": who, "mood": shot.get("mood") if shot.get("mood") in MOODS else "stare",
                                  "seconds": seconds})
            elif "beat" in shot:
                b = shot.get("beat")
                shots.append({"beat": max(0.3, min(2.5, float(b))) if isinstance(b, (int, float)) else 0.8})
            elif "show" in shot:
                eid = _exhibit_id(shot.get("show"), known)
                if eid is None:
                    log.append(f"dropped show of unknown exhibit {shot.get('show')}")
                    continue
                highlight = str(shot.get("highlight") or "").strip()
                if highlight and highlight.lower() not in _exhibit_text(known[eid]).lower():
                    highlight = ""
                caption = " ".join(str(shot.get("caption") or "").split())[:40]
                if caption and check_line(caption, "", "aside", record, limit=40):
                    caption = ""
                shots.append({"show": eid, "highlight": highlight, "caption": caption})
            elif "meanwhile" in shot:
                eid = _exhibit_id(shot.get("meanwhile"), known)
                if eid is not None and known[eid]["kind"] == "bit":
                    shots.append({"meanwhile": eid})
            elif "sting" in shot and shot.get("sting") in STINGS:
                shots.append({"sting": shot["sting"]})
            elif "caption" in shot:
                text = " ".join(str(shot.get("caption", "")).split())[:34]
                if text and not check_line(text, "", "aside", record, limit=34) and not _repeats(text, said[-2:], 0.5):
                    shots.append({"caption": text})
        if any("say" in s for s in shots):
            scenes.append({"name": str(sc.get("name", ""))[:60], "shots": shots})
    if len(scenes) < 2:
        return None
    return {"title": " ".join(str(script.get("title", "")).split())[:70],
            "logline": " ".join(str(script.get("logline", "")).split())[:200],
            "runner": " ".join(str(script.get("runner", "")).split())[:200], "scenes": scenes}


def script_text(script: dict) -> str:
    """The script as the table read sees it, with line ids."""
    rows, n = [], 0
    for i, sc in enumerate(script["scenes"]):
        rows.append(f"\nSCENE {i + 1}{' (COLD OPEN)' if i == 0 else ''}: {sc['name']}")
        for shot in sc["shots"]:
            if "say" in shot:
                n += 1
                shot["id"] = f"L{n}"
                to = " (to camera)" if shot["to"] == "camera" else ""
                rows.append(f"  [L{n}] {CHARACTER[shot['say']].upper()}{to}: {shot['line']}")
            elif "react" in shot:
                rows.append(f"  ({CHARACTER[shot['react']]} reacts: {shot['mood']})")
            elif "beat" in shot:
                rows.append("  (beat)")
            elif "show" in shot:
                rows.append(f"  (on screen: exhibit E{shot['show']}{', highlighting ' + repr(shot['highlight']) if shot['highlight'] else ''})")
            elif "meanwhile" in shot:
                rows.append(f"  (cut to: meanwhile, E{shot['meanwhile']})")
    return "\n".join(rows)


# -- the room ---------------------------------------------------------------------------------------

def write_episode(events: list[dict], adapters: dict, progress=print, head: str = "Claude",
                  timeout_s: float = 420.0, log_dir: Path | None = None) -> dict | None:
    """Head writer + table read. Returns a plan with sketch scenes, or None (then use plan_cut)."""
    tmp = Path(tempfile.mkdtemp(prefix="workshop-room-"))
    facts = fact_sheet(events)
    log: list[str] = []
    if head not in adapters:
        return None
    prompt = HEAD_WRITER.format(stings="|".join(STINGS), moods=", ".join(MOODS), facts=facts)
    progress(f"writers' room: {head} is drafting the episode")
    try:
        reply = _run(adapters[head], head, prompt, tmp, timeout_s)()
    except Exception as exc:
        progress(f"writers' room: the draft failed ({exc})")
        return None
    draft = _parse_script(reply)
    script = validate(draft, events, log) if draft else None
    if script is None:
        progress("writers' room: the draft wasn't usable")
        _save_log(log_dir, log, reply)
        return None
    text = script_text(script)
    lines = {s["id"]: s for sc in script["scenes"] for s in sc["shots"] if "say" in s}
    progress(f"writers' room: draft has {len(script['scenes'])} scenes, {len(lines)} lines; table read")
    record = corpus(events)
    jobs = {}
    for agent in ("Codex", "Claude"):
        if agent not in adapters or not any(s["say"] == agent for s in lines.values()):
            continue
        other = "Claude" if agent == "Codex" else "Codex"
        mine = [i for i, s in lines.items() if s["say"] == agent]
        p = TABLE_READ.format(me=CHARACTER[agent], agent=agent, other=CHARACTER[other], voice=VOICE[agent],
                              tag=", ".join(mine), script=text, facts=facts[:12000])
        try:
            jobs[agent] = _run(adapters[agent], agent, p, tmp, timeout_s)
        except Exception as exc:
            log.append(f"table read: {agent} unavailable ({exc})")
    for agent, wait in jobs.items():
        try:
            notes = parse_reply(wait())
        except Exception as exc:
            log.append(f"table read: {agent} failed ({exc})")
            continue
        for lid, new in notes.items():
            shot = lines.get(lid)
            if not shot or shot["say"] != agent or not new or new == shot["line"]:
                continue
            new = new.strip().strip('"“”')
            problem = check_line(new, shot["line"], "line", record,
                                 limit=min(MAX_LINE, max(len(shot["line"]) + 25, 60)))
            log.append(f"table read {CHARACTER[agent]} {lid}: {'REJECTED (' + problem + ')' if problem else 'ok'}\n"
                       f"  draft: {shot['line']}\n  final: {new}")
            if not problem:
                shot["draft"], shot["line"], shot["by"] = shot["line"], new, agent
    _save_log(log_dir, log, reply)
    return to_plan(script, events)


def _parse_script(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    for start in [i for i, ch in enumerate(text) if ch == "{"][:20]:
        try:
            data, _ = decoder.raw_decode(text[start:])
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("scenes"), list):
            return data
    return None


def _save_log(log_dir: Path | None, log: list[str], draft_reply: str) -> None:
    if log_dir is None:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "writers-room.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    (log_dir / "draft.txt").write_text(draft_reply, encoding="utf-8")


def to_plan(script: dict, events: list[dict]) -> dict:
    title, brief = project_title(events)
    scenes = []
    for i, sc in enumerate(script["scenes"]):
        scene = {"kind": "sketch", "name": sc["name"], "shots": sc["shots"], "chapter": sc["name"] or f"Scene {i}"}
        if i == 0:
            scene["chapter"] = "Cold open"
            scene["cold_open"] = True
        scenes.append(scene)
        if i == 0:
            scenes.append({"kind": "title", "title": script.get("title") or title,
                           "subtitle": f"Gilfoyle and Dinesh build: {title}"})
    scenes.append({"kind": "finale", "lines": finale_lines(events), "tagline": "Somehow.", "chapter": "Project complete"})
    return {"title": script.get("title") or title, "project": title, "logline": script.get("logline") or brief[:200],
            "runner": script.get("runner", ""), "disclaimer": DISCLAIMER_DRAMATISED, "scenes": scenes}
