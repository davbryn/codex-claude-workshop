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


def sentences(text: str) -> list[str]:
    plain = re.sub(r"\s+", " ", strip_markdown(text)).strip()
    if not plain:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT.split(plain) if s.strip()]


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


def bubble_excerpt(content: str, limit: int = 240) -> str:
    """A short, conversational excerpt for a speech bubble (emoji kept)."""
    parts = sections(content)
    chosen = _conversational(parts.get("thoughts", ""), 2)
    if len(" ".join(chosen)) < 110:
        chosen += _conversational(parts.get("result", ""), 1)
    if not chosen:
        for key in ("_intro", "result", "next", "actions"):
            chosen = _conversational(parts.get(key, ""), 2)
            if chosen:
                break
    if not chosen:
        chosen = sentences(content)[:2]
    return _take(chosen, limit)


def speech_text(content: str, limit: int = 300) -> str:
    """Text to read aloud: Thoughts, one Result sentence, one Next sentence. No code, paths or emoji."""
    parts = sections(content)
    picked = _conversational(parts.get("thoughts", ""), 2)
    picked = [_take(picked, 180)] if picked else []
    picked += _conversational(parts.get("result", ""), 1)
    picked += _conversational(parts.get("next", ""), 1)
    if not any(picked):
        picked = _conversational(content, 3)
    text = _take([p for p in picked if p], limit)
    return clean_for_speech(text)


def clean_for_speech(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = _PATH_RE.sub(lambda m: m.group(1), text)
    text = re.sub(r"@(Codex|Claude)\b", r"\1", text)
    text = text.replace("↔", "and").replace("→", "to").replace("—", ", ").replace("–", ", ")
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()
