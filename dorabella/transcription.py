"""The Dorabella cipher (Elgar to Dora Penny, 14 July 1897) as glyphs.

The 87 symbols split into 21 distinct glyphs, labelled A..U in order of first
appearance (the usual isomorph transcription).  Every occurrence of each label
was checked side by side against the original, and each label was given its
sector and arc count by eye.  The isomorph (which symbols are the same) is
solid; a few diagonal tilts are judgement calls at the photograph's
resolution.  Edit GLYPHS if you read a symbol differently.
"""
from .discs import Glyph

# One string per line of Elgar's note.
ISOMORPH = ["ABCDEFGDHAIJKLJMJJFBBJNGOGNIP",
            "GJGFQDHRSCJJCFNKGJIJFTPKLQHHQIP",
            "CPFUPCLUUNPCJFUKPNDBNPFDLED"]

# label -> where the arcs sit + how many.  W1 is a "c", W2 "ε", W3 "ξ", N2 "m", S2 "ω".
GLYPHS = {
    "E": "W1", "L": "NW1", "N": "N1", "H": "NE1", "K": "SE1", "G": "S1", "Q": "SW1",
    "A": "W2", "C": "NW2", "F": "N2", "R": "E2", "J": "SE2", "T": "S2", "O": "SW2",
    "D": "W3", "I": "NW3", "M": "N3", "B": "E3", "P": "SE3", "U": "S3", "S": "SW3",
}

LABELS = "".join(ISOMORPH)
CIPHER = [Glyph.parse(GLYPHS[c]) for c in LABELS]

# Elgar's own encipherment of "do you go to london" from the notebook page: the plain key.
LONDON_PLAIN = "DOYOUGOTOLONDON"
LONDON_CIPHER = [Glyph.parse(t) for t in "NW1 E2 SW2 E2 S2 N1 E2 S1 E2 NE2 E2 E1 NW1 E2 E1".split()]
