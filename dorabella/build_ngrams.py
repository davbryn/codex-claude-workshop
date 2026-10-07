"""Rebuild english_quadgrams.txt.gz, the English model the solver scores with.

Source: the NLTK Gutenberg sample (public-domain 19th-century prose), downloaded separately:
    curl -O https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/gutenberg.zip
    python -m dorabella.build_ngrams gutenberg.zip

Letters are folded to Elgar's 24-letter alphabet (J->I, V->U).  Verse and scripture are left out.
"""
import gzip
import sys
import zipfile
from collections import Counter
from pathlib import Path

from .discs import normalise

PROSE = ["austen-emma", "austen-persuasion", "austen-sense", "bryant-stories", "burgess-busterbrown",
         "carroll-alice", "chesterton-ball", "chesterton-brown", "chesterton-thursday",
         "edgeworth-parents", "melville-moby_dick"]
OUT = Path(__file__).with_name("english_quadgrams.txt.gz")


def main(zip_path: str) -> None:
    counts, letters = Counter(), 0
    with zipfile.ZipFile(zip_path) as z:
        for name in PROSE:
            text = normalise(z.read(f"gutenberg/{name}.txt").decode("utf-8", "ignore"))
            letters += len(text)
            counts.update(text[i:i + 4] for i in range(len(text) - 3))
    with gzip.open(OUT, "wt") as f:
        f.write(f"# Quadgram counts, {letters} letters of NLTK Gutenberg prose: {', '.join(PROSE)}\n")
        for gram, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            f.write(f"{gram} {n}\n")
    print(f"{letters} letters, {len(counts)} distinct quadgrams -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
