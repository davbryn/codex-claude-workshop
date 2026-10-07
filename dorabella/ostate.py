"""O-state experiments: does the letter O switch the discs between two states?

Notebook evidence: beneath "DO YOU GO TO LONDON TOMORROW?" Elgar put a mark
below every O and above every other letter, and wrote 23 (letters) and
"9 O's".  This module tests whether a simple O-controlled two-state disc
mechanism explains anything.  It does not assume it does.

A rule has three parts:

trigger    what counts as "an O" for this character
    letter-O   the letter is O (the plaintext when encoding, the decoded letter when decoding)
    glyph-E2   the physical glyph is E2, where Elgar's printed key puts O
    mapped-O   the glyph sits where O currently is on the discs in state A
               (equals E2 only while the 2-arc disc is unturned)

behaviour  how the trigger chooses between state A and state B
    classify   this character uses B if it is an O, else A (the notebook's O / not-O marks)
    toggle     every O flips A <-> B for the FOLLOWING characters (the O itself uses the old state)
    set        an O puts the following characters in B, a non-O puts them back in A
    advance    every O applies the transform to the discs for good (e.g. an O turns a disc one notch)

transform  what state B is, relative to state A
    reverse-arcs   arc counts 1,2,3 read discs 3,2,1 (the 123 / 321 hypothesis)
    mirror         letters run anticlockwise (the mirror image of state A)
    swap-12 / swap-23 / swap-13   two discs change places
    rotate:<disc>:<±n>   turn disc 1, 2, 3, the used disc, or all discs by n sectors

The existing constant stepping still applies after every character.  With
behaviour "off" the engine reproduces discs.DiscSet exactly.

    python -m dorabella.ostate notebook
    python -m dorabella.ostate trace --behaviour toggle --transform reverse-arcs "do you go to london tomorrow"
    python -m dorabella.ostate trace --decode --trigger glyph-E2 --behaviour classify --transform mirror W2 E3 NW2
    python -m dorabella.ostate search --top 15
"""
from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass, field, replace

from .discs import ALPHABET, COMPASS, DISCS, Glyph, normalise

LONDON_FULL = "DO YOU GO TO LONDON TOMORROW"
# Elgar's own encipherment of "do you go to london" (bottom left of the notebook page), read from the
# photograph.  Arc counts are clear; the exact tilt of a few symbols (D, Y, T, L) is read at low resolution.
LONDON_PLAIN = "DOYOUGOTOLONDON"
LONDON_CIPHER = "NW1 E2 SW2 E2 S2 N1 E2 S1 E2 NE2 E2 E1 NW1 E2 E1"
UNRESOLVED_NOTES = ['"1 2 3 4 4", with two distinct handwritten forms of 4 '
                    '(written below the London example; not used in any search)']

TRIGGERS = ["letter-O", "glyph-E2", "mapped-O"]
BEHAVIOURS = ["off", "classify", "toggle", "set", "advance"]
SEARCH_TRANSFORMS = ["reverse-arcs", "mirror", "swap-13", "rotate:all:+1", "rotate:all:-1",
                     "rotate:used:+1", "rotate:used:-1"]
E2 = Glyph(COMPASS.index("E"), 2)


# -- the notebook marks ---------------------------------------------------------

def o_marks(text: str) -> list[tuple[str, str]]:
    """Elgar's marks: every O below the line (↓), every other letter above (↑)."""
    return [(c, "↓" if c == "O" else "↑") for c in normalise(text)]


def alternating_marks(text: str) -> list[str]:
    """What simple alternating ticks would look like, for comparison."""
    return ["↑" if i % 2 == 0 else "↓" for i, _ in enumerate(normalise(text))]


# -- disc states -------------------------------------------------------------------

