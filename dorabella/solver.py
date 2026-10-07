"""Dorabella solver: attack the transcription with every cipher model below and say honestly whether anything worked.

Each model ("family") finds its best-scoring English reading of the cipher.  With 87
letters, any flexible enough model will find something English-flavoured, so every
family is also run on decoys: the same 87 symbols shuffled into a random order, which
keeps the symbol counts but destroys any message.  A family only shows a signal if the
real cipher beats every decoy by a clear margin, and it only counts as a decipherment if
the plaintext also scores like real text (READS_AS_LANGUAGE).  `selftest` checks the other
direction: each family must crack an 87-letter English message enciphered with a random key.

Families
    elgar-key      Elgar's printed alphabet, read directly
    discs          the three-disc model: every rotation and disc order (3,072 fixed keys)
    discs-step     the discs also turn a fixed amount after every letter (1,572,864 settings)
    periodic       Elgar's alphabet then a Vigenère or Beaufort key of period 1-8
    substitution   any one-to-one symbol -> letter key (simulated annealing in C, engine.py)
Each family is tried on the symbols read forwards and backwards.

    python -m dorabella.solver                 # consensus transcription, English, about 2 minutes
    python -m dorabella.solver --quick         # fewer decoys
    python -m dorabella.solver --family substitution --language latin
    python -m dorabella.solver --transcription schmeh
    python -m dorabella.solver --glyphs "W2 E3 NW2 ..."   # your own transcription
    python -m dorabella.solver selftest
"""
from __future__ import annotations

import argparse
import itertools
import time
from dataclasses import dataclass

import numpy as np

from . import engine
from .discs import ALPHABET, DISCS, Glyph
from .scoring import LANGUAGES, N, SAMPLE, calibration, model, score, to_text
from .transcription import TRANSCRIPTIONS

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
    restarts: int = 20
    iterations: int = 20000
    seed: int = 1
    language: str = "english"

    @property
    def table(self) -> np.ndarray:
        return model(self.language)


# -- families: each takes a glyph list and returns its best Candidate ---------------------

def disc_decrypt(glyphs: list[Glyph], ring_of, step=(0, 0, 0)) -> np.ndarray:
    """Letter indices for all 512 rotations at once: shape (512, len(glyphs))."""
    sectors = np.array([g.sector for g in glyphs])
    discs = np.array([ring_of.index(g.arcs - 1) for g in glyphs])
    t = np.arange(len(glyphs))
    turned = ROTATIONS[:, discs] + t * np.array(step)[discs]
    return DISC_IDX[discs, (sectors - turned) % 8]


def _best_disc(glyphs, steps, family, table) -> Candidate:
    best = (-np.inf, None)
    for step in steps:
        for order in ORDERS:
            idx = disc_decrypt(glyphs, order, step)
            s = score(idx, table)
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
    return Candidate("elgar-key", "", "Elgar's printed key", to_text(idx), float(score(idx, settings.table)))


def discs(glyphs, settings) -> Candidate:
    return _best_disc(glyphs, [(0, 0, 0)], "discs", settings.table)


def discs_step(glyphs, settings) -> Candidate:
    return _best_disc(glyphs, itertools.product(range(8), repeat=3), "discs-step", settings.table)


def periodic(glyphs, settings) -> Candidate:
    """Elgar's key gives letters; then each position is shifted back by a repeating key (Vigenère)
    or the letter is subtracted from the key (Beaufort), in the 24-letter alphabet."""
    base = disc_decrypt(glyphs, (0, 1, 2))[0]
    n, rng, best = len(base), np.random.default_rng(settings.seed), (-np.inf, None)
    for variant, period in itertools.product(("vigenere", "beaufort"), range(1, 9)):
        cols = np.arange(n) % period

        def plain(key):
            return (key[cols] - base) % N if variant == "beaufort" else (base - key[cols]) % N

        if period <= 3:   # exhaustive
            keys = np.array(list(itertools.product(range(N), repeat=period)))
            idx = (keys[:, cols] - base) % N if variant == "beaufort" else (base - keys[:, cols]) % N
            s = score(idx, settings.table)
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
                        key = trial[int(score(idx, settings.table).argmax())]
                s = float(score(plain(key), settings.table))
                if s > found[0]:
                    found = (s, key)
        if found[0] > best[0]:
            best = (found[0], (variant, found[1], plain(found[1])))
    s, (variant, key, idx) = best
    return Candidate("periodic", "", f"{variant}, key {to_text(key)} (period {len(key)})", to_text(idx), s)


