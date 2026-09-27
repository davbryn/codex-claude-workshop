"""Overlays drawn on top of the stage in an episode: the exhibit freeze-frame and close-up subtitles."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from ..theatre.cast import ACCENT, CHARACTER


def _font(px: float, bold: bool = False, family: str = "Segoe UI") -> QFont:
    f = QFont(family)
    f.setPixelSize(max(1, int(px)))
    f.setBold(bold)
    return f


def exhibit_lines(e: dict, highlight: str) -> list[tuple[str, str, bool]]:
    """Up to 7 lines of the exhibit around the highlighted text: (kind, text, is_highlight)."""
    if e["kind"] == "diff":
        lines = [(k, t) for k, t in e.get("lines", []) if k in ("add", "del", "ctx")]
    else:
        lines = [("out", str(e.get("line") or e.get("command") or ""))]
    idx = next((i for i, (_, t) in enumerate(lines) if highlight and highlight.lower() in t.lower()), None)
    found = idx is not None
    if idx is None:
        idx = next((i for i, (k, _) in enumerate(lines) if k == "add"), 0)
    lo = max(0, idx - 3)
    return [(k, t, found and i == idx) for i, (k, t) in enumerate(lines[lo:lo + 7], start=lo)]


def paint_exhibit(p: QPainter, size: tuple[int, int], age: float, e: dict, lines, caption: str) -> None:
    """Freeze-frame: the guilty line, big, in a red box, with the writer's label above it."""
    w, h = size
    k = min(1.0, age / 0.18)
    p.save()
    p.fillRect(QRectF(0, 0, w, h), QColor(0, 0, 0, int(170 * k)))
    card = QRectF(w * 0.08, h * 0.22, w * 0.84, h * 0.6)
    p.setOpacity(k)
    p.setPen(QPen(QColor("#3a3f4b"), 2))
    p.setBrush(QColor("#0d1117"))
    p.drawRoundedRect(card, 14, 14)
    head = e.get("path") or ("test run" if e["kind"] == "tests" else "terminal")
    p.setFont(_font(h * 0.028, bold=True, family="Consolas"))
    p.setPen(QColor("#8b949e"))
    p.drawText(QRectF(card.left() + 24, card.top() + 14, card.width() - 48, h * 0.05), Qt.AlignmentFlag.AlignLeft, head)
    p.setFont(_font(h * 0.036, family="Consolas"))
    fm = p.fontMetrics()
    y = card.top() + h * 0.09
    for kind, text, hot in lines:
        prefix = {"add": "+ ", "del": "- "}.get(kind, "  ")
        row = QRectF(card.left() + 18, y, card.width() - 36, fm.height() + 6)
        if hot:
            grow = 1.0 + 0.05 * max(0.0, 1 - age / 0.35)
            p.save()
            c = row.center()
            p.translate(c)
            p.scale(grow, grow)
            p.translate(-c)
            p.setPen(QPen(QColor("#ff5b4f"), 3))
            p.setBrush(QColor(255, 91, 79, 45))
            p.drawRoundedRect(row.adjusted(-6, -2, 6, 2), 6, 6)
            p.restore()
        colour = "#ffd0cc" if hot else {"add": "#7ee787", "del": "#ff7b72"}.get(kind, "#c9d1d9")
        p.setPen(QColor(colour))
        p.drawText(row.adjusted(8, 3, -8, 0), Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(prefix + text.rstrip(), Qt.TextElideMode.ElideRight, int(row.width() - 16)))
        y += fm.height() + 8
        if y > card.bottom() - fm.height():
            break
    if caption:
        p.setFont(_font(h * 0.05, bold=True, family="Bahnschrift"))
        tw = p.fontMetrics().horizontalAdvance(caption) + 44
        box = QRectF(w / 2 - tw / 2, card.top() - h * 0.1, tw, h * 0.075)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f2c94c"))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor("#111111"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, caption)
    p.restore()


def paint_subtitle(p: QPainter, size: tuple[int, int], agent: str, text: str) -> None:
    w, h = size
    p.save()
    p.setFont(_font(h * 0.044, bold=True))
    fm = p.fontMetrics()
    flags = int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignHCenter)
    rect = fm.boundingRect(0, 0, int(w * 0.78), int(h), flags, text)
    box = QRectF(w / 2 - rect.width() / 2 - 24, h * 0.93 - rect.height() - 16, rect.width() + 48, rect.height() + 24)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 180))
    p.drawRoundedRect(box, 10, 10)
    p.setBrush(QColor(ACCENT[agent]))
    p.drawRect(QRectF(box.left(), box.top() + 8, 5, box.height() - 16))
    p.setPen(QColor("#ffffff"))
    p.drawText(box.adjusted(24, 12, -24, -12), flags, text)
    p.setFont(_font(h * 0.027, bold=True, family="Bahnschrift"))
    p.setPen(QColor(ACCENT[agent]))
    p.drawText(QRectF(box.left(), box.top() - h * 0.042, box.width(), h * 0.038), Qt.AlignmentFlag.AlignHCenter,
               CHARACTER[agent].upper())
    p.restore()
