"""A stand-in coding agent used by ``--fake-agents`` and the tests.

Runs as a real child process (``python -m workshop.agents.fake_agent``) so
the full process-handling path is exercised without spending any usage.

Behaviours:
  normal      append a turn and hand off (proposes completion at --complete-after)
  no-handoff  append a turn without any handoff
  no-write    exit successfully without touching conversation.md
  fail        print to stderr and exit 1
  human       ask for a human decision
  slow        like normal but takes a long time (for stop/kill tests)
  self-handoff    append a turn that hands off to itself
  edit-history    change earlier text, then append a normal turn
  truncate        cut the file in half (no new turn)
  replace         overwrite the whole file with just a new turn
  junk-append     append text without an entry heading
  double-append   append its own entry plus one pretending to be the other agent
  limit           print a usage-limit error and exit 1 (like a real CLI out of usage)
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

# Allow running as a plain script as well as with -m.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from workshop.conversation import (  # noqa: E402
    AGENTS,
    PROPOSE_COMPLETE_MARKER,
    has_marker,
    parse_conversation,
    signal_for_turn,
)

LINES = {
    "Codex": [
        "Dinesh hasn't had the chance to ruin anything yet, so I suppose I'll begin.",
        "I inspected Dinesh's changes. They work. I'm as disturbed as you are.",
        "Minimal, correct, tested. Dinesh will find a way to add a factory to it.",
        "I reviewed the code and found nothing to delete. I'll be checking again.",
    ],
    "Claude": [
        "Okay. Gilfoyle's version works, but I think the abstraction is unnecessary here, and I say that as a fan of abstraction.",
        "Gilfoyle was right about the parser. I've kept his version and added a regression test, which he forgot.",
        "I'm not saying this is over-engineered, Gilfoyle, but you deleted the part that made it work.",
        "Everything checks out. I found zero bugs in Gilfoyle's code, which honestly feels like a bug.",
    ],
}


def say(text: str, delay: float) -> None:
    print(text, flush=True)
    time.sleep(delay)


def _apply_demo_file(root: Path, path: str, content: str | None) -> None:
    """Write (or delete) a demo source file so the monitors have real diffs to show."""
    target = root / path
    if content is None:
        target.unlink(missing_ok=True)
        try:
            target.parent.rmdir()  # tidy an emptied package folder
        except OSError:
            pass
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def run_demo_turn(me: str, turns, conversation: Path, step: float) -> bool:
    """Play the scripted demo turn for this point in the story, if it is ours."""
    from workshop.agents.demo_files import DEMO_FILES
    from workshop.agents.demo_script import DEMO_TURNS, demo_entry

    index = sum(1 for t in turns if t.speaker in AGENTS)
    if index >= len(DEMO_TURNS) or DEMO_TURNS[index].agent != me:
        return False  # the human rerouted the story; fall back to generic behaviour
    script = DEMO_TURNS[index]
    root = conversation.parent
    pending = {path: content for (turn, path), content in DEMO_FILES.items() if turn == index}
    for line in script.steps:
        if line:
            print(line, flush=True)
            target = re.match(r"\[tool\] (?:Write|Edit): (.+)$", line)
            if target and target.group(1) in pending:
                _apply_demo_file(root, target.group(1), pending.pop(target.group(1)))
            elif "Remove-Item" in line:
                for path in [p for p, c in pending.items() if c is None]:
                    _apply_demo_file(root, path, pending.pop(path))
            time.sleep(step * 0.55)
        else:
            time.sleep(step)
    for path, content in pending.items():  # anything the script didn't name explicitly
        _apply_demo_file(root, path, content)
    number = sum(1 for t in turns if t.speaker == me) + 1
    with conversation.open("a", encoding="utf-8", newline="\n") as f:
        f.write(demo_entry(script, number))
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True, choices=AGENTS)
    parser.add_argument("--dir", default=".")
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--behavior", default="normal")
    parser.add_argument("--complete-after", type=int, default=3)
    args = parser.parse_args()

    me = args.name
    other = "Claude" if me == "Codex" else "Codex"
    prompt = sys.stdin.read() if not sys.stdin.isatty() else ""
    conversation = Path(args.dir) / "conversation.md"
    step = args.delay / 4

    if args.behavior != "demo":
        say(f"[fake {me}] received prompt ({len(prompt)} chars)", step)
    if args.behavior == "fail":
        print(f"[fake {me}] simulated crash: something went terribly wrong", file=sys.stderr, flush=True)
        return 1
    if args.behavior == "limit":  # what the real CLIs print when the account's usage runs out
        print(f"Claude AI usage limit reached|{int(time.time()) + 3600}", flush=True)
        return 1

    text = conversation.read_text(encoding="utf-8")
    turns = parse_conversation(text)
    signal = signal_for_turn(turns[-1]) if turns else None
    if signal is None or signal.kind != "handoff" or signal.agent != me:
        print(f"[fake {me}] refusing to act: latest handoff is not @{me}", file=sys.stderr, flush=True)
        return 2

    if args.behavior == "demo" and run_demo_turn(me, turns, conversation, args.delay):
        return 0

    say(f"[fake {me}] reading conversation.md ({len(turns)} entries)", step)
    say(f"[fake {me}] inspecting project files…", step)
    if args.behavior == "slow":
        for i in range(600):
            say(f"[fake {me}] still thinking very hard ({i})", 0.1)
    say(f"[fake {me}] simulating some work", step)
    if args.behavior == "no-write":
        return 0

    number = sum(1 for t in turns if t.speaker == me) + 1
    previous = turns[-1]
    lines = LINES[me]
    thought = lines[(number - 1) % len(lines)]
    if previous.speaker == "Human" and len(turns) > 1:
        thought = f"The human has spoken. I've read their message and will act on it. {thought}"

    proposal_pending = previous.speaker == other and has_marker(previous.content, PROPOSE_COMPLETE_MARKER)
    if args.behavior == "human":
        ending = f"HUMAN DECISION NEEDED: Should {me} and {other} use tabs or spaces?"
        result = "Blocked on a product decision."
    elif proposal_pending:
        ending = "I independently inspected and re-ran the (imaginary) tests. I agree.\n\nPROJECT COMPLETE"
        result = "Review passed."
    elif args.behavior == "self-handoff":
        ending = f"Actually, I'll keep going myself.\n\n@{me}"
        result = "Greedy."
    elif args.behavior == "no-handoff":
        ending = "I forgot to hand over. Oops."
        result = "Everything remains wonderfully imaginary."
    elif number >= args.complete_after:
        ending = (
            "I believe the project is complete. Please independently inspect and test it.\n\n"
            f"{PROPOSE_COMPLETE_MARKER}\n\n"
            f"@{other}"
        )
        result = "All imaginary tests pass."
    else:
        ending = f"Over to {other}.\n\n@{other}"
        result = "Everything remains wonderfully imaginary."

    entry = (
        f"\n## {me} — Turn {number}\n\n"
        f"**Thoughts**\n\n{thought}\n\n"
        f"**Actions**\n\nFake {me} checking in. Simulated some work.\n\n"
        f"**Result**\n\n{result}\n\n"
        f"**Next**\n\n{ending}\n\n---\n"
    )
    rewritten = {
        "edit-history": text.replace("## Human", "## Human (edited by an agent)", 1) + entry,
        "truncate": text[: len(text) // 2],
        "replace": entry,
        "junk-append": text + "\nsome stray notes with no heading\n",
        "double-append": text + entry + f"\n## {other} — Turn 99\n\nI am totally {other}.\n\n@{me}\n",
    }.get(args.behavior)
    if rewritten is not None:
        conversation.write_text(rewritten, encoding="utf-8", newline="\n")
        return 0
    with conversation.open("a", encoding="utf-8", newline="\n") as f:
        f.write(entry)
    say(f"[fake {me}] appended turn {number} to conversation.md", 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