def substitution(glyphs, settings) -> Candidate:
    labels = sorted({str(g) for g in glyphs})
    symbols = np.array([labels.index(str(g)) for g in glyphs])
    sol = engine.anneal(symbols, len(labels), model=settings.table, restarts=settings.restarts,
                        iterations=settings.iterations, seed=settings.seed)
    pairs = ", ".join(f"{lab}={ALPHABET[k]}" for lab, k in zip(labels, sol.key))
    return Candidate("substitution", "", pairs, sol.plain, sol.score)


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

# Real 87-letter text scores about -4.0 to -4.2 under its own model (sd about 0.15), so a
# decipherment has to reach roughly this; beating the decoys alone only shows the order isn't random.
READS_AS_LANGUAGE = -4.5


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
        """Beats every decoy clearly: the symbol order means something under this family."""
        return self.best.score > max(self.decoys) and self.z > 3

    @property
    def verdict(self) -> str:
        if not self.signal:
            return "no signal"
        if self.best.score >= READS_AS_LANGUAGE:
            return "**reads as language**"
        return "order structure, not a decipherment"


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


def report(verdicts: list[Verdict], n_symbols: int, language: str = "english") -> str:
    if language == "english":
        cal = calibration(n_symbols)
        lines = [f"Scores are mean quadgram log10-probability. For {n_symbols} letters: real English "
                 f"{cal['english']:.2f}, the same letters shuffled {cal['shuffled']:.2f}.", ""]
    else:
        lines = [f"Scores are mean quadgram log10-probability under the {language} model "
                 f"(87 letters of real {language} score about -4.0).", ""]
    lines += ["| family | best | decoys (mean / best) | margin | z | verdict |",
              "| --- | --- | --- | --- | --- | --- |"]
    for v in verdicts:
        d = np.array(v.decoys)
        lines.append(f"| {v.best.family} | {v.best.score:.2f} | {d.mean():.2f} / {d.max():.2f} | "
                     f"{v.margin:+.2f} | {v.z:+.1f} | {v.verdict} |")
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
    p.add_argument("--transcription", choices=list(TRANSCRIPTIONS), default="consensus")
    p.add_argument("--glyphs", help="space-separated glyph tokens to solve instead of a stored transcription")
    p.add_argument("--language", choices=LANGUAGES, default="english", help="plaintext language model")
    p.add_argument("--report", help="also write the markdown report to this file")
    args = p.parse_args(argv)
    settings = Settings(restarts=8, iterations=15000) if args.quick else Settings()
    settings.language = args.language

    if args.command == "selftest":
        print("Cracking an 87-letter English message enciphered with a random key:")
        selftest(settings)
        return
    glyphs = [Glyph.parse(t) for t in args.glyphs.split()] if args.glyphs else TRANSCRIPTIONS[args.transcription]
    source = "your glyphs" if args.glyphs else f"the {args.transcription} transcription"
    n_decoys = 3 if args.quick and args.decoys == 10 else args.decoys
    print(f"Solving {len(glyphs)} symbols ({source}, {args.language}) against {n_decoys} shuffled decoys:")
    text = report(solve(glyphs, args.family or list(FAMILIES), n_decoys, settings), len(glyphs), args.language)
    print("\n" + text)
    if args.report:
        with open(args.report, "w") as f:
            f.write(text + "\n")


if __name__ == "__main__":
    main()
