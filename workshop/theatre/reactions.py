"""Deterministic, cosmetic reaction rules.

Reactions are theatre: they are picked from *public* conversation text and
observable CLI output only, and they never influence orchestration. False
positives are fine; claims about internal mental state are not made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePath

from ..conversation import (
    COMPLETE_MARKER,
    HUMAN_DECISION_MARKER,
    PROPOSE_COMPLETE_MARKER,
    ConversationTurn,
    has_marker,
)
from .text import sections, strip_code


def _rx(*phrases: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(phrases) + r")\b", re.I)


DISAGREE_RX = _rx(
    r"i (?:strongly |respectfully |completely )?disagree",
    r"i don'?t agree",
    r"i do not agree",
    r"(?:codex|claude) (?:is|was) wrong",
    r"unnecessary(?: abstraction)?",
    r"over-?engineer(?:ed|ing)",
    r"over engineered",
    r"this introduces a bug",
    r"i wouldn'?t",
    r"i don'?t think",
    r"not convinced",
    r"i object",
    r"strongly prefer",
    r"crime against",
)
SELF_ADMIT_RX = _rx(
    r"i was wrong",
    r"my (?:own )?(?:mistake|bad|error|fault|bug)",
    r"i missed",
    r"i overlooked",
    r"i got (?:that|it) wrong",
    r"i stand corrected",
    r"mea culpa",
    r"i broke",
)
CONCEDE_RX = re.compile(
    r"\b(?:(?:codex|claude) (?:was|is) right|you'?re right|you were right|good catch|fair point|"
    r"nice catch|i concede|(?:codex|claude)'?s (?:version|approach|solution) is (?:better|cleaner))\b",
    re.I,
)
FIX_RX = _rx(r"fixed", r"fixes", r"resolved", r"repaired", r"corrected")
BUG_RX = _rx(r"bug", r"crash(?:ed|es)?", r"regression", r"mistake", r"broken", r"off-by-one", r"typo")
SUCCESS_RX = _rx(
    r"all (?:\d+ )?tests? pass(?:ed|es|ing)?",
    r"tests? (?:all )?pass(?:ed|es|ing)?",
    r"\d+ passed",
    r"(?:now )?works",
    r"working",
    r"fixed",
    r"benchmark improved",
    r"successful(?:ly)?",
    r"green",
)
STRONG_SUCCESS_RX = re.compile(r"\ball (\d+) tests? pass|\b(\d+)/\1 (?:tests? )?pass|\b(\d+) passed, 0 failed", re.I)
TEST_COUNT_RX = re.compile(r"\b(\d+) (?:tests? )?(?:passed|pass|passing)\b|\ball (\d+) tests?\b", re.I)
FAIL_RX = re.compile(r"\b(?:tests? (?:still )?fail(?:ed|s|ing)?|\d+ failed|failing tests?|FAILED)\b", re.I)
CONFUSED_RX = _rx(r"confus(?:ed|ing)", r"unclear", r"not sure", r"puzzl(?:ed|ing)", r"mystery", r"no idea", r"baffl(?:ed|ing)")
REVIEW_RX = _rx(r"review(?:ed|ing)?", r"inspect(?:ed|ing)?", r"verif(?:y|ied|ying)", r"double-check(?:ed)?", r"audit(?:ed)?")


@dataclass
class EntryReaction:
    speaker: str
    disagreement: bool = False
    self_admission: bool = False
    concedes_other: bool = False
    fixed_other_bug: bool = False
    fixed_own_mistake: bool = False
    success: bool = False
    strong_success: bool = False
    tests_failed: bool = False
    confused: bool = False
    reviewing: bool = False
    mentions_other: bool = False
    proposes_completion: bool = False
    declares_complete: bool = False
    human_needed: bool = False
    test_count: int | None = None

    @property
    def admits_mistake(self) -> bool:
        return self.self_admission or self.concedes_other

    def primary_state(self) -> str:
        """The speaker's theatrical reaction after speaking."""
        if self.declares_complete:
            return "celebrating"
        if self.human_needed:
            return "waiting"
        if self.fixed_own_mistake:
            return "pleased"
        if self.admits_mistake:
            return "embarrassed"
        if self.disagreement:
            return "disagreeing"
        if self.tests_failed and not self.success:
            return "confused"
        if self.strong_success or self.proposes_completion:
            return "celebrating"
        if self.success:
            return "pleased"
        if self.confused:
            return "confused"
        return "idle"

    def listener_state(self, rivalry: bool = True) -> str | None:
        """How the *other* agent reacts while this entry is performed."""
        if self.declares_complete:
            return "celebrating"
        if self.concedes_other:
            return "smug" if rivalry else "pleased"
        if self.fixed_other_bug:
            return "embarrassed"
        if self.disagreement:
            return "annoyed" if rivalry else "confused"
        return None


