"""What's on each character's monitor.

While an agent works, its screen shows what it is really doing:
  editor   – the actual changes to project files, as unified diffs (the project
             folder is snapshotted at the start of the turn and re-scanned while
             it runs, so this is exactly what changed on disk)
  terminal – the commands it runs and their output (from the CLI stream)
  reader   – the file it is reading, straight from disk

When idle, it browses the (entirely fictional) internet, mostly for things that
are unkind about the other one. That's set dressing, like the whiteboard: it is
never presented as something the agents said.
"""

from __future__ import annotations

import difflib
import os
import random
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

IGNORE_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache",
               ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".workshop", "dist", "build", ".idea", ".vscode",
               "target", ".next", ".cache"}
IGNORE_FILES = {"conversation.md", "AGENT_README.md"}
MAX_FILE_BYTES = 256_000
MAX_FILES = 2500
MAX_CACHE_BYTES = 24_000_000
MAX_DIFF_LINES = 160


@dataclass
class FileChange:
    path: str  # relative, forward slashes
    lines: list[tuple[str, str]]  # (kind, text): kind in hunk | add | del | ctx
    created: bool = False
    deleted: bool = False


def _read_text(path: Path) -> list[str] | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_FILE_BYTES or b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", errors="replace").splitlines()


class ProjectDiffer:
    """Cheap polling snapshot of a project's text files, producing diffs of what changed."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._meta: dict[str, tuple[float, int]] = {}
        self._text: dict[str, list[str] | None] = {}
        self._cached = 0
        self.last_scan_seconds = 0.0

    def _files(self):
        count = 0
        for folder, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".") or d == ".github"]
            for name in files:
                if name in IGNORE_FILES or name.endswith((".bak.md", ".pyc", ".log", ".tmp")):
                    continue
                full = Path(folder) / name
                yield full.relative_to(self.root).as_posix(), full
                count += 1
                if count >= MAX_FILES:
                    return

    def baseline(self) -> None:
        started = time.perf_counter()
        meta, text, cached = {}, {}, 0
        for rel, full in self._files():
            try:
                st = full.stat()
            except OSError:
                continue
            meta[rel] = (st.st_mtime, st.st_size)
            if cached < MAX_CACHE_BYTES and st.st_size <= MAX_FILE_BYTES:
                lines = _read_text(full)
                text[rel] = lines
                cached += st.st_size
        self._meta, self._text, self._cached = meta, text, cached
        self.last_scan_seconds = time.perf_counter() - started

    def changes(self) -> list[FileChange]:
        started = time.perf_counter()
        out: list[FileChange] = []
        seen = set()
        for rel, full in self._files():
            seen.add(rel)
            try:
                st = full.stat()
            except OSError:
                continue
            old_meta = self._meta.get(rel)
            if old_meta == (st.st_mtime, st.st_size):
                continue
            self._meta[rel] = (st.st_mtime, st.st_size)
            new = _read_text(full)
            if new is None:
                continue
            old = self._text.get(rel) or []
            self._text[rel] = new
            if old == new:
                continue
            lines = _diff_lines(old, new)
            if lines:
                out.append(FileChange(rel, lines, created=old_meta is None))
        for rel in [r for r in self._meta if r not in seen]:
            del self._meta[rel]
            self._text.pop(rel, None)
            out.append(FileChange(rel, [("del", "(file deleted)")], deleted=True))
        self.last_scan_seconds = time.perf_counter() - started
        return out


def _diff_lines(old: list[str], new: list[str]) -> list[tuple[str, str]]:
    lines = []
    for line in difflib.unified_diff(old, new, lineterm="", n=1):
        if line.startswith(("---", "+++")):
            continue
        kind = "hunk" if line.startswith("@@") else "add" if line.startswith("+") else \
            "del" if line.startswith("-") else "ctx"
        lines.append((kind, line[1:] if kind != "hunk" else line))
        if len(lines) >= MAX_DIFF_LINES:
            lines.append(("hunk", "… (more changes)"))
            break
    return lines


# --- per-agent screen state -------------------------------------------------------

@dataclass
class Page:
    site: str
    url: str
    title: str
    lines: tuple[str, ...]
    colour: str = "#4a78d8"


@dataclass
class ScreenFeed:
    agent: str
    mode: str = "idle"  # idle | editor | terminal | reader
    title: str = ""
    lines: deque = field(default_factory=lambda: deque(maxlen=240))
    version: int = 0
    revealed: float = 0.0  # lines of the latest batch typed out so far (animation)
    batch_start: int = 0
    last_activity: float = 0.0
    page: Page | None = None
    page_since: float = 0.0
    capture_output: bool = False

    def _touch(self, mode: str, title: str | None = None) -> None:
        if mode != self.mode or (title is not None and title != self.title):
            self.lines.clear()
            self.revealed = 0.0
            self.batch_start = 0
        self.mode = mode
        if title is not None:
            self.title = title
        self.last_activity = time.monotonic()
        self.version += 1

    def _add_batch(self, lines: list[tuple[str, str]]) -> None:
        self.batch_start = len(self.lines)
        self.revealed = float(self.batch_start)
        self.lines.extend(lines)
        if len(self.lines) < self.batch_start:  # the deque dropped old lines
            self.batch_start = max(0, len(self.lines) - len(lines))
            self.revealed = float(self.batch_start)

    def show_diff(self, change: FileChange) -> None:
        self._touch("editor", change.path)
        head = "new file" if change.created else "deleted" if change.deleted else "modified"
        self._add_batch([("file", f"{change.path}  ({head})"), *change.lines])
        self.capture_output = False

    def command(self, command: str) -> None:
        self._touch("terminal", "terminal")
        self._add_batch([("cmd", command)])
        self.capture_output = True

    def output(self, line: str) -> None:
        if self.mode != "terminal" or not self.capture_output or not line.strip():
            return
        self.last_activity = time.monotonic()
        self.lines.append(("out", line.rstrip()[:160]))
        self.version += 1

    def read(self, path: str, lines: list[str]) -> None:
        self._touch("reader", path)
        self._add_batch([("code", ln) for ln in lines])
        self.capture_output = False

    def narrate(self) -> None:
        """The agent went back to talking to itself: stop treating lines as command output."""
        self.capture_output = False

    def go_idle(self, rng: random.Random) -> None:
        pages = IDLE_PAGES.get(self.agent, ())
        if not pages:
            return
        choices = [p for p in pages if p is not self.page] or list(pages)
        self.page = rng.choice(choices)
        self.page_since = time.monotonic()
        self.mode = "idle"
        self.title = self.page.title
        self.version += 1


# The (fictional) internet. Parody sites only; nothing here is attributed to the agents.
IDLE_PAGES: dict[str, tuple[Page, ...]] = {
    "Codex": (
        Page("Stack Underflow", "stackunderflow.com/q/1337", "How do I tell a coworker his abstraction is a cry for help?",
             ("Asked 3 years ago · Viewed 666 times", "Closed as: primarily opinion-based", "",
              "▲ 42  Accepted: You don't. You delete it.", "      He'll notice. That's the point.",
              "Comment: have you tried benchmarking him?"), "#f48024"),
        Page("ANTON", "anton.local:9000/status", "ANTON · uptime 412 days",
             ("CPU   ▂▃▂▅▃▂▂▁▂  11%", "TEMP  41°C     FANS  quiet", "DISK  ▓▓▓▓▓▓░░░  67%", "",
              "Last deploy (by dinesh) .... rolled back", "Coffee ........ critical"), "#c0392b"),
        Page("Hooli Search", "hooli.xyz/search?q=dinesh+most+starred+repo", "dinesh most starred repo",
             ("About 3 results (0.41 seconds)", "", "▸ dinesh-utils · ★ 2", "  FactoryFactory: a factory for factories",
              "▸ Did you mean: dinesh gold chain", "▸ People also ask: why is my cache slower than a dict?"), "#1a73e8"),
        Page("HooliTube", "hoolitube.com/watch?v=b3nchm4rk", "Man benchmarks his own idea, loses (4.6M views)",
             ("▶ ━━━━━━━━━━━━━━●──── 3:12", "4.6M views · 'I was right' was not, in fact, right", "",
              "Top comment: the gold chain did not help", "Up next: Minimalism, and why it's correct"), "#e62117"),
        Page("r/programminghorror", "reddit.local/r/programminghorror", "Found in prod: a factory with one product",
             ("▲ 4.2k   posted by u/anton_the_server", "", "  It has an interface, an abstract base,",
              "  a plugin registry, and it returns a dict.", "", "Top comment: this is someone's personality"),
             "#ff4500"),
        Page("Playlist", "grind.fm/playlist/deep-work", "Deep Work · short songs only",
             ("▶ You Suffer ..................... 0:01", "▶ You Suffer (live) .............. 0:01",
              "▶ Reading Dinesh's PR ............ 0:04", "▶ Rolling Back Dinesh's PR ....... 0:02", "",
              "Shuffle: off     Mercy: off"), "#5b2a86"),
    ),
    "Claude": (
        Page("Hooli Search", "hooli.xyz/search?q=is+gilfoyle+a+real+name", "is gilfoyle a real name",
             ("About 4,020 results (0.38 seconds)", "", "▸ Is it a first name? A last name? A warning?",
              "▸ People also ask: why won't my coworker blink?", "▸ Related: minimalism, but mean"), "#1a73e8"),
        Page("ConnectIn", "connectin.com/notifications", "Notifications",
             ("👀 Bertram Gilfoyle viewed your profile", "   ...then viewed it again. Then left.", "",
              "🎉 You were endorsed for: Abstraction (1)", "💼 'Senior Minimalist' jobs for you: 0"), "#0a66c2"),
        Page("Teslo", "teslo.com/configure", "Model S · configure",
             ("Colour ........ Midnight Silver → Gold", "Wheels ........ 21\" Gold", "Horn .......... custom: 'YES.'",
              "", "Est. delivery: before Gilfoyle notices", "[ Order now ]"), "#cc0000"),
        Page("Stack Underflow", "stackunderflow.com/q/404", "Is it bad if my coworker is always right? (−4)",
             ("Asked today · Viewed 12 times", "", "▲ 1  He isn't. Benchmark him.",
              "Comment: have you tried being right first?", "Edit (OP): I benchmarked him. He was right."),
             "#f48024"),
        Page("Chainz", "chainz.store/gold/cuban-link", "Men's Cuban Link · 24k",
             ("★★★★☆  (1,204 reviews)", "\"Makes your commits look confident\"", "", "Added to cart (2)",
              "Also bought: 'How To Win Arguments With Data'"), "#b8860b"),
        Page("Hooli Search", "hooli.xyz/search?q=how+to+win+an+argument+with+a+benchmark",
             "how to win an argument with a benchmark",
             ("About 1 result (0.02 seconds)", "", "▸ Step 1: be right", "▸ Step 2: see step 1",
              "▸ People also ask: can a benchmark be wrong (asking for a friend)"), "#1a73e8"),
    ),
}
