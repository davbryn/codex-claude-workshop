"""Dorabella solver: attack the transcription with every cipher model below and say honestly whether anything worked.

Each model ("family") finds its best-scoring English reading of the cipher.  With 87
letters, any flexible enough model will find something English-flavoured, so every
family is also run on decoys: the same 87 symbols shuffled into a random order, which
keeps the symbol counts but destroys any message.  A family only shows a signal if the
real cipher beats every decoy by a clear margin.  `selftest` checks the other direction:
each family must crack an 87-letter English message enciphered with a random key.

Families
    elgar-key      Elgar's printed alphabet, read directly
    discs          the three-disc model: every rotation and disc order (3,072 fixed keys)
    discs-step     the discs also turn a fixed amount after every letter (1,572,864 settings)
    periodic       Elgar's alphabet then a Vigenère or Beaufort key of period 1-8
    substitution   any one-to-one symbol -> letter key (simulated annealing)
Each family is tried on the symbols read forwards and backwards.

    python -m dorabella.solver                 # full run, about 4 minutes
    python -m dorabella.solver --quick         # fewer decoys and annealing restarts
    python -m dorabella.solver --family periodic --family substitution
    python -m dorabella.solver --glyphs "W2 E3 NW2 ..."   # your own transcription
    python -m dorabella.solver selftest
"""
from __future__ import annotations

import argparse
import itertools
import time
from dataclasses import dataclass

import numpy as np

from .discs import ALPHABET, DISCS, Glyph
from .scoring import N, QUAD, calibration, quad_index, score, to_text, SAMPLE
from .transcription import CIPHER

DISC_IDX = np.array([[ALPHABET.index(c) for c in letters] for letters in DISCS])
ROTATIONS = np.array(list(itertools.product(range(8), repeat=3)))
ORDERS = list(itertools.permutations(range(3)))


@dataclass
class Candidate:
    family: str
    reading: str
    key: str
    plaintext: str
    score: float


@dataclass
class Settings:
    restarts: int = 10
    iterations: int = 20000
    seed: int = 1


# -- families: each takes a glyph list and returns its best Candidate ---------------------

def disc_decrypt(glyphs: list[Glyph], ring_of, step=(0, 0, 0)) -> np.ndarray:
    """Letter indices for all 512 rotations at once: shape (512, len(glyphs))."""
    sectors = np.array([g.sector for g in glyphs])
    discs = np.array([ring_of.index(g.arcs - 1) for g in glyphs])
    t = np.arange(len(glyphs))
    turned = ROTATIONS[:, discs] + t * np.array(step)[discs]
    return DISC_IDX[discs, (sectors - turned) % 8]


def _best_disc(glyphs, steps, family) -> Candidate:
    best = (-np.inf, None)
    for step in steps:
        for order in ORDERS:
            idx = disc_decrypt(glyphs, order, step)
            s = score(idx)
            k = int(s.argmax())
            if s[k] > best[0]:
                best = (float(s[k]), (tuple(ROTATIONS[k]), order, step, idx[k]))
    s, (rot, order, step, idx) = best
    key = f"rotation {'·'.join(map(str, rot))}, disc rings {'·'.join(str(r + 1) for r in order)}"
    if any(step):
        key += f", step {'·'.join(map(str, step))} per letter"
    return Candidate(family, "", key, to_text(idx), s)


def elgar_key(glyphs, settings) -> Candidate:
    idx = disc_decrypt(glyphs, (0, 1, 2))[0]
    return Candidate("elgar-key", "", "Elgar's printed key", to_text(idx), float(score(idx)))


def discs(glyphs, settings) -> Candidate:
    return _best_disc(glyphs, [(0, 0, 0)], "discs")


def discs_step(glyphs, settings) -> Candidate:
    return _best_disc(glyphs, itertools.product(range(8), repeat=3), "discs-step")


