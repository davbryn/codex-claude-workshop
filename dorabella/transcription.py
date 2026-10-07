"""The Dorabella cipher (Elgar to Dora Penny, 14 July 1897) as glyphs, plus Elgar's own known encipherments.

Each glyph is written as the side its arcs sit on plus the arc count: W1 is a "c", W2 "ε",
W3 "ξ", E2 "3", N2 "m", S2 "ω" (see discs.py).

CONSENSUS is the default reading: the majority of five readers published by Hauer et al.
(HistoCrypt 2021), which also matches Hartmeier (2006) and Pelling (2012) everywhere except
a handful of hard glyphs.  Triangulating the three independent readers gives error rates of
about 1% (Hartmeier), 3% (Pelling) and 10% (Schmeh); see the Cairn analysis cited in README.
The 13 positions where readers disagree are listed in CONTESTED.

SCHMEH is the reading this project started from (Schmeh's MysteryTwister isomorph, glyphs by
eye).  It differs from the consensus at 10 positions; an independent remeasurement of every
glyph's tilt and arc count from the photograph sides with the consensus at all the strong ones.
"""
from .discs import Glyph

CONSENSUS_LINES = [
    "W2 E3 NW2 W3 W1 N2 S1 W3 NE1 SW2 NW3 SE2 SE1 NW1 SE2 N3 SE2 SE2 N2 E3 E3 SE2 NW1 SW1 SW2 SW1 N1 NW3 SE3",
    "S1 SE2 S1 N2 SW1 W3 NE1 NE2 W3 NW2 SE2 SE2 NW2 N2 N1 SE1 S1 SE2 NW3 SE2 N2 S2 SE3 SE1 NW1 SW1 NE1 NE1 SW1 NW3 SE3",
    "NW2 SE3 N2 S2 SE3 NW2 NW1 S2 S3 N1 SE3 NW2 SE2 N2 S2 SE1 SE3 N1 W3 E3 N1 SE3 N2 W3 NW1 SW1 W3",
]
CONTESTED = [9, 12, 21, 22, 23, 25, 33, 37, 50, 68, 77, 84, 85]   # 0-based positions where readers disagree

# The older reading: label string (A..U by first appearance) and each label's glyph.
SCHMEH_ISOMORPH = ["ABCDEFGDHAIJKLJMJJFBBJNGOGNIP",
                   "GJGFQDHRSCJJCFNKGJIJFTPKLQHHQIP",
                   "CPFUPCLUUNPCJFUKPNDBNPFDLED"]
SCHMEH_GLYPHS = {
    "E": "W1", "L": "NW1", "N": "N1", "H": "NE1", "K": "SE1", "G": "S1", "Q": "SW1",
    "A": "W2", "C": "NW2", "F": "N2", "R": "E2", "J": "SE2", "T": "S2", "O": "SW2",
    "D": "W3", "I": "NW3", "M": "N3", "B": "E3", "P": "SE3", "U": "S3", "S": "SW3",
}

TRANSCRIPTIONS = {
    "consensus": [Glyph.parse(t) for line in CONSENSUS_LINES for t in line.split()],
    "schmeh": [Glyph.parse(SCHMEH_GLYPHS[c]) for c in "".join(SCHMEH_ISOMORPH)],
}
CIPHER = TRANSCRIPTIONS["consensus"]
LINE_LENGTHS = [29, 31, 27]

# Elgar's own encipherments on his notebook page (1924 or later: it names his spaniel Marco,
# born that year), all readable with the plain key -- every disc at 0.
NOTEBOOK = {
    "DOYOUGOTOLONDON": "NW1 E2 SW2 E2 S2 N1 E2 S1 E2 NE2 E2 E1 NW1 E2 E1",
    "MARCOELGAR": "NE3 W1 SE2 W3 E2 NW2 NE2 N1 W1 SE2",
    "AUERYOLDCYPHER": "W1 S2 NW2 SE2 SW2 E2 NE2 NW1 W3 SW2 E3 N2 NW2 SE2",   # "A very old cypher", V written U
}
LONDON_PLAIN = "DOYOUGOTOLONDON"
LONDON_CIPHER = [Glyph.parse(t) for t in NOTEBOOK[LONDON_PLAIN].split()]
