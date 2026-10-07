"""The page's O-state engine (JavaScript) must agree with dorabella/ostate.py.  Needs Node; skipped without it."""
import itertools
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from dorabella.analyse import CIPHER
from dorabella.ostate import BEHAVIOURS, LONDON_FULL, TRIGGERS, Rule, State, run
from dorabella.discs import normalise
from dorabella.analyse import score
import numpy as np
from dorabella.discs import ALPHABET

PAGE = Path(__file__).resolve().parents[1] / "discs.html"
TRANSFORMS = ["reverse-arcs", "mirror", "swap-12", "swap-23", "swap-13", "rotate:all:+1",
              "rotate:used:-1", "rotate:2:+3"]
STARTS = [((0, 0, 0), (0, 1, 2), (0, 0, 0)), ((3, 6, 1), (2, 0, 1), (1, 0, 2))]


def page_engine() -> str:
    html = PAGE.read_text()
    blocks = dict(re.findall(r'<script id="([\w-]+)">\n(.*?)</script>', html, re.S))
    return blocks["trigrams"] + blocks["ostate-engine"]


@unittest.skipUnless(shutil.which("node"), "node not installed")
class PageMatchesPython(unittest.TestCase):
    def test_traces_and_scores_agree(self):
        cases = [(t, b, tr, s) for t, b, tr in itertools.product(TRIGGERS, BEHAVIOURS, TRANSFORMS) for s in STARTS]
        london = normalise(LONDON_FULL)
        dorabella = [str(g) for g in CIPHER]
        script = page_engine() + f"""
const cases = {json.dumps(cases)};
const out = cases.map(([trigger, behaviour, transform, [rot, ring, step]]) => {{
  const rule = {{ trigger, behaviour, transform }}, st = OState.state(rot, ring, false);
  const enc = OState.run(rule, st, [...{json.dumps(london)}], false, step);
  const dec = OState.run(rule, st, {json.dumps(dorabella)}.map(parse), true, step);
  const brief = t => t.map(s => [tok(s.glyph), s.letter, s.trigger, s.stateBefore, s.stateAfter, s.offsetsAfter, s.disc, s.note]);
  return [brief(enc), brief(dec)];
}});
const text = OState.run({{behaviour: "off", trigger: "letter-O", transform: "none"}}, OState.state(), {json.dumps(dorabella)}.map(parse), true).map(s => s.letter).join("");
console.log(JSON.stringify({{ out, score: OState.score(text), text }}));
"""
        result = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
        brief = lambda t: [[str(s.glyph), s.letter, s.trigger, s.state_before, s.state_after,
                            list(s.offsets_after), s.disc, s.note] for s in t]
        for (trig, beh, tr, (rot, ring, step)), (js_enc, js_dec) in zip(cases, result["out"]):
            rule, start = Rule(trig, beh, tr), State(rot, ring)
            self.assertEqual(js_enc, brief(run(rule, start, london, False, step)), (rule, rot))
            self.assertEqual(js_dec, brief(run(rule, start, CIPHER, True, step)), (rule, rot))
        py_score = float(score(np.array([[ALPHABET.index(c) for c in result["text"]]]))[0])
        self.assertAlmostEqual(result["score"], py_score, places=9)


if __name__ == "__main__":
    unittest.main()
