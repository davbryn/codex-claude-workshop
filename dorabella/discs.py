"""Three nested rotating discs for Elgar's Dorabella cipher alphabet.

Elgar's key has 24 symbols: one, two or three small arcs ("c", "ε", "ξ"),
each drawn in one of eight orientations 45 degrees apart.  Read as a disc,
a single "c" is simply the left-hand arc of a circle: the symbol's
orientation names a sector of the disc, and the number of arcs names which
of three nested discs (rings) the letter sits on.

    ring 1 (inner, one arc)    A D G K N Q T X
    ring 2 (middle, two arcs)  B E H L O R U Y
    ring 3 (outer, three arcs) C F I M P S W Z

Sectors are numbered 0..7 clockwise from the left (west), so with no
rotation A is a "c" on the left, D is one step clockwise, and so on: that
setting reproduces Elgar's printed key exactly.  Rotating a disc by r
sectors moves every letter on it r sectors clockwise; the discs can also be
swapped between rings.  J is written as I and V as U, as in the key.

A glyph is written as compass point + arc count, e.g. ``W1`` is a single
arc on the west side (a "c", opening east).
"""
from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass, field

ALPHABET = "ABCDEFGHIKLMNOPQRSTUWXYZ"   # 24 letters, J=I, V=U
SECTORS = 8
COMPASS = ["W", "NW", "N", "NE", "E", "SE", "S", "SW"]   # clockwise from the left

# The three letter discs, as Elgar's key lays them out (disc d = arc count d+1).
DISCS = [ALPHABET[d::3] for d in range(3)]


def normalise(text: str) -> str:
    """Upper-case letters only, with J->I and V->U."""
    return "".join(c for c in text.upper().replace("J", "I").replace("V", "U") if c in ALPHABET)


@dataclass(frozen=True)
class Glyph:
    sector: int   # 0..7 clockwise from west: where the arc sits on the disc
    arcs: int     # 1..3: which ring

    def __str__(self) -> str:
        return f"{COMPASS[self.sector]}{self.arcs}"

    @classmethod
    def parse(cls, token: str) -> "Glyph":
        token = token.strip().upper()
        return cls(COMPASS.index(token[:-1]), int(token[-1]))

    @property
    def opens_degrees(self) -> int:
        """Direction the arc opens towards, in degrees anticlockwise from east (a "c" opens at 0)."""
        return (-self.sector * 45) % 360


@dataclass
class DiscSet:
    """rotation[d]: sectors disc d is turned clockwise.  ring_of[d]: ring (0..2) disc d sits on.
    step[d]: extra sectors disc d turns after every letter (0 = fixed key)."""
    rotation: list[int] = field(default_factory=lambda: [0, 0, 0])
    ring_of: list[int] = field(default_factory=lambda: [0, 1, 2])
    step: list[int] = field(default_factory=lambda: [0, 0, 0])

    def __post_init__(self) -> None:
        if sorted(self.ring_of) != [0, 1, 2]:
            raise ValueError("ring_of must be a permutation of 0, 1, 2")
        self.rotation = [r % SECTORS for r in self.rotation]

    def copy(self) -> "DiscSet":
        return DiscSet(list(self.rotation), list(self.ring_of), list(self.step))

    def rotate(self, disc: int, by: int = 1) -> None:
        self.rotation[disc] = (self.rotation[disc] + by) % SECTORS

    def advance(self) -> None:
        for d in range(3):
            self.rotate(d, self.step[d])

    # -- single letters at the current setting ---------------------------
    def glyph_for(self, letter: str) -> Glyph:
        i = ALPHABET.index(normalise(letter))
        disc, slot = i % 3, i // 3
        return Glyph((slot + self.rotation[disc]) % SECTORS, self.ring_of[disc] + 1)

    def letter_for(self, glyph: Glyph) -> str:
        disc = self.ring_of.index(glyph.arcs - 1)
        slot = (glyph.sector - self.rotation[disc]) % SECTORS
        return DISCS[disc][slot]

    def layout(self) -> list[list[str]]:
        """layout()[ring][sector] -> letter now showing there."""
        rings = [[""] * SECTORS for _ in range(3)]
        for d, letters in enumerate(DISCS):
            for slot, letter in enumerate(letters):
                rings[self.ring_of[d]][(slot + self.rotation[d]) % SECTORS] = letter
        return rings

    # -- messages ----------------------------------------------------------
    def encode(self, text: str) -> list[Glyph]:
        state, out = self.copy(), []
        for letter in normalise(text):
            out.append(state.glyph_for(letter))
            state.advance()
        return out

    def decode(self, glyphs: list[Glyph]) -> str:
        state, out = self.copy(), []
        for g in glyphs:
            out.append(state.letter_for(g))
            state.advance()
        return "".join(out)

    def describe(self) -> str:
        parts = [f"disc {'ABC'[d]}… on ring {self.ring_of[d] + 1} turned {self.rotation[d]}×45°"
                 for d in range(3)]
        if any(self.step):
            parts.append(f"stepping {self.step} per letter")
        return "; ".join(parts)


