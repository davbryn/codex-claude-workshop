"""Deterministic demo scenario used by ``--demo`` and ``--fake-agents``.

Each DemoTurn lists fake CLI output lines (Codex uses the real `codex exec`
format, Claude uses our stream-json condensation) and the public entry the
fake agent appends. It walks through: normal work, test success,
disagreement, a failing test, an admitted mistake, a caught bug, a human
decision, character development, a completion proposal, independent review
and PROJECT COMPLETE.
"""

from __future__ import annotations

from dataclasses import dataclass

DEMO_PROMPT = "Build a tiny command-line todo app with add, list, done and delete. Keep it small and well tested."


@dataclass(frozen=True)
class DemoTurn:
    agent: str
    steps: tuple[str, ...]  # output lines; "" is a pause
    thoughts: str
    actions: str
    result: str
    next: str
    ending: str  # final control line(s)


def _codex_exec(command: str, *output: str, ok: bool = True) -> tuple[str, ...]:
    return ("exec", f'"powershell.exe" -Command "{command}"',
            " succeeded in 640ms:" if ok else " exited 1 in 700ms:", *output)


DEMO_TURNS: tuple[DemoTurn, ...] = (
    DemoTurn(
        "Codex",
        ("codex", "I'll read the brief and get something working.",
         *_codex_exec("Get-Content AGENT_README.md; Get-Content conversation.md"), "",
         "[tool] Write: todo.py", "[tool] Write: test_todo.py", "",
         *_codex_exec("python -m pytest -q", "....", "4 passed in 0.03s")),
        "Claude hasn't touched anything yet, so the codebase is currently flawless. "
        "I wrote a 38-line todo app that keeps todos in a plain list. You're welcome.",
        "Created `todo.py` with add, list, done and delete, plus `test_todo.py`.",
        "All 4 tests pass.",
        "Claude, review the storage layer. Please resist the urge to add a factory.",
        "@Claude",
    ),
    DemoTurn(
        "Claude",
        ("[tool] Read: todo.py", "[tool] Read: test_todo.py", "",
         "[tool] Write: storage.py", "[tool] Edit: todo.py", "[tool] Edit: test_todo.py", "",
         "[tool] Bash: python -m pytest -q", "[tool result] 6 passed in 0.04s"),
        "I disagree! A global list with no persistence is a crime against architecture. "
        "Your todos vanish the moment the program exits. That's not minimalism, that's amnesia.",
        "Introduced a small `TodoStore` class that saves to `todos.json`, and added two persistence tests.",
        "6 tests pass. Todos now survive a restart, which I consider a basic human right.",
        "Codex, please review `TodoStore`. It is one class. It is not a factory. I checked.",
        "@Codex",
    ),
    DemoTurn(
        "Codex",
        ("codex", "Inlining TodoStore. Four lines should do it.",
         "[tool] Edit: storage.py", "",
         *_codex_exec("python -m pytest -q", "..F...",
                      "FAILED test_todo.py::test_todos_survive_restart - AssertionError",
                      "1 failed, 5 passed in 0.05s", ok=False), "",
         "codex", "Hm.", "[tool] Edit: storage.py", "",
         *_codex_exec("python -m pytest -q", "......", "6 passed in 0.04s")),
        "I tried to inline Claude's TodoStore into four lines and the persistence test failed immediately. "
        "My mistake. Claude was right that the save path matters.",
        "Restored the store, then trimmed it from 41 lines to 23, because some standards must be maintained.",
        "All 6 tests pass. I have been mildly humbled.",
        "Claude, check `delete` with an out-of-range index. I have a feeling.",
        "@Claude",
    ),
    DemoTurn(
        "Claude",
        ("[tool] Read: todo.py", "",
         "[tool] Bash: python todo.py delete 99", "[tool error] Traceback (most recent call last): IndexError: list index out of range", "",
         "[tool] Edit: todo.py", "[tool] Edit: test_todo.py", "",
         "[tool] Bash: python -m pytest -q", "[tool result] 7 passed in 0.04s"),
        "Your hunch was spot on: Codex's delete command crashed on index 99 with a raw IndexError. "
        "I fixed it with a friendly message and added a regression test.",
        "`delete` and `done` now validate the index. Added `test_delete_out_of_range`.",
        "7 tests pass. Nobody has to see a stack trace today.",
        "Codex, should `list` show completed items? That smells like a product decision.",
        "@Codex",
    ),
    DemoTurn(
        "Codex",
        ("[tool] Read: todo.py", "",
         *_codex_exec("python -m pytest -q", ".......", "7 passed in 0.04s")),
        "Claude's fix is correct and only slightly verbose. "
        "I could guess the list behaviour, but guessing product decisions is how todo apps end up with blockchain integration.",
        "Reviewed the index validation and re-ran the suite.",
        "7 tests pass.",
        "HUMAN DECISION NEEDED: Should `todo list` hide completed items by default?",
        "@Claude",
    ),
    DemoTurn(
        "Claude",
        ("[tool] Read: conversation.md", "",
         "[tool] Edit: todo.py", "[tool] Edit: test_todo.py", "[tool] Edit: storage.py", "",
         "[tool] Bash: python -m pytest -q", "[tool result] 9 passed in 0.05s"),
        "The human has spoken, and the human has taste! Completed items are now hidden unless you pass `--all`.",
        "Added the `--all` flag with two tests. I also fixed my own earlier bug: TodoStore rewrote the file "
        "even when nothing had changed. Character development!",
        "All 9 tests pass.",
        "Codex, please give it a final review.",
        "@Codex",
    ),
    DemoTurn(
        "Codex",
        ("[tool] Read: todo.py", "[tool] Read: storage.py", "[tool] Read: test_todo.py", "",
         *_codex_exec("python -m pytest -q", ".........", "9 passed in 0.05s")),
        "I reviewed everything. It is small, correct and tested. "
        "Mostly my doing, but I'll allow Claude partial credit.",
        "Read every file and re-ran the full suite.",
        "All 9 tests pass; no open issues.",
        "Claude, please independently review and test before agreeing.",
        "PROPOSE PROJECT COMPLETE\n\n@Claude",
    ),
    DemoTurn(
        "Claude",
        ("[tool] Read: todo.py", "[tool] Read: storage.py", "",
         "[tool] Bash: python -m pytest -q", "[tool result] 9 passed in 0.05s",
         "[tool] Bash: python todo.py list --all"),
        "I re-ran every test and tried the CLI myself. Partial credit graciously accepted. "
        "This project is officially done and dusted. Well, done and listed.",
        "Independent review of all files, full test run, and a manual CLI check.",
        "All 9 tests pass and the CLI behaves exactly as the human asked.",
        "Nothing left. Take a bow, Codex.",
        "PROJECT COMPLETE",
    ),
)


def demo_entry(turn: DemoTurn, number: int) -> str:
    return (
        f"\n## {turn.agent} — Turn {number}\n\n"
        f"**Thoughts**\n\n{turn.thoughts}\n\n"
        f"**Actions**\n\n{turn.actions}\n\n"
        f"**Result**\n\n{turn.result}\n\n"
        f"**Next**\n\n{turn.next}\n\n"
        f"{turn.ending}\n\n---\n"
    )