@dataclass(frozen=True)
class State:
    rotation: tuple[int, int, int] = (0, 0, 0)   # sectors each disc is turned clockwise
    ring_of: tuple[int, int, int] = (0, 1, 2)    # ring (0..2) each disc sits on: ring r writes r+1 arcs
    mirror: bool = False                          # letters run anticlockwise

    def disc_for_arcs(self, arcs: int) -> int:
        return self.ring_of.index(arcs - 1)

    def arc_mapping(self) -> str:
        """e.g. '1→3, 2→2, 3→1': arc count -> disc number (disc 1 = A D G..., 2 = B E H..., 3 = C F I...)."""
        return ", ".join(f"{a}→{self.disc_for_arcs(a) + 1}" for a in (1, 2, 3))

    def encode(self, letter: str) -> Glyph:
        i = ALPHABET.index(letter)
        disc, slot = i % 3, i // 3
        pos = slot + self.rotation[disc]
        return Glyph((-pos if self.mirror else pos) % 8, self.ring_of[disc] + 1)

    def decode(self, glyph: Glyph) -> str:
        disc = self.disc_for_arcs(glyph.arcs)
        pos = -glyph.sector if self.mirror else glyph.sector
        return DISCS[disc][(pos - self.rotation[disc]) % 8]

    def turned(self, discs, by: int) -> "State":
        return replace(self, rotation=tuple((r + by) % 8 if d in discs else r
                                            for d, r in enumerate(self.rotation)))


def transform(state: State, name: str, used_disc: int) -> State:
    """State B for a given state A.  ``used_disc`` is the disc the current character is on."""
    if name == "none":
        return state
    if name == "reverse-arcs":
        return replace(state, ring_of=tuple(2 - r for r in state.ring_of))
    if name == "mirror":
        return replace(state, mirror=not state.mirror)
    if name.startswith("swap-"):
        i, j = int(name[5]) - 1, int(name[6]) - 1
        ring = list(state.ring_of)
        ring[i], ring[j] = ring[j], ring[i]
        return replace(state, ring_of=tuple(ring))
    if name.startswith("rotate:"):
        _, target, by = name.split(":")
        discs = {"all": (0, 1, 2), "used": (used_disc,)}.get(target) or (int(target) - 1,)
        return state.turned(discs, int(by))
    raise ValueError(f"unknown transform {name!r}")


def describe_transform(name: str) -> str:
    if name.startswith("rotate:"):
        _, target, by = name.split(":")
        what = {"all": "all discs", "used": "the used disc"}.get(target, f"disc {target}")
        return f"turn {what} {by}"
    return {"none": "no change", "reverse-arcs": "arc order 123→321", "mirror": "mirrored (anticlockwise)",
            "swap-12": "swap discs 1↔2", "swap-23": "swap discs 2↔3", "swap-13": "swap discs 1↔3"}[name]


# -- rules and the engine ----------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    trigger: str = "letter-O"
    behaviour: str = "off"
    transform: str = "reverse-arcs"

    def __post_init__(self):
        if self.trigger not in TRIGGERS or self.behaviour not in BEHAVIOURS:
            raise ValueError(f"bad rule {self}")
        transform(State(), self.transform, 0)   # validates the name

    def describe(self) -> str:
        if self.behaviour == "off":
            return "no O rule"
        return f"trigger {self.trigger}, {self.behaviour}, B = {describe_transform(self.transform)}"


PRESETS = {
    "1": ("A = normal order 1,2,3; B = reversed 3,2,1", "reverse-arcs"),
    "2": ("A = clockwise; B = mirrored / anticlockwise", "mirror"),
    "3": ("A = normal offsets; B = offsets +1,+1,+1", "rotate:all:+1"),
    "4": ("A = normal; B = swap inner and outer discs", "swap-13"),
}


@dataclass
class Step:
    index: int
    input: str           # the plaintext letter or the glyph token that went in
    glyph: Glyph | None
    letter: str          # plaintext letter ('?' when no letter fits)
    trigger: bool
    state_before: str    # 'A' or 'B': the state this character was read in
    mapping: str         # active arc -> disc mapping
    offsets_before: tuple[int, int, int]
    mirror: bool
    disc: int            # effective disc used (1..3)
    state_after: str     # the state the next character starts in
    offsets_after: tuple[int, int, int]
    note: str = ""       # 'ambiguous' / 'no letter fits' / 'discs turned'

    @property
    def mark(self) -> str:
        return "↓" if self.letter == "O" else "↑"

    def row(self) -> str:
        g = str(self.glyph) if self.glyph else "--"
        return (f"{self.index:>3}  {self.input:>3}  {g:<4} {COMPASS[self.glyph.sector] if self.glyph else '':<3}"
                f"{self.glyph.arcs if self.glyph else '':<2} {'O!' if self.trigger else '  '}  {self.state_before}"
                f"  {self.mapping}  {'·'.join(map(str, self.offsets_before))}{'m' if self.mirror else ' '}"
                f"  {self.disc}  {self.letter if self.input == g else g:>4} {self.mark}"
                f"  {self.state_before}→{self.state_after}  {'·'.join(map(str, self.offsets_after))}  {self.note}")