def all_settings(stepping: bool = False):
    """Every fixed setting (8^3 rotations x 6 ring orders = 3072), optionally with all step patterns."""
    steps = itertools.product(range(SECTORS), repeat=3) if stepping else [(0, 0, 0)]
    for step in steps:
        for order in itertools.permutations(range(3)):
            for rot in itertools.product(range(SECTORS), repeat=3):
                yield DiscSet(list(rot), list(order), list(step))


def find_settings(glyphs: list[Glyph], crib: str, stepping: bool = False) -> list[DiscSet]:
    """Settings under which ``glyphs`` decode to text starting with ``crib``."""
    crib = normalise(crib)
    head = glyphs[:len(crib)]
    return [s for s in all_settings(stepping) if s.decode(head) == crib]


def render_rings(discs: DiscSet) -> str:
    rows = ["sector  " + " ".join(f"{c:>3}" for c in COMPASS)]
    for ring, letters in enumerate(discs.layout()):
        rows.append(f"ring {ring + 1}  " + " ".join(f"{c:>3}" for c in letters))
    return "\n".join(rows)


def _settings_from(args) -> DiscSet:
    return DiscSet(args.rotation, [r - 1 for r in args.rings], args.step)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--rotation", type=int, nargs=3, default=[0, 0, 0], metavar=("R1", "R2", "R3"),
                   help="clockwise sectors to turn the A-, B- and C- discs")
    p.add_argument("--rings", type=int, nargs=3, default=[1, 2, 3], metavar=("A", "B", "C"),
                   help="which ring (1-3) each disc sits on")
    p.add_argument("--step", type=int, nargs=3, default=[0, 0, 0], metavar=("S1", "S2", "S3"),
                   help="sectors each disc turns after every letter")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="print which letter sits in each sector")
    e = sub.add_parser("encode"); e.add_argument("text")
    d = sub.add_parser("decode"); d.add_argument("glyphs", nargs="+", help="e.g. NW1 E2 SW2")
    s = sub.add_parser("search", help="find settings that decode glyphs to a crib")
    s.add_argument("crib"); s.add_argument("glyphs", nargs="+")
    s.add_argument("--stepping", action="store_true", help="also try every stepping pattern")
    args = p.parse_args(argv)

    discs = _settings_from(args)
    if args.cmd == "show":
        print(discs.describe()); print(render_rings(discs))
    elif args.cmd == "encode":
        text = normalise(args.text)
        glyphs = discs.encode(text)
        print(discs.describe())
        print(" ".join(f"{c}={g}" for c, g in zip(text, glyphs)))
        print(" ".join(map(str, glyphs)))
    elif args.cmd == "decode":
        print(discs.decode([Glyph.parse(t) for t in args.glyphs]))
    elif args.cmd == "search":
        hits = find_settings([Glyph.parse(t) for t in args.glyphs], args.crib, args.stepping)
        print(f"{len(hits)} setting(s)")
        for h in hits[:50]:
            print(" ", h.describe())


if __name__ == "__main__":
    main()
