import unittest

from dorabella.discs import ALPHABET, DiscSet, Glyph, find_settings, normalise

LONDON = "do you go to london"


class ElgarKey(unittest.TestCase):
    def test_unrotated_discs_reproduce_elgars_key(self):
        key = DiscSet()
        # a, b, c are one, two and three arcs in the same (left-hand) sector
        self.assertEqual([str(key.glyph_for(c)) for c in "ABC"], ["W1", "W2", "W3"])
        self.assertEqual(str(key.glyph_for("D")), "NW1")   # next group, one sector clockwise
        self.assertEqual(str(key.glyph_for("U")), "S2")    # two cups below: "ω"
        self.assertEqual(str(key.glyph_for("G")), "N1")    # one arc on top: "n"
        self.assertEqual(str(key.glyph_for("O")), "E2")    # two arcs on the right: "3"

    def test_every_letter_has_its_own_glyph(self):
        glyphs = {DiscSet().glyph_for(c) for c in ALPHABET}
        self.assertEqual(len(glyphs), 24)

    def test_j_and_v_merge_like_the_key(self):
        self.assertEqual(normalise("Jive!"), "IIUE")


class Rotation(unittest.TestCase):
    def test_rotating_one_disc_moves_only_its_letters(self):
        discs = DiscSet()
        discs.rotate(0, 1)
        self.assertEqual(str(discs.glyph_for("A")), "NW1")
        self.assertEqual(str(discs.glyph_for("X")), "W1")
        self.assertEqual(str(discs.glyph_for("B")), "W2")

    def test_full_turn_is_identity(self):
        discs = DiscSet()
        for _ in range(8):
            discs.rotate(2)
        self.assertEqual(discs.rotation, [0, 0, 0])

    def test_round_trip_under_every_fixed_setting_sample(self):
        for setting in (DiscSet([1, 2, 3]), DiscSet([7, 0, 4], [2, 0, 1]),
                        DiscSet([3, 3, 3], [1, 2, 0], step=[1, 0, 3])):
            self.assertEqual(setting.decode(setting.encode(LONDON)), normalise(LONDON))

    def test_stepping_changes_repeated_letters(self):
        stepped = DiscSet(step=[0, 1, 0]).encode("OOO")
        self.assertEqual(len(set(stepped)), 3)


class London(unittest.TestCase):
    def test_london_message_with_the_plain_key(self):
        glyphs = " ".join(map(str, DiscSet().encode(LONDON)))
        self.assertEqual(glyphs, "NW1 E2 SW2 E2 S2 N1 E2 S1 E2 NE2 E2 E1 NW1 E2 E1")

    def test_crib_search_recovers_the_setting(self):
        secret = DiscSet([5, 2, 6], [0, 2, 1])
        hits = find_settings(secret.encode(LONDON), LONDON)
        self.assertIn((secret.rotation, secret.ring_of), [(h.rotation, h.ring_of) for h in hits])

    def test_glyph_tokens_round_trip(self):
        for g in DiscSet().encode(LONDON):
            self.assertEqual(Glyph.parse(str(g)), g)


if __name__ == "__main__":
    unittest.main()
