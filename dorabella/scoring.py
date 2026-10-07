"""How much a string of Elgar-alphabet letters reads like a language: mean quadgram log10-probability.

English is built from 4.5 million letters of 19th-century prose (see build_ngrams.py).
Latin, French, German and Italian models (models/*.txt.gz) are built the same way from
period prose; each file's header names its sources.  Higher is more language-like.  An
87-letter passage scores about -4.0 to -4.2 under its own language's model; the same
letters shuffled about -6.3 to -6.8 (see calibration()).
"""
import gzip
from functools import cache
from pathlib import Path

import numpy as np

from .discs import ALPHABET, normalise

N = len(ALPHABET)   # 24
MODELS_DIR = Path(__file__).with_name("models")
LANGUAGES = sorted(p.name.split("_")[0] for p in MODELS_DIR.glob("*_quadgrams.txt.gz"))


@cache
def model(language: str = "english") -> np.ndarray:
    """Quadgram log10-probabilities, indexed ((a*N + b)*N + c)*N + d, unseen grams floored."""
    counts = np.zeros(N ** 4)
    with gzip.open(MODELS_DIR / f"{language}_quadgrams.txt.gz", "rt") as f:
        for line in f:
            if not line.startswith("#"):
                gram, n = line.split()
                a, b, c, d = (ALPHABET.index(ch) for ch in gram)
                counts[((a * N + b) * N + c) * N + d] = int(n)
    total = counts.sum()
    return np.where(counts > 0, np.log10(np.maximum(counts, 1) / total), np.log10(0.01 / total)).astype(np.float32)


QUAD = model("english")


def quad_index(idx: np.ndarray) -> np.ndarray:
    return ((idx[..., :-3] * N + idx[..., 1:-2]) * N + idx[..., 2:-1]) * N + idx[..., 3:]


def score(idx: np.ndarray, table: np.ndarray = QUAD) -> np.ndarray:
    """Mean quadgram log-probability of each row of letter indices."""
    return table[quad_index(np.asarray(idx))].mean(-1)


def score_text(text: str, table: np.ndarray = QUAD) -> float:
    return float(score(np.array([ALPHABET.index(c) for c in normalise(text)]), table))


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
