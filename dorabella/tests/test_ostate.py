import itertools
import unittest

from dorabella.analyse import CIPHER
from dorabella.discs import DiscSet, Glyph, normalise
from dorabella.ostate import (LONDON_FULL, TRIGGERS, Rule, State, alternating_marks, decode, encode,
                              london_check, o_marks, run, transform)

LONDON = normalise(LONDON_FULL)


class NotebookMarks(unittest.TestCase):
    def test_23_letters_9_os(self):
        self.assertEqual(len(LONDON), 23)
        self.assertEqual(LONDON.count("O"), 9)

    def test_every_o_below_everything_else_above(self):
        marks = o_marks(LONDON)
        self.assertEqual(marks[:5], [("D", "↑"), ("O", "↓"), ("Y", "↑"), ("O", "↓"), ("U", "↑")])
        self.assertTrue(all((m == "↓") == (c == "O") for c, m in marks))

    def pair(self, a, b):
        marks = o_marks(LONDON)
        i = next(i for i in range(len(marks) - 1) if marks[i][0] == a and marks[i + 1][0] == b)
        return marks[i][1] + marks[i + 1][1]

    def test_nd_and_rr_stay_above(self):
        self.assertEqual(self.pair("N", "D"), "↑↑")
        self.assertEqual(self.pair("R", "R"), "↑↑")

    def test_rule_breaks_alternation_exactly_at_ug_nd_nt_rr(self):
        marks = [m for _, m in o_marks(LONDON)]
        breaks = [LONDON[i:i + 2] for i in range(len(marks) - 1) if marks[i] == marks[i + 1]]
        self.assertEqual(breaks, ["UG", "ND", "NT", "RR"])
        self.assertNotEqual(marks, alternating_marks(LONDON))


class Engine(unittest.TestCase):
    def test_off_reproduces_the_existing_disc_model(self):
        for rot, ring, step in (((0, 0, 0), (0, 1, 2), (0, 0, 0)), ((3, 1, 6), (2, 0, 1), (1, 0, 5))):
            old = DiscSet(list(rot), list(ring), list(step))
            start = State(rot, ring)
            self.assertEqual(encode(Rule(), start, LONDON, step), old.encode(LONDON))
            self.assertEqual(decode(Rule(), start, CIPHER, step), old.decode(CIPHER))

    def test_reverse_arcs_maps_1_to_3_and_3_to_1(self):
        b = transform(State(), "reverse-arcs", 0)
        self.assertEqual(b.arc_mapping(), "1→3, 2→2, 3→1")
        self.assertEqual(b.decode(Glyph.parse("NW1")), "F")   # NW on disc 3 (C F I ...)
        self.assertEqual(b.decode(Glyph.parse("NW3")), "D")

    def test_toggle_changes_the_following_letters_not_the_o(self):
        trace = run(Rule("letter-O", "toggle", "reverse-arcs"), State(), "DONDON", False)
        self.assertEqual([s.state_before for s in trace], list("AABBBA"))
        self.assertEqual([str(s.glyph) for s in trace], ["NW1", "E2", "E3", "NW3", "E2", "E1"])
        self.assertTrue(trace[1].trigger and trace[4].trigger)

    def test_set_and_classify(self):
        set_trace = run(Rule("letter-O", "set", "mirror"), State(), "OXOO", False)
        self.assertEqual([s.state_before for s in set_trace], list("ABAB"))
        cls = run(Rule("letter-O", "classify", "rotate:all:+1"), State(), "OXOO", False)
        self.assertEqual([s.state_before for s in cls], list("BABB"))

    def test_advance_keeps_turning(self):
        trace = run(Rule("letter-O", "advance", "rotate:used:+1"), State(), "OOO", False)
        self.assertEqual([str(s.glyph) for s in trace], ["E2", "SE2", "S2"])
        self.assertEqual(trace[-1].offsets_after, (0, 3, 0))

    def test_every_rule_round_trips(self):
        for trig, beh, tr in itertools.product(TRIGGERS, ("toggle", "set", "advance"),
                                               ("reverse-arcs", "mirror", "swap-12", "rotate:used:-1")):
            rule = Rule(trig, beh, tr)
            glyphs = encode(rule, State((1, 2, 3)), LONDON, (0, 1, 0))
            self.assertEqual(decode(rule, State((1, 2, 3)), glyphs, (0, 1, 0)), LONDON, rule)

    def test_classify_flags_collisions(self):
        # In B, O moves to SE2, which is also R in state A, so SE2 cannot be read uniquely.
        rule = Rule("letter-O", "classify", "rotate:all:+1")
        trace = run(rule, State(), encode(rule, State(), "OR"), True)
        self.assertEqual([s.note for s in trace], ["ambiguous", "ambiguous"])


class Triggers(unittest.TestCase):
    def test_e2_and_mapped_o_differ_once_the_middle_disc_turns(self):
        turned = State((0, 1, 0))
        o_glyph = turned.encode("O")
        self.assertEqual(str(o_glyph), "SE2")
        e2 = run(Rule("glyph-E2", "toggle", "mirror"), turned, [o_glyph], True)[0]
        mapped = run(Rule("mapped-O", "toggle", "mirror"), turned, [o_glyph], True)[0]
        self.assertFalse(e2.trigger)
        self.assertTrue(mapped.trigger)

    def test_decoded_o_and_e2_differ_too(self):
        turned = State((0, 1, 0))   # E2 now decodes to L
        step = run(Rule("letter-O", "toggle", "mirror"), turned, [Glyph.parse("E2")], True)[0]
        self.assertEqual(step.letter, "L")
        self.assertFalse(step.trigger)


class LondonExample(unittest.TestCase):
    def test_plain_key_reproduces_elgars_london_line(self):
        self.assertEqual(london_check(Rule()), [])

    def test_toggling_123_321_contradicts_it(self):
        problems = london_check(Rule("letter-O", "toggle", "reverse-arcs"))
        self.assertTrue(problems)
        self.assertIn("Elgar wrote", problems[0])


if __name__ == "__main__":
    unittest.main()
