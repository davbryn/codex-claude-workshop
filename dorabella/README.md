# Dorabella cipher solver

Tools for attacking Elgar's Dorabella cipher (14 July 1897), and an honest record of what
they found.

**Status: not solved.** Every cipher family tried here either fails to beat shuffled
copies of the cipher, or beats them without producing anything that reads as language.
Each family first proves it can crack an 87-letter test message enciphered its way, so a
negative means the cipher is not that kind, not that the search was too weak.
[RESULTS.md](RESULTS.md) has the numbers.

```bash
python -m dorabella.solver                        # five families, consensus reading, English, ~2 min
python -m dorabella.solver --quick                # fewer decoys
python -m dorabella.solver --family substitution --language latin
python -m dorabella.solver --transcription schmeh # the older reading
python -m dorabella.solver --glyphs "W2 E3 NW2 ..."   # your own reading
python -m dorabella.solver selftest               # each family cracks a test message
python -m dorabella.structure                     # key-free order statistics against shuffles
```

Needs Python 3.10+, numpy and a C compiler (`cc`); `engine.c` is compiled on first use.

## What is established

**The transcription.** Three readers transcribed the 1937 plate independently, and they
agree on 74 of 87 glyphs. Their error rates work out to about 1% (Hartmeier), 3%
(Pelling) and 10% (Schmeh). This project started from Schmeh's reading, the noisy one,
and now defaults to the published five-reader consensus (Hauer et al., HistoCrypt
2021). An independent remeasurement of every glyph's tilt and arc count from the
photograph sides with the consensus at all its strong differences from Schmeh.

**Elgar's notebook page is a 1924 reconstruction, and it uses the plain key.** Every
enciphered line on it reads with all discs at 0:

- MARCO ELGAR (Marco was his spaniel, born 1924)
- A VERY OLD CYPHER (written twice: once in round glyphs, once in square ones)
- DO YOU GO TO LONDON

The three right-hand rows are the 24-glyph table written out in sector order. "23" and
"90s" count the letters and the O's of the TOMORROW sentence. The quartered disc
drawings show 8 directions as 4 + 4; their tick marks cannot be read as disc rotations.
Nothing on the page shows the discs being turned. Since the page postdates Dorabella by
27 years, it does not say which key Dorabella used.

**The symbol order is not random, but no tested key turns it into language.** Under the
best one-to-one key, Dorabella beats every shuffled copy of itself (z ≈ +3 to +4). It
still scores about 0.7 per letter-quadruple short of real English. The best keys produce
gibberish, and the same holds under Latin, French, German and Italian models.

**One direction pattern is written three times with different arc counts.** Read only the
direction each glyph faces, and the six-symbol pattern SE NW SE N S SE appears at
positions 46, 59 and 70. Every reader agrees on all 18 directions, but the arc counts
differ in each copy:

```
46: SE2 NW3 SE2 N2 S2 SE3
59: SE3 NW2 SE3 N2 S2 SE3
70: SE3 NW2 SE2 N2 S2 SE1
```

That one pattern accounts for all of the direction stream's excess order. It also
accounts for about half of the long-known excess of adjacent opposite-facing glyphs
("mirror pairs", 13 against about 5 expected), and that excess turns out to be purely a
direction effect. English under a natural key produces three copies with differing arcs
in about one 87-letter window in 3,000–4,000. Allowing for the statistic having been
chosen after seeing it, that becomes roughly 1 in 100 to 1 in 1,000.

If the three copies are the same plaintext, the arc count is not a periodic or
short-memory function of the letter. Every such rule was checked and none fits. The live
readings are that the arcs are free (the direction carries the message) or that this is
a coincidence. Direction-only decoding under Elgar's letter groups gives gibberish, and
decoding under arbitrary groups is untestable at this length. Run
`python -m dorabella.structure` to see it.

## What has been ruled out

Each row was run with a positive control and identical-procedure decoys; details and
numbers are in RESULTS.md. "Prior work" means the extensive Cairn analysis
(github.com/Jonathan-A-White/Cairn, `research/dorabella`) and Hauer et al. (2021).

| family | verdict |
| --- | --- |
| Elgar's printed key; all 3,072 fixed disc settings; discs stepping per letter (1.57M) | no signal |
| Vigenère / Beaufort over Elgar's key, periods 1–8 | no signal |
| one-to-one substitution: English, Latin, French, German, Italian | order structure only, gibberish |
| English variants: vowel-less, words reversed, phonetic, telegraphese, letter pairs swapped | no signal after multiple-testing correction |
| phonemes (Pitman 24-class, merged ARPAbet), as the prior work proposed | no signal; consonant skeleton untestable |
| arc count enciphered by a running, autokey, positional or keyword rule (3,751 rules) | no signal |
| a shared transcription error: two glyphs merged, one split, one deleted or inserted, the line-3 dot | no rescue |
| word-based solver (dictionary segmentation) | strings of 2–3-letter words |
| direction-only reading under Elgar's letter groups (80,640 layouts) | gibberish; arbitrary groups untestable |
| directions as a melody (80,640 pitch mappings, folk and hymn tune models) | fits better than shuffles, but only as much as any structured source; no tune |
| 8-letter alphabets (German note names A–H, ETAOINSH…), semaphore pairs, Morse or Wilkins triliteral on the arcs, Bacon biliteral | no signal |
| glyph types as nulls, Schooling's sliding card at the dot, skip and line-order readings, autokey (all primers), rail fence | no signal |
| published solutions (Packwood 2020, Belanger 2022, Roberts 2013, Henderson 2011) | not consistent with any fixed key, or 88 letters long |
| prior work: Elgar's 1924 key geometry (483,840 keys), columnar and local transposition, keyword-mixed keys | exhausted |

## What is left

These cannot be tested on 87 symbols, or not without an outside source:

- a pair code with an unknown table;
- an arbitrary letter grouping of the directions;
- two interleaved alphabets;
- a running key, book code or nomenclator;
- an anagram;
- a misreading that all three readers share.

What could still move this is new material rather than more searching:

- more ciphertext in the same system. The 18-symbol 1886 Liszt fragment is the only
  other known sample, and it is too short alone.
- an 1897 key, draft or explanation among Elgar's or the Penny family's papers.

A better image of the plate is unlikely to help. The prior work found that 3× resolution
changed nothing, and an independent remeasurement here agreed with the consensus.

## Files

| file | what it does |
| --- | --- |
| `transcription.py` | consensus and Schmeh readings, contested positions, Elgar's notebook encipherments |
| `discs.py` | Elgar's alphabet as three nested discs, with rotations and steps; CLI |
| `discs.html` | interactive disc viewer: turn, encode, decode, crib search |
| `scoring.py`, `models/` | quadgram models: English, Latin, French, German, Italian (period prose; sources in each file's header) |
| `build_ngrams.py` | rebuilds the English model from the NLTK Gutenberg sample |
| `engine.c`, `engine.py` | fast simulated annealing over keys, plus decoy trials and held-out English controls |
| `solver.py` | the five families, decoys, verdicts and self-test |
| `structure.py` | key-free order statistics: repeated pairs per stream, mirror pairs, repeated direction patterns |

Elgar's alphabet as discs: each glyph's direction picks one of 8 sectors, and its arc
count picks one of three nested discs. With every disc at 0 this is Elgar's printed key:

| sector | W | NW | N | NE | E | SE | S | SW |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 arc | A | D | G | K | N | Q | T | X |
| 2 arcs | B | E | H | L | O | R | U | Y |
| 3 arcs | C | F | I | M | P | S | W | Z |

## Tests

```bash
python -m unittest discover -s dorabella/tests -t .
```
