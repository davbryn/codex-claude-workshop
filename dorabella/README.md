# Dorabella cipher discs

A test bench for the idea that Elgar's Dorabella alphabet is a set of three
nested, rotating discs.

Each Dorabella symbol is one, two or three small arcs in one of eight
orientations. Read as a disc, a single "c" is the left-hand arc of a circle.
So the orientation says **which sector** of the disc the letter is in, and the
arc count says **which of three nested discs** it is on:

| sector | W | NW | N | NE | E | SE | S | SW |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ring 1 (one arc) | A | D | G | K | N | Q | T | X |
| ring 2 (two arcs) | B | E | H | L | O | R | U | Y |
| ring 3 (three arcs) | C | F | I | M | P | S | W | Z |

With no rotation this is Elgar's printed key (J is written as I, V as U).
Turning a disc moves every letter on it round by 45° steps. Discs can also be
swapped between rings, and can optionally step after every letter
(Alberti style). That gives 8³ × 6 = 3072 fixed settings.

Glyphs are written as text tokens: the side the arcs sit on plus the arc
count. `W1` is a "c", `E2` is a "3", `S2` is an "ω", `N1` is an "n".

## Interactive discs

Open `dorabella/discs.html` in a browser. Turn the discs, swap rings, type a
message and step through it letter by letter, decode glyph tokens, and search
all settings for a crib.

## Command line

```bash
python -m dorabella.discs show
python -m dorabella.discs encode "do you go to london"
python -m dorabella.discs --rotation 2 5 1 encode "do you go to london"
python -m dorabella.discs decode NW1 E2 SW2 E2 S2 N1 E2
python -m dorabella.discs search "do you go" NE1 NW2 E2 NW2 NE2 E1 NW2
python -m dorabella.discs --rings 2 1 3 --step 1 0 0 encode "london"
```

`--rotation` turns the A…, B… and C… discs clockwise by that many sectors,
`--rings` says which ring each disc sits on, and `--step` turns each disc
after every letter.

## Trying the discs on the Dorabella cipher

```bash
python -m dorabella.analyse        # needs numpy
```

`analyse.py` holds a transcription of the 1897 cipher. The 87 symbols are
labelled A–U by glyph identity (the usual isomorph transcription, checked
symbol by symbol against the original). Each label was then given a sector and
arc count by eye. The script decodes the cipher under all 3,072 fixed settings
and all 1,572,864 stepping settings, and ranks the results with English letter
trigrams from Newton's *Opticks* (`english_trigrams.txt`).

First result: no setting reads as English. Every fixed disc setting is a
simple substitution, so it cannot beat the best simple substitution, and that
is gibberish too. The stepping settings depend on how each glyph's
orientation was read, so edit `GLYPHS` if you read a symbol differently.

## O-state experiments

Beneath "DO YOU GO TO LONDON TOMORROW?" Elgar put a mark below every O and
above every other letter, and wrote 23 and "9 O's" beside it. `ostate.py`
(and the "O-state experiments" section of the page) tests whether an O
switches the discs between two states. It does not assume that it does.

A rule is a **trigger**, a **behaviour** and a **state B**:

| part | options |
| --- | --- |
| trigger | `letter-O`: the letter is O (plaintext when encoding, decoded letter when decoding) · `glyph-E2`: the physical glyph is E2 · `mapped-O`: the glyph sits where O currently is in state A |
| behaviour | `classify`: this character is read in B if it is an O · `toggle`: each O flips A/B for the following characters · `set`: O puts the next character in B, a non-O puts it back in A · `advance`: each O applies the change to the discs for good |
| state B | `reverse-arcs` (arc counts 1,2,3 read discs 3,2,1) · `mirror` (letters anticlockwise) · `swap-12` / `swap-23` / `swap-13` · `rotate:<1,2,3,used,all>:<±n>` |

The trigger options differ once a disc has turned. With the middle disc
turned one sector, O is written SE2: `mapped-O` fires on SE2, `glyph-E2`
still fires on E2, and `letter-O` fires on whatever decodes to O.

```bash
python -m dorabella.ostate notebook      # 23 letters, 9 Os, the ↑/↓ marks
python -m dorabella.ostate london        # which rules reproduce Elgar's London line
python -m dorabella.ostate trace --behaviour toggle --transform reverse-arcs "do you go to london tomorrow"
python -m dorabella.ostate trace --decode --trigger glyph-E2 --behaviour classify --transform mirror W2 E3 NW2
python -m dorabella.ostate search        # every rule x 512 starting offsets on Dorabella (~40 s)
```

The page's O-state logic is a separate, page-free script block. It is
checked against `ostate.py` by `tests/test_page_parity.py` (needs Node).
New notebook-derived rules go in as new triggers or transforms in both
places.

### First results

- **The marks.** The O-below / other-above rule keeps a mark on the same side
  at four places, not two: UG, ND, NT and RR. The photograph shows a pair
  of upper marks over U G as well, so the rule fits the page.
- **Elgar's own London encipherment.** The bottom-left line on the notebook
  page is "do you go to london" written with the plain key. Every toggle,
  set and advance rule contradicts it. With 123→321 toggling, for example,
  the N and D after the O in LONDON would need 3 arcs, but Elgar wrote 1.
  The only rules that reproduce it are classify rules whose state B cannot
  move O. O is on the middle disc, which 123→321 leaves alone, and on the
  W–E mirror axis. Those rules change nothing at all, in London or in
  Dorabella.
- **Dorabella.** Under the plain key Dorabella decodes to only one O, and
  has only one E2 symbol, where English would have about six Os in 87
  letters. So any E2-triggered rule fires at most once. The best O-state
  results score about −4.55, the same as shuffled letters (−4.42) and far
  from English (−3.43).

So far no simple O-controlled two-state rule explains the London example
and Dorabella together.

## Unresolved notebook evidence

- "1 2 3 4 4", with two distinct handwritten forms of 4, written below the
  London example. Recorded only; not used in any search.

## Tests

```bash
python -m unittest discover -s dorabella/tests -t .
```
