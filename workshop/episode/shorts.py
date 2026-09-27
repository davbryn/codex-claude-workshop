"""The vertical (Shorts) frame: a headline on top, the 16:9 picture in the middle, big captions underneath."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen

from ..theatre.cast import ACCENT, CHARACTER
from .overlays import _font


def short_headline(plan: dict) -> tuple[str, str]:
    h = plan.get("headline") or {}
    top = f"{h.get('project', plan.get('project', ''))} in {h.get('language', '')}".upper().strip()
    rule = (h.get("limit") or "").upper()
    return top, (rule + "?!") if rule else ""


def _outlined(p: QPainter, rect: QRectF, text: str, px: float, fill: str, family: str = "Impact",
              flags: int = int(Qt.AlignmentFlag.AlignCenter)) -> None:
    """Big meme-style text: a fill with a thick black outline."""
    font = _font(px, bold=False, family=family)
    path = QPainterPath()
    p.save()
    p.setFont(font)
    metrics = p.fontMetrics()
    lines = []
    for word in text.split():  # simple word wrap
        if lines and metrics.horizontalAdvance(lines[-1] + " " + word) <= rect.width():
            lines[-1] += " " + word
        else:
            lines.append(word)
    total = len(lines) * metrics.height()
    y = rect.top() + (rect.height() - total) / 2 + metrics.ascent()
    for line in lines:
        x = rect.left() + (rect.width() - metrics.horizontalAdvance(line)) / 2
        path.addText(x, y, font, line)
        y += metrics.height()
    p.setPen(QPen(QColor("#000000"), px * 0.14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                  Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(fill))
    p.drawPath(path)
    p.restore()


def paint_short_frame(p: QPainter, size: tuple[int, int], frame: QImage, plan: dict,
                      saying: tuple[str, str, float] | None, wheel: tuple | None = None) -> None:
    w, h = size
    bg = QLinearGradient(0, 0, 0, h)
    bg.setColorAt(0, QColor("#1b1030"))
    bg.setColorAt(0.5, QColor("#0b0a10"))
    bg.setColorAt(1, QColor("#1b1030"))
    p.fillRect(QRectF(0, 0, w, h), bg)
    top, rule = short_headline(plan)
    _outlined(p, QRectF(30, 150, w - 60, 190), top, 88, "#ffffff")
    if rule:
        _outlined(p, QRectF(30, 330, w - 60, 150), rule, 104, "#f2c94c")
    if wheel is not None:  # the wheel, full width: it's the star of the Short
        from .wheel_paint import paint_wheel

        spin, angle, landed, title = wheel
        p.save()
        p.translate(0, 470)
        p.setClipRect(QRectF(0, 0, w, 1330))
        paint_wheel(p, (w, 1330), spin, angle, landed, title)
        p.restore()
        _outlined(p, QRectF(30, 150, w - 60, 190), short_headline(plan)[0], 88, "#ffffff")
        return
    pic_h = w * frame.height() / max(1, frame.width())
    pic = QRectF(0, 540, w, pic_h)
    p.drawImage(pic, frame)
    p.setPen(QPen(QColor("#f2c94c"), 6))
    p.drawLine(0, int(pic.top()), w, int(pic.top()))
    p.drawLine(0, int(pic.bottom()), w, int(pic.bottom()))
    if saying:
        agent, text, _until = saying
        p.setFont(_font(40, bold=True, family="Bahnschrift"))
        p.setPen(QColor(ACCENT[agent]))
        p.drawText(QRectF(0, pic.bottom() + 50, w, 60), Qt.AlignmentFlag.AlignCenter, CHARACTER[agent].upper())
        _outlined(p, QRectF(50, pic.bottom() + 110, w - 100, h - pic.bottom() - 260), text, 64, "#ffffff",
                  family="Segoe UI Black")
    p.setFont(_font(30, bold=True, family="Bahnschrift"))
    p.setPen(QColor("#9d8fc4"))
    p.drawText(QRectF(0, h - 110, w, 50), Qt.AlignmentFlag.AlignCenter, "GILFOYLE vs DINESH · WHEEL OF DESTINY")
