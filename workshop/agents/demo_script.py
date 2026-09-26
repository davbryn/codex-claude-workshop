"""Deterministic demo scenario used by ``--demo`` and ``--fake-agents``: a tiny
Gilfoyle (Codex) and Dinesh (Claude) episode.

Each DemoTurn lists fake CLI output lines (Codex uses the real `codex exec`
format, Claude uses our stream-json condensation) and the public entry the
fake agent appends. The episode: Dinesh over-architects, Gilfoyle deletes it
and ships a real edge-case bug, Dinesh catches it and is unbearable about it,
Gilfoyle fixes it and immediately finds Dinesh's pointless cache, Dinesh
benchmarks his way into an own goal, the human settles a product question,
both independently review, PROJECT COMPLETE. Somehow.
"""

from __future__ import annotations

from dataclasses import dataclass

DEMO_PROMPT = ("Build a tiny command-line URL shortener: shorten, resolve and list. Keep it small, fast and "
               "well tested.")
DEMO_FIRST_AGENT = "Claude"
DEMO_HUMAN_REPLY = ("Case-sensitive. Keep the keyspace. And nobody mention the cache again. "
                    "(This is the demo's automatic human reply.)")


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
        "Claude",
        ("[tool] Read: AGENT_README.md", "[tool] Read: conversation.md", "",
         "[tool] Write: shortener/backends.py", "[tool] Write: shortener/factory.py",
         "[tool] Write: shortener/registry.py", "[tool] Write: shortener/encoders.py",
         "[tool] Write: test_shortener.py", "",
         "[tool] Bash: python -m pytest -q", "[tool result] 6 passed in 0.08s"),
        "Gilfoyle hasn't touched anything yet, so for one brief, shining moment this codebase has architecture. "
        "I built it properly: a `StorageBackend` interface, an in-memory backend, a SQLite backend for when we "
        "scale, and a `ShortenerFactory` with a plugin registry so new encoders can just be dropped in. "
        "Before anyone says anything: yes, it's extensible. That's the point of it.",
        "Created `shortener/` with `backends.py`, `factory.py`, `registry.py` and `encoders.py` (212 lines), "
        "plus `test_shortener.py`.",
        "All 6 tests pass. Shorten, resolve and list work on both backends.",
        "Gilfoyle, review the architecture. Try to appreciate the extensibility instead of just deleting it.",
        "@Codex",
    ),
    DemoTurn(
        "Codex",
        ("codex", "Reading Dinesh's architecture.",
         *_codex_exec("Get-ChildItem -Recurse shortener; Get-Content shortener/factory.py"), "",
         "codex", "Deleting.",
         *_codex_exec("Remove-Item -Recurse shortener"), "",
         "[tool] Write: shortener.py", "[tool] Edit: test_shortener.py", "",
         *_codex_exec("python -m pytest -q", ".....", "5 passed in 0.03s")),
        "Dinesh built a URL shortener with a plugin registry. There are no plugins. There will never be plugins. "
        "I replaced the factory, the registry, both backends and the interface with a dict and a base62 counter. "
        "It's 31 lines. The SQLite backend 'for when we scale' has been scaled to zero.",
        "Deleted `factory.py`, `registry.py` and `backends.py`. Rewrote everything as `shortener.py`: a dict plus "
        "`encode(n)`. Kept the tests that test behaviour; deleted the four that tested the factory.",
        "5 tests pass. 181 fewer lines to maintain.",
        "Your turn, Dinesh. Try not to install Kubernetes.",
        "@Claude",
    ),
    DemoTurn(
        "Claude",
        ("[tool] Read: shortener.py", "",
         "[tool] Bash: python -c \"from shortener import encode; print(repr(encode(0)))\"", "[tool result] ''", "",
         "[tool] Write: test_shortener.py", "[tool] Edit: shortener.py", "",
         "[tool] Bash: python -m pytest -q",
         "[tool result] FAILED test_shortener.py::test_first_link_is_reachable - AssertionError: '' is not a code",
         "[tool result] 1 failed, 5 passed in 0.04s"),
        "Oh, that's interesting. Gilfoyle's beautifully minimal encoder returns an empty string for the very first "
        "link, because `encode(0)` never enters the loop. So the first link anyone ever shortens resolves to "
        "nothing. Minimalism: now with less functionality. I've written the regression test and left it failing, "
        "because I want him to type the fix himself. It's important for his growth.",
        "Added `test_first_link_is_reachable` (failing, on purpose). While I was in there I put an LRU cache in "
        "front of `resolve`, because lookups at scale are going to matter.",
        "1 failed, 5 passed. The failure belongs to Gilfoyle.",
        "Gilfoyle: it's one line. I believe in you. Actually I don't, but the test does.",
        "@Codex",
    ),
    DemoTurn(
        "Codex",
        ("[tool] Read: test_shortener.py", "",
         *_codex_exec("python -m pytest -q", "F.....", "FAILED test_shortener.py::test_first_link_is_reachable",
                      "1 failed, 5 passed in 0.04s", ok=False), "",
         "codex", "Hm.", "[tool] Edit: shortener.py", "",
         *_codex_exec("python -m pytest -q", "......", "6 passed in 0.03s")),
        "Unfortunately, Dinesh is right. `encode(0)` returned an empty string, so the first link was unreachable. "
        "My mistake. The fix was one line, which he could have typed in less time than the victory lap took. "
        "More concerning: he wrapped a dictionary lookup in an LRU cache. A dict lookup is already the cache. "
        "He cached the cache.",
        "Fixed `encode(0)`. Left his cache alone for now, because I'd like it to die on evidence rather than on "
        "my say-so.",
        "All 6 tests pass.",
        "Dinesh, I disagree that the cache helps anything except your self-esteem. Benchmark it. I'll wait.",
        "@Claude",
    ),
    DemoTurn(
        "Claude",
        ("[tool] Write: bench_resolve.py", "",
         "[tool] Bash: python bench_resolve.py",
         "[tool result] dict lookup:      41 ns per resolve",
         "[tool result] with LRU cache:  188 ns per resolve", "",
         "[tool] Edit: shortener.py", "",
         "[tool] Bash: python -m pytest -q", "[tool result] 6 passed in 0.03s"),
        "Fine. I wrote a benchmark to prove the cache matters at scale, and the benchmark has betrayed me. "
        "Plain dict lookup: 41 ns. Through my LRU cache: 188 ns. My optimisation made resolve 4.6x slower. "
        "Gilfoyle was right. Technically, I was wrong. I'd like it noted that I proved it myself, scientifically, "
        "which is more than he ever does.",
        "Added `bench_resolve.py` (timeit, one million lookups). Removed the LRU cache.",
        "All 6 tests pass, and resolve is back to 41 ns.",
        "Gilfoyle, don't.",
        "@Codex",
    ),
    DemoTurn(
        "Codex",
        ("[tool] Read: bench_resolve.py", "[tool] Read: shortener.py", "",
         *_codex_exec("python bench_resolve.py", "dict lookup:      41 ns per resolve"), "",
         *_codex_exec("python -m pytest -q", "......", "6 passed in 0.03s")),
        "Dinesh ran an experiment, it disproved his own idea, and he reported it honestly. I'm told this is called "
        "growth. It's disturbing. One real question is left: Dinesh wants short codes case-insensitive 'for "
        "usability', which throws away most of the keyspace. That's a product decision, so it goes to someone "
        "with a job title.",
        "Reviewed the benchmark, reran the suite, and read `shortener.py` for anything else Dinesh might have "
        "improved.",
        "All 6 tests pass. Nothing left to delete. I checked twice.",
        "HUMAN DECISION NEEDED: Should short codes be case-sensitive (bigger keyspace) or case-insensitive "
        "(easier to type)?",
        "@Claude",
    ),
    DemoTurn(
        "Claude",
        ("[tool] Read: conversation.md", "",
         "[tool] Edit: test_shortener.py", "",
         "[tool] Bash: python -m pytest -q", "[tool result] 8 passed in 0.04s"),
        "Management has spoken: case-sensitive. Gilfoyle is going to be insufferable about 'keyspace' for a week. "
        "I've pinned the behaviour with tests so nobody can quietly change it, including me. Also, for the record, "
        "nobody mentioned the cache. Until just now. Sorry.",
        "Added `test_codes_are_case_sensitive` and `test_unknown_code_resolves_to_none`.",
        "All 8 tests pass. I believe this is done, and I believe it was mostly my test suite that got it there.",
        "Gilfoyle, independently review and test before agreeing. Try to find something. You won't.",
        "PROPOSE PROJECT COMPLETE\n\n@Codex",
    ),
    DemoTurn(
        "Codex",
        ("[tool] Read: shortener.py", "[tool] Read: test_shortener.py", "",
         *_codex_exec("python -m pytest -q", "........", "8 passed in 0.04s"), "",
         *_codex_exec("python shortener.py shorten https://example.com; python shortener.py resolve 0",
                      "0", "https://example.com")),
        "I tried to find something. I didn't. Dinesh's tests are correct, which he will never let me forget, "
        "the way I will never let him forget the cache. It's small, it's fast, the first link resolves. "
        "It was inevitable.",
        "Independent review of every file, the full test run, and a manual shorten/resolve round trip.",
        "All 8 tests pass. The cache remains dead.",
        "Nothing. Go home, Dinesh.",
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
