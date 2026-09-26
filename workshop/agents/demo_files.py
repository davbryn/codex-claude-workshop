"""Source files the --demo episode actually writes, so the monitors show real diffs.

Keyed by (turn index, path). A value of None deletes the file. The code follows
the story: Dinesh's over-built package, Gilfoyle's 31-line rewrite with the
encode(0) bug, the LRU cache, the one-line fix, the benchmark, the removal.
"""

BACKENDS = '''"""Storage backends. Swappable, because we will scale."""
from abc import ABC, abstractmethod
import sqlite3


class StorageBackend(ABC):
    @abstractmethod
    def put(self, code: str, url: str) -> None: ...

    @abstractmethod
    def get(self, code: str) -> str | None: ...


class InMemoryBackend(StorageBackend):
    def __init__(self):
        self._data = {}

    def put(self, code, url):
        self._data[code] = url

    def get(self, code):
        return self._data.get(code)


class SQLiteBackend(StorageBackend):
    def __init__(self, path=":memory:"):
        self._db = sqlite3.connect(path)
        self._db.execute("create table if not exists links (code text primary key, url text)")

    def put(self, code, url):
        self._db.execute("insert into links values (?, ?)", (code, url))

    def get(self, code):
        row = self._db.execute("select url from links where code = ?", (code,)).fetchone()
        return row[0] if row else None
'''

FACTORY = '''"""ShortenerFactory: builds a shortener from a backend and an encoder plugin."""
from .backends import InMemoryBackend, SQLiteBackend
from .registry import ENCODERS


class ShortenerFactory:
    BACKENDS = {"memory": InMemoryBackend, "sqlite": SQLiteBackend}

    @classmethod
    def create(cls, backend="memory", encoder="base62"):
        return Shortener(cls.BACKENDS[backend](), ENCODERS[encoder]())


class Shortener:
    def __init__(self, backend, encoder):
        self.backend, self.encoder, self.next_id = backend, encoder, 1

    def shorten(self, url):
        code = self.encoder.encode(self.next_id)
        self.backend.put(code, url)
        self.next_id += 1
        return code

    def resolve(self, code):
        return self.backend.get(code)
'''

REGISTRY = '''"""Plugin registry, so new encoders can simply be dropped in."""
ENCODERS = {}


def register(name):
    def wrap(cls):
        ENCODERS[name] = cls
        return cls
    return wrap
'''

ENCODERS = '''from .registry import register

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


@register("base62")
class Base62Encoder:
    def encode(self, n: int) -> str:
        out = ""
        while n:
            n, r = divmod(n, 62)
            out = ALPHABET[r] + out
        return out or ALPHABET[0]
'''

TESTS_V1 = '''from shortener.factory import ShortenerFactory


def test_round_trip_memory():
    s = ShortenerFactory.create("memory")
    assert s.resolve(s.shorten("https://example.com")) == "https://example.com"


def test_round_trip_sqlite():
    s = ShortenerFactory.create("sqlite")
    assert s.resolve(s.shorten("https://example.com")) == "https://example.com"


def test_unknown_code():
    assert ShortenerFactory.create().resolve("nope") is None
'''

SHORTENER_V1 = '''"""A URL shortener. It's a dict."""
import sys

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
links: dict[str, str] = {}


def encode(n: int) -> str:
    out = ""
    while n:
        n, r = divmod(n, 62)
        out = ALPHABET[r] + out
    return out


def shorten(url: str) -> str:
    code = encode(len(links))
    links[code] = url
    return code


def resolve(code: str) -> str | None:
    return links.get(code)


if __name__ == "__main__":
    cmd, arg = sys.argv[1], sys.argv[2]
    print(shorten(arg) if cmd == "shorten" else resolve(arg))
'''

TESTS_V2 = '''from shortener import resolve, shorten


def test_round_trip():
    assert resolve(shorten("https://example.com")) == "https://example.com"


def test_unknown_code():
    assert resolve("nope") is None
'''

TESTS_V3 = TESTS_V2 + '''

def test_first_link_is_reachable():
    import shortener
    shortener.links.clear()
    code = shortener.shorten("https://first.example")
    assert code, "the very first link got an empty code"
    assert shortener.resolve(code) == "https://first.example"
'''

SHORTENER_V2 = SHORTENER_V1.replace('''import sys
''', '''import sys
from functools import lru_cache
''').replace('''def resolve(code: str) -> str | None:
    return links.get(code)''', '''@lru_cache(maxsize=4096)  # lookups at scale
def resolve(code: str) -> str | None:
    return links.get(code)''')

