"""Running a Wheel of Destiny challenge: log the spins, get the cast's reactions, enforce the rules each turn."""

from __future__ import annotations

import tempfile
from pathlib import Path

from . import challenge
from .conversation import AGENTS


def spin_reactions(spins: list[challenge.Spin], adapters: dict, progress=print, timeout_s: float = 180.0) -> dict:
    """{agent: {spin index (0-based): line}} from each agent's own CLI (side calls, no tools)."""
    from .episode.writers import _run, parse_reply

    tmp = Path(tempfile.mkdtemp(prefix="workshop-wheel-"))
    jobs, out = {}, {}
    for agent in AGENTS:
        if agent in adapters:
            try:
                jobs[agent] = _run(adapters[agent], agent, challenge.reaction_prompt(agent, spins), tmp, timeout_s)
            except Exception as exc:
                progress(f"wheel: {agent} can't react ({exc})")
    for agent, wait in jobs.items():
        try:
            reply = parse_reply(wait())
        except Exception as exc:
            progress(f"wheel: {agent}'s reactions failed ({exc})")
            continue
        out[agent] = {}
        for key, line in reply.items():
            try:
                index = int(str(key).strip()) - 1
            except ValueError:
                continue
            if 0 <= index < len(spins) and line.strip():
                out[agent][index] = line.strip()[:140]
    return out


class ChallengeReferee:
    """Adds the rules and the latest rules check to every turn's prompt, and logs each check."""

    def __init__(self, orchestrator, capture, spins: list[challenge.Spin], progress=print, twist_after: int = 2,
                 react: bool = True, rng=None):
        self.o = orchestrator
        self.capture = capture
        self.spins = list(spins)
        self.progress = progress
        self.rules = challenge.rules_text(self.spins)
        self.last_report = "RULES CHECK: nothing written yet."
        self.turns = 0
        self.twist_after = twist_after  # spin the Twist Wheel after this many turns (0 = never)
        self.react = react
        self.rng = rng
        self.twist_note = ""
        base = orchestrator.prompt_theatre

        def theatre(agent: str, text: str) -> str:
            parts = [base(agent, text) if base else "", self.twist_note, self.rules, self.last_report]
            return "\n\n".join(p for p in parts if p)

        orchestrator.prompt_theatre = theatre
        orchestrator.turn_finished.connect(self._on_turn_finished)

    def _on_turn_finished(self, agent: str, _code: int) -> None:
        self.turns += 1
        self._check(agent)
        if self.twist_after and self.turns == self.twist_after:
            try:
                self._twist(agent)
            except Exception as exc:  # a failed twist must never break the workshop
                self.progress(f"twist failed: {exc}")

    def _check(self, agent: str, after_twist: bool = False) -> None:
        try:
            violations = challenge.check(self.o.project_dir, self.spins)
        except Exception as exc:  # the referee must never break the workshop
            self.progress(f"rules check failed: {exc}")
            return
        self.last_report = challenge.report(violations, self.spins)
        self.capture.log.add("rules_check", agent=agent, count=len(violations), after_twist=after_twist,
                             violations=[v.as_dict() for v in violations[:30]])
        self.progress(f"rules check after {agent}{' (new rules)' if after_twist else ''}: "
                      f"{len(violations)} violation(s)")

    def _twist(self, agent: str) -> None:
        """Halfway through, the Twist Wheel: a second limitation, a request from Jared, or a skill swap."""
        twist = challenge.spin_twist(self.spins, self.rng)
        self.progress(f"TWIST WHEEL: {twist.slice.label}")
        index = len(self.spins)
        self.spins.append(twist)
        reactions = {}
        if self.react:
            reactions = spin_reactions([twist], self.o.adapters, progress=self.progress)
        self.capture.log.add("spin", index=index, **twist.as_event())
        for who in AGENTS:
            line = reactions.get(who, {}).get(0)
            if line:
                self.capture.log.add("spin_reaction", index=index, agent=who, line=line)
        self.rules = challenge.rules_text(self.spins)
        self.twist_note = (f"*** THE TWIST WHEEL HAS BEEN SPUN, halfway through the build. It landed on: "
                           f"{twist.slice.label}. {twist.slice.rule} The rules below are updated. Adapt the "
                           "existing code; say how in your entry. ***")
        try:
            (Path(self.o.project_dir) / "CHALLENGE.md").write_text(self.rules + "\n", encoding="utf-8")
        except OSError:
            pass
        self._check(agent, after_twist=True)


def log_spins(capture, spins: list[challenge.Spin], reactions: dict) -> None:
    for i, spin in enumerate(spins):
        capture.log.add("spin", index=i, **spin.as_event())
        for agent in AGENTS:
            line = reactions.get(agent, {}).get(i)
            if line:
                capture.log.add("spin_reaction", index=i, agent=agent, line=line)


def react_later(project_dir: Path, adapters: dict, progress=print) -> int:
    """Ask the cast to react to spins that were logged without reactions. Returns how many lines were added."""
    from .episode.capture import EPISODE_DIR, EventLog, read_events

    path = Path(project_dir) / EPISODE_DIR / "events.jsonl"
    events = read_events(path)
    logged = [e for e in events if e["kind"] == "spin"]
    have = {(e["index"], e["agent"]) for e in events if e["kind"] == "spin_reaction"}
    if not logged or len(have) >= 2 * len(logged):
        return 0
    spins = [challenge.Spin(e["wheel"], e.get("who"), [challenge.Slice(**s) for s in e["slices"]], e["result"],
                            e.get("near_misses", [])) for e in logged]
    reactions = spin_reactions(spins, adapters, progress=progress)
    log = EventLog(path)
    added = 0
    for agent, lines in reactions.items():
        for i, line in sorted(lines.items()):
            if (logged[i]["index"], agent) not in have:
                log.add("spin_reaction", index=logged[i]["index"], agent=agent, line=line)
                added += 1
    return added
