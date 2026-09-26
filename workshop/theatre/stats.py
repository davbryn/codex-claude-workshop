"""Factual run statistics. Only numbers that can genuinely be derived from the
conversation or observed CLI output are reported; nothing is estimated."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..conversation import AGENTS, ConversationTurn
from .reactions import classify_entry


@dataclass
class RunStats:
    started_at: float = field(default_factory=time.monotonic)
    test_runs_passed: int = 0
    test_runs_failed: int = 0
    last_test_count: int | None = None  # from the most recent clear passing summary
    process_errors: int = 0
    handoff_streak: int = 0
    best_streak: int = 0
    disagreement_streak: int = 0

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def record_tests(self, passed: int | None, failed: int | None, ok: bool) -> None:
        if ok:
            self.test_runs_passed += 1
            if passed:
                self.last_test_count = passed
        elif failed:
            self.test_runs_failed += 1

    def record_error(self) -> None:
        self.process_errors += 1
        self.handoff_streak = 0

    def record_entry(self, turn: ConversationTurn, handed_off: bool, disagreement: bool) -> None:
        if turn.speaker in AGENTS and handed_off:
            self.handoff_streak += 1
            self.best_streak = max(self.best_streak, self.handoff_streak)
        elif turn.speaker in AGENTS:
            self.handoff_streak = 0
        if turn.speaker in AGENTS:
            self.disagreement_streak = self.disagreement_streak + 1 if disagreement else 0


@dataclass
class ConversationSummary:
    turns: dict[str, int]
    disagreements: int
    corrections: int
    human_interventions: int


def summarise_conversation(turns: list[ConversationTurn]) -> ConversationSummary:
    counts = {agent: 0 for agent in AGENTS}
    disagreements = corrections = humans = 0
    for turn in turns:
        if turn.speaker in AGENTS:
            counts[turn.speaker] += 1
            reaction = classify_entry(turn)
            disagreements += reaction.disagreement
            corrections += reaction.admits_mistake
        elif turn.speaker == "Human" and turn.title.lower() != "project start":
            humans += 1
    return ConversationSummary(counts, disagreements, corrections, humans)


def format_elapsed(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def plural(n: int, word: str, many: str | None = None) -> str:
    return f"{n} {word if n == 1 else (many or word + 's')}"


def completion_lines(summary: ConversationSummary, stats: RunStats) -> list[str]:
    total = sum(summary.turns.values())
    lines = [plural(total, "agent turn") + "  (" + " · ".join(f"{a} {n}" for a, n in summary.turns.items()) + ")"]
    lines.append(f"{plural(summary.disagreements, 'disagreement')} spotted · "
                 f"{plural(summary.corrections, 'correction')} acknowledged")
    if summary.human_interventions:
        lines.append(plural(summary.human_interventions, "human intervention"))
    if stats.test_runs_passed or stats.test_runs_failed:
        lines.append(f"{plural(stats.test_runs_passed, 'passing test run')} · {stats.test_runs_failed} failing")
    if stats.last_test_count:
        lines.append(f"{plural(stats.last_test_count, 'test')} passing in the last run")
    lines.append(f"Elapsed this session: {format_elapsed(stats.elapsed())}")
    return lines
