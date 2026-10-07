import unittest

import numpy as np

from dorabella import engine


class EngineTest(unittest.TestCase):
    def test_cracks_english_under_random_key(self):
        rng = np.random.default_rng(11)
        text = engine.english_sample(rng)
        cipher = rng.permutation(24)[engine.letters(text)]
        labels, seq = np.unique(cipher, return_inverse=True)
        sol = engine.anneal(seq, len(labels), restarts=10, iterations=20000, seed=3)
        accuracy = np.mean([a == b for a, b in zip(sol.plain, text)])
        self.assertGreaterEqual(accuracy, 0.9)

    def test_score_matches_numpy_scoring(self):
        from dorabella.scoring import score
        idx = engine.letters(engine.HELD_OUT[0][:60])
        key = np.arange(24)
        self.assertAlmostEqual(engine.mean_score(idx, key), float(score(idx)), places=4)

    def test_nulls_and_breaks(self):
        key = np.array([0, -1, 2])
        self.assertEqual(engine.plaintext([0, 1, 2, -1, 2], key), "AC C")

    def test_shuffled_keeps_breaks_and_symbols(self):
        seq = np.array([0, 1, 2, -1, 3, 4])
        out = engine.shuffled(seq, np.random.default_rng(0))
        self.assertEqual(out[3], -1)
        self.assertEqual(sorted(out), sorted(seq))


if __name__ == "__main__":
    unittest.main()