def periodic(glyphs, settings) -> Candidate:
    """Elgar's key gives letters; then each position is shifted back by a repeating key (Vigenère)
    or the letter is subtracted from the key (Beaufort), in the 24-letter alphabet."""
    base = disc_decrypt(glyphs, (0, 1, 2))[0]
    n, rng, best = len(base), np.random.default_rng(settings.seed), (-np.inf, None)
    for variant, period in itertools.product(("vigenere", "beaufort"), range(1, 9)):
        cols = np.arange(n) % period
        sign = 1 if variant == "beaufort" else -1

        def plain(key):
            return (key[cols] - base) % N if variant == "beaufort" else (base - key[cols]) % N

        if period <= 3:   # exhaustive
            keys = np.array(list(itertools.product(range(N), repeat=period)))
            idx = (keys[:, cols] - base) % N if variant == "beaufort" else (base - keys[:, cols]) % N
            s = score(idx)
            k = int(s.argmax())
            found = (float(s[k]), keys[k])
        else:   # coordinate ascent with restarts
            found = (-np.inf, None)
            for _ in range(settings.restarts):
                key = rng.integers(0, N, period)
                for _ in range(6):
                    for c in range(period):
                        trial = np.repeat(key[None], N, 0)
                        trial[:, c] = np.arange(N)
                        idx = (trial[:, cols] - base) % N if variant == "beaufort" else (base - trial[:, cols]) % N
                        key = trial[int(score(idx).argmax())]
                s = float(score(plain(key)))
                if s > found[0]:
                    found = (s, key)
        if found[0] > best[0]:
            best = (found[0], (variant, found[1], plain(found[1])))
    s, (variant, key, idx) = best
    return Candidate("periodic", "", f"{variant}, key {to_text(key)} (period {len(key)})", to_text(idx), s)


def anneal(symbols: np.ndarray, n_symbols: int, settings: Settings, rng) -> tuple[float, np.ndarray]:
    """Simulated annealing over one-to-one symbol -> letter keys; returns (mean score, key)."""
    best = (-np.inf, None)
    m = len(symbols) - 3
    for _ in range(settings.restarts):
        key = rng.permutation(N)[:n_symbols]
        cur = QUAD[quad_index(key[symbols])].sum()
        run_best = (cur, key.copy())
        temps = np.geomspace(20.0, 0.5, settings.iterations)
        moves_i = rng.integers(0, n_symbols, settings.iterations)
        moves_j = rng.integers(0, N, settings.iterations)
        coins = rng.random(settings.iterations)
        for it in range(settings.iterations):
            i, j = moves_i[it], moves_j[it]
            old = key[i]
            if old == j:
                continue
            other = np.flatnonzero(key == j)
            key[i] = j
            if other.size:
                key[other[0]] = old
            new = QUAD[quad_index(key[symbols])].sum()
            if new >= cur or coins[it] < np.exp((new - cur) / temps[it]):
                cur = new
            else:
                key[i] = old
                if other.size:
                    key[other[0]] = j
            if cur > run_best[0]:
                run_best = (cur, key.copy())
        if run_best[0] / m > best[0]:
            best = (float(run_best[0] / m), run_best[1])
    return best


def substitution(glyphs, settings) -> Candidate:
    labels = sorted({str(g) for g in glyphs})
    symbols = np.array([labels.index(str(g)) for g in glyphs])
    s, key = anneal(symbols, len(labels), settings, np.random.default_rng(settings.seed))
    pairs = ", ".join(f"{lab}={ALPHABET[k]}" for lab, k in zip(labels, key))
    return Candidate("substitution", "", pairs, to_text(key[symbols]), s)


FAMILIES = {"elgar-key": elgar_key, "discs": discs, "discs-step": discs_step,
            "periodic": periodic, "substitution": substitution}
READINGS = {"forward": lambda g: list(g), "backward": lambda g: list(g)[::-1]}


def best_reading(family: str, glyphs, settings) -> Candidate:
    best = None
    for reading, read in READINGS.items():
        c = FAMILIES[family](read(glyphs), settings)
        c.reading = reading
        if best is None or c.score > best.score:
            best = c
    return best


# -- the verdict ----------------------------------------------------------------------------

@dataclass
class Verdict:
    best: Candidate
    decoys: list[float]

    @property
    def margin(self) -> float:
        return self.best.score - max(self.decoys)

    @property
    def z(self) -> float:
        d = np.array(self.decoys)
        return float((self.best.score - d.mean()) / (d.std() or 1e-9))

    @property
    def signal(self) -> bool:
        return self.best.score > max(self.decoys) and self.z > 3


