"""Key-free statistics: what the order of the cipher's symbols says before any key is guessed.

Every statistic here survives any substitution key, so it can be compared with shuffles of
the cipher (same glyphs, random order) without solving anything.  Each glyph is looked at
three ways: the whole glyph, its direction alone, and its arc count alone.

The striking result on the consensus reading: the direction stream has far more repeated
neighbours than its shuffles, and nearly all of it comes from one direction pattern,
SE NW SE N S SE, written three times (positions 46, 59, 70) with different arc counts each
time.  The arc stream has no order structure at all.

    python -m dorabella.structure
    python -m dorabella.structure --transcription schmeh --shuffles 20000
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict

import numpy as np

from .discs import COMPASS, SECTORS, Glyph
from .transcription import TRANSCRIPTIONS


def streams(glyphs: list[Glyph]) -> dict[str, np.ndarray]:
    sector = np.array([g.sector for g in glyphs])
    arcs = np.array([g.arcs for g in glyphs])
    return {"glyph": sector * 3 + arcs - 1, "direction": sector, "arcs": arcs}


def pair_repeats(seq) -> int:
    """How often adjacent pairs repeat: sum over distinct pairs of C(count, 2)."""
    counts = Counter(zip(seq[:-1], seq[1:]))
    return sum(c * (c - 1) // 2 for c in counts.values())


def mirror_pairs(glyphs: list[Glyph], same_arcs: bool = True) -> int:
    """Adjacent glyphs facing opposite ways (180 degrees apart)."""
    return sum((a.sector - b.sector) % SECTORS == SECTORS // 2 and (a.arcs == b.arcs or not same_arcs)
               for a, b in zip(glyphs, glyphs[1:]))


def repeats(seq, n: int, times: int = 2) -> dict[tuple, list[int]]:
    """n-grams that occur at least `times` times without overlapping, with their start positions."""
    starts = defaultdict(list)
    for i in range(len(seq) - n + 1):
        gram = tuple(seq[i:i + n])
        if not starts[gram] or i >= starts[gram][-1] + n:
            starts[gram].append(i)
    return {g: p for g, p in starts.items() if len(p) >= times}


def longest_repeat(seq, times: int = 3) -> tuple[int, dict[tuple, list[int]]]:
    n = 1
    while repeats(seq, n + 1, times):
        n += 1
    return n, repeats(seq, n, times)


def against_shuffles(glyphs: list[Glyph], stat, n: int = 5000, seed: int = 0) -> tuple[float, float, float, float]:
    """(observed, shuffle mean, shuffle sd, p = share of shuffles at least as high)."""
    rng = np.random.default_rng(seed)
    observed = stat(glyphs)
    sims = np.array([stat([glyphs[i] for i in rng.permutation(len(glyphs))]) for _ in range(n)])
    return observed, sims.mean(), sims.std(), (1 + np.sum(sims >= observed)) / (1 + n)


def report(glyphs: list[Glyph], shuffles: int = 5000) -> str:
    lines = ["Repeated adjacent pairs, against shuffles of the same glyphs:", ""]
    for name in ("glyph", "direction", "arcs"):
        obs, mean, sd, p = against_shuffles(glyphs, lambda g, k=name: pair_repeats(streams(g)[k]), shuffles)
        lines.append(f"  {name:<10} {obs:4d}   shuffles {mean:6.1f} ± {sd:4.1f}   z {(obs - mean) / sd:+5.2f}   p {p:.4f}")
    for same, label in ((True, "same arc count"), (False, "any arc count")):
        obs, mean, sd, p = against_shuffles(glyphs, lambda g, s=same: mirror_pairs(g, s), shuffles)
        lines.append(f"  mirror pairs, {label:<15} {obs:3d}   shuffles {mean:5.1f} ± {sd:3.1f}   p {p:.4f}")
    direction = streams(glyphs)["direction"]
    n, found = longest_repeat(direction, times=3)
    lines += ["", f"Longest direction pattern written three times: {n} symbols"]
    for gram, starts in found.items():
        lines.append(f"  {' '.join(COMPASS[s] for s in gram)}")
        for s in starts:
            lines.append(f"    at {s:2d}: {' '.join(str(g) for g in glyphs[s:s + n])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--transcription", choices=list(TRANSCRIPTIONS), default="consensus")
    p.add_argument("--shuffles", type=int, default=5000)
    args = p.parse_args(argv)
    print(report(TRANSCRIPTIONS[args.transcription], args.shuffles))


if __name__ == "__main__":
    main()
