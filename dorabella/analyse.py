"""Try every disc setting on the Dorabella cipher and rank the results by how English they read.

The transcription below was read from the 1897 cipher: the 87 symbols split
into 21 distinct glyphs (labelled A..U in order of first appearance, the
usual isomorph transcription), and each glyph was then given its sector and
arc count by eye.  Edit GLYPHS if you read a symbol differently.

    python -m dorabella.analyse              # fixed settings and stepping settings
    python -m dorabella.analyse --top 20
"""
from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path

import numpy as np

from .discs import ALPHABET, COMPASS, DISCS, DiscSet, Glyph, normalise

# The cipher as glyph labels, one string per line of Elgar's note.
ISOMORPH = ["ABCDEFGDHAIJKLJMJJFBBJNGOGNIP",
            "GJGFQDHRSCJJCFNKGJIJFTPKLQHHQIP",
            "CPFUPCLUUNPCJFUKPNDBNPFDLED"]

# label -> where the arcs sit + how many.  W1 is a "c", W2 "ε", W3 "ξ", N2 "m", S2 "ω".
GLYPHS = {
    "E": "W1", "L": "NW1", "N": "N1", "H": "NE1", "K": "SE1", "G": "S1", "Q": "SW1",
    "A": "W2", "C": "NW2", "F": "N2", "R": "E2", "J": "SE2", "T": "S2", "O": "SW2",
    "D": "W3", "I": "NW3", "M": "N3", "B": "E3", "P": "SE3", "U": "S3", "S": "SW3",
}

CIPHER = [Glyph.parse(GLYPHS[c]) for c in "".join(ISOMORPH)]


def trigram_table() -> np.ndarray:
    counts = np.ones((24, 24, 24))   # add-one smoothing
    for line in (Path(__file__).with_name("english_trigrams.txt")).read_text().splitlines():
        if line and not line.startswith("#"):
            tri, n = line.split()
            counts[tuple(ALPHABET.index(c) for c in tri)] += int(n)
    return np.log10(counts / counts.sum())


TRIGRAMS = trigram_table()
# Each disc's letters as alphabet indices: DISC_IDX[d][slot]
DISC_IDX = np.array([[ALPHABET.index(c) for c in letters] for letters in DISCS])


def score(idx: np.ndarray) -> np.ndarray:
    """Mean trigram log-probability of each row of letter indices (higher is more English)."""
    return TRIGRAMS[idx[..., :-2], idx[..., 1:-1], idx[..., 2:]].mean(-1)


def decrypt_all(glyphs: list[Glyph], ring_of: tuple[int, int, int], step: tuple[int, int, int]) -> np.ndarray:
    """Letter indices for all 512 rotations at once: shape (512, len(glyphs))."""
    sectors = np.array([g.sector for g in glyphs])
    discs = np.array([ring_of.index(g.arcs - 1) for g in glyphs])
    t = np.arange(len(glyphs))
    rots = np.array(list(itertools.product(range(8), repeat=3)))           # (512, 3)
    turned = rots[:, discs] + t * np.array(step)[discs]                     # (512, n)
    slots = (sectors - turned) % 8
    return DISC_IDX[discs, slots]


def search(glyphs: list[Glyph], stepping: bool):
    steps = itertools.product(range(8), repeat=3) if stepping else [(0, 0, 0)]
    rots = list(itertools.product(range(8), repeat=3))
    best = []
    for step in steps:
        for ring_of in itertools.permutations(range(3)):
            idx = decrypt_all(glyphs, ring_of, step)
            s = score(idx)
            for k in np.argsort(s)[-5:]:
                best.append((float(s[k]), DiscSet(list(rots[k]), list(ring_of), list(step)),
                             "".join(ALPHABET[i] for i in idx[k])))
        best = sorted(best, key=lambda b: -b[0])[:200]
    return best


def substitution_ceiling(glyphs: list[Glyph], restarts: int = 30, seed: int = 1) -> tuple[float, str]:
    """Best score any simple substitution reaches (hill climbing): what a 'perfect' fixed key could give."""
    rng = np.random.default_rng(seed)
    labels = sorted({str(g) for g in glyphs})
    seq = np.array([labels.index(str(g)) for g in glyphs])
    best = (-math.inf, "")
    for _ in range(restarts):
        key = rng.permutation(24)[:len(labels)]
        cur = score(key[seq])
        for _ in range(4000):
            trial = key.copy()
            i = rng.integers(len(labels))
            j = rng.integers(24)
            k = np.where(trial == j)[0]
            if k.size:
                trial[k[0]] = trial[i]
            trial[i] = j
            s = score(trial[seq])
            if s >= cur:
                key, cur = trial, s
        if cur > best[0]:
            best = (float(cur), "".join(ALPHABET[i] for i in key[seq]))
    return best


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--no-stepping", action="store_true", help="only the 3072 fixed settings")
    args = p.parse_args(argv)

    print("Cipher as glyphs:")
    for line in ISOMORPH:
        print("  " + " ".join(GLYPHS[c] for c in line))
    print("\nWith the discs at Elgar's key (all at 0):")
    print("  " + DiscSet().decode(CIPHER))

    sample = normalise("My dear Dora, I have been thinking of the music for the next week and "
                       "whether you will come to Malvern with your father in the spring")[:87]
    print("\nCalibration (mean trigram score, higher is more English):")
    print(f"  {score(np.array([ALPHABET.index(c) for c in sample])):.2f}  real English, 87 letters")
    shuffled = np.random.default_rng(0).permutation([ALPHABET.index(c) for c in sample])
    print(f"  {score(shuffled):.2f}  the same letters shuffled")
    ceiling, text = substitution_ceiling(CIPHER)
    print(f"  {ceiling:.2f}  best any simple substitution can do with this cipher: {text}")

    print(f"\nBest of the 3072 fixed settings:")
    for s, setting, text in search(CIPHER, stepping=False)[:args.top]:
        print(f"  {s:.2f}  {text}\n        {setting.describe()}")
    if not args.no_stepping:
        print(f"\nBest of the 1,572,864 stepping settings:")
        for s, setting, text in search(CIPHER, stepping=True)[:args.top]:
            print(f"  {s:.2f}  {text}\n        {setting.describe()}")


if __name__ == "__main__":
    main()
