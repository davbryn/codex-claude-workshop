"""Turn public conversation entries into short bubble and speech excerpts.

Everything here works only on text an agent actually appended to
conversation.md. Nothing is invented; excerpts are trimmed, never rewritten.
"""

from __future__ import annotations

import re

_FENCE_BLOCK = re.compile(r"(^|\n)\s*(```|~~~).*?(\n\s*\2[^\n]*|\Z)", re.DOTALL)
_SECTION_RE = re.compile(r"^\s*(?:#{1,6}\s*)?\*{0,2}(thoughts?|actions?|result|results|next)\*{0,2}:?\s*$", re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[\"'(\[A-Z0-9@`*_])")
_PATH_RE = re.compile(r"(?:[A-Za-z]:)?[\\/]?(?:[\w.\-~]+[\\/])+([\w.\-]+)")
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF⬀-⯿️‍]+"
)
CONTROL_LINES = re.compile(
    r"^\s*\**\s*(@(codex|claude)|PROPOSE PROJECT COMPLETE|PROJECT COMPLETE|---)\s*\**\s*$", re.I
)


def strip_code(text: str) -> str:
    return _FENCE_BLOCK.sub("\n", text)


def strip_markdown(text: str) -> str:
    """Plain readable text: no code blocks, emphasis, links, bullets or control lines."""
    text = strip_code(text)
    lines = [ln for ln in text.splitlines() if not CONTROL_LINES.match(ln)]
    text = "\n".join(lines)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"\1", text)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
    return text


def sections(content: str) -> dict[str, str]:
    """Split an entry into its **Thoughts** / **Actions** / **Result** / **Next** sections."""
    found: dict[str, list[str]] = {}
    current = "_intro"
    in_fence = False
    for line in content.splitlines():
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
        match = None if in_fence else _SECTION_RE.match(line)
        if match:
            name = match.group(1).lower()
            current = {"thought": "thoughts", "action": "actions", "results": "result"}.get(name, name)
            found.setdefault(current, [])
        else:
            found.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in found.items() if "\n".join(v).strip()}


def _looks_technical(sentence: str) -> bool:
    letters = sum(ch.isalpha() or ch.isspace() for ch in sentence)
    if not sentence or letters / len(sentence) < 0.72:
        return True
    return bool(re.search(r"Traceback|File \".*\", line \d+|^\s*at \w|[{};]\s*$|^\$ |==>|:\d+:\d+", sentence))


_PROTECT = {".": "", "!": "", "?": ""}


def sentences(text: str) -> list[str]:
    # punctuation inside `inline code` (e.g. `Summer2024!`) doesn't end a sentence
    text = re.sub(r"`[^`\n]+`", lambda m: "".join(_PROTECT.get(c, c) for c in m.group(0)), text)
    plain = re.sub(r"\s+", " ", strip_markdown(text)).strip()
    if not plain:
        return []
    restore = str.maketrans({v: k for k, v in _PROTECT.items()})
    return [s.strip().translate(restore) for s in _SENTENCE_SPLIT.split(plain) if s.strip()]


def _take(parts: list[str], limit: int) -> str:
    out = ""
    for part in parts:
        candidate = f"{out} {part}".strip()
        if len(candidate) > limit:
            if not out:
                cut = part[:limit].rsplit(" ", 1)[0].rstrip(",;:—-")
                return cut + "…"
            break
        out = candidate
    return out


def _conversational(text: str, count: int) -> list[str]:
    return [s for s in sentences(text) if not _looks_technical(s)][:count]


# --- choosing the line worth showing -------------------------------------------

_KEYWORDS = re.compile(
    r"\b(?:you|your|you're|wrong|right|bug|actually|unfortunately|obviously|somehow|apparently|again|"
    r"of course|told you|welcome|concede|admit|correct|incorrect|nobody|never|interesting|weird|"
    r"ego|feelings|cry|kubernetes|factory|abstraction|minimal\w*|over-?engineer\w*|delet\w+|crash\w*|"
    r"slower|faster|race condition|edge case|benchmark\w*|lines|hooli|pied piper|like it was|like a|like an)\b",
    re.I)
_NAMES = re.compile(r"\b(?:gilfoyle|dinesh|codex|claude)\b", re.I)
_BOILERPLATE = re.compile(
    r"^(?:i )?(?:read|ran|re-ran|reviewed|created|added|updated|inspected|checked|opened|looked at|implemented|"
    r"wrote|edited|modified|verified|here(?:'s| is))\b|^(?:all )?\d+ tests? pass", re.I)
_SECTION_WEIGHT = {"thoughts": 2.0, "_intro": 1.0, "result": 0.4, "next": 0.0, "actions": -1.0}


def score_sentence(sentence: str, section: str = "thoughts") -> float:
    """How entertaining/relevant a public sentence is for the speech bubble (deterministic)."""
    if _looks_technical(sentence):
        return -10.0
    score = _SECTION_WEIGHT.get(section, 0.0)
    score += 3.0 * min(2, len(_NAMES.findall(sentence)))
    score += 1.5 * min(3, len(_KEYWORDS.findall(sentence)))
    if sentence.rstrip().endswith(("!", "?")):
        score += 0.5
    if _BOILERPLATE.search(sentence):
        score -= 2.5
    if len(sentence) < 18:
        score -= 1.0
    elif len(sentence) > 200:
        score -= 1.5
    return score


def _candidates(content: str) -> list[tuple[str, int, str]]:
    """(section, index-in-section, sentence) for every conversational sentence, in order."""
    out = []
    for key, text in sections(content).items():
        for i, sentence in enumerate(sentences(text)):
            out.append((key, i, sentence))
    return out


def _best_passage(content: str, limit: int) -> tuple[str, set[str]]:
    cands = [c for c in _candidates(content) if not _looks_technical(c[2])]
    if not cands:
        return "", set()
    scored = [(score_sentence(s, key), -n, key, i, s) for n, (key, i, s) in enumerate(cands)]
    best = max(scored)
    _, _, key, i, sentence = best
    same = [s for k, j, s in cands if k == key]
    chosen = [sentence]
    # keep a short setup before the line, and the punchline after it, when they fit
    if i > 0 and len(sentence) < 70 and len(same[i - 1]) < 90 and score_sentence(same[i - 1], key) > 0:
        chosen.insert(0, same[i - 1])
    if i + 1 < len(same) and len(" ".join(chosen + [same[i + 1]])) <= limit:
        chosen.append(same[i + 1])
    return _take(chosen, limit), set(chosen)


def bubble_excerpt(content: str, limit: int = 240) -> str:
    """The most entertaining real excerpt of an entry for a speech bubble (emoji kept, never rewritten)."""
    text, _ = _best_passage(content, limit)
    if text:
        return text
    return _take(sentences(content)[:2], limit)


def speech_text(content: str, limit: int = 300) -> str:
    """What the character says aloud: the bubble passage, plus the best remaining line if it fits."""
    text, used = _best_passage(content, min(limit, 220))
    if not text:
        return clean_for_speech(_take(_conversational(content, 3), limit))
    rest = [(score_sentence(s, k), s) for k, _, s in _candidates(content) if s not in used]
    rest = [r for r in rest if r[0] > 0]
    if rest:
        extra = max(rest)[1]
        if len(text) + 1 + len(extra) <= limit:
            text = f"{text} {extra}"
    return clean_for_speech(text)


def clean_for_speech(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = _PATH_RE.sub(lambda m: m.group(1), text)
    text = re.sub(r"@(Codex|Claude)\b", r"\1", text)
    text = text.replace("↔", "and").replace("→", "to").replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()
