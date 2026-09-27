"""The writers' room: each agent punches up only its own character's lines.

The editor (plan.py) decides what's in the episode. Then Codex is asked, once, to
rewrite Gilfoyle's lines and Claude, once, to rewrite Dinesh's, each from the
original line plus the facts of what really happened. Nobody writes for the
other character.

Every rewrite is fact-checked deterministically against the session log: any
number, file name, function call or identifier it mentions must appear in the
record. A line that fails, is too long or comes back empty keeps the original
wording. The rewritten episode is labelled as a dramatisation, and script.json
keeps each original line next to its rewrite.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from ..theatre.cast import CHARACTER
from .plan import DISCLAIMER_DRAMATISED

LIMITS = {"line": 220, "aside": 120, "cutaway": 110}

PROMPT = """You are {me} (the {agent} agent, playing {me} from HBO's Silicon Valley). A real coding session you
took part in with {other} is being cut into a short comedy episode. This is the writers' room: below are YOUR
lines, each as you originally wrote it, with the facts of what really happened at that moment.

Punch each one up in {me}'s voice: tighter, better timing, one clean punchline, a callback where it lands.
Shorter is funnier: cut setup, cut lists of facts, end on the joke. Most lines should get SHORTER.
The rules are strict:
- Use ONLY the facts given. Do not invent numbers, file names, function names, test counts, events or outcomes.
  If a fact isn't listed, it didn't happen.
- Do not add new claims about what anyone did or said. Rephrase and sharpen what the original and facts say.
- Keep what the line is about and who the joke is aimed at. Keep {me} in character ({voice}).
- It must still make sense on its own when heard once, out loud, by someone who can't read code.
- Write only {me}'s lines. Never write lines for {other} or anyone else.
- Each line must be speakable aloud: no markdown, no code blocks, no emoji. Stay under the character limit.
- If a line is already as good as it gets, return it unchanged.
- Workplace-funny: no slurs, nothing about real people.

The episode, in order (for context and callbacks):
{outline}

Your lines:
{slots}

Reply with ONLY a JSON object mapping each slot id to your new line, e.g. {{"s4": "...", "s9a": "..."}}.
Do not use tools, do not read or write files."""

VOICE = {"Codex": "deadpan, dry, contemptuous, economical; Satanist sysadmin who is always right",
         "Claude": "defensive, excitable, petty, desperate to win; gloats hard when he catches a bug"}


def slots_for(plan: dict, agent: str) -> list[dict]:
    """The lines in the plan that belong to ``agent``'s character."""
    out = []
    for i, s in enumerate(plan["scenes"]):
        if s.get("cold_open"):
            continue  # the cold open replays a story line; it's rewritten with it
        if s["kind"] == "line" and s["speaker"] == agent:
            out.append({"id": f"s{i}", "kind": "line", "scene": i, "text": s["text"], "event": s.get("event")})
        elif s["kind"] == "screen" and (s.get("aside") or {}).get("speaker") == agent and s["aside"].get("text"):
            out.append({"id": f"s{i}a", "kind": "aside", "scene": i, "text": s["aside"]["text"],
                        "event": s["aside"].get("event")})
        elif s["kind"] == "cutaway" and s["agent"] == agent and s.get("text"):
            out.append({"id": f"s{i}", "kind": "cutaway", "scene": i, "text": s["text"], "event": s.get("event")})
    return out


def _facts(slot: dict, plan: dict, events: dict) -> str:
    """What really happened around this line, from the log."""
    scene = plan["scenes"][slot["scene"]]
    e = events.get(slot.get("event")) or {}
    facts = []
    if slot["kind"] == "line":
        facts.append("his full entry: " + " ".join(e.get("content", "").split())[:1400])
        if scene.get("moment"):
            facts.append(f"the moment: {scene['moment'].replace('_', ' ')}")
    elif slot["kind"] == "aside":
        facts.append(f"said while moving the kanban card '{e.get('card', '')}'")
        show = scene.get("show", {})
        for ev_id in show.get("events", []):
            ev = events.get(ev_id, {})
            if ev.get("kind") == "diff":
                added = [t for k, t in ev.get("lines", []) if k == "add"][:12]
                facts.append(f"on screen: his edit to {ev.get('path')}: " + " | ".join(x.strip() for x in added if x.strip()))
            elif ev.get("kind") == "tests":
                facts.append(f"on screen: test run: {ev.get('line')}")
    elif slot["kind"] == "cutaway":
        bit = e.get("bit", {})
        facts.append(f"while the other one worked he made a {bit.get('kind')}: '{bit.get('title')}': "
                     + " ".join(str(bit.get("body", "")).split())[:300])
    return "; ".join(f for f in facts if f)


def outline(plan: dict) -> str:
    rows = []
    for i, s in enumerate(plan["scenes"]):
        if s["kind"] == "line":
            rows.append(f"[s{i}] {CHARACTER[s['speaker']]}: {s['text']}")
        elif s["kind"] == "screen" and s.get("aside"):
            rows.append(f"[s{i}a] ({CHARACTER[s['aside']['speaker']]}, muttering at his monitor) {s['aside']['text']}")
        elif s["kind"] == "screen" and s["show"]["type"] == "terminal":
            rows.append(f"[s{i}] (a test run fails on {CHARACTER[s['agent']]}'s screen)")
        elif s["kind"] == "cutaway":
            rows.append(f"[s{i}] ({CHARACTER[s['agent']]}, meanwhile) {s.get('text', '')}")
        elif s["kind"] == "card":
            rows.append(f"[s{i}] CARD: {s['title']}: {' '.join(s.get('lines', []))[:200]}")
    return "\n".join(rows)


def build_prompt(plan: dict, events: dict, agent: str, slots: list[dict]) -> str:
    other = CHARACTER["Claude" if agent == "Codex" else "Codex"]
    rows = [f"- {s['id']} ({s['kind']}, max {max_chars(s['kind'], s['text'])} characters)\n  original: {s['text']}\n"
            f"  facts: {_facts(s, plan, events)}" for s in slots]
    return PROMPT.format(me=CHARACTER[agent], agent=agent, other=other, voice=VOICE[agent],
                         outline=outline(plan), slots="\n".join(rows))


# -- fact check ------------------------------------------------------------------------------

_CHECKS = [
    re.compile(r"`([^`]+)`"),
    re.compile(r"\b[A-Za-z_][\w.]*\([^)]{0,30}\)"),  # encode(0), resolve()
    re.compile(r"\b[\w-]+\.(?:py|js|ts|tsx|md|json|txt|toml|ya?ml|cfg|ini|sh|ps1|csv|html|css)\b", re.I),
    re.compile(r"\b[a-z0-9]+(?:_[a-z0-9]+)+\b"),  # snake_case
    re.compile(r"\b[a-z]+[A-Z]\w*\b|\b[A-Z][a-z]+[A-Z]\w*\b"),  # camelCase / CamelCase
    re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])"),  # numbers
]
_BANNED = re.compile(r"@(?:Codex|Claude)\b|PROJECT COMPLETE|HUMAN DECISION NEEDED|```", re.I)


