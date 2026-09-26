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
"""

from __future__ import annotations

import argparse
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
        "Claude hasn't had the chance to ruin anything yet, so I suppose I'll begin.",
        "I inspected Claude's changes. They work. I'm as surprised as you are.",
        "Minimal, elegant, correct. Pick three.",
        "I have reviewed the code and found nothing to remove. A first.",
    ],
    "Claude": [
        "Oh, this is a *lovely* start! Although I think the abstraction is unnecessary here.",
        "Codex was right about the parser — I've kept its version and added a regression test.",
        "I'm not saying this is over-engineered, but it has a load-bearing wrapper class.",
        "Everything checks out. I'd say this is… byte-sized perfection.",
    ],
}


def say(text: str, delay: float) -> None:
    print(text, flush=True)
    time.sleep(delay)


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

    say(f"[fake {me}] received prompt ({len(prompt)} chars)", step)
    if args.behavior == "fail":
        print(f"[fake {me}] simulated crash: something went terribly wrong", file=sys.stderr, flush=True)
        return 1

    text = conversation.read_text(encoding="utf-8")
    turns = parse_conversation(text)
    signal = signal_for_turn(turns[-1]) if turns else None
    if signal is None or signal.kind != "handoff" or signal.agent != me:
        print(f"[fake {me}] refusing to act: latest handoff is not @{me}", file=sys.stderr, flush=True)
        return 2

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
