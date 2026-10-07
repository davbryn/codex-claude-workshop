import unittest

import numpy as np

from dorabella.discs import ALPHABET, DiscSet
from dorabella.scoring import calibration, score_text
from dorabella.solver import Settings, disc_decrypt, selftest
from dorabella.transcription import CIPHER, GLYPHS, ISOMORPH, LONDON_CIPHER, LONDON_PLAIN


class Transcription(unittest.TestCase):
    def test_87_symbols_from_21_distinct_glyphs(self):
        self.assertEqual([len(line) for line in ISOMORPH], [29, 31, 27])
        self.assertEqual(len(set("".join(ISOMORPH))), 21)
        self.assertEqual(len(set(GLYPHS.values())), 21)

    def test_elgars_london_line_is_the_plain_key(self):
        self.assertEqual(DiscSet().decode(LONDON_CIPHER), LONDON_PLAIN)


class Scoring(unittest.TestCase):
    def test_english_far_above_shuffled(self):
        cal = calibration()
        self.assertGreater(cal["english"] - cal["shuffled"], 1.5)
        self.assertGreater(score_text("DO YOU GO TO LONDON TOMORROW"), score_text("XQZKWPXQZKWPXQZKWPXQZKW"))


class Solver(unittest.TestCase):
    def test_vectorised_discs_match_discset(self):
        for ring_of, step in (((0, 1, 2), (0, 0, 0)), ((2, 0, 1), (1, 0, 3))):
            rows = disc_decrypt(CIPHER, ring_of, step)
            for rot in ((0, 0, 0), (3, 1, 7)):
                text = "".join(ALPHABET[i] for i in rows[rot[0] * 64 + rot[1] * 8 + rot[2]])
                self.assertEqual(text, DiscSet(list(rot), list(ring_of), list(step)).decode(CIPHER))

    def test_every_family_cracks_an_87_letter_message(self):
        results = selftest(Settings(restarts=6, iterations=12000), log=lambda *a: None)
        for family, accuracy in results.items():
            self.assertGreaterEqual(accuracy, 0.95, family)


if __name__ == "__main__":
    unittest.main()