def classify_entry(turn: ConversationTurn, other: str | None = None) -> EntryReaction:
    content = turn.content
    prose = strip_code(content)
    other = other or ("Claude" if turn.speaker == "Codex" else "Codex")
    r = EntryReaction(speaker=turn.speaker)
    r.proposes_completion = has_marker(content, PROPOSE_COMPLETE_MARKER)
    r.declares_complete = has_marker(content, COMPLETE_MARKER)
    r.human_needed = HUMAN_DECISION_MARKER.lower() in content.lower()
    r.disagreement = bool(DISAGREE_RX.search(prose))
    r.self_admission = bool(SELF_ADMIT_RX.search(prose))
    r.concedes_other = bool(CONCEDE_RX.search(prose)) and turn.speaker != "Human"
    r.success = bool(SUCCESS_RX.search(prose))
    r.tests_failed = bool(FAIL_RX.search(prose)) and not re.search(r"\b0 failed\b", prose)
    r.confused = bool(CONFUSED_RX.search(prose))
    r.reviewing = bool(REVIEW_RX.search(prose))
    r.mentions_other = bool(re.search(rf"\b{other}\b", prose, re.I))
    strong = STRONG_SUCCESS_RX.search(prose)
    r.strong_success = bool(strong)
    counts = [int(g) for m in TEST_COUNT_RX.finditer(prose) for g in m.groups() if g]
    r.test_count = max(counts) if counts else None

    fixed = bool(FIX_RX.search(prose))
    own_bug = re.search(r"\bmy (?:own )?(?:earlier |previous |original )?(?:bug|mistake|error|regression)", prose, re.I)
    others_bug = re.search(
        rf"\b{other}'?s (?:\w+ ){{0,3}}(?:bug|mistake|crash|regression|typo|error)|"
        rf"\bbug (?:in|from) {other}'?s\b|\b{other}'?s (?:\w+ ){{0,3}}(?:crashes|crashed|breaks|broke)\b",
        prose,
        re.I,
    )
    r.fixed_own_mistake = fixed and bool(own_bug)
    r.fixed_other_bug = fixed and bool(others_bug) and not r.fixed_own_mistake
    return r


# --- CLI output ---------------------------------------------------------------

_TOOL_LINE = re.compile(r"^\[tool\] (\w+): ?(.*)$")
_READ_TOOLS = {"Read", "Grep", "Glob", "LS", "NotebookRead"}
_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_SHELL_TOOLS = {"Bash", "PowerShell", "Shell"}
TEST_CMD_RX = re.compile(
    r"\b(?:pytest|py\.test|unittest|npm (?:run )?test|yarn test|pnpm test|jest|vitest|mocha|cargo test|go test|"
    r"dotnet test|mvn test|gradle test|rspec|phpunit|ctest|node --test|deno test|tox|nox)\b|test[-_\w]*\.(?:ps1|sh|js|py)\b",
    re.I,
)
READ_CMD_RX = re.compile(r"^(?:cat|type|Get-Content|gc|less|more|head|tail|rg|grep|Select-String|ls|dir|Get-ChildItem|find|tree)\b", re.I)
_PS_WRAPPED = re.compile(r"-Command\s+[\"'@]*\s*(.*)$", re.I)

_PYTEST_SUMMARY = re.compile(r"(?:^|[=\s])(?:(\d+) failed,? )?(\d+) passed(?:,? (\d+) failed)?[^\n]*?\bin [\d.]+s", re.I)
_UNITTEST_RAN = re.compile(r"^Ran (\d+) tests? in", re.I)
_UNITTEST_FAILED = re.compile(r"^FAILED \((?:failures|errors)=(\d+)", re.I)
_JEST = re.compile(r"^Tests:\s+(?:(\d+) failed, )?(?:\d+ skipped, )?(\d+) passed", re.I)
_CARGO = re.compile(r"test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed", re.I)
_GENERIC_PASS = re.compile(r"\b(?:ALL (?:TESTS )?PASSED|PASS: all (\d+))\b", re.I)
_GENERIC_FAIL = re.compile(r"^(?:\[tool result\] )?(?:FAIL(?:ED)?\b|\d+ failed\b)", re.I)
_ERROR_LINE = re.compile(r"^(?:Traceback \(most recent call last\)|\[tool error\])")


@dataclass
class OutputCue:
    activity: str | None = None  # short public status, e.g. "Running tests…"
    kind: str | None = None  # read | edit | test | command | plan
    file: str | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    tests_ok: bool = False  # a clear, successful test summary
    error: bool = False

    def __bool__(self) -> bool:
        return any(
            v not in (None, False) for v in (self.activity, self.tests_passed, self.tests_failed, self.tests_ok, self.error)
        )