TRACE_HEADER = ("  #   in  sym  dir arc trig st  arc→disc            offsets   disc  out    "
                "transition  offsets after")


def _is_o(rule: Rule, letter: str, glyph: Glyph, base: State) -> bool:
    if rule.trigger == "letter-O":
        return letter == "O"
    if rule.trigger == "glyph-E2":
        return glyph == E2
    return glyph == base.encode("O")   # mapped-O: where O is in state A right now


def run(rule: Rule, start: State, items, decode: bool, step=(0, 0, 0)) -> list[Step]:
    """Encode letters (decode=False) or decode glyphs (decode=True), recording every step."""
    base, in_b, trace = start, False, []
    for i, item in enumerate(items):
        if decode:
            glyph, letter = item, None
            used = base.disc_for_arcs(glyph.arcs)
        else:
            glyph, letter = None, item
            used = ALPHABET.index(item) % 3
        alt = transform(base, rule.transform, used)
        note = ""
        if rule.behaviour == "classify":
            # The character is read in B exactly when it is an O; keep the readings that agree with that.
            options = []
            for name, st in (("A", base), ("B", alt)):
                g = glyph if decode else st.encode(letter)
                l = st.decode(g) if decode else letter
                if _is_o(rule, l, g, base) == (name == "B"):
                    options.append((name, st, g, l))
            if not options:
                note = "no letter fits"
                options = [("A", base, glyph or base.encode(letter), "?" if decode else letter)]
            elif len(options) == 2:
                note = "ambiguous"
            name, active, glyph, letter = options[0]
            current = name
        else:
            current = "B" if in_b else "A"
            active = alt if in_b else base
            glyph = glyph or active.encode(letter)
            letter = letter or active.decode(glyph)
        fired = _is_o(rule, letter, glyph, base) if rule.behaviour != "off" else False
        if rule.behaviour == "toggle" and fired:
            in_b = not in_b
        elif rule.behaviour == "set":
            in_b = fired
        elif rule.behaviour == "advance" and fired:
            base, note = transform(base, rule.transform, used), "discs changed"
        base = replace(base, rotation=tuple((r + s) % 8 for r, s in zip(base.rotation, step)))
        trace.append(Step(i, str(item) if decode else item, glyph, letter, fired, current,
                          active.arc_mapping(), active.rotation, active.mirror,
                          active.disc_for_arcs(glyph.arcs) + 1, "B" if in_b else "A", base.rotation, note))
    return trace


def encode(rule: Rule, start: State, text: str, step=(0, 0, 0)) -> list[Glyph]:
    return [s.glyph for s in run(rule, start, normalise(text), False, step)]


def decode(rule: Rule, start: State, glyphs, step=(0, 0, 0)) -> str:
    return "".join(s.letter for s in run(rule, start, glyphs, True, step))


def london_check(rule: Rule, start: State = State(), step=(0, 0, 0)) -> list[str]:
    """Where the rule disagrees with Elgar's own London encipherment (empty list = reproduces it)."""
    expected = [Glyph.parse(t) for t in LONDON_CIPHER.split()]
    problems = []
    for st, want in zip(run(rule, start, LONDON_PLAIN, False, step), expected):
        if st.note == "no letter fits":
            problems.append(f"{st.index}:{st.letter} cannot be enciphered")
        elif st.glyph != want:
            problems.append(f"{st.index}:{st.letter} gives {st.glyph}, Elgar wrote {want}")
    return problems


# -- search --------------------------------------------------------------------------

@dataclass
class Result:
    score: float
    plaintext: str
    rule: Rule
    rotation: tuple[int, int, int]
    london_ok: bool
    same_as: list[str] = field(default_factory=list)