def claims(text: str) -> list[str]:
    found = []
    for pattern in _CHECKS:
        for m in pattern.finditer(text):
            found.append((m.group(1) if m.groups() else m.group(0)).strip())
    return [c for c in found if c]


def corpus(events: list[dict]) -> str:
    parts = []
    for e in events:
        for key in ("content", "text", "brief", "command", "line", "path", "card"):
            if isinstance(e.get(key), str):
                parts.append(e[key])
        if e.get("kind") == "diff":
            parts.extend(t for _, t in e.get("lines", []))
        if e.get("kind") == "bit":
            parts.extend(str(v) for v in e.get("bit", {}).values())
        if e.get("kind") == "tests":
            parts.append(f"{e.get('passed')} passed {e.get('failed')} failed")
    return "\n".join(parts).lower()


def max_chars(kind: str, original: str) -> int:
    """A rewrite may be a little longer than the original, never much (padding kills the timing)."""
    return int(min(LIMITS[kind], max(70, len(original) * 1.2)))


def check_line(new: str, original: str, kind: str, record: str, limit: int | None = None) -> str | None:
    """Why ``new`` can't be used, or None if it passes."""
    new = new.strip()
    if not new:
        return "empty"
    limit = limit or max_chars(kind, original)
    if len(new) > limit + 10:
        return f"too long ({len(new)} > {limit})"
    if _BANNED.search(new):
        return "protocol words or markdown"
    allowed = record + "\n" + original.lower()
    for claim in claims(new):
        if claim.lower() not in allowed:
            return f"'{claim}' isn't in the record"
    return None


def parse_reply(text: str) -> dict[str, str]:
    decoder = json.JSONDecoder()
    for start in [i for i, ch in enumerate(text) if ch == "{"][:40]:
        try:
            data, _ = decoder.raw_decode(text[start:])
        except ValueError:
            continue
        if isinstance(data, dict) and data:
            return {str(k): " ".join(str(v).split()) for k, v in data.items() if isinstance(v, (str, int, float))}
    return {}


