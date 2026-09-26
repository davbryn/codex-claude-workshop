"""Renders a character's monitor contents (editor / terminal / reader / idle browser) into a QImage.

The stage warps the image onto the monitor in perspective. Content comes from
workshop/theatre/screens.py: real diffs, real commands and output, real file
contents, or (when idle) the fictional web.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QLinearGradient, QPainter, QPainterPath, QPen

from ..theatre.screens import ScreenFeed

W, H = 300, 198
MONO = "Consolas"
ACCENT = {"Codex": "#57e389", "Claude": "#7fb2ff"}
PROMPT = {"Codex": "PS gilfoyle>", "Claude": "PS dinesh>"}


def _font(px: float, bold: bool = False, family: str = MONO) -> QFont:
    f = QFont(family)
    f.setPixelSize(int(px))
    f.setBold(bold)
    return f


def _elide(fm: QFontMetricsF, text: str, width: float) -> str:
    return fm.elidedText(text.replace("\t", "    "), Qt.TextElideMode.ElideRight, width)


def render_screen(feed: ScreenFeed | None, agent: str, t: float, active: bool, width: int = W,
                  height: int = H) -> QImage:
    """Render at any canvas size: the small monitor texture, or the full-stage close-up."""
    W, H = width, height
    img = QImage(W, H, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#07090c"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    if feed is None:
        _paint_blank(p, W, H, agent, t)
    elif feed.mode == "idle" and feed.page is not None:
        _paint_browser(p, W, H, feed, t)
    elif feed.mode == "bit" and feed.bit:
        _paint_bit(p, W, H, feed, agent, t)
    elif feed.mode == "kanban" and feed.board is not None:
        _paint_kanban(p, W, H, feed, t)
    elif feed.mode == "terminal":
        _paint_terminal(p, W, H, feed, agent, t)
    elif feed.mode in ("editor", "reader"):
        _paint_editor(p, W, H, feed, agent, t)
    else:
        _paint_blank(p, W, H, agent, t)
    # scanlines + a little bloom so it reads as a screen, not a sticker
    p.setPen(QPen(QColor(0, 0, 0, 38), 1))
    for y in range(0, H, 3):
        p.drawLine(0, y, W, y)
    if not active:
        p.fillRect(QRectF(0, 0, W, H), QColor(0, 0, 0, 70))
    p.end()
    return img


def _paint_blank(p: QPainter, W: int, H: int, agent: str, t: float) -> None:
    p.fillRect(QRectF(0, 0, W, H), QColor("#0b0e13"))
    p.setFont(_font(13))
    p.setPen(QColor(ACCENT.get(agent, "#8fb8ff")))
    cursor = "█" if int(t * 2) % 2 == 0 else " "
    p.drawText(QPointF(12, 28), f"{PROMPT.get(agent, 'PS>')} {cursor}")


def _title_bar(p: QPainter, W: int, H: int, title: str, colour: str, icon: str) -> float:
    p.fillRect(QRectF(0, 0, W, 22), QColor("#1a1d23"))
    p.fillRect(QRectF(8, 3, min(W - 16, 20 + len(title) * 7.2), 19), QColor("#0e1116"))
    p.fillRect(QRectF(8, 3, 3, 19), QColor(colour))
    p.setFont(_font(12))
    p.setPen(QColor("#d7dce4"))
    fm = QFontMetricsF(p.font())
    p.drawText(QRectF(16, 3, W - 30, 19), Qt.AlignmentFlag.AlignVCenter, _elide(fm, f"{icon} {title}", W - 40))
    return 26.0


def _paint_editor(p: QPainter, W: int, H: int, feed: ScreenFeed, agent: str, t: float) -> None:
    p.fillRect(QRectF(0, 0, W, H), QColor("#0e1116"))
    reader = feed.mode == "reader"
    top = _title_bar(p, W, H, feed.title, "#8fb8ff" if reader else ACCENT[agent], "📖" if reader else "✎")
    font = _font(12.5)
    p.setFont(font)
    fm = QFontMetricsF(font)
    lh = fm.height() + 1
    rows = int((H - top - 4) // lh)
    lines = list(feed.lines)
    shown = len(lines) if reader else min(len(lines), int(feed.revealed) + 1)
    if reader:  # a slow scroll through the file, with a highlight band as he reads
        span = max(1, len(lines) - rows)
        start = int((t * 1.2) % (span + rows * 0.5)) if len(lines) > rows else 0
        start = min(start, span) if len(lines) > rows else 0
    else:
        start = max(0, shown - rows)
    visible = lines[start:shown]
    colours = {"add": ("#9be9a8", "#12301d"), "del": ("#ff9c9c", "#3a1418"), "hunk": ("#7fd4ff", None),
               "ctx": ("#8a93a3", None), "file": ("#ffd479", "#262012"), "code": ("#c9d1d9", None)}
    gutter = 34
    y = top
    for i, (kind, text) in enumerate(visible):
        fg, bg = colours.get(kind, ("#c9d1d9", None))
        if bg:
            p.fillRect(QRectF(0, y, W, lh), QColor(bg))
        if reader and i == min(len(visible) - 1, rows // 2):
            p.fillRect(QRectF(0, y, W, lh), QColor(143, 184, 255, 36))
        p.setPen(QColor("#4b5463"))
        mark = {"add": "+", "del": "−"}.get(kind, "")
        number = str(start + i + 1) if kind in ("code", "ctx") else mark
        p.drawText(QRectF(2, y, gutter - 8, lh), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number)
        p.setPen(QColor(fg))
        p.setFont(_font(12.5, bold=kind == "file"))
        p.drawText(QRectF(gutter, y, W - gutter - 4, lh), Qt.AlignmentFlag.AlignVCenter,
                   _elide(fm, text, W - gutter - 6))
        y += lh
    if not reader and visible and int(t * 2.5) % 2 == 0:
        p.fillRect(QRectF(gutter + min(W - gutter - 12, fm.horizontalAdvance(visible[-1][1][:40])) + 2,
                          y - lh + 3, 7, lh - 6), QColor(ACCENT[agent]))


def _paint_terminal(p: QPainter, W: int, H: int, feed: ScreenFeed, agent: str, t: float) -> None:
    p.fillRect(QRectF(0, 0, W, H), QColor("#050607"))
    top = _title_bar(p, W, H, "Windows PowerShell", "#3a7bd5", "▶")
    font = _font(12.5)
    p.setFont(font)
    fm = QFontMetricsF(font)
    lh = fm.height() + 1
    rows = int((H - top - 4) // lh)
    lines = list(feed.lines)
    visible = lines[max(0, len(lines) - rows):]
    y = top
    prompt = PROMPT.get(agent, "PS>")
    for kind, text in visible:
        if kind == "cmd":
            p.setPen(QColor(ACCENT[agent]))
            p.drawText(QPointF(6, y + lh - 4), prompt)
            p.setPen(QColor("#f0f0f0"))
            x = 6 + fm.horizontalAdvance(prompt) + 6
            p.drawText(QPointF(x, y + lh - 4), _elide(fm, text, W - x - 4))
        else:
            low = text.lower()
            colour = "#9be9a8" if ("passed" in low or low.startswith("ok")) and "failed" not in low else \
                "#ff8c8c" if any(w in low for w in ("failed", "error", "traceback", "exception")) else "#aab3c0"
            p.setPen(QColor(colour))
            p.drawText(QPointF(8, y + lh - 4), _elide(fm, text, W - 12))
        y += lh
    if int(t * 2) % 2 == 0:
        p.setPen(QColor(ACCENT[agent]))
        p.drawText(QPointF(6, min(H - 4, y + lh - 4)), "█")


def _wrap(p: QPainter, text: str, rect: QRectF, colour: str, font: QFont) -> float:
    p.setFont(font)
    p.setPen(QColor(colour))
    fm = QFontMetricsF(font)
    bounds = fm.boundingRect(rect, int(Qt.TextFlag.TextWordWrap), text)
    p.drawText(rect, int(Qt.TextFlag.TextWordWrap), text)
    return min(rect.height(), bounds.height())


def _paint_bit(p: QPainter, W: int, H: int, feed: ScreenFeed, agent: str, t: float) -> None:
    """The idle agent's own idle-time creation: an email to Jared, a search, a doodle, a chat, a note."""
    bit = feed.bit
    kind = bit.get("kind", "note")
    title, body = bit.get("title", ""), bit.get("body", "")
    # type it out over a few seconds, like he's actually writing it
    age = max(0.0, t - feed.bit.get("_t0", t))
    shown = body[: int(age * 45)] if age < len(body) / 45 else body
    if kind == "email":
        p.fillRect(QRectF(0, 0, W, H), QColor("#ffffff"))
        p.fillRect(QRectF(0, 0, W, 24), QColor("#0f5fb8"))
        p.setFont(_font(12, bold=True, family="Segoe UI"))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(8, 0, W - 16, 24), Qt.AlignmentFlag.AlignVCenter, "✉ New message — Hooli Mail")
        rows = (("To:", "Jared (management)"), ("Cc:", "HR" if "hr" in body.lower() else ""), ("Subject:", title))
        y = 28
        p.setFont(_font(11.5, family="Segoe UI"))
        fm = QFontMetricsF(p.font())
        for label, value in rows:
            if not value:
                continue
            p.setPen(QColor("#6b7280"))
            p.drawText(QPointF(10, y + fm.ascent()), label)
            p.setPen(QColor("#111827"))
            p.drawText(QPointF(66, y + fm.ascent()), _elide(fm, value, W - 76))
            y += fm.height() + 3
            p.setPen(QPen(QColor("#e5e7eb"), 1))
            p.drawLine(QPointF(8, y), QPointF(W - 8, y))
            y += 4
        _wrap(p, shown, QRectF(10, y + 4, W - 20, H - y - 34), "#1f2937", _font(12, family="Segoe UI"))
        p.fillRect(QRectF(10, H - 28, 64, 20), QColor("#0f5fb8"))
        p.setFont(_font(11, bold=True, family="Segoe UI"))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(10, H - 28, 64, 20), Qt.AlignmentFlag.AlignCenter, "Send")
    elif kind == "search":
        p.fillRect(QRectF(0, 0, W, H), QColor("#ffffff"))
        p.setFont(_font(18, bold=True, family="Segoe UI"))
        x = 12
        for ch, col in zip("Hooli", ("#4285f4", "#ea4335", "#fbbc05", "#4285f4", "#34a853")):
            p.setPen(QColor(col))
            p.drawText(QPointF(x, 30), ch)
            x += QFontMetricsF(p.font()).horizontalAdvance(ch)
        box = QRectF(10, 40, W - 20, 26)
        p.setPen(QPen(QColor("#dadce0"), 1))
        p.setBrush(QColor("#ffffff"))
        p.drawRoundedRect(box, 13, 13)
        typed = title[: int(age * 18)]
        cursor = "|" if int(t * 2) % 2 == 0 and len(typed) < len(title) else ""
        p.setFont(_font(12, family="Segoe UI"))
        fm = QFontMetricsF(p.font())
        p.setPen(QColor("#202124"))
        p.drawText(QRectF(24, 40, W - 48, 26), Qt.AlignmentFlag.AlignVCenter, _elide(fm, "🔍 " + typed + cursor, W - 50))
        if len(typed) >= len(title):
            _wrap(p, body, QRectF(14, 76, W - 28, H - 80), "#1a0dab", _font(12, family="Segoe UI"))
    elif kind == "doodle":
        p.fillRect(QRectF(0, 0, W, H), QColor("#fdf6d8"))
        p.setPen(QPen(QColor(120, 160, 220, 70), 1))
        for y in range(34, H, 16):
            p.drawLine(0, y, W, y)
        p.setPen(QPen(QColor(220, 90, 90, 90), 1))
        p.drawLine(28, 0, 28, H)
        p.setFont(_font(12, bold=True, family="Segoe Print"))
        p.setPen(QColor("#3b3b8f"))
        p.drawText(QRectF(34, 4, W - 40, 26), Qt.AlignmentFlag.AlignVCenter, title)
        lines = shown.splitlines()
        font = _font(13, family=MONO)
        p.setFont(font)
        fm = QFontMetricsF(font)
        y = 40
        for line in lines[:9]:
            p.drawText(QPointF(38, y + fm.ascent()), line)
            y += fm.height()
    elif kind == "chat":
        p.fillRect(QRectF(0, 0, W, H), QColor("#1a1d21"))
        p.fillRect(QRectF(0, 0, 70, H), QColor("#3f0e40"))
        p.setFont(_font(10.5, bold=True, family="Segoe UI"))
        p.setPen(QColor("#e9d7ea"))
        for i, ch in enumerate(("# general", "# engineering", "# random", "@ jared")):
            p.drawText(QPointF(6, 22 + i * 18), ch)
        p.setFont(_font(12, bold=True, family="Segoe UI"))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(80, 4, W - 90, 22), Qt.AlignmentFlag.AlignVCenter, title or "# engineering")
        p.setFont(_font(11.5, bold=True, family="Segoe UI"))
        p.setPen(QColor(ACCENT.get(agent, "#8fb8ff")))
        p.drawText(QPointF(80, 44), {"Codex": "gilfoyle", "Claude": "dinesh"}.get(agent, agent))
        _wrap(p, shown, QRectF(80, 50, W - 90, H - 56), "#d1d2d3", _font(12, family="Segoe UI"))
    else:  # note
        p.fillRect(QRectF(0, 0, W, H), QColor("#1e1e1e"))
        top = _title_bar(p, W, H, title or "notes.txt", "#c586c0", "📝")
        _wrap(p, shown, QRectF(10, top + 4, W - 20, H - top - 8), "#d4d4d4", _font(12.5, family=MONO))


