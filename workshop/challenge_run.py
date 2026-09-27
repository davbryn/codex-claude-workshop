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

    def __init__(self, orchestrator, capture, spins: list[challenge.Spin], progress=print):
        self.o = orchestrator
        self.capture = capture
        self.spins = spins
        self.progress = progress
        self.rules = challenge.rules_text(spins)
        self.last_report = "RULES CHECK: nothing written yet."
        base = orchestrator.prompt_theatre

        def theatre(agent: str, text: str) -> str:
            parts = [base(agent, text) if base else "", self.rules, self.last_report]
            return "\n\n".join(p for p in parts if p)

        orchestrator.prompt_theatre = theatre
        orchestrator.turn_finished.connect(self._on_turn_finished)

    def _on_turn_finished(self, agent: str, _code: int) -> None:
        try:
            violations = challenge.check(self.o.project_dir, self.spins)
        except Exception as exc:  # the referee must never break the workshop
            self.progress(f"rules check failed: {exc}")
            return
        self.last_report = challenge.report(violations, self.spins)
        self.capture.log.add("rules_check", agent=agent, count=len(violations),
                             violations=[v.as_dict() for v in violations[:30]])
        self.progress(f"rules check after {agent}: {len(violations)} violation(s)")


def log_spins(capture, spins: list[challenge.Spin], reactions: dict) -> None:
    for i, spin in enumerate(spins):
        capture.log.add("spin", index=i, **spin.as_event())
        for agent in AGENTS:
            line = reactions.get(agent, {}).get(i)
            if line:
                capture.log.add("spin_reaction", index=i, agent=agent, line=line)
