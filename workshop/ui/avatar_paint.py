"""Procedural, vector avatars (no image assets, no brand logos).

Both characters are drawn in a 100×100 unit box anchored at the feet, so they
scale cleanly. Faces are drawn from continuous Pose parameters (lid cover,
slant, mouth curve/opening…), so every in-between expression renders and
transitions morph smoothly.
"""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

from ..theatre.avatar_state import Pose

CODEX_GREEN = QColor("#39d98a")
CODEX_GLOW = QColor("#7dffc4")
CLAUDE_BASE = QColor("#f39a6b")
CLAUDE_DARK = QColor("#8e3b1e")
INK = QColor("#2b1a14")
SHOULDERS = {"Codex": ((31, 74), (69, 74)), "Claude": ((21, 64), (79, 64))}


def _pen(color, width: float, cap=Qt.PenCapStyle.RoundCap) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(cap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _alpha(color, a: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


def _font(px: float, bold: bool = True, family: str = "Segoe UI") -> QFont:
    f = QFont(family)
    f.setPixelSize(max(1, int(px)))
    f.setBold(bold)
    return f


def paint_avatar(p: QPainter, rect: QRectF, agent: str, pose: Pose, active: bool = False) -> None:
    """Draw ``agent`` into ``rect`` (feet on the bottom edge)."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = min(rect.width(), rect.height()) / 100.0
    p.translate(rect.center().x() - 50 * s, rect.bottom() - 100 * s)
    p.scale(s, s)
    p.translate(50 + pose.shake + pose.lean, 98 + pose.bob)
    p.rotate(pose.tilt)
    p.scale(1 / math.sqrt(max(pose.squash, 0.5)), pose.squash)
    p.translate(-50, -98)
    if agent == "Codex":
        _paint_codex(p, pose, active)
    else:
        _paint_claude(p, pose, active)
    _paint_props(p, pose, agent)
    p.restore()


def avatar_pixmap(agent: str, size: int, pose: Pose | None = None) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    if pose is None:
        pose = Pose(mouth_curve=0.6, mouth_asym=0.7 if agent == "Codex" else 0.0,
                    brow_asym=0.6 if agent == "Codex" else 0.0)
    paint_avatar(painter, QRectF(0, 0, size, size), agent, pose)
    painter.end()
    return pix


# --- shared mouth geometry -----------------------------------------------------------

def _mouth_paths(pose: Pose, mx: float, my: float, scale: float) -> tuple[QPainterPath, QPainterPath | None]:
    """Returns (lip line, filled opening or None) for the parametric mouth."""
    w = 7.0 * pose.mouth_width * scale
    curve = pose.mouth_curve
    asym = pose.mouth_asym
    left = QPointF(mx - w, my - curve * 2.8 * scale + asym * 1.0 * scale)
    right = QPointF(mx + w, my - curve * 2.8 * scale - asym * 3.2 * scale)
    ctrl_y = my + curve * 4.5 * scale
    wave = pose.mouth_wave

    def curve_points(control_y: float, n: int = 10) -> list[QPointF]:
        pts = []
        for i in range(n + 1):
            u = i / n
            x = (1 - u) ** 2 * left.x() + 2 * (1 - u) * u * mx + u * u * right.x()
            y = (1 - u) ** 2 * left.y() + 2 * (1 - u) * u * control_y + u * u * right.y()
            if wave > 0.02 and 0 < i < n:
                y += wave * 1.5 * scale * (1 if i % 2 else -1)
            pts.append(QPointF(x, y))
        return pts

    upper = curve_points(ctrl_y)
    line = QPainterPath(upper[0])
    for pt in upper[1:]:
        line.lineTo(pt)
    if pose.mouth_open < 0.06:
        return line, None
    lower = curve_points(ctrl_y + pose.mouth_open * 10 * scale + 1.0)
    opening = QPainterPath(upper[0])
    for pt in upper[1:]:
        opening.lineTo(pt)
    for pt in reversed(lower):
        opening.lineTo(pt)
    opening.closeSubpath()
    return line, opening


def _draw_arms(p: QPainter, agent: str, pose: Pose, front: bool, outer, inner, hand, rim,
               widths: tuple[float, float], hand_r: float) -> None:
    shoulders = SHOULDERS[agent]
    for (elbow, hand_pt, is_front), shoulder in ((pose.arm_left, shoulders[0]), (pose.arm_right, shoulders[1])):
        if is_front != front:
            continue
        path = QPainterPath(QPointF(*shoulder))
        path.quadTo(QPointF(*elbow), QPointF(*hand_pt))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(outer, widths[0]))
        p.drawPath(path)
        p.setPen(_pen(inner, widths[1]))
        p.drawPath(path)
        p.setPen(_pen(rim, 0.9))
        p.setBrush(QColor(hand))
        p.drawEllipse(QPointF(*hand_pt), hand_r, hand_r)


# --- Codex --------------------------------------------------------------------------------

def _paint_codex(p: QPainter, pose: Pose, active: bool) -> None:
    t = pose.time
    arm_args = ("#0b1016", "#26323f", "#33424f", _alpha(CODEX_GREEN, 0.7), (7.5, 5.6), 3.6)
    _draw_arms(p, "Codex", pose, False, *arm_args)

    torso = QRectF(31, 69, 38, 27)
    grad = QLinearGradient(0, 69, 0, 96)
    grad.setColorAt(0, QColor("#2a3847"))
    grad.setColorAt(1, QColor("#121920"))
    p.setPen(_pen("#070a0d", 1.2))
    p.setBrush(grad)
    p.drawRoundedRect(torso, 7, 7)
    p.setPen(_pen(_alpha("#ffffff", 0.06), 1))
    p.drawLine(QPointF(35, 71.5), QPointF(65, 71.5))
    p.setPen(_pen(_alpha(CODEX_GREEN, 0.35), 0.8))
    p.setBrush(QColor("#0a0f13"))
    p.drawRoundedRect(QRectF(39.5, 76, 21, 9), 2.5, 2.5)
    for i, colour in enumerate(("#39d98a", "#f5c542", "#4aa8ff")):
        lit = ((int(t * 4) + i) % 3 == 0) if active else i == 0
        p.setPen(Qt.PenStyle.NoPen)
        if lit:
            p.setBrush(_alpha(colour, 0.35))
            p.drawEllipse(QPointF(44.5 + i * 5.5, 80.5), 2.8, 2.8)
        p.setBrush(QColor(colour) if lit else QColor(colour).darker(320))
        p.drawEllipse(QPointF(44.5 + i * 5.5, 80.5), 1.5, 1.5)

    p.setBrush(QColor("#161e26"))
    p.setPen(_pen("#070a0d", 0.8))
    p.drawRoundedRect(QRectF(44, 63, 12, 8), 2, 2)

    # antenna (springy)
    state = pose.state
    antenna_colour = {"error": "#ff5d5d", "reviewing": "#f5c542", "confused": "#f5c542", "disagreeing": "#ff8a5c",
                      "annoyed": "#ff8a5c", "sleeping": "#4a6a8a"}.get(state, "#39d98a")
    pulse = 0.55 + 0.45 * math.sin(t * (6 if active else 2))
    p.save()
    p.translate(50, 13)
    p.rotate(max(-35.0, min(35.0, pose.wobble)))
    p.setPen(_pen("#33424f", 2.2))
    p.drawLine(QPointF(0, 0), QPointF(0, -7.5))
    glow = QRadialGradient(QPointF(0, -9.5), 7)
    glow.setColorAt(0, _alpha(antenna_colour, 0.55 * pulse * (0.4 + pose.glow)))
    glow.setColorAt(1, _alpha(antenna_colour, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QPointF(0, -9.5), 7, 7)
    p.setBrush(QColor(antenna_colour).lighter(110 + int(40 * pulse)))
    p.drawEllipse(QPointF(0, -9.5), 2.6, 2.6)
    p.restore()

    head = QRectF(14.5, 12, 71, 54)
    if active:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_alpha(CODEX_GREEN, 0.16 * (0.7 + 0.3 * pulse)), 6))
        p.drawRoundedRect(head, 13, 13)
    shell = QLinearGradient(0, 12, 0, 66)
    shell.setColorAt(0, QColor("#35475a"))
    shell.setColorAt(0.5, QColor("#1f2a36"))
    shell.setColorAt(1, QColor("#121920"))
    p.setBrush(shell)
    p.setPen(_pen(_alpha(CODEX_GREEN, 0.85), 1.6))
    p.drawRoundedRect(head, 13, 13)
    p.setPen(_pen("#070a0d", 0.8))
    p.setBrush(QColor("#2c3a48"))
    for x in (11.5, 85.5):
        p.drawRoundedRect(QRectF(x, 31, 3, 12), 1.5, 1.5)
    p.setPen(_pen(_alpha("#ffffff", 0.10), 1.2))
    p.drawLine(QPointF(24, 14.5), QPointF(76, 14.5))

    screen = QRectF(21, 18.5, 58, 42)
    sg = QLinearGradient(0, 18, 0, 60)
    sg.setColorAt(0, QColor("#0b3a26"))
    sg.setColorAt(1, QColor("#031a10"))
    p.setBrush(sg)
    p.setPen(_pen("#02100a", 1.2))
    p.drawRoundedRect(screen, 8, 8)
    vignette = QRadialGradient(QPointF(50, 39), 38)
    vignette.setColorAt(0, _alpha(CODEX_GREEN, 0.10 + 0.08 * pose.glow))
    vignette.setColorAt(1, _alpha("#000000", 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(vignette)
    p.drawRoundedRect(screen, 8, 8)
    scale = abs(p.transform().m22()) or 1.0
    if pose.code_rain > 0.03:
        rain = _code_rain(scale)
        offset = (t * 9) % 42
        half = rain.height() / 2
        p.save()
        p.setOpacity(p.opacity() * 0.3 * pose.code_rain)
        p.drawPixmap(screen, rain, QRectF(0, (42 - offset) / 42 * half, rain.width(), half))
        p.restore()
    if pose.glitch > 0.05:
        rng = random.Random(int(t * 14))
        jitter = (rng.random() - 0.5) * 3 * pose.glitch
        for colour, dx in (("#ff3b6b", 1.3 + jitter), ("#3bd5ff", -1.3 - jitter)):
            p.save()
            p.translate(dx, 0)
            p.setOpacity(p.opacity() * 0.45 * pose.glitch)
            _codex_face(p, pose, QColor(colour))
            p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(3):
            y = 19 + rng.random() * 40
            p.setBrush(_alpha("#bfffe0", 0.12 * pose.glitch))
            p.drawRect(QRectF(21, y, 58, 0.8 + rng.random() * 2.2))
    _codex_face(p, pose, CODEX_GLOW)
    overlay = _screen_overlay(scale)
    p.drawPixmap(screen, overlay, QRectF(overlay.rect()))

    _draw_arms(p, "Codex", pose, True, *arm_args)


_OVERLAYS: dict[int, QPixmap] = {}
_RAIN: dict[int, QPixmap] = {}


def _screen_overlay(scale: float) -> QPixmap:
    key = max(1, int(round(scale * 10)))
    if key not in _OVERLAYS:
        s = key / 10
        pix = QPixmap(max(1, int(58 * s)), max(1, int(42 * s)))
        pix.fill(Qt.GlobalColor.transparent)
        q = QPainter(pix)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        q.scale(s, s)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, 58, 42), 8, 8)
        q.setClipPath(clip)
        q.setPen(_pen(_alpha("#000000", 0.28), 0.55, Qt.PenCapStyle.FlatCap))
        y = 0.8
        while y < 42:
            q.drawLine(QPointF(0, y), QPointF(58, y))
            y += 2.2
        glare = QPainterPath(QPointF(0, 0))
        glare.lineTo(27, 0)
        glare.lineTo(7, 42)
        glare.lineTo(0, 42)
        glare.closeSubpath()
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(_alpha("#ffffff", 0.045))
        q.drawPath(glare)
        q.end()
        if len(_OVERLAYS) > 12:
            _OVERLAYS.clear()
        _OVERLAYS[key] = pix
    return _OVERLAYS[key]


def _code_rain(scale: float) -> QPixmap:
    """A tileable texture of faint code glyphs: two identical 42-unit halves stacked."""
    key = max(1, int(round(scale * 10)))
    if key not in _RAIN:
        s = key / 10
        pix = QPixmap(max(1, int(58 * s)), max(2, int(84 * s)))
        pix.fill(Qt.GlobalColor.transparent)
        q = QPainter(pix)
        q.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        q.scale(s, s)
        q.setFont(_font(3.6, bold=False, family="Consolas"))
        rng = random.Random(7)
        tokens = ["def", "if", "{}", "=>", "0x1f", "ok", "();", "[]", "for", "i++", "!=", "fn", "::", "01", "let", "&&"]
        lines = ["  ".join(rng.choice(tokens) for _ in range(6)) for _ in range(10)]
        for half in (0, 42):
            for row, text in enumerate(lines):
                q.setPen(_alpha(CODEX_GLOW, 0.5 + 0.5 * ((row * 37) % 10) / 10))
                q.drawText(QPointF(2 + (row % 3), half + 4 + row * 4.2), text)
        q.end()
        if len(_RAIN) > 12:
            _RAIN.clear()
        _RAIN[key] = pix
    return _RAIN[key]


def _codex_face(p: QPainter, pose: Pose, glow: QColor) -> None:
    t = pose.time
    lx, ly = pose.look_x * 4.5, pose.look_y * 3.2
    far = 1 if pose.look_x >= 0 else -1
    for side in (-1, 1):
        cx, cy = 50 + side * 11 + lx, 35 + ly
        raise_ = pose.brow_raise * 3.6 + (pose.brow_asym * 4.0 if side == far else 0)
        by = cy - 10.5 * pose.eye_scale - raise_
        inner_drop = pose.brow_angle * 3.5
        p.setPen(_pen(_alpha(glow, 0.9), 2.1))
        p.drawLine(QPointF(cx + side * 4.5, by), QPointF(cx - side * 4.5, by + inner_drop))
        _codex_eye(p, pose, side, cx, cy, glow)

    mx, my = 50 + lx * 0.5, 50.5 + ly * 0.4
    line, opening = _mouth_paths(pose, mx, my, 1.0)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if opening is not None:
        p.setPen(_pen(_alpha(glow, 0.7), 1.2))
        p.setBrush(_alpha(glow, 0.85))
        p.drawPath(opening)
    else:
        p.setPen(_pen(glow, 2.3))
        p.drawPath(line)
    if pose.props.get("keyboard", 0) > 0.5 and int(t * 2.5) % 2 == 0:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha(glow, 0.9))
        p.drawRect(QRectF(mx + 10, my - 4, 3.2, 6.5))
    if pose.blush > 0.05:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha("#ff7aa8", pose.blush * 0.8))
        for x in (26.5, 66.5):
            for i in range(3):
                p.drawRect(QRectF(x + i * 2.4, 44 - (i % 2) * 0.6, 1.6, 1.6))


def _codex_eye(p: QPainter, pose: Pose, side: int, cx: float, cy: float, glow: QColor) -> None:
    w, h = 8.0 * pose.eye_scale, 11.5 * pose.eye_scale
    top = cy - h / 2 + h * min(0.85, pose.lid_top)
    bottom = cy + h / 2 - h * pose.lid_bottom
    mid = (top + bottom) / 2
    height = max(0.0, (bottom - top) * pose.eye_open)
    top, bottom = mid - height / 2, mid + height / 2
    rect_alpha = 1.0 - pose.happy
    if height < 1.4:
        if rect_alpha > 0.02:
            path = QPainterPath(QPointF(cx - 4.5, mid + 0.5))
            path.quadTo(cx, mid + 3, cx + 4.5, mid + 0.5)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(_pen(_alpha(glow, rect_alpha), 2.2))
            p.drawPath(path)
    elif rect_alpha > 0.02:
        inner_x = cx - side * w / 2
        outer_x = cx + side * w / 2
        slant = max(0.0, min(height - 1.0, pose.lid_slant * 4.2))
        poly = QPainterPath(QPointF(outer_x, top))
        poly.lineTo(inner_x, top + slant)
        poly.lineTo(inner_x, bottom)
        poly.lineTo(outer_x, bottom)
        poly.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha(glow, 0.25 * rect_alpha))
        p.drawRoundedRect(QRectF(cx - w / 2 - 1.6, top - 1.6, w + 3.2, height + 3.2), 3, 3)
        p.setBrush(_alpha(glow, rect_alpha))
        p.drawPath(poly)
        if height > 6:
            p.setBrush(_alpha("#ffffff", 0.55 * rect_alpha))
            p.drawRect(QRectF(cx - w / 2 + 1.2, top + 1.2 + slant * 0.5, 2, 2))
    if pose.happy > 0.02:
        path = QPainterPath(QPointF(cx - 4.8, cy + 2.5))
        path.lineTo(cx, cy - 3)
        path.lineTo(cx + 4.8, cy + 2.5)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_alpha(glow, 0.35 * pose.happy), 5))
        p.drawPath(path)
        p.setPen(_pen(_alpha(glow, pose.happy), 2.6))
        p.drawPath(path)


# --- Claude ------------------------------------------------------------------------------

def _paint_claude(p: QPainter, pose: Pose, active: bool) -> None:
    t = pose.time
    arm_args = (CLAUDE_DARK, "#ec8c5e", "#f7a77a", CLAUDE_DARK, (10.5, 8.6), 4.6)
    _draw_arms(p, "Claude", pose, False, *arm_args)

    droop = {"embarrassed": 38, "error": 55, "sleeping": 48, "confused": 20}.get(pose.state, 0)
    perk = -12 if pose.state in ("celebrating", "complete", "pleased", "surprised") else 0
    sway = math.sin(t * 2.2) * 5 + droop + perk + pose.wobble
    p.save()
    p.translate(50, 27)
    p.rotate(max(-70.0, min(80.0, sway * 0.45)))
    stem = QPainterPath(QPointF(0, 2))
    stem.quadTo(-1, -7, 1.5, -12)
    p.setPen(_pen("#7a4a22", 2.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(stem)
    p.translate(1.5, -12)
    for angle, size in ((-40 + sway * 0.4, 1.0), (35 + sway * 0.3, 0.85)):
        p.save()
        p.rotate(angle)
        leaf = QPainterPath(QPointF(0, 0))
        leaf.cubicTo(3 * size, -3 * size, 9 * size, -3 * size, 12 * size, 0)
        leaf.cubicTo(9 * size, 3 * size, 3 * size, 3 * size, 0, 0)
        lg = QLinearGradient(0, -3, 0, 3)
        lg.setColorAt(0, QColor("#ffe08a"))
        lg.setColorAt(1, QColor("#f2b33d"))
        p.setBrush(lg)
        p.setPen(_pen("#b87a14", 0.9))
        p.drawPath(leaf)
        p.setPen(_pen(_alpha("#b87a14", 0.6), 0.6))
        p.drawLine(QPointF(1, 0), QPointF(10 * size, 0))
        p.restore()
    p.restore()

    body = QRectF(18.5, 24, 63, 72)
    if active:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_alpha("#ffb38a", 0.2 * (0.7 + 0.3 * math.sin(t * 4))), 6))
        p.drawEllipse(body)
    grad = QRadialGradient(QPointF(40, 44), 58, QPointF(38, 38))
    grad.setColorAt(0, QColor("#ffe0c8"))
    grad.setColorAt(0.35, QColor("#f8b085"))
    grad.setColorAt(0.8, QColor("#e27a4d"))
    grad.setColorAt(1, QColor("#b85834"))
    p.setBrush(grad)
    p.setPen(_pen(_alpha(CLAUDE_DARK, 0.75), 1.4))
    p.drawEllipse(body)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_alpha("#fff1e6", 0.28))
    p.drawEllipse(QPointF(50, 80), 15, 10)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pen(_alpha("#fff4ea", 0.35), 1.6))
    p.drawArc(QRectF(23, 28, 54, 60), 100 * 16, 60 * 16)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_alpha("#ff5f86", 0.18 + pose.blush * 0.55))
    for x in (29.5, 70.5):
        p.drawEllipse(QPointF(x, 63), 6.2, 3.6)

    _claude_face(p, pose)
    _draw_arms(p, "Claude", pose, True, *arm_args)

    if pose.steam > 0.05:
        p.setPen(Qt.PenStyle.NoPen)
        for side in (-1, 1):
            for i in range(3):
                phase = (t * 0.9 + i / 3 + (0.15 if side > 0 else 0)) % 1
                c = QPointF(50 + side * (22 + phase * 8), 24 - phase * 20)
                r = 2.5 + phase * 5
                a = pose.steam * (1 - phase) ** 0.8
                p.setPen(_pen(_alpha("#8f9aa8", 0.7 * a), 0.8))
                p.setBrush(_alpha("#f4f7fb", 0.92 * a))
                p.drawEllipse(c, r, r)


def _claude_face(p: QPainter, pose: Pose) -> None:
    lx, ly = pose.look_x * 3.0, pose.look_y * 2.6
    far = 1 if pose.look_x >= 0 else -1
    for side in (-1, 1):
        cx, cy = 50 + side * 11.5 + lx * 0.6, 50 + ly * 0.6
        raise_ = pose.brow_raise * 4.2 + (pose.brow_asym * 4 if side == far else 0)
        by = cy - 13.5 * pose.eye_scale - raise_
        inner = pose.brow_angle * 4.2
        brow = QPainterPath(QPointF(cx + side * 6.5, by + 0.6))
        brow.quadTo(cx, by - 3.2 + inner * 0.3, cx - side * 6.5, by + inner)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen("#5c2410", 2.8))
        p.drawPath(brow)
        _claude_eye(p, pose, side, cx, cy, lx, ly)

    mx, my = 50 + lx * 0.4, 68.5 + ly * 0.3
    dark = QColor("#5a1d12")
    line, opening = _mouth_paths(pose, mx, my, 1.0)
    if opening is None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(dark, 2.4))
        p.drawPath(line)
        return
    p.setPen(_pen(dark, 1.4))
    p.setBrush(dark)
    p.drawPath(opening)
    box = opening.boundingRect()
    p.setPen(Qt.PenStyle.NoPen)
    if box.height() > 3.5:
        p.setBrush(QColor("#ff7b7b"))
        p.drawEllipse(QPointF(mx, box.bottom() - box.height() * 0.3), box.width() * 0.26, box.height() * 0.22)
    if pose.teeth > 0.05 and box.height() > 3:
        p.setBrush(_alpha("#fffaf3", pose.teeth))
        top_y = box.top() + box.height() * 0.08
        p.drawRoundedRect(QRectF(mx - box.width() * 0.36, top_y, box.width() * 0.72, min(2.4, box.height() * 0.25)),
                          0.8, 0.8)


def _claude_eye(p: QPainter, pose: Pose, side: int, cx: float, cy: float, lx: float, ly: float) -> None:
    rx, ry = 7.4 * pose.eye_scale, 9.2 * pose.eye_scale
    sclera = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)
    open_alpha = 1.0 - pose.happy
    cover = max(1.0 - pose.eye_open, pose.lid_top)
    if cover > 0.92:
        if open_alpha > 0.02:
            path = QPainterPath(QPointF(cx - 6, cy))
            path.quadTo(cx, cy + 4.5, cx + 6, cy)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(_pen(_alpha(INK, open_alpha), 2.4))
            p.drawPath(path)
    elif open_alpha > 0.02:
        p.save()
        p.setOpacity(p.opacity() * open_alpha)
        p.setPen(_pen(_alpha(CLAUDE_DARK, 0.55), 1.0))
        p.setBrush(QColor("#fffaf4"))
        p.drawEllipse(sclera)
        pr = 4.2 * pose.pupil * pose.eye_scale
        ring = pr + 1.1
        px = cx + max(-(rx - ring - 0.6), min(rx - ring - 0.6, lx * 1.2))
        py = cy + max(-(ry - ring - 0.6), min(ry - ring - 0.6, ly * 1.4 + 0.8))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#6b3a24"))
        p.drawEllipse(QPointF(px, py), ring, ring)
        p.setBrush(INK)
        p.drawEllipse(QPointF(px, py), pr, pr)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(px - 1.5, py - 1.8), 1.5, 1.5)
        p.drawEllipse(QPointF(px + 1.6, py + 1.4), 0.6, 0.6)
        lid_rect = sclera.adjusted(-0.4, -0.4, 0.4, 0.4)
        p.setBrush(QColor("#ee9164"))
        if cover > 0.02:
            k = max(-1.0, min(1.0, 1 - 2 * cover))
            theta = math.degrees(math.asin(k))
            p.drawChord(lid_rect, int(theta * 16), int((180 - 2 * theta) * 16))
        if pose.lid_bottom > 0.02:
            k = max(-1.0, min(1.0, 1 - 2 * pose.lid_bottom))
            theta = math.degrees(math.asin(k))
            p.drawChord(lid_rect, int((180 + theta) * 16), int((180 - 2 * theta) * 16))
        if pose.lid_slant > 0.05:
            drop = min(1.0, pose.lid_slant)
            inner_low = cy - ry * (0.75 - 0.7 * drop)
            outer_low = cy - ry * 0.8
            lid_path = QPainterPath(QPointF(cx - rx - 1, cy - ry - 1))
            lid_path.lineTo(cx + rx + 1, cy - ry - 1)
            if side < 0:
                lid_path.lineTo(cx + rx + 1, inner_low)
                lid_path.lineTo(cx - rx - 1, outer_low)
            else:
                lid_path.lineTo(cx + rx + 1, outer_low)
                lid_path.lineTo(cx - rx - 1, inner_low)
            lid_path.closeSubpath()
            eye_path = QPainterPath()
            eye_path.addEllipse(lid_rect)
            p.drawPath(lid_path.intersected(eye_path))
        if cover > 0.02 or pose.lid_slant > 0.05 or pose.lid_bottom > 0.02:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(_pen(_alpha(CLAUDE_DARK, 0.55), 1.0))
            p.drawEllipse(sclera)
        p.restore()
    if pose.happy > 0.02:
        path = QPainterPath(QPointF(cx - 6, cy + 2.5))
        path.quadTo(cx, cy - 7, cx + 6, cy + 2.5)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_alpha(INK, pose.happy), 3.0))
        p.drawPath(path)


# --- props ----------------------------------------------------------------------------------

def _star(p: QPainter, c: QPointF, r: float, color, alpha: float = 1.0) -> None:
    path = QPainterPath(QPointF(c.x(), c.y() - r))
    for i in range(1, 8):
        a = i * math.pi / 4
        rr = r if i % 2 == 0 else r * 0.32
        path.lineTo(c.x() + math.sin(a) * rr, c.y() - math.cos(a) * rr)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_alpha(color, alpha))
    p.drawPath(path)


def _paint_props(p: QPainter, pose: Pose, agent: str) -> None:
    base_opacity = p.opacity()
    for name, alpha in pose.props.items():
        painter = _PROP_PAINTERS.get(name)
        if painter:
            p.setOpacity(base_opacity * min(1.0, alpha))
            painter(p, pose, agent, pose.time)
    p.setOpacity(base_opacity)


def _prop_keyboard(p, pose, agent, t):
    kb = QPainterPath(QPointF(29, 99))
    kb.lineTo(71, 99)
    kb.lineTo(67, 92.5)
    kb.lineTo(33, 92.5)
    kb.closeSubpath()
    p.setPen(_pen("#05080b", 0.8))
    p.setBrush(QColor("#1d2530"))
    p.drawPath(kb)
    p.setPen(Qt.PenStyle.NoPen)
    for row in range(2):
        for col in range(8):
            lit = (int(t * 11) * 7 + col * 3 + row * 5) % 9 == 0
            p.setBrush(_alpha("#7dffc4" if agent == "Codex" else "#ffc89e", 0.95) if lit else QColor("#39434f"))
            p.drawRoundedRect(QRectF(35.5 + col * 3.7 + row * 0.8, 94.2 + row * 2.3, 2.8, 1.6), 0.5, 0.5)


def _prop_sparks(p, pose, agent, t):
    if agent == "Claude":
        for i in range(3):
            a = t * 1.6 + i * 2.1
            c = QPointF(50 + math.cos(a) * 25, 16 + math.sin(a) * 6)
            _star(p, c, 2.6 + math.sin(t * 5 + i) * 0.8, "#ffe7a3", 0.55 + 0.4 * math.sin(t * 4 + i))
    else:
        p.setFont(_font(5.5, bold=True, family="Consolas"))
        for i, glyph in enumerate(("01", "{}", "=>")):
            phase = (t * 0.6 + i / 3) % 1
            p.setPen(_alpha(CODEX_GLOW, 0.7 * math.sin(phase * math.pi)))
            p.drawText(QPointF(58 + i * 9 - phase * 4, 6 - phase * 10), glyph)


def _prop_sparkles(p, pose, agent, t):
    for i, (x, y) in enumerate(((12, 30), (88, 26), (20, 8), (80, 6), (50, -6))):
        tw = 0.5 + 0.5 * math.sin(t * 6 + i * 1.7)
        _star(p, QPointF(x, y), 3 + 2.5 * tw, "#fff1a8", 0.35 + 0.65 * tw)


def _prop_zzz(p, pose, agent, t):
    for i in range(3):
        phase = (t * 0.45 + i / 3) % 1
        p.setFont(_font(6 + i * 2.5))
        p.setPen(_alpha("#bcd3ff", math.sin(phase * math.pi) * 0.9))
        p.drawText(QPointF(72 + phase * 14 + i * 2, 18 - phase * 20 - i * 3), "z")


def _prop_question(p, pose, agent, t):
    p.setFont(_font(18))
    p.setPen(QColor("#f5c542"))
    p.drawText(QPointF(80, 14 + math.sin(t * 4) * 1.5), "?")


def _prop_exclaim(p, pose, agent, t):
    p.setFont(_font(20))
    p.setPen(QColor("#ff8a5c"))
    p.drawText(QPointF(82, 14 + math.sin(t * 12) * 1.2), "!")


def _prop_bolt(p, pose, agent, t):
    flick = 0.6 + 0.4 * abs(math.sin(t * 13))
    at = QPointF(84, 4)
    path = QPainterPath(QPointF(at.x() + 2, at.y()))
    for dx, dy in ((-6, 9), (-1, 9), (-4, 10), (7, -12), (2, -12), (5, -4)):
        path.lineTo(path.currentPosition() + QPointF(dx, dy))
    path.closeSubpath()
    p.setPen(_pen(_alpha("#7a5200", flick), 0.8))
    p.setBrush(_alpha("#ffd54a", flick))
    p.drawPath(path)


def _prop_sweat(p, pose, agent, t):
    phase = (t * 0.7) % 1
    c = QPointF(79, 30 + phase * 14)
    drop = QPainterPath(QPointF(c.x(), c.y() - 5))
    drop.quadTo(c.x() + 4, c.y() + 1, c.x(), c.y() + 3)
    drop.quadTo(c.x() - 4, c.y() + 1, c.x(), c.y() - 5)
    p.setPen(_pen(_alpha("#2f6fa8", 0.8), 0.8))
    p.setBrush(_alpha("#9fd4ff", 0.9 * (1 - phase * 0.6)))
    p.drawPath(drop)


def _prop_magnifier(p, pose, agent, t):
    mx = 72 + pose.look_x * 5
    my = 56 + math.sin(t * 2.3) * 2
    p.setPen(_pen("#5d4a3a" if agent == "Claude" else "#26323f", 3.4))
    p.drawLine(QPointF(mx + 5, my + 5), QPointF(mx + 11, my + 12))
    p.setPen(_pen("#c8d0da", 1.6))
    p.setBrush(_alpha("#dff4ff", 0.28))
    p.drawEllipse(QPointF(mx, my), 7, 7)
    p.setPen(_pen(_alpha("#ffffff", 0.7), 1.1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(mx - 5, my - 5, 10, 10), 100 * 16, 70 * 16)


def _prop_error(p, pose, agent, t):
    pulse = 1 + 0.12 * math.sin(t * 10)
    c = QPointF(84, 12)
    glow = QRadialGradient(c, 13 * pulse)
    glow.setColorAt(0, _alpha("#ff4d4d", 0.5))
    glow.setColorAt(1, _alpha("#ff4d4d", 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(c, 13 * pulse, 13 * pulse)
    p.setBrush(QColor("#e53935"))
    p.setPen(_pen("#ffffff", 1.2))
    p.drawEllipse(c, 7 * pulse, 7 * pulse)
    p.setFont(_font(10))
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(c.x() - 7, c.y() - 7.5, 14, 14), Qt.AlignmentFlag.AlignCenter, "!")


_PROP_PAINTERS = {
    "keyboard": _prop_keyboard, "sparks": _prop_sparks, "sparkles": _prop_sparkles, "zzz": _prop_zzz,
    "question": _prop_question, "exclaim": _prop_exclaim, "bolt": _prop_bolt, "sweat": _prop_sweat,
    "magnifier": _prop_magnifier, "error": _prop_error,
}