SHORTENER_V3 = SHORTENER_V2.replace('''        out = ALPHABET[r] + out
    return out
''', '''        out = ALPHABET[r] + out
    return out or ALPHABET[0]
''')

BENCH = '''"""Does the cache help? (Dinesh: yes. The benchmark: no.)"""
import timeit

import shortener

shortener.links.update({shortener.encode(i): f"https://example.com/{i}" for i in range(10_000)})
for label in ("with LRU cache", "dict lookup"):
    fn = shortener.resolve if label.startswith("with") else shortener.links.get
    ns = timeit.timeit(lambda: fn("2Bi"), number=1_000_000) * 1000
    print(f"{label:>16}: {ns:5.0f} ns per resolve")
'''

SHORTENER_V4 = SHORTENER_V3.replace('''from functools import lru_cache
''', "").replace('''@lru_cache(maxsize=4096)  # lookups at scale
''', "")

TESTS_V4 = TESTS_V3 + '''

def test_codes_are_case_sensitive():
    import shortener
    shortener.links.clear()
    codes = [shortener.shorten(f"https://example.com/{i}") for i in range(80)]
    assert "a" in codes and "A" in codes and shortener.resolve("a") != shortener.resolve("A")


def test_unknown_code_resolves_to_none():
    assert resolve("zzzzzz") is None
'''

DEMO_FILES: dict[tuple[int, str], str | None] = {
    (0, "shortener/backends.py"): BACKENDS,
    (0, "shortener/factory.py"): FACTORY,
    (0, "shortener/registry.py"): REGISTRY,
    (0, "shortener/encoders.py"): ENCODERS,
    (0, "shortener/__init__.py"): "",
    (0, "test_shortener.py"): TESTS_V1,
    (1, "shortener/backends.py"): None,
    (1, "shortener/factory.py"): None,
    (1, "shortener/registry.py"): None,
    (1, "shortener/encoders.py"): None,
    (1, "shortener/__init__.py"): None,
    (1, "shortener.py"): SHORTENER_V1,
    (1, "test_shortener.py"): TESTS_V2,
    (2, "test_shortener.py"): TESTS_V3,
    (2, "shortener.py"): SHORTENER_V2,
    (3, "shortener.py"): SHORTENER_V3,
    (4, "bench_resolve.py"): BENCH,
    (4, "shortener.py"): SHORTENER_V4,
    (6, "test_shortener.py"): TESTS_V4,
}


# --- the demo's kanban board: (start of turn, mid-turn, end of turn) per turn ---------

def _board(todo, doing, done, asides) -> str:
    def section(name, items):
        return f"## {name}\n" + "".join(f"- {item}\n" for item in items) + "\n"
    return ("# Kanban\n\n<!-- Set up by management (Jared) so everyone can see progress at a glance. "
            "Please keep it current! -->\n\n" + section("To do", todo) + section("Doing", doing)
            + section("Done", done) + "## Asides\n" + "".join(f"- {a}\n" for a in asides))


_JARED = 'Read the brief together (Gilfoyle, Dinesh) — "Synergy starts with a shared understanding! — Jared"'
_A = []  # asides accumulate over the episode


def _asides(*new):
    _A.extend(new)
    return list(_A)