@dataclass
class ActivityTracker:
    """Turns raw CLI output lines into public activity + test cues for one agent."""

    files_edited: set[str] = field(default_factory=set)
    _expect_codex_command: bool = False
    _unittest_ran: int | None = None

    def reset(self) -> None:
        self.files_edited.clear()
        self._expect_codex_command = False
        self._unittest_ran = None

    def feed(self, line: str) -> OutputCue:
        raw = line.rstrip()
        stripped = raw.strip()
        cue = OutputCue()

        # Codex prints "exec" on its own line, followed by the command.
        if stripped == "exec":
            self._expect_codex_command = True
            return cue
        if self._expect_codex_command and stripped:
            self._expect_codex_command = False
            return self._command(stripped)

        tool = _TOOL_LINE.match(stripped)
        if tool:
            name, arg = tool.groups()
            if name in _EDIT_TOOLS:
                file = _basename(arg)
                self.files_edited.add(file)
                return OutputCue(activity=f"Editing {file}…", kind="edit", file=file)
            if name in _READ_TOOLS:
                target = _basename(arg) if arg and name == "Read" else None
                return OutputCue(activity=f"Reading {target}…" if target else "Searching the project…", kind="read")
            if name in _SHELL_TOOLS:
                return self._command(arg)
            if name in ("TodoWrite", "TaskCreate", "TaskUpdate"):
                return OutputCue(activity="Updating the plan…", kind="plan")
            if name in ("WebFetch", "WebSearch"):
                return OutputCue(activity="Looking something up…", kind="read")
            return OutputCue(activity=f"Using {name}…", kind="command")

        return self._results(stripped) or cue

    def _command(self, command: str) -> OutputCue:
        wrapped = _PS_WRAPPED.search(command)
        inner = (wrapped.group(1) if wrapped else command).strip().strip("\"'@").strip()
        first = re.split(r"[;&|\n]", inner, maxsplit=1)[0].strip() or inner
        if TEST_CMD_RX.search(inner):
            return OutputCue(activity="Running tests…", kind="test")
        if READ_CMD_RX.match(first):
            return OutputCue(activity="Reading files…", kind="read")
        if re.match(r"^git\b", first):
            return OutputCue(activity="Checking git…", kind="command")
        short = first if len(first) <= 38 else first[:37] + "…"
        return OutputCue(activity=f"Running {short}", kind="command")

    def _results(self, line: str) -> OutputCue | None:
        text = re.sub(r"^\[tool result\]\s*", "", line)
        if m := _CARGO.search(text):
            passed, failed = int(m.group(1)), int(m.group(2))
            return OutputCue(tests_passed=passed, tests_failed=failed, tests_ok=failed == 0)
        if m := _PYTEST_SUMMARY.search(text):
            failed = int(m.group(1) or m.group(3) or 0)
            passed = int(m.group(2))
            return OutputCue(tests_passed=passed, tests_failed=failed, tests_ok=failed == 0)
        if m := _JEST.search(text):
            failed = int(m.group(1) or 0)
            return OutputCue(tests_passed=int(m.group(2)), tests_failed=failed, tests_ok=failed == 0)
        if m := _UNITTEST_RAN.search(text):
            self._unittest_ran = int(m.group(1))
            return None
        if text == "OK" or text.startswith("OK ("):
            if self._unittest_ran is not None:
                passed, self._unittest_ran = self._unittest_ran, None
                return OutputCue(tests_passed=passed, tests_failed=0, tests_ok=True)
            return None
        if m := _UNITTEST_FAILED.search(text):
            self._unittest_ran = None
            return OutputCue(tests_failed=int(m.group(1)))
        if m := _GENERIC_PASS.search(text):
            return OutputCue(tests_passed=int(m.group(1)) if m.group(1) else None, tests_ok=True)
        if _GENERIC_FAIL.search(text):
            return OutputCue(tests_failed=1)
        if _ERROR_LINE.search(line):
            return OutputCue(error=True)
        return None


def _basename(path: str) -> str:
    path = path.strip().strip("\"'")
    return PurePath(path.replace("\\", "/")).name or path


# --- small helpers for the stage ----------------------------------------------

def sections_of(turn: ConversationTurn) -> dict[str, str]:
    return sections(turn.content)


def asks_for_review(turn: ConversationTurn | None) -> bool:
    """True when an entry hands over asking the next agent to review/verify."""
    if turn is None:
        return False
    if has_marker(turn.content, PROPOSE_COMPLETE_MARKER):
        return True
    nxt = sections(turn.content).get("next", "")
    return bool(REVIEW_RX.search(nxt))