# -- running the CLIs ------------------------------------------------------------------------------

def _run(adapter, agent: str, prompt: str, tmp: Path, timeout_s: float):
    """Start one side call (tools off / read-only, in a temp folder). Returns a waiter."""
    from PySide6.QtCore import QProcess, QProcessEnvironment

    exe = adapter.resolve_executable()
    out_file = tmp / f"{agent.lower()}-writers.txt"
    out_file.unlink(missing_ok=True)
    if agent == "Claude":
        args, drop = ["-p", "--output-format", "text", "--tools", ""], ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
    else:
        args, drop = ["exec", "--color", "never", "--skip-git-repo-check", "--sandbox", "read-only",
                      "--output-last-message", str(out_file), "-"], ()
    spec = adapter.make_spec(exe, args, stdin=prompt)
    proc = QProcess()
    proc.setWorkingDirectory(str(tmp))
    env = QProcessEnvironment.systemEnvironment()
    for name in drop:
        env.remove(name)
    proc.setProcessEnvironment(env)
    proc.setProgram(spec.program)
    proc.setArguments(spec.args)
    if spec.native_arguments is not None and hasattr(proc, "setNativeArguments"):
        proc.setNativeArguments(spec.native_arguments)
    proc.start()
    if not proc.waitForStarted(10000):
        raise RuntimeError("the CLI did not launch")
    proc.write(prompt.encode("utf-8"))
    proc.closeWriteChannel()

    def wait() -> str:
        if not proc.waitForFinished(int(timeout_s * 1000)):
            proc.kill()
            proc.waitForFinished(3000)
            raise RuntimeError(f"timed out after {timeout_s:.0f}s")
        text = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        if agent == "Codex" and out_file.exists():
            text = out_file.read_text(encoding="utf-8", errors="replace")
        return text

    return wait


def punch_up(plan: dict, events: list[dict], adapters: dict, progress=print, timeout_s: float = 300.0,
             log_dir: Path | None = None) -> dict:
    """Return a copy of ``plan`` with each character's lines rewritten by his own agent (where they pass)."""
    plan = json.loads(json.dumps(plan))
    by_id = {e["id"]: e for e in events}
    record = corpus(events)
    tmp = Path(tempfile.mkdtemp(prefix="workshop-writers-"))
    jobs = {}
    for agent in ("Codex", "Claude"):
        slots = slots_for(plan, agent)
        if not slots or agent not in adapters:
            continue
        prompt = build_prompt(plan, by_id, agent, slots)
        try:
            jobs[agent] = (slots, _run(adapters[agent], agent, prompt, tmp, timeout_s), prompt)
            progress(f"writers' room: {CHARACTER[agent]} ({agent}) is punching up {len(slots)} of his lines")
        except Exception as exc:
            progress(f"writers' room: {agent} unavailable ({exc}); keeping his original lines")
    report = []
    changed = 0
    for agent, (slots, wait, prompt) in jobs.items():
        try:
            reply = parse_reply(wait())
        except Exception as exc:
            progress(f"writers' room: {agent} failed ({exc}); keeping his original lines")
            continue
        for slot in slots:
            new = reply.get(slot["id"], "").strip().strip('"“”')
            if not new or new == slot["text"]:
                continue
            problem = check_line(new, slot["text"], slot["kind"], record)
            report.append(f"{agent} {slot['id']}: {'REJECTED (' + problem + ')' if problem else 'ok'}\n"
                          f"  was: {slot['text']}\n  now: {new}")
            if problem:
                continue
            scene = plan["scenes"][slot["scene"]]
            if slot["kind"] == "aside":
                scene["aside"]["original_text"] = scene["aside"]["text"]
                scene["aside"]["text"] = new
            else:
                scene["original_text"] = scene["text"]
                scene["text"] = new
                for other in plan["scenes"]:  # the cold open replays this line
                    if other.get("cold_open") and other.get("event") == scene.get("event"):
                        other["original_text"], other["text"] = other["text"], new
            scene["rewritten_by"] = agent
            changed += 1
    if log_dir is not None and report:
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "writers-room.log").write_text("\n".join(report) + "\n", encoding="utf-8")
    rejected = sum(1 for r in report if "REJECTED" in r)
    progress(f"writers' room: {changed} line(s) rewritten, {rejected} rejected by the fact check")
    if changed:
        plan["disclaimer"] = DISCLAIMER_DRAMATISED
    return plan
