"""Regenerate the bundled placeholder avatars in assets/.

    python tools/make_avatars.py

Replace assets/codex.png / assets/claude.png with your own images any time.
"""

import math
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QRadialGradient

SIZE = 256
ASSETS = Path(__file__).resolve().parents[1] / "assets"


def pen(color, width) -> QPen:
    result = QPen(QColor(color), width)
    result.setCapStyle(Qt.PenCapStyle.RoundCap)
    result.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return result


def canvas() -> tuple[QImage, QPainter]:
    img = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return img, p


def codex() -> QImage:
    """Dark terminal robot."""
    img, p = canvas()
    p.setBrush(QColor("#11161c"))
    p.setPen(QPen(QColor("#39d98a"), 6))
    p.drawRoundedRect(QRectF(20, 20, 216, 216), 40, 40)
    # antenna
    p.setPen(pen("#39d98a", 6))
    p.drawLine(QPointF(128, 20), QPointF(128, 44))
    # screen face
    p.setBrush(QColor("#0b2a1c"))
    p.setPen(QPen(QColor("#1f7a50"), 4))
    p.drawRoundedRect(QRectF(48, 62, 160, 120), 18, 18)
    # eyes: terminal prompt ">" and block cursor
    p.setPen(pen("#39d98a", 10))
    path = QPainterPath(QPointF(72, 92))
    path.lineTo(96, 112)
    path.lineTo(72, 132)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#39d98a"))
    p.drawRect(QRectF(150, 96, 30, 38))
    # mouth / underscore
    p.drawRoundedRect(QRectF(104, 152, 48, 8), 4, 4)
    # bolts
    for x in (34, 222):
        p.drawEllipse(QPointF(x, 128), 6, 6)
    p.end()
    return img


def claude() -> QImage:
    """Warm abstract bloom / brain."""
    img, p = canvas()
    grad = QRadialGradient(QPointF(128, 118), 128)
    grad.setColorAt(0, QColor("#ffd2b0"))
    grad.setColorAt(0.6, QColor("#e98a5a"))
    grad.setColorAt(1, QColor("#b8532c"))
    p.setBrush(grad)
    p.setPen(QPen(QColor("#7a2f14"), 5))
    p.drawEllipse(QRectF(20, 20, 216, 216))
    # petals / neural lobes
    p.setPen(pen(QColor(255, 244, 232, 220), 7))
    centre = QPointF(128, 120)
    for i in range(8):
        a = i * math.pi / 4
        end = QPointF(centre.x() + math.cos(a) * 62, centre.y() + math.sin(a) * 62)
        p.drawLine(centre, end)
        p.setBrush(QColor("#fff4e8"))
        p.drawEllipse(end, 8, 8)
    p.setBrush(QColor("#fff4e8"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(centre, 20, 20)
    p.end()
    return img


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    ASSETS.mkdir(exist_ok=True)
    codex().save(str(ASSETS / "codex.png"))
    claude().save(str(ASSETS / "claude.png"))
    print("Wrote", ASSETS / "codex.png", "and", ASSETS / "claude.png")
