"""Read-only, styled viewer for conversation.md."""

from __future__ import annotations

import html
import re

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QTextBrowser

from ..conversation import COMPLETE_MARKER, HUMAN_DECISION_MARKER, PROPOSE_COMPLETE_MARKER, parse_conversation
from ..theatre.cast import CHARACTER
from .theme import ACCENTS, CARD_BG as THEME_CARD_BG

SPEAKER_COLOURS = dict(ACCENTS)
CARD_BG = dict(THEME_CARD_BG)

_HANDOFF_LINE = re.compile(r"^\**\s*@(Codex|Claude)\s*\**$", re.IGNORECASE)
ICONS = {"Codex": "avatar:codex", "Claude": "avatar:claude"}


def _badge(text: str, bg: str, fg: str = "#10141b") -> str:
    return (f'<div style="margin-top:4px;"><span style="background:{bg};color:{fg};font-weight:bold;'
            f'font-size:11px;">&nbsp;&nbsp;{text}&nbsp;&nbsp;</span></div>')


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
            out.append(f'<div style="margin-top:4px;color:{SPEAKER_COLOURS[name]};font-weight:bold;">'
                       f'→ @{name}</div>')
        elif stripped.strip("*_` ").rstrip(".!") == PROPOSE_COMPLETE_MARKER:
            out.append(_badge("⚑ PROPOSE PROJECT COMPLETE", "#3a6f8f", "#e6f6ff"))
        elif stripped.strip("*_` ").rstrip(".!") == COMPLETE_MARKER:
            out.append(_badge("✓ PROJECT COMPLETE", "#8fd9ff"))
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
        title = html.escape(turn.title) if turn.title else ""
        if turn.speaker in CHARACTER:
            name = (f'{CHARACTER[turn.speaker].upper()} <span style="color:{colour};font-weight:normal;">'
                    f'({turn.speaker})</span>')
            icon = f'<img src="{ICONS[turn.speaker]}" width="40" height="40">'
        else:
            name = "YOU" if turn.title.lower() != "project start" else "THE BRIEF"
            icon = '<span style="font-size:26px;">👤</span>'
        parts.append(
            '<table width="100%" cellspacing="0" cellpadding="7" style="margin-bottom:8px;">'
            f'<tr><td width="46" valign="top" bgcolor="{CARD_BG.get(turn.speaker, "#1a1714")}">{icon}</td>'
            f'<td bgcolor="{CARD_BG.get(turn.speaker, "#1a1714")}">'
            f'<div style="color:{colour};font-weight:bold;font-size:14px;letter-spacing:1px;">{name}'
            f'<span style="color:#8b8378;font-weight:normal;"> &nbsp;•&nbsp; {title}</span></div>'
            f'<div style="color:#ddd5c8;font-family:Consolas,monospace;font-size:13px;">'
            f'{_render_body(turn.content)}</div>'
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
        self._icons = {}

    def loadResource(self, kind: int, url: QUrl):
        """Serve the procedural mini avatars for <img src="avatar:…">."""
        if url.scheme() == "avatar" and kind == QTextDocument.ResourceType.ImageResource.value:
            agent = "Codex" if url.path() == "codex" else "Claude"
            if agent not in self._icons:
                from .avatar_paint import avatar_pixmap

                self._icons[agent] = avatar_pixmap(agent, 80).toImage()
            return self._icons[agent]
        return super().loadResource(kind, url)

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
