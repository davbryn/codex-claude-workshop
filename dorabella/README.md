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

## Tests

```bash
python -m unittest discover -s dorabella/tests -t .
```
