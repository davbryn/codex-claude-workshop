"""How English a string of Elgar-alphabet letters reads: mean quadgram log10-probability.

The model is built from 4.5 million letters of 19th-century prose (see build_ngrams.py).
Higher is more English.  An 87-letter English passage scores about -4.1; the same
letters shuffled about -6.5 (see calibration()).
"""
import gzip
from pathlib import Path

import numpy as np

from .discs import ALPHABET, normalise

N = len(ALPHABET)   # 24


def _load() -> np.ndarray:
    counts = np.zeros(N ** 4)
    with gzip.open(Path(__file__).with_name("english_quadgrams.txt.gz"), "rt") as f:
        for line in f:
            if not line.startswith("#"):
                gram, n = line.split()
                a, b, c, d = (ALPHABET.index(ch) for ch in gram)
                counts[((a * N + b) * N + c) * N + d] = int(n)
    total = counts.sum()
    return np.where(counts > 0, np.log10(np.maximum(counts, 1) / total), np.log10(0.01 / total)).astype(np.float32)


QUAD = _load()


def quad_index(idx: np.ndarray) -> np.ndarray:
    return ((idx[..., :-3] * N + idx[..., 1:-2]) * N + idx[..., 2:-1]) * N + idx[..., 3:]


def score(idx: np.ndarray) -> np.ndarray:
    """Mean quadgram log-probability of each row of letter indices."""
    return QUAD[quad_index(np.asarray(idx))].mean(-1)


def score_text(text: str) -> float:
    return float(score(np.array([ALPHABET.index(c) for c in normalise(text)])))


def to_text(idx) -> str:
    return "".join(ALPHABET[i] for i in idx)


# Held-out sample (not in the training corpus), in the register of a letter of the period.
SAMPLE = normalise("My dear Dora, I hope that you and your father will come over to Malvern on Thursday "
                   "next. The weather has been very fine and I have finished the new piece at last; "
                   "you must hear it before anyone else does.")


def calibration(length: int = 87) -> dict[str, float]:
    text = SAMPLE[:length]
    shuffled = to_text(np.random.default_rng(0).permutation([ALPHABET.index(c) for c in text]))
    return {"english": score_text(text), "shuffled": score_text(shuffled)}
