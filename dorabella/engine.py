"""Fast key search and the decoy test every hypothesis has to pass.

`anneal` searches symbol -> letter keys with simulated annealing written in C (engine.c,
compiled on first use with the system C compiler).  It is about 100x faster than the numpy
annealer in solver.py, which is what makes it affordable to run each hypothesis on many
decoys as well as on the cipher.

`trial` is the test: run a search on the cipher and on shuffled copies of it (same symbols,
random order, so no message) and report the empirical p-value.  `power` is the other half:
encipher held-out English the hypothesis's way and check the same search cracks it.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .discs import ALPHABET, normalise
from .scoring import QUAD

_SRC = Path(__file__).with_name("engine.c")
_BUILD = Path(__file__).with_name("_build")


def _load_library() -> ctypes.CDLL:
    so = _BUILD / f"engine-{hashlib.sha1(_SRC.read_bytes()).hexdigest()[:12]}.so"
    if not so.exists():
        _BUILD.mkdir(exist_ok=True)
        fd, tmp = tempfile.mkstemp(suffix=".so", dir=_BUILD)
        os.close(fd)
        subprocess.run(["cc", "-O3", "-shared", "-fPIC", "-o", tmp, str(_SRC), "-lm"], check=True)
        os.replace(tmp, so)   # atomic, so parallel builds don't collide
    lib = ctypes.CDLL(str(so))
    ints, floats, doubles = (np.ctypeslib.ndpointer(t, flags="C_CONTIGUOUS") for t in (np.int32, np.float32, np.float64))
    lib.anneal.restype = ctypes.c_double
    lib.anneal.argtypes = [ints, ctypes.c_int, ctypes.c_int, floats, ctypes.c_int, ints, ints, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_double, ctypes.c_uint64,
                           ints, doubles]
    lib.score_key.restype = ctypes.c_double
    lib.score_key.argtypes = [ints, ctypes.c_int, ints, floats, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    return lib


_LIB = _load_library()
FREE, NULL = -2, -1


@dataclass
class Solution:
    score: float          # mean quadgram log10-probability of the plaintext
    key: np.ndarray       # letter per symbol, -1 = null
    plain: str
    runs: list[float] = field(default_factory=list)   # each restart's best mean score


def _alphabet_size(model: np.ndarray) -> int:
    a = round(len(model) ** 0.25)
    assert a ** 4 == len(model), "model must be an A^4 quadgram table"
    return a


def plaintext(seq, key, alphabet: str = ALPHABET) -> str:
    """Letters for a symbol sequence under a key; breaks become spaces, nulls vanish."""
    return "".join(" " if s < 0 else ("" if key[s] < 0 else alphabet[key[s]]) for s in seq)


def mean_score(seq, key, model: np.ndarray = QUAD) -> float:
    seq, key = np.ascontiguousarray(seq, np.int32), np.ascontiguousarray(key, np.int32)
    grams = ctypes.c_int()
    total = _LIB.score_key(seq, len(seq), key, np.ascontiguousarray(model, np.float32), _alphabet_size(model),
                           ctypes.byref(grams))
    return total / max(grams.value, 1)


def anneal(seq, n_symbols: int | None = None, *, model: np.ndarray = QUAD, fixed=None, groups=None,
           injective: bool = True, restarts: int = 10, iterations: int = 20000,
           t0: float = 20.0, t1: float = 0.5, seed: int = 1, alphabet: str = ALPHABET) -> Solution:
    """Best key for `seq` (symbol ids 0..n_symbols-1, negative = line break) under `model`.

    fixed:  per-symbol FREE (-2), NULL (-1) or a letter index (default: all free)
    groups: per-symbol group id; letters are distinct within a group if injective
    """
    seq = np.ascontiguousarray(seq, np.int32)
    S = int(n_symbols if n_symbols is not None else seq.max() + 1)
    A = _alphabet_size(model)
    fixed = np.full(S, FREE, np.int32) if fixed is None else np.ascontiguousarray(fixed, np.int32)
    groups = np.zeros(S, np.int32) if groups is None else np.ascontiguousarray(groups, np.int32)
    if injective:
        for g in np.unique(groups):
            assert np.sum((groups == g) & (fixed != NULL)) <= A, f"group {g} has more symbols than letters"
    key = np.zeros(S, np.int32)
    runs = np.zeros(restarts, np.float64)
    _LIB.anneal(seq, len(seq), S, np.ascontiguousarray(model, np.float32), A, fixed, groups, int(injective),
                restarts, iterations, t0, t1, seed, key, runs)
    grams = ctypes.c_int()
    total = _LIB.score_key(seq, len(seq), key, np.ascontiguousarray(model, np.float32), A, ctypes.byref(grams))
    g = max(grams.value, 1)
    return Solution(total / g, key, plaintext(seq, key, alphabet), list(runs / g))


# -- the decoy test ---------------------------------------------------------------------------

def shuffled(seq, rng) -> np.ndarray:
    """Same symbols, random order; line breaks stay where they are."""
    seq = np.array(seq)
    body = np.flatnonzero(seq >= 0)
    out = seq.copy()
    out[body] = seq[rng.permutation(body)]
    return out


@dataclass
class Trial:
    name: str
    best: float
    detail: str
    decoys: list[float]

    @property
    def p(self) -> float:
        """Chance a message-free shuffle scores this well (empirical, with the +1 correction)."""
        return (1 + sum(d >= self.best for d in self.decoys)) / (1 + len(self.decoys))

    @property
    def z(self) -> float:
        d = np.array(self.decoys)
        return float((self.best - d.mean()) / (d.std() or 1e-9))

    def line(self) -> str:
        d = np.array(self.decoys)
        return (f"{self.name:<34} {self.best:6.2f}  decoys {d.mean():6.2f} ± {d.std():.2f} (max {d.max():6.2f})  "
                f"z {self.z:+5.1f}  p {self.p:.3f}  {self.detail}")


def trial(name: str, search: Callable[[np.ndarray], tuple[float, str]], seq, n_decoys: int = 30,
          seed: int = 0) -> Trial:
    """Run `search` (seq -> (score, description)) on the cipher and on `n_decoys` shuffles of it."""
    rng = np.random.default_rng(seed)
    best, detail = search(np.asarray(seq))
    decoys = [search(shuffled(seq, rng))[0] for _ in range(n_decoys)]
    return Trial(name, best, detail, decoys)


# -- power: can the search crack English enciphered this way? ---------------------------------

# Held-out English (not in the training corpus), in the register of a letter of the 1890s.
HELD_OUT = [normalise(t) for t in [
    "My dear Dora, I hope that you and your father will come over to Malvern on Thursday next. The weather "
    "has been very fine and I have finished the new piece at last; you must hear it before anyone else does.",
    "We reached the hotel late last night after a most tiresome journey, the train having stopped for an hour "
    "outside Birmingham for no reason that anybody could discover. Alice sends her love and wishes you were here.",
    "Thank you for the parcel which came safely this morning. The music is quite charming and I shall try it "
    "over with the choir on Friday evening if the organist has recovered from his cold by then.",
    "I am sorry to say that I cannot come to the concert after all, as my mother is unwell and I must stay at "
    "home to look after her. Please tell your sister that I will write to her as soon as I am able.",
    "The garden is looking very pretty now that the roses are out, and the old dog lies in the sun all day "
    "long and will not stir even for his dinner. We walked up the hill on Sunday and saw three counties.",
    "Do not forget to bring the books you promised, and your bicycle if the roads are dry. We shall meet you "
    "at the station at half past four and drive back through the lanes in time for tea with the vicar.",
    "Your letter made us laugh very much indeed. The story of the cat and the bishop is quite the best thing "
    "I have heard this year, and I have told it to everybody I know, though I fear I spoiled the ending.",
    "It rained all day so we stayed indoors and played at cards until supper, when the doctor arrived with news "
    "of the wedding. Nobody had expected it in the least, and there was great excitement in the house.",
]]


def english_sample(rng, length: int = 87) -> str:
    text = HELD_OUT[rng.integers(len(HELD_OUT))]
    start = rng.integers(0, len(text) - length + 1)
    return text[start:start + length]


def letters(text: str) -> np.ndarray:
    return np.array([ALPHABET.index(c) for c in text])