def solve(glyphs, families, n_decoys: int, settings: Settings, log=print) -> list[Verdict]:
    rng = np.random.default_rng(settings.seed + 100)
    decoys = [[glyphs[i] for i in rng.permutation(len(glyphs))] for _ in range(n_decoys)]
    verdicts = []
    for family in families:
        t = time.time()
        best = best_reading(family, glyphs, settings)
        control = [best_reading(family, d, settings).score for d in decoys]
        verdicts.append(Verdict(best, control))
        log(f"  {family:<13} {best.score:6.2f}  decoys best {max(control):6.2f}  ({time.time() - t:.0f}s)")
    return verdicts


def report(verdicts: list[Verdict], n_symbols: int) -> str:
    cal = calibration(n_symbols)
    lines = [f"Scores are mean quadgram log10-probability. For {n_symbols} letters: real English "
             f"{cal['english']:.2f}, the same letters shuffled {cal['shuffled']:.2f}.", "",
             "| family | best | decoys (mean / best) | margin | z | verdict |",
             "| --- | --- | --- | --- | --- | --- |"]
    for v in verdicts:
        d = np.array(v.decoys)
        lines.append(f"| {v.best.family} | {v.best.score:.2f} | {d.mean():.2f} / {d.max():.2f} | "
                     f"{v.margin:+.2f} | {v.z:+.1f} | {'**signal**' if v.signal else 'no signal'} |")
    lines.append("")
    for v in verdicts:
        lines += [f"**{v.best.family}** ({v.best.reading}), {v.best.score:.2f}: `{v.best.plaintext}`",
                  f"key: {v.best.key}", ""]
    return "\n".join(lines)


# -- self-test: can each family crack a real 87-letter message? ---------------------------------

def selftest(settings: Settings, log=print) -> dict[str, float]:
    from .discs import DiscSet
    rng = np.random.default_rng(7)
    text = SAMPLE[:87]
    letters = np.array([ALPHABET.index(c) for c in text])
    results = {}

    disc_key = DiscSet([3, 6, 1], [1, 2, 0], [0, 5, 2])
    cases = {"discs-step": disc_key.encode(text)}
    period_key = np.array([ALPHABET.index(c) for c in "DORA"])
    shifted = to_text((letters + period_key[np.arange(87) % 4]) % N)
    cases["periodic"] = DiscSet().encode(shifted)
    scramble = rng.permutation(N)
    all_glyphs = [Glyph(s, a) for a in (1, 2, 3) for s in range(8)]
    cases["substitution"] = [all_glyphs[scramble[i]] for i in letters]

    for family, glyphs in cases.items():
        c = FAMILIES[family](glyphs, settings)
        accuracy = float(np.mean([a == b for a, b in zip(c.plaintext, text)]))
        results[family] = accuracy
        log(f"  {family:<13} {accuracy:6.0%} of letters recovered, score {c.score:.2f}  {c.plaintext[:40]}...")
    return results


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("command", nargs="?", default="solve", choices=["solve", "selftest"])
    p.add_argument("--family", action="append", choices=list(FAMILIES), help="run only these (repeatable)")
    p.add_argument("--decoys", type=int, default=10)
    p.add_argument("--quick", action="store_true", help="3 decoys, fewer annealing restarts")
    p.add_argument("--glyphs", help="space-separated glyph tokens to solve instead of the stored transcription")
    p.add_argument("--report", help="also write the markdown report to this file")
    args = p.parse_args(argv)
    settings = Settings(restarts=6, iterations=12000) if args.quick else Settings()

    if args.command == "selftest":
        print("Cracking an 87-letter English message enciphered with a random key:")
        selftest(settings)
        return
    glyphs = [Glyph.parse(t) for t in args.glyphs.split()] if args.glyphs else CIPHER
    n_decoys = 3 if args.quick and args.decoys == 10 else args.decoys
    print(f"Solving {len(glyphs)} symbols against {n_decoys} shuffled decoys:")
    text = report(solve(glyphs, args.family or list(FAMILIES), n_decoys, settings), len(glyphs))
    print("\n" + text)
    if args.report:
        with open(args.report, "w") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
