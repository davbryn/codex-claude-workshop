# Dorabella cipher solver

A solver for Elgar's Dorabella cipher (14 July 1897). It tests whether the cipher
is one of several cipher types, and it reports honestly when it finds nothing.

```bash
python -m dorabella.solver              # full run, about 2 minutes (needs numpy)
python -m dorabella.solver --quick      # fewer decoys, about 40 seconds
python -m dorabella.solver selftest     # prove each family can crack an 87-letter message
python -m dorabella.solver --family substitution --glyphs "W2 E3 NW2 ..."   # your own reading
```

## How it works

**Transcription** (`transcription.py`). The 87 symbols split into 21 distinct
glyphs, labelled A–U by first appearance (the standard isomorph). Every
occurrence of each label was checked side by side against the original. Each
glyph is written as where its arcs sit plus the arc count: `W1` is a "c",
`W2` "ε", `E2` "3", `S2` "ω", `N2` "m". Which symbols are the same is
solid. A few diagonal tilts are judgement calls, so edit `GLYPHS` or pass
`--glyphs` to test another reading.

**Elgar's key as three discs** (`discs.py`). Each symbol's direction picks
one of 8 sectors and its arc count picks one of three nested discs. With every
disc at 0 this is Elgar's printed alphabet, and it reproduces his own
"do you go to london" example on the notebook page.

| sector | W | NW | N | NE | E | SE | S | SW |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 arc | A | D | G | K | N | Q | T | X |
| 2 arcs | B | E | H | L | O | R | U | Y |
| 3 arcs | C | F | I | M | P | S | W | Z |

**Scoring** (`scoring.py`). Letter-quadruple frequencies from 4.5 million
letters of 19th-century prose (`build_ngrams.py` rebuilds them). An
87-letter English passage scores about −4.1; the same letters shuffled
about −6.5.

**Families** (`solver.py`). Each is tried on the symbols read forwards and
backwards:

| family | what it tries |
| --- | --- |
| elgar-key | Elgar's printed alphabet |
| discs | all 3,072 disc rotations and orders |
| discs-step | the discs also turn a fixed amount after every letter (1,572,864 settings) |
| periodic | Elgar's alphabet, then a Vigenère or Beaufort key of period 1–8 |
| substitution | any one-to-one symbol → letter key (simulated annealing); this covers elgar-key and discs |

**Decoys.** With only 87 letters, a flexible search always finds something
English-flavoured. So every family is also run on 10 decoys: the same 87
symbols in a random order. That keeps the symbol counts and destroys any
message. A family shows a signal only if the real cipher beats every decoy
and sits more than 3 standard deviations above them.

**Self-test.** An 87-letter English letter, enciphered with a random key of
each kind. Every family recovers it 100%, so "no signal" means the cipher
isn't that kind (or the transcription is off), not that the solver is too
weak.

## Results

See `RESULTS.md`. No family shows a signal. Under the best possible
substitution key, Dorabella scores −5.02 and its shuffled decoys −5.00, so its
symbol order is no more English-like than random. A genuine 87-letter
substitution cipher would reach about −4.1.

## Notebook evidence on record

- Under "DO YOU GO TO LONDON TOMORROW?" Elgar marked every O below the line
  and every other letter above, with "23" and "9 O's". An O-controlled
  two-state disc mechanism was tested and dropped. Every version that changes
  anything contradicts Elgar's own London encipherment. The rest change
  nothing, because O sits on the middle disc and on the W–E axis.
- Under Elgar's key, Dorabella contains a single O (one E2 symbol), where
  87 letters of English would have about six.
- Unresolved: "1 2 3 4 4", with two distinct handwritten forms of 4. Not
  used in any search.

## Disc viewer

Open `discs.html` to turn the discs by hand, encode, step through letters,
decode, and search fixed settings for a crib.

## Tests

```bash
python -m unittest discover -s dorabella/tests -t .
```
