"""Challenge graphics: the Wheel of Destiny, full-screen cards, the RULE VIOLATION klaxon and the status bar."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient

from ..theatre.cast import CHARACTER
from .overlays import _font

WHEEL_TITLES = {"project": "SPIN {n}: THE PROJECT", "language": "SPIN {n}: THE LANGUAGE",
                "limit": "SPIN {n}: THE LIMITATION", "twist": "THE TWIST WHEEL"}


def wheel_title(spin: dict, n: int) -> str:
    if spin["wheel"] == "skill":
        return f"SPIN {n}: {CHARACTER[spin['who']].upper()}'S SKILL LEVEL"
    return WHEEL_TITLES[spin["wheel"]].format(n=n)


def wheel_angle(spin: dict, t: float, duration: float, turns: int = 5) -> tuple[float, int]:
    """(rotation in degrees, index of the slice under the pointer) at time t of a spin that stops at ``duration``.

    Slice i covers [i*step, (i+1)*step) degrees clockwise from the pointer (which sits at 0°, on the right) when the
    wheel is unrotated. Rotating by -(result + 0.5) * step brings the middle of the result to the pointer.
    """
    n = len(spin["slices"])
    step = 360.0 / n
    final = turns * 360 - (spin["result"] + 0.5) * step
    x = min(1.0, max(0.0, t / duration))
    angle = final * (1 - (1 - x) ** 3.2)
    under = int(((-angle) % 360) // step) % n
    return angle, under


def paint_wheel(p: QPainter, size: tuple[int, int], spin: dict, angle: float, landed: float | None,
                title: str) -> None:
    """The wheel at rotation ``angle`` (degrees). ``landed``: seconds since it stopped, or None while spinning."""
    w, h = size
    slices = spin["slices"]
    n = len(slices)
    p.save()
    bg = QRadialGradient(QPointF(w / 2, h * 0.55), w * 0.7)
    bg.setColorAt(0, QColor("#2a1f3d"))
    bg.setColorAt(1, QColor("#0a0710"))
    p.fillRect(QRectF(0, 0, w, h), bg)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(40):  # marquee bulbs, chasing
        on = (i + int(abs(angle) / 9)) % 3 == 0
        p.setBrush(QColor("#ffd966" if on else "#5a4a20"))
        x = (i + 0.5) * w / 40
        p.drawEllipse(QPointF(x, 10), 4, 4)
        p.drawEllipse(QPointF(x, h - 10), 4, 4)
    p.setFont(_font(h * 0.055, bold=True, family="Bahnschrift"))
    p.setPen(QColor("#f2c94c"))
    p.drawText(QRectF(0, h * 0.03, w, h * 0.08), Qt.AlignmentFlag.AlignCenter, title)
    cx, cy, r = w / 2, h * 0.53, min(h * 0.34, w * 0.44)
    p.save()
    p.translate(cx, cy)
    p.rotate(angle)
    step = 360.0 / n
    label_font = _font(max(10, min(h * 0.03, step * 0.55)), bold=True, family="Bahnschrift")
    for i, s in enumerate(slices):
        # Qt angles are counter-clockwise from 3 o'clock; ours run clockwise, hence the minus signs
        path = QPainterPath(QPointF(0, 0))
        path.arcTo(QRectF(-r, -r, 2 * r, 2 * r), -(i * step), -step)
        path.closeSubpath()
        colour = QColor(s.get("colour") or "#f2c94c")
        if i % 2:
            colour = colour.darker(125)
        p.setPen(QPen(QColor("#1a1a1a"), 2))
        p.setBrush(colour)
        p.drawPath(path)
        p.save()
        p.rotate(i * step + step / 2)
        p.setFont(label_font)
        p.setPen(QColor("#111111") if colour.lightness() > 140 else QColor("#ffffff"))
        p.drawText(QRectF(r * 0.18, -r * 0.08, r * 0.76, r * 0.16),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                   p.fontMetrics().elidedText(s["label"], Qt.TextElideMode.ElideRight, int(r * 0.74)))
        p.restore()
    p.setBrush(QColor("#111111"))
    p.setPen(QPen(QColor("#f2c94c"), 4))
    p.drawEllipse(QPointF(0, 0), r * 0.12, r * 0.12)
    p.restore()
    p.setPen(QPen(QColor("#f2c94c"), 6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(cx, cy), r + 3, r + 3)
    tip = QPointF(cx + r - 10, cy)  # the pointer, at 3 o'clock
    p.setPen(QPen(QColor("#111111"), 2))
    p.setBrush(QColor("#ffffff"))
    p.drawPolygon(QPolygonF([tip, QPointF(cx + r + 42, cy - 24), QPointF(cx + r + 42, cy + 24)]))
    if landed is not None:
        s = slices[spin["result"]]
        p.setOpacity(min(1.0, landed / 0.3))
        box = QRectF(w * 0.1, h * 0.7, w * 0.8, h * 0.23)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 230))
        p.drawRoundedRect(box, 14, 14)
        p.setFont(_font(h * 0.07, bold=True, family="Bahnschrift"))
        p.setPen(QColor(s.get("colour") or "#f2c94c").lighter(135))
        p.drawText(QRectF(box.left(), box.top() + h * 0.01, box.width(), h * 0.09), Qt.AlignmentFlag.AlignCenter,
                   s["label"].upper())
        p.setFont(_font(h * 0.027))
        p.setPen(QColor("#e8e2d6"))
        p.drawText(box.adjusted(30, h * 0.1, -30, -8),
                   int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignHCenter), s.get("rule", "")[:220])
    p.restore()


def paint_big_card(p: QPainter, size: tuple[int, int], age: float, heading: str, rows: list[tuple[str, str]],
                   footer: str = "", colour: str = "#f2c94c") -> None:
    """A full-screen card: a heading and label/value rows that land one by one (the premise, the rules)."""
    w, h = size
    k = min(1.0, age / 0.3)
    p.save()
    p.fillRect(QRectF(0, 0, w, h), QColor(8, 8, 12, int(238 * k)))
    p.setOpacity(k)
    p.setFont(_font(h * 0.07, bold=True, family="Bahnschrift"))
    p.setPen(QColor(colour))
    p.drawText(QRectF(0, h * 0.07, w, h * 0.1), Qt.AlignmentFlag.AlignCenter, heading)
    y = h * 0.23
    for i, (label, value) in enumerate(rows):
        p.setOpacity(k * max(0.0, min(1.0, (age - 0.3 - i * 0.35) / 0.3)))
        p.setFont(_font(h * 0.028, bold=True, family="Bahnschrift"))
        p.setPen(QColor("#9aa0aa"))
        p.drawText(QRectF(w * 0.04, y, w * 0.34, h * 0.08),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), label.upper())
        p.setFont(_font(h * 0.046, bold=True))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(w * 0.41, y, w * 0.56, h * 0.08),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), value)
        y += h * 0.1
    if footer:
        p.setOpacity(k * max(0.0, min(1.0, (age - 0.4 - len(rows) * 0.35) / 0.4)))
        p.setFont(_font(h * 0.03, family="Georgia"))
        p.setPen(QColor("#cfc6b6"))
        p.drawText(QRectF(w * 0.1, h * 0.8, w * 0.8, h * 0.14),
                   int(Qt.TextFlag.TextWordWrap) | int(Qt.AlignmentFlag.AlignHCenter), footer)
    p.restore()


def paint_violation(p: QPainter, size: tuple[int, int], age: float, text: str, detail: str,
                    colour: str = "#b3120f") -> None:
    """RULE VIOLATION (or PLOT TWIST): strobe, hazard stripes, klaxon banner."""
    w, h = size
    p.save()
    pulse = 0.5 + 0.5 * math.sin(age * 14)
    base = QColor(colour)
    strobe = QColor(base)
    strobe.setAlpha(int(60 + 70 * pulse))
    p.fillRect(QRectF(0, 0, w, h), strobe)
    band = QRectF(0, h * 0.35, w, h * 0.3)
    g = QLinearGradient(band.topLeft(), band.bottomLeft())
    g.setColorAt(0, base)
    g.setColorAt(1, base.darker(220))
    p.fillRect(band, g)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#f2c94c"))
    offset = (age * 120) % 60
    for i in range(-1, int(w / 60) + 2):
        x = i * 60 - offset
        for top in (band.top(), band.bottom() - 12):
            p.drawPolygon(QPolygonF([QPointF(x, top), QPointF(x + 30, top), QPointF(x + 18, top + 12),
                                     QPointF(x - 12, top + 12)]))
    scale = 1.0 + 0.1 * max(0.0, 1 - age / 0.25)
    p.translate(w / 2, h / 2)
    p.scale(scale, scale)
    p.translate(-w / 2, -h / 2)
    p.setFont(_font(h * 0.09, bold=True, family="Impact"))
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(0, band.top() + h * 0.03, w, h * 0.13), Qt.AlignmentFlag.AlignCenter, text)
    p.setFont(_font(h * 0.032, bold=True, family="Consolas"))
    p.setPen(QColor("#ffe0de"))
    p.drawText(QRectF(w * 0.05, band.top() + h * 0.17, w * 0.9, h * 0.08), Qt.AlignmentFlag.AlignCenter,
               p.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideMiddle, int(w * 0.9)))
    p.restore()


def paint_hud(p: QPainter, size: tuple[int, int], hud: dict) -> None:
    """The challenge status bar, top left: the rules, violations, tests, turn."""
    w, h = size
    p.save()
    p.setFont(_font(h * 0.024, bold=True, family="Bahnschrift"))
    fm = p.fontMetrics()
    rules = hud.get("rules", "")
    right = f"RULE BREAKS {hud.get('violations', 0)}   TESTS {hud.get('tests', '-')}   TURN {hud.get('turn', '-')}"
    width = min(w - 28, fm.horizontalAdvance(rules) + fm.horizontalAdvance(right) + 70)
    box = QRectF(14, 14, width, fm.height() + 16)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 175))
    p.drawRoundedRect(box, 8, 8)
    p.setPen(QColor("#f2c94c"))
    p.drawText(box.adjusted(14, 0, 0, 0), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), rules)
    p.setPen(QColor("#ff8a80") if hud.get("violations") else QColor("#b8f5c3"))
    p.drawText(box.adjusted(0, 0, -14, 0), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), right)
    p.restore()