def search(glyphs, transforms=SEARCH_TRANSFORMS, behaviours=("classify", "toggle", "set", "advance"),
           triggers=TRIGGERS, top: int = 20) -> list[Result]:
    """Every trigger x behaviour x transform x starting offsets (normal disc order), ranked by English score."""
    import numpy as np
    from .analyse import score
    seen: dict[str, Result] = {}
    for trig, beh, tr in itertools.product(triggers, behaviours, transforms):
        rule = Rule(trig, beh, tr)
        for rot in itertools.product(range(8), repeat=3):
            text = decode(rule, State(rot), glyphs)
            key = f"{rule.describe()}, offsets {'·'.join(map(str, rot))}"
            if text in seen:
                seen[text].same_as.append(key)
                continue
            s = float(score(np.array([[ALPHABET.index(c) if c in ALPHABET else 0 for c in text]]))[0])
            seen[text] = Result(s, text, rule, rot, not london_check(rule, State(rot)))
    return sorted(seen.values(), key=lambda r: -r.score)[:top]


# -- command line ------------------------------------------------------------------------

def _print_notebook() -> None:
    marks = o_marks(LONDON_FULL)
    letters = "".join(c for c, _ in marks)
    print(f"{letters}\nlength = {len(letters)}\nO count = {letters.count('O')}\n")
    print(" ".join(c for c, _ in marks))
    print(" ".join(m for _, m in marks) + "   Elgar's marks: O below, every other letter above")
    print(" ".join(alternating_marks(LONDON_FULL)) + "   simple alternation, for comparison")
    breaks = [f"{a}{b}" for (a, m1), (b, m2) in zip(marks, marks[1:]) if m1 == m2]
    print(f"\nWhere the marks don't alternate: {', '.join(breaks)}")
    print("\nUnresolved notebook evidence:")
    for note in UNRESOLVED_NOTES:
        print(f"  {note}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("notebook", help="check the O / not-O marks under the London example")
    t = sub.add_parser("trace", help="encode or decode with an O rule, showing every step")
    t.add_argument("items", nargs="+", help="plaintext, or glyph tokens with --decode")
    t.add_argument("--decode", action="store_true")
    t.add_argument("--trigger", choices=TRIGGERS, default="letter-O")
    t.add_argument("--behaviour", choices=BEHAVIOURS, default="toggle")
    t.add_argument("--transform", default="reverse-arcs")
    t.add_argument("--rotation", type=int, nargs=3, default=[0, 0, 0])
    t.add_argument("--step", type=int, nargs=3, default=[0, 0, 0])
    sub.add_parser("london", help="which O rules reproduce Elgar's own London encipherment?")
    s = sub.add_parser("search", help="search O rules on the Dorabella cipher")
    s.add_argument("--top", type=int, default=15)
    args = p.parse_args(argv)

    if args.cmd == "notebook":
        _print_notebook()
    elif args.cmd == "trace":
        rule = Rule(args.trigger, args.behaviour, args.transform)
        items = [Glyph.parse(t) for t in args.items] if args.decode else normalise(" ".join(args.items))
        trace = run(rule, State(tuple(args.rotation)), items, args.decode, tuple(args.step))
        print(rule.describe())
        print(TRACE_HEADER)
        for st in trace:
            print(st.row())
        print("\n" + ("".join(st.letter for st in trace) if args.decode else " ".join(str(st.glyph) for st in trace)))
    elif args.cmd == "london":
        from .analyse import CIPHER
        plain = decode(Rule(), State(), CIPHER)
        print(f"Elgar's London line: {LONDON_CIPHER}\n")
        for trig, beh, tr in itertools.product(TRIGGERS, BEHAVIOURS[1:], SEARCH_TRANSFORMS):
            rule = Rule(trig, beh, tr)
            problems = london_check(rule)
            effect = "no change to Dorabella" if decode(rule, State(), CIPHER) == plain else "changes Dorabella"
            print(f"{'reproduced  ' if not problems else 'contradicted'}  {rule.describe():58} "
                  + (effect if not problems else problems[0]))
    elif args.cmd == "search":
        from .analyse import CIPHER
        for r in search(CIPHER, top=args.top):
            print(f"{r.score:.2f}  {r.plaintext}\n      {r.rule.describe()}, offsets {'·'.join(map(str, r.rotation))}"
                  + f", London {'reproduced' if r.london_ok else 'contradicted'}"
                  + (f"  (+{len(r.same_as)} equivalent)" if r.same_as else ""))


if __name__ == "__main__":
    main()
