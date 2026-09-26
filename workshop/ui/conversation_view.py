"""Read-only, styled viewer for conversation.md."""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTextBrowser

from ..conversation import COMPLETE_MARKER, HUMAN_DECISION_MARKER, parse_conversation
from .agent_panel import ACCENTS

SPEAKER_COLOURS = {**ACCENTS, "Human": "#8fb8ff"}
CARD_BG = {"Codex": "#15201b", "Claude": "#241913", "Human": "#161d2b"}

_HANDOFF_LINE = re.compile(r"^\**\s*@(Codex|Claude)\s*\**$", re.IGNORECASE)


def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r'<code style="background:#2a2f38;color:#e6c07b;">&nbsp;\1&nbsp;</code>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", text)
    return text


def _render_body(content: str) -> str:
    out: list[str] = []
    in_code = False
    code: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            if in_code:
                out.append(
                    '<pre style="background:#0d1117;color:#c9d1d9;padding:6px;">'
                    + html.escape("\n".join(code))
                    + "</pre>"
                )
                code = []
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if not stripped:
            out.append('<div style="font-size:5px;">&nbsp;</div>')
        elif stripped in ("---", "***", "___"):
            continue
        elif m := _HANDOFF_LINE.match(stripped):
            name = m.group(1).capitalize()
            out.append(
                f'<div><span style="background:{SPEAKER_COLOURS[name]};color:#111;font-weight:bold;">'
                f"&nbsp;➜ @{name}&nbsp;</span></div>"
            )
        elif COMPLETE_MARKER in stripped and len(stripped) < 40:
            out.append('<div style="color:#8fd9ff;font-weight:bold;font-size:15px;">✓ PROJECT COMPLETE</div>')
        elif stripped.upper().startswith(HUMAN_DECISION_MARKER):
            out.append(f'<div style="color:#f5c542;font-weight:bold;">⚠ {_inline(stripped)}</div>')
        elif re.fullmatch(r"\*\*[^*]+\*\*:?", stripped) or stripped.startswith("#"):
            out.append(f'<div style="color:#d7dce4;font-weight:bold;">{_inline(stripped.lstrip("# "))}</div>')
        elif re.match(r"^[-*+]\s+", stripped):
            out.append(f"<div>&nbsp;&nbsp;•&nbsp;{_inline(stripped[2:].strip())}</div>")
        else:
            indent = "&nbsp;" * (len(line) - len(line.lstrip()))
            out.append(f"<div>{indent}{_inline(stripped)}</div>")
    if code:
        out.append('<pre style="background:#0d1117;color:#c9d1d9;">' + html.escape("\n".join(code)) + "</pre>")
    return "\n".join(out)


def render_conversation_html(text: str) -> str:
    turns = parse_conversation(text)
    if not turns:
        body = html.escape(text) or "<i>conversation.md is empty.</i>"
        return f'<div style="color:#c9d1d9;white-space:pre-wrap;">{body}</div>'
    parts = []
    for turn in turns:
        colour = SPEAKER_COLOURS.get(turn.speaker, "#ccc")
        title = f" — {html.escape(turn.title)}" if turn.title else ""
        parts.append(
            '<table width="100%" cellspacing="0" cellpadding="8" style="margin-bottom:10px;">'
            f'<tr><td width="5" bgcolor="{colour}"></td>'
            f'<td bgcolor="{CARD_BG.get(turn.speaker, "#1a1d23")}">'
            f'<div style="color:{colour};font-weight:bold;font-size:15px;">{turn.speaker}{title}</div>'
            f'<div style="color:#c9d1d9;">{_render_body(turn.content)}</div>'
            "</td></tr></table>"
        )
    return "\n".join(parts)


class ConversationView(QTextBrowser):
    """Re-renders when the text changes; follows new content unless scrolled up."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setReadOnly(True)
        self._text: str | None = None

    def set_conversation(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        bar = self.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 30
        previous = bar.value()
        self.setHtml(render_conversation_html(text))
        # Layout finishes asynchronously; scroll once the new maximum is known.
        restore = (lambda: bar.setValue(bar.maximum())) if at_bottom else (lambda: bar.setValue(previous))
        restore()
        QTimer.singleShot(0, restore)
