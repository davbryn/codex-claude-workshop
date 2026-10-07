import unittest

import numpy as np

from dorabella.analyse import CIPHER, GLYPHS, ISOMORPH, decrypt_all, score
from dorabella.discs import ALPHABET, DiscSet


class Transcription(unittest.TestCase):
    def test_87_symbols_from_21_distinct_glyphs(self):
        self.assertEqual([len(line) for line in ISOMORPH], [29, 31, 27])
        self.assertEqual(len(set("".join(ISOMORPH))), 21)
        self.assertEqual(len(set(GLYPHS.values())), 21)


class Search(unittest.TestCase):
    def test_vectorised_decrypt_matches_discset(self):
        for ring_of, step in (((0, 1, 2), (0, 0, 0)), ((2, 0, 1), (1, 0, 3))):
            rows = decrypt_all(CIPHER, ring_of, step)
            # row index = rotation (a, b, c) in base 8
            for rot in ((0, 0, 0), (3, 1, 7)):
                k = rot[0] * 64 + rot[1] * 8 + rot[2]
                text = "".join(ALPHABET[i] for i in rows[k])
                self.assertEqual(text, DiscSet(list(rot), list(ring_of), list(step)).decode(CIPHER))

    def test_english_outscores_gibberish(self):
        idx = lambda t: np.array([ALPHABET.index(c) for c in t])
        self.assertGreater(score(idx("DOYOUGOTOLONDONTOMORROW")), score(idx("XQZKWPXQZKWPXQZKWPXQZKW")))


if __name__ == "__main__":
    unittest.main()