OWNER_COLOUR = {"gilfoyle": "#e0564b", "codex": "#e0564b", "dinesh": "#6f9dff", "claude": "#6f9dff"}


def _paint_kanban(p: QPainter, W: int, H: int, feed: ScreenFeed, t: float) -> None:
    board = feed.board
    p.fillRect(QRectF(0, 0, W, H), QColor("#eef0f3"))
    p.fillRect(QRectF(0, 0, W, 22), QColor("#2f3a4b"))
    p.setFont(_font(12, bold=True, family="Segoe UI"))
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(8, 0, W - 16, 22), Qt.AlignmentFlag.AlignVCenter, "📋 KANBAN.md · shared board (courtesy of management)")
    asides = board.asides[-2:]
    foot = 18 * len(asides) + (6 if asides else 0)
    gap = 6
    col_w = (W - gap * 4) / 3
    top = 28
    for i, column in enumerate(("To do", "Doing", "Done")):
        x = gap + i * (col_w + gap)
        rect = QRectF(x, top, col_w, H - top - foot - 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#dfe3e9"))
        p.drawRoundedRect(rect, 5, 5)
        cards = board.columns.get(column, [])
        p.setFont(_font(11.5, bold=True, family="Segoe UI"))
        p.setPen(QColor("#44505f"))
        p.drawText(QRectF(x + 6, top + 2, col_w - 12, 16), Qt.AlignmentFlag.AlignVCenter,
                   f"{column.upper()}  {len(cards)}")
        y = top + 20
        title_font = _font(11.5, family="Segoe UI")
        aside_font = _font(10.5, family="Segoe UI")
        aside_font.setItalic(True)
        fm_t, fm_a = QFontMetricsF(title_font), QFontMetricsF(aside_font)
        for card in cards[-7:]:
            text_w = col_w - 16
            title_rect = fm_t.boundingRect(QRectF(0, 0, text_w, 60), int(Qt.TextFlag.TextWordWrap), card.title)
            title_h = min(title_rect.height(), fm_t.height() * 2 + 2)
            aside_h = fm_a.height() + 2 if card.aside else 0
            h = title_h + aside_h + 10
            if y + h > rect.bottom() - 2:
                break
            box = QRectF(x + 4, y, col_w - 8, h)
            hot = card.title in feed.highlight
            p.setPen(QPen(QColor("#f2c14e"), 2.2) if hot else QPen(QColor("#c9ced6"), 1))
            p.setBrush(QColor("#fffbe8") if hot else QColor("#ffffff"))
            p.drawRoundedRect(box, 4, 4)
            owner = card.owner.split(",")[0].strip().lower()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(OWNER_COLOUR.get(owner, "#9aa3ae")))
            p.drawRect(QRectF(box.left(), box.top() + 3, 3, box.height() - 6))
            p.setFont(title_font)
            p.setPen(QColor("#1f2530"))
            p.drawText(QRectF(box.left() + 8, box.top() + 4, text_w, title_h), int(Qt.TextFlag.TextWordWrap), card.title)
            if card.aside:
                p.setFont(aside_font)
                p.setPen(QColor("#6a7383"))
                p.drawText(QPointF(box.left() + 8, box.top() + 4 + title_h + fm_a.ascent()),
                           _elide(fm_a, f"“{card.aside}”", text_w))
            y += h + 4
    if asides:
        p.setFont(_font(11, family="Segoe UI"))
        fm = QFontMetricsF(p.font())
        y = H - foot
        for name, text in asides:
            colour = OWNER_COLOUR.get(name.lower(), "#44505f")
            p.setPen(QColor(colour))
            p.drawText(QPointF(8, y + fm.ascent()), _elide(fm, f"{name}: “{text}”", W - 16))
            y += 18