DEMO_KANBAN: dict[int, tuple[str, str | None, str]] = {}
DEMO_KANBAN[0] = (
    _board([_JARED], ['Build the URL shortener (Dinesh) — "Jared made us a kanban. I will use it properly, since one of us has to."'], [], _asides()),
    _board([_JARED], ['Build the URL shortener (Dinesh) — "Jared made us a kanban. I will use it properly, since one of us has to."'], [],
           _asides("Dinesh: Six tests, all green. Screenshot this, Jared.")),
    _board(["Review the architecture (Gilfoyle)"], [],
           ['Build the URL shortener (Dinesh) — "Pluggable backends, a factory and a registry. You are welcome, future us."', _JARED.replace(" (Gilfoyle, Dinesh)", " (Gilfoyle, Dinesh)")],
           list(_A)),
)
DEMO_KANBAN[1] = (
    _board([], ['Review the architecture (Gilfoyle) — "Reviewing is a strong word. Deleting is the word."'],
           ['Build the URL shortener (Dinesh) — "Pluggable backends, a factory and a registry. You are welcome, future us."'],
           _asides("Gilfoyle: I have been assigned work by a kanban board. This is how civilisations end.")),
    None,
    _board(["Check edge cases (Dinesh)"], [],
           ['Delete the plugin registry (Gilfoyle) — "It had no plugins. Now it has no registry. Balance."',
            'Build the URL shortener (Dinesh) — "Pluggable backends, a factory and a registry. You are welcome, future us."'],
           list(_A)),
)
DEMO_KANBAN[2] = (
    _board([], ['Check edge cases (Dinesh) — "Checking all 31 of Gilfoyle\'s lines. Should take 31 seconds."'],
           ['Delete the plugin registry (Gilfoyle) — "It had no plugins. Now it has no registry. Balance."'], list(_A)),
    _board([], ['Check edge cases (Dinesh) — "Checking all 31 of Gilfoyle\'s lines. Should take 31 seconds."'],
           ['Delete the plugin registry (Gilfoyle) — "It had no plugins. Now it has no registry. Balance."'],
           _asides("Dinesh: Oh no. Oh YES. encode(0) returns nothing. The first link goes nowhere.")),
    _board(["Fix encode(0) (Gilfoyle)"], [],
           ['Found the encode(0) bug (Dinesh) — "Leaving the fix for him. It is a growth opportunity."',
            'Add an LRU cache to resolve (Dinesh) — "Lookups at scale."'], list(_A)),
)
DEMO_KANBAN[3] = (
    _board([], ['Fix encode(0) (Gilfoyle) — "A one-line fix, and a card for it. Jared must be thrilled."'],
           ['Found the encode(0) bug (Dinesh) — "Leaving the fix for him. It is a growth opportunity."',
            'Add an LRU cache to resolve (Dinesh) — "Lookups at scale."'], list(_A)),
    _board([], ['Fix encode(0) (Gilfoyle) — "A one-line fix, and a card for it. Jared must be thrilled."'],
           ['Add an LRU cache to resolve (Dinesh) — "Lookups at scale."'],
           _asides("Gilfoyle: He put a cache in front of a dictionary. The dictionary is the cache.")),
    _board(["Prove the cache helps (Dinesh)"], [],
           ['Fix encode(0) (Gilfoyle) — "Fixed. Please stop dragging it back to Doing, Dinesh."',
            'Add an LRU cache to resolve (Dinesh) — "Lookups at scale."'], list(_A)),
)
DEMO_KANBAN[4] = (
    _board([], ['Prove the cache helps (Dinesh) — "Benchmark incoming. Prepare to be humbled."'],
           ['Fix encode(0) (Gilfoyle) — "Fixed. Please stop dragging it back to Doing, Dinesh."'], list(_A)),
    _board([], ['Prove the cache helps (Dinesh) — "Benchmark incoming. Prepare to be humbled."'],
           ['Fix encode(0) (Gilfoyle) — "Fixed. Please stop dragging it back to Doing, Dinesh."'],
           _asides("Dinesh: The numbers are… loading. They are loading wrong.")),
    _board(["Review the benchmark (Gilfoyle)"], [],
           ['Remove the LRU cache (Dinesh) — "Nobody say anything."',
            'Fix encode(0) (Gilfoyle) — "Fixed. Please stop dragging it back to Doing, Dinesh."'], list(_A)),
)
DEMO_KANBAN[5] = (
    _board([], ['Review the benchmark (Gilfoyle) — "I would like to frame this card."'],
           ['Remove the LRU cache (Dinesh) — "Nobody say anything."'], list(_A)),
    None,
    _board(["Decide on case-sensitive codes (Management)"], [],
           ['Review the benchmark (Gilfoyle) — "Escalated to management. Jared will love that there is a card."',
            'Remove the LRU cache (Dinesh) — "Nobody say anything."'], list(_A)),
)
DEMO_KANBAN[6] = (
    _board([], ['Case-sensitivity tests (Dinesh) — "Management has spoken, and I am a team player."'],
           ['Review the benchmark (Gilfoyle) — "Escalated to management. Jared will love that there is a card."'], list(_A)),
    None,
    _board(["Final review (Gilfoyle)"], [],
           ['Case-sensitivity tests (Dinesh) — "Proposing completion. Nobody touch the board."',
            'Review the benchmark (Gilfoyle) — "Escalated to management. Jared will love that there is a card."'], list(_A)),
)
DEMO_KANBAN[7] = (
    _board([], ['Final review (Gilfoyle) — "Reviewing. Silently."'],
           ['Case-sensitivity tests (Dinesh) — "Proposing completion. Nobody touch the board."'], list(_A)),
    None,
    _board([], [],
           ['Final review (Gilfoyle) — "Everything is in Done. Jared can finally sleep."',
            'Case-sensitivity tests (Dinesh) — "Proposing completion. Nobody touch the board."'], list(_A)),
)
