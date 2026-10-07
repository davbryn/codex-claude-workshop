import unittest

from dorabella import structure
from dorabella.discs import ALPHABET, DiscSet, Glyph
from dorabella.scoring import LANGUAGES, calibration, model, score_text
from dorabella.solver import Candidate, Settings, Verdict, disc_decrypt, selftest
from dorabella.transcription import CIPHER, LINE_LENGTHS, NOTEBOOK, TRANSCRIPTIONS


class Transcription(unittest.TestCase):
    def test_87_symbols_in_three_lines(self):
        self.assertEqual(sum(LINE_LENGTHS), 87)
        for glyphs in TRANSCRIPTIONS.values():
            self.assertEqual(len(glyphs), 87)

    def test_consensus_uses_20_glyphs_and_differs_from_schmeh_at_10_positions(self):
        self.assertEqual(len({str(g) for g in CIPHER}), 20)
        diffs = [i for i, (a, b) in enumerate(zip(CIPHER, TRANSCRIPTIONS["schmeh"])) if a != b]
        self.assertEqual(diffs, [9, 22, 23, 25, 36, 37, 63, 67, 74, 85])

    def test_every_notebook_line_is_the_plain_key(self):
        for plain, tokens in NOTEBOOK.items():
            self.assertEqual(DiscSet().decode([Glyph.parse(t) for t in tokens.split()]), plain)


class Scoring(unittest.TestCase):
    def test_english_far_above_shuffled(self):
        cal = calibration()
        self.assertGreater(cal["english"] - cal["shuffled"], 1.5)
        self.assertGreater(score_text("DO YOU GO TO LONDON TOMORROW"), score_text("XQZKWPXQZKWPXQZKWPXQZKW"))

    def test_each_language_prefers_its_own_text(self):
        self.assertEqual(set(LANGUAGES), {"english", "french", "german", "italian", "latin"})
        latin, english = "GALLIAESTOMNISDIUISAINPARTESTRES", "ALLGAULISDIVIDEDINTOTHREEPARTS"
        self.assertGreater(score_text(latin, model("latin")), score_text(latin, model("english")))
        self.assertGreater(score_text(english, model("english")), score_text(english, model("latin")))


class Structure(unittest.TestCase):
    def test_direction_motif_written_three_times(self):
        n, found = structure.longest_repeat(structure.streams(CIPHER)["direction"], times=3)
        self.assertEqual(n, 6)
        self.assertEqual(list(found.values()), [[46, 59, 70]])

    def test_mirror_pairs(self):
        self.assertEqual(structure.mirror_pairs(CIPHER), 13)
        self.assertEqual(structure.mirror_pairs(CIPHER, same_arcs=False), 27)


class Solver(unittest.TestCase):
    def test_vectorised_discs_match_discset(self):
        for ring_of, step in (((0, 1, 2), (0, 0, 0)), ((2, 0, 1), (1, 0, 3))):
            rows = disc_decrypt(CIPHER, ring_of, step)
            for rot in ((0, 0, 0), (3, 1, 7)):
                text = "".join(ALPHABET[i] for i in rows[rot[0] * 64 + rot[1] * 8 + rot[2]])
                self.assertEqual(text, DiscSet(list(rot), list(ring_of), list(step)).decode(CIPHER))

    def test_beating_decoys_is_not_a_decipherment_unless_it_reads_as_language(self):
        decoys = [-5.1, -5.0, -5.2, -5.05]
        self.assertEqual(Verdict(Candidate("f", "", "", "", -4.8), decoys).verdict, "order structure, not a decipherment")
        self.assertEqual(Verdict(Candidate("f", "", "", "", -4.1), decoys).verdict, "**reads as language**")
        self.assertEqual(Verdict(Candidate("f", "", "", "", -5.08), decoys).verdict, "no signal")

    def test_every_family_cracks_an_87_letter_message(self):
        results = selftest(Settings(restarts=8, iterations=15000), log=lambda *a: None)
        for family, accuracy in results.items():
            self.assertGreaterEqual(accuracy, 0.95, family)


if __name__ == "__main__":
    unittest.main()