def _paint_browser(p: QPainter, W: int, H: int, feed: ScreenFeed, t: float) -> None:
    page = feed.page
    # chrome
    p.fillRect(QRectF(0, 0, W, H), QColor("#f4f5f7"))
    p.fillRect(QRectF(0, 0, W, 44), QColor("#dfe2e6"))
    p.fillRect(QRectF(8, 4, 170, 18), QColor("#f4f5f7"))
    p.setFont(_font(11, family="Segoe UI"))
    fm = QFontMetricsF(p.font())
    p.setPen(QColor("#303337"))
    p.drawText(QRectF(14, 4, 160, 18), Qt.AlignmentFlag.AlignVCenter, _elide(fm, page.title, 156))
    p.setBrush(QColor("#ffffff"))
    p.setPen(QPen(QColor("#c4c8ce"), 1))
    p.drawRoundedRect(QRectF(8, 24, W - 16, 17), 8, 8)
    p.setPen(QColor("#5f6368"))
    p.drawText(QRectF(18, 24, W - 36, 17), Qt.AlignmentFlag.AlignVCenter, _elide(fm, "🔒 " + page.url, W - 40))
    # site header
    p.fillRect(QRectF(0, 44, W, 30), QColor(page.colour))
    p.setFont(_font(15, bold=True, family="Segoe UI"))
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(12, 44, W - 24, 30), Qt.AlignmentFlag.AlignVCenter, page.site)
    # page
    age = t
    p.setFont(_font(13.5, bold=True, family="Segoe UI"))
    fm = QFontMetricsF(p.font())
    p.setPen(QColor("#1b1d21"))
    title_rect = fm.boundingRect(QRectF(12, 80, W - 24, 60), int(Qt.TextFlag.TextWordWrap), page.title)
    p.drawText(QRectF(12, 80, W - 24, title_rect.height() + 2), int(Qt.TextFlag.TextWordWrap), page.title)
    y = 84 + title_rect.height()
    p.setFont(_font(12, family="Segoe UI"))
    fm = QFontMetricsF(p.font())
    for line in page.lines:
        p.setPen(QColor("#1a0dab" if line.startswith("▸") else "#3c4043"))
        p.drawText(QPointF(14, y + fm.ascent()), _elide(fm, line, W - 28))
        y += fm.height() + 2
        if y > H - 10:
            break
    # a mouse pointer idly wandering around
    mx = W * (0.55 + 0.3 * math.sin(age * 0.7))
    my = H * (0.55 + 0.25 * math.sin(age * 1.1 + 1))
    arrow = QPainterPath(QPointF(mx, my))
    for dx, dy in ((0, 14), (4, 10), (7, 16), (9, 15), (6, 9), (11, 9)):
        arrow.lineTo(mx + dx, my + dy)
    arrow.closeSubpath()
    p.setPen(QPen(QColor("#ffffff"), 1))
    p.setBrush(QColor("#111111"))
    p.drawPath(arrow)


def screen_glass(p: QPainter, rect: QRectF) -> None:
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, QColor(255, 255, 255, 26))
    g.setColorAt(0.35, QColor(255, 255, 255, 0))
    p.fillRect(rect, g)
