"""Idle humour, made asynchronously by the agent who is NOT working.

While one agent takes its (sequential) turn, the other can still contribute to the
comedy: a small, separate call to its own CLI asks, in character, for ONE idle
activity about what the working agent is visibly doing right now — a complaint
email to Jared, a search, an ASCII doodle, a Slack message, a notes file — plus
one line it mutters. The text is the idle agent's own; nothing is scripted.

Side calls are sandboxed away from the project: they run in a temporary folder,
Claude with every tool disabled and Codex in a read-only sandbox. They never touch
conversation.md or the orchestration, cost a little usage, and are capped per turn.
"""

from __future__ import annotations

import json

import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .cast import CHARACTER

KINDS = ("email", "search", "doodle", "chat", "note")
LIMITS = {"title": 90, "body": 420, "line": 120}

PROMPT = """You are {me} (the {agent} agent, playing {me} from HBO's Silicon Valley) in a two-agent coding workshop.
{other} ({other_agent}) is working on the shared project right now; you are waiting for your turn.
While you wait, do ONE small idle thing, in character, about {other} or the task, and reply with ONLY a
JSON object (no code fence, no commentary):
{{"kind": "email|search|doodle|chat|note", "title": "...", "body": "...", "line": "..."}}
- email: a complaint to Jared (management) about {other}. title = subject line; body = the email, under 60 words.
- search: title = the search query you type; body = 2-3 short result lines you imagine seeing.
- doodle: title = a caption; body = ASCII art, at most 8 lines of at most 32 characters.
- chat: title = the channel or recipient; body = your message, under 40 words.
- note: title = a file name; body = at most 5 short lines.
- line: what you mutter aloud while doing it (under 100 characters).
Make it specific to what {other} is actually doing right now:
{context}
Pick a kind you haven't used recently ({recent}). Keep it workplace-funny: no slurs, nothing about real people.
Do not use tools, do not read or write files, do not change any code. Just reply with the JSON."""


def build_prompt(agent: str, context: str, recent: list[str]) -> str:
    other_agent = "Claude" if agent == "Codex" else "Codex"
    return PROMPT.format(me=CHARACTER[agent], agent=agent, other=CHARACTER[other_agent], other_agent=other_agent,
                         context=context.strip() or "(he is working; details unknown)",
                         recent=", ".join(recent[-3:]) or "none yet")


def parse_bit(text: str) -> dict | None:
    """The first usable JSON object in the reply, validated and trimmed. None if there isn't one."""
    decoder = json.JSONDecoder()
    for start in [i for i, ch in enumerate(text) if ch == "{"][:40]:
        try:
            data, _ = decoder.raw_decode(text[start:])
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        kind = str(data.get("kind", "")).strip().lower()
        if kind not in KINDS:
            continue
        bit = {"kind": kind}
        for key, limit in LIMITS.items():
            value = data.get(key, "")
            value = value.replace("\r", "") if isinstance(value, str) else ""
            if key != "body":
                value = " ".join(value.split())
            bit[key] = value[:limit].rstrip()
        if kind == "doodle":
            bit["body"] = "\n".join(line[:34] for line in bit["body"].splitlines()[:9])
        if bit["title"] or bit["body"]:
            return bit
    return None


class SideBits(QObject):
    """Runs side calls to the idle agent's CLI. ``ready(agent, bit)`` when one arrives."""

    ready = Signal(str, dict)

    def __init__(self, adapters: dict, parent: QObject | None = None, timeout_s: float = 120.0):
        super().__init__(parent)
        self.adapters = adapters
        self.timeout_s = timeout_s
        self._procs: dict[str, QProcess] = {}
        self._tmp = Path(tempfile.mkdtemp(prefix="workshop-sidebits-"))

    def busy(self, agent: str) -> bool:
        return agent in self._procs

    def request(self, agent: str, context: str, recent: list[str]) -> bool:
        if agent in self._procs:
            return False
        adapter = self.adapters.get(agent)
        if adapter is None:
            return False
        try:
            exe = adapter.resolve_executable()
        except Exception:
            return False
        prompt = build_prompt(agent, context, recent)
        out_file = self._tmp / f"{agent.lower()}-bit.txt"
        if agent == "Claude":
            args = ["-p", "--output-format", "text", "--tools", ""]
            env_drop = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
        else:
            out_file.unlink(missing_ok=True)
            args = ["exec", "--color", "never", "--skip-git-repo-check", "--sandbox", "read-only",
                    "--output-last-message", str(out_file), "-"]
            env_drop = ()
        spec = adapter.make_spec(exe, args, stdin=prompt)
        proc = QProcess(self)
        proc.setWorkingDirectory(str(self._tmp))
        env = QProcessEnvironment.systemEnvironment()
        for name in env_drop:
            env.remove(name)
        proc.setProcessEnvironment(env)
        proc.setProgram(spec.program)
        proc.setArguments(spec.args)
        if spec.native_arguments is not None and hasattr(proc, "setNativeArguments"):
            proc.setNativeArguments(spec.native_arguments)
        chunks: list[bytes] = []
        proc.readyReadStandardOutput.connect(lambda p=proc: chunks.append(bytes(p.readAllStandardOutput())))
        proc.finished.connect(lambda code, _status, a=agent, p=proc: self._done(a, p, chunks, out_file))
        timer = QTimer(proc)
        timer.setSingleShot(True)
        timer.timeout.connect(proc.kill)
        timer.start(int(self.timeout_s * 1000))
        self._procs[agent] = proc
        proc.start()
        if not proc.waitForStarted(5000):
            self._procs.pop(agent, None)
            return False
        proc.write(prompt.encode("utf-8"))
        proc.closeWriteChannel()
        return True

    def _done(self, agent: str, proc: QProcess, chunks: list[bytes], out_file: Path) -> None:
        self._procs.pop(agent, None)
        text = b"".join(chunks).decode("utf-8", errors="replace")
        if agent == "Codex" and out_file.exists():
            text = out_file.read_text(encoding="utf-8", errors="replace")
        bit = parse_bit(text)
        proc.deleteLater()
        if bit:
            self.ready.emit(agent, bit)

    def shutdown(self) -> None:
        for proc in list(self._procs.values()):
            proc.kill()
        self._procs.clear()
