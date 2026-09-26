"""Procedural vector characters (no image assets): Gilfoyle (Codex) and Dinesh (Claude).

Both are seated caricatures drawn in a 100×100 unit box whose bottom edge
sits just below their desk. The stage paints them in two layers so the desk
can sit between: ``layer="body"`` (hair, torso, head, face) and
``layer="front"`` (forearms and hands on the desk, plus props).

Faces are driven by continuous Pose parameters (lid cover, slant, brows,
mouth curve/opening, gaze), and the head turns in fake 3D toward wherever the
character is looking, so every in-between expression renders and morphs.
Caricatures in the spirit of the Silicon Valley characters; no photos, no
likenesses traced from images.
"""

from __future__ import annotations

import math

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
from ..theatre.cast import ACCENT

SHOULDERS = {"Codex": ((27.0, 68.0), (73.0, 68.0)), "Claude": ((26.0, 68.0), (74.0, 68.0))}

LOOK = {
    "Codex": dict(
        skin="#e2b495", skin_dark="#b98468", lid="#cf9f82", hair="#1b1411", hair_hi="#3a2c24",
        beard="#261b16", brow="#1b1411", iris="#4a3526", lips="#8a5646",
        top="#141418", top_hi="#24242b", top_edge="#060608", shirt="#0d0d10", sleeve="#18181d",
    ),
    "Claude": dict(
        skin="#b97d52", skin_dark="#8d5a37", lid="#a86f47", hair="#120d0b", hair_hi="#2b211c",
        beard="#2a1a12", brow="#140d0a", iris="#2e1c12", lips="#7a3f30",
        top="#6e1f30", top_hi="#8a2c40", top_edge="#3d0f19", shirt="#2b3552", sleeve="#6e1f30",
    ),
}


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


def paint_avatar(p: QPainter, rect: QRectF, agent: str, pose: Pose, active: bool = False,
                 layer: str = "all") -> None:
    """Draw ``agent`` into ``rect``. layer: "body", "front" or "all"."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = min(rect.width(), rect.height()) / 100.0
    p.translate(rect.center().x() - 50 * s, rect.bottom() - 100 * s)
    p.scale(s, s)
    p.translate(50 + pose.shake + pose.lean, 100 + pose.bob)
    p.rotate(pose.tilt * 0.6)
    p.scale(1 / math.sqrt(max(pose.squash, 0.5)), pose.squash)
    p.translate(-50, -100)
    look = LOOK.get(agent, LOOK["Claude"])
    if layer in ("body", "all"):
        _paint_body(p, agent, pose, look, active)
    if layer in ("front", "all"):
        _draw_arms(p, agent, pose, look, front=True)
        _paint_props(p, pose, agent)
    p.restore()


def portrait_pixmap(agent: str, size: int, pose: Pose | None = None, background: bool = True) -> QPixmap:
    """Head-and-shoulders portrait (conversation icons, scoreboard, window icon)."""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    q = QPainter(pix)
    q.setRenderHint(QPainter.RenderHint.Antialiasing)
    if background:
        g = QLinearGradient(0, 0, 0, size)
        g.setColorAt(0, QColor("#2a2320") if agent == "Codex" else QColor("#1e2533"))
        g.setColorAt(1, QColor("#120f0e") if agent == "Codex" else QColor("#10141c"))
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, size, size), size * 0.16, size * 0.16)
        q.setClipPath(path)
        q.fillRect(QRectF(0, 0, size, size), g)
    if pose is None:
        pose = Pose(mouth_curve=0.3 if agent == "Codex" else 0.6, mouth_asym=0.8 if agent == "Codex" else 0.1,
                    brow_asym=0.5 if agent == "Codex" else 0.2, lid_top=0.34 if agent == "Codex" else 0.0,
                    look_x=0.15 if agent == "Codex" else -0.15)
    s = size / 56.0
    paint_avatar(q, QRectF(-22 * s, -10 * s, 100 * s, 100 * s), agent, pose, layer="body")
    if background:
        q.setClipping(False)
        q.setPen(_pen(_alpha(ACCENT.get(agent, "#888"), 0.7), max(1.0, size / 40)))
        q.setBrush(Qt.BrushStyle.NoBrush)
        q.drawRoundedRect(QRectF(0.5, 0.5, size - 1, size - 1), size * 0.16, size * 0.16)
    q.end()
    return pix


def avatar_pixmap(agent: str, size: int, pose: Pose | None = None) -> QPixmap:
    return portrait_pixmap(agent, size, pose)


# --- shared geometry ---------------------------------------------------------------------

def _mouth_paths(pose: Pose, mx: float, my: float, scale: float) -> tuple[QPainterPath, QPainterPath | None]:
    """Returns (lip line, filled opening or None) for the parametric mouth."""
    w = 5.2 * pose.mouth_width * scale
    curve = pose.mouth_curve
    asym = pose.mouth_asym
    left = QPointF(mx - w, my - curve * 2.0 * scale + asym * 0.8 * scale)
    right = QPointF(mx + w, my - curve * 2.0 * scale - asym * 2.4 * scale)
    ctrl_y = my + curve * 3.4 * scale
    wave = pose.mouth_wave

    def curve_points(control_y: float, n: int = 10) -> list[QPointF]:
        pts = []
        for i in range(n + 1):
            u = i / n
            x = (1 - u) ** 2 * left.x() + 2 * (1 - u) * u * mx + u * u * right.x()
            y = (1 - u) ** 2 * left.y() + 2 * (1 - u) * u * control_y + u * u * right.y()
            if wave > 0.02 and 0 < i < n:
                y += wave * 1.0 * scale * (1 if i % 2 else -1)
            pts.append(QPointF(x, y))
        return pts

    upper = curve_points(ctrl_y)
    line = QPainterPath(upper[0])
    for pt in upper[1:]:
        line.lineTo(pt)
    if pose.mouth_open < 0.06:
        return line, None
    lower = curve_points(ctrl_y + pose.mouth_open * 7 * scale + 0.8)
    opening = QPainterPath(upper[0])
    for pt in upper[1:]:
        opening.lineTo(pt)
    for pt in reversed(lower):
        opening.lineTo(pt)
    opening.closeSubpath()
    return line, opening


def _draw_arms(p: QPainter, agent: str, pose: Pose, look: dict, front: bool) -> None:
    shoulders = SHOULDERS.get(agent, SHOULDERS["Claude"])
    for (elbow, hand_pt, is_front), shoulder in ((pose.arm_left, shoulders[0]), (pose.arm_right, shoulders[1])):
        if is_front != front:
            continue
        path = QPainterPath(QPointF(*shoulder))
        path.quadTo(QPointF(*elbow), QPointF(*hand_pt))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(look["top_edge"], 9.5))
        p.drawPath(path)
        p.setPen(_pen(look["sleeve"], 7.8))
        p.drawPath(path)
        p.setPen(_pen(_alpha(look["top_hi"], 0.55), 2.0))
        p.drawPath(path.translated(-0.8, -0.8))
        # cuff + hand
        hx, hy = hand_pt
        ex, ey = elbow
        ang = math.atan2(hy - ey, hx - ex)
        cuff = QPointF(hx - math.cos(ang) * 2.4, hy - math.sin(ang) * 2.4)
        p.setPen(_pen(look["top_edge"], 7.4))
        p.drawPoint(cuff)
        p.setPen(_pen(_alpha(look["skin_dark"], 0.9), 0.8))
        p.setBrush(QColor(look["skin"]))
        p.save()
        p.translate(hx, hy)
        p.rotate(math.degrees(ang) - 90)
        hand = QPainterPath(QPointF(-3.0, -1.0))
        hand.cubicTo(-3.6, 2.8, -1.8, 4.4, 0.2, 4.3)
        hand.cubicTo(2.4, 4.2, 3.6, 2.6, 3.1, -1.0)
        hand.cubicTo(2.2, -2.6, -2.2, -2.6, -3.0, -1.0)
        p.drawPath(hand)
        p.restore()


def _eye(p: QPainter, pose: Pose, cx: float, cy: float, rx: float, ry: float, look: dict, side: int,
         gaze_x: float, gaze_y: float) -> None:
    open_alpha = 1.0 - pose.happy
    cover = max(1.0 - pose.eye_open, min(0.9, pose.lid_top))
    sclera = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)
    if cover > 0.9:
        if open_alpha > 0.02:
            path = QPainterPath(QPointF(cx - rx, cy + 0.3))
            path.quadTo(cx, cy + ry * 0.8, cx + rx, cy + 0.3)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(_pen(_alpha("#1a100c", open_alpha), 1.2))
            p.drawPath(path)
    elif open_alpha > 0.02:
        p.save()
        p.setOpacity(p.opacity() * open_alpha)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#f3eee6"))
        p.drawEllipse(sclera)
        ir = min(rx, ry) * 0.72 * (0.85 + 0.15 * pose.pupil)
        ix = cx + max(-(rx - ir * 0.7), min(rx - ir * 0.7, gaze_x))
        iy = cy + max(-(ry - ir * 0.6), min(ry - ir * 0.6, gaze_y))
        eye_clip = QPainterPath()
        eye_clip.addEllipse(sclera)
        p.setClipPath(eye_clip, Qt.ClipOperation.IntersectClip)
        p.setBrush(QColor(look["iris"]))
        p.drawEllipse(QPointF(ix, iy), ir, ir)
        p.setBrush(QColor("#0b0706"))
        p.drawEllipse(QPointF(ix, iy), ir * 0.5 * pose.pupil, ir * 0.5 * pose.pupil)
        p.setBrush(_alpha("#ffffff", 0.85))
        p.drawEllipse(QPointF(ix - ir * 0.35, iy - ir * 0.4), ir * 0.28, ir * 0.28)
        # lids
        p.setBrush(QColor(look["lid"]))
        lid_rect = sclera.adjusted(-0.4, -0.4, 0.4, 0.4)
        if cover > 0.02:
            h = lid_rect.height() * cover
            lid = QPainterPath()
            lid.addRect(QRectF(lid_rect.left() - 1, lid_rect.top() - 1, lid_rect.width() + 2, h + 1))
            p.drawPath(lid)
        if pose.lid_bottom > 0.02:
            h = lid_rect.height() * pose.lid_bottom
            p.drawRect(QRectF(lid_rect.left() - 1, lid_rect.bottom() - h, lid_rect.width() + 2, h + 1))
        if pose.lid_slant > 0.05:
            drop = min(1.0, pose.lid_slant)
            top = lid_rect.top() + lid_rect.height() * cover
            inner = top + ry * 1.1 * drop
            path = QPainterPath(QPointF(lid_rect.left() - 1, lid_rect.top() - 1))
            path.lineTo(lid_rect.right() + 1, lid_rect.top() - 1)
            if side < 0:  # inner corner is on the right for the left eye
                path.lineTo(lid_rect.right() + 1, inner)
                path.lineTo(lid_rect.left() - 1, top)
            else:
                path.lineTo(lid_rect.right() + 1, top)
                path.lineTo(lid_rect.left() - 1, inner)
            path.closeSubpath()
            p.drawPath(path)
        p.restore()
        # lash line on the upper lid edge
        edge_y = cy - ry + 2 * ry * cover
        p.setPen(_pen(_alpha("#150d0a", 0.9 * open_alpha), 0.9))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx - rx * 0.95, edge_y + (0.5 if cover > 0.05 else ry * 0.35)),
                   QPointF(cx + rx * 0.95, edge_y + (0.5 if cover > 0.05 else ry * 0.35)))
    if pose.happy > 0.02:
        path = QPainterPath(QPointF(cx - rx, cy + 0.8))
        path.quadTo(cx, cy - ry * 1.2, cx + rx, cy + 0.8)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(_alpha("#150d0a", pose.happy), 1.3))
        p.drawPath(path)


def _brows(p: QPainter, pose: Pose, cx: float, by: float, gap: float, length: float, thick: float, colour: str,
           turn: float, travel: float) -> None:
    far = 1 if turn >= 0 else -1
    for side in (-1, 1):
        x = cx + side * gap
        raise_ = pose.brow_raise * travel + (pose.brow_asym * travel * 0.9 if side == far else 0)
        inner = pose.brow_angle * travel * 0.8
        outer_pt = QPointF(x + side * length * 0.55, by - raise_ + 0.3)
        inner_pt = QPointF(x - side * length * 0.45, by - raise_ + inner)
        mid = QPointF(x, by - raise_ - 1.0 + inner * 0.3)
        brow = QPainterPath(outer_pt)
        brow.quadTo(mid, inner_pt)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(_pen(colour, thick))
        p.drawPath(brow)


def _body_shape(top_y: float, half_w: float) -> QPainterPath:
    body = QPainterPath(QPointF(50 - half_w * 0.42, top_y - 2))
    body.cubicTo(50 - half_w * 0.9, top_y - 1, 50 - half_w, top_y + 4, 50 - half_w, top_y + 12)
    body.lineTo(50 - half_w * 0.94, 104)
    body.lineTo(50 + half_w * 0.94, 104)
    body.lineTo(50 + half_w, top_y + 12)
    body.cubicTo(50 + half_w, top_y + 4, 50 + half_w * 0.9, top_y - 1, 50 + half_w * 0.42, top_y - 2)
    body.closeSubpath()
    return body


def _paint_body(p: QPainter, agent: str, pose: Pose, look: dict, active: bool) -> None:
    if agent == "Codex":
        _paint_gilfoyle(p, pose, look, active)
    else:
        _paint_dinesh(p, pose, look, active)


# --- Gilfoyle ---------------------------------------------------------------------------------

def _paint_gilfoyle(p: QPainter, pose: Pose, L: dict, active: bool) -> None:
    turn = max(-1.0, min(1.0, pose.look_x))
    fx = turn * 3.6  # facial features shift with the head turn
    hx = 50 + turn * 1.2
    sway = pose.wobble * 0.05

    # long hair behind the shoulders
    back = QPainterPath(QPointF(hx - 15, 22))
    back.cubicTo(hx - 24, 30, hx - 22 + sway, 58, hx - 21 + sway * 1.5, 76)
    back.lineTo(hx + 21 + sway * 1.5, 76)
    back.cubicTo(hx + 22 + sway, 58, hx + 24, 30, hx + 15, 22)
    back.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(L["hair"]))
    p.drawPath(back)

    _draw_arms(p, "Codex", pose, L, front=False)

    # black hoodie
    body = _body_shape(66, 29)
    g = QLinearGradient(0, 62, 0, 100)
    g.setColorAt(0, QColor(L["top_hi"]))
    g.setColorAt(1, QColor(L["top"]))
    p.setPen(_pen(L["top_edge"], 1.0))
    p.setBrush(g)
    p.drawPath(body)
    # hood bunched round the neck, zip line, a faint print on the tee
    p.setBrush(QColor("#1d1d23"))
    p.setPen(_pen(L["top_edge"], 0.8))
    hood = QPainterPath(QPointF(35, 64))
    hood.cubicTo(38, 71, 62, 71, 65, 64)
    hood.cubicTo(60, 67.5, 40, 67.5, 35, 64)
    p.drawPath(hood)
    p.setBrush(QColor(L["shirt"]))
    p.setPen(Qt.PenStyle.NoPen)
    tee = QPainterPath(QPointF(44, 67))
    tee.lineTo(56, 67)
    tee.lineTo(54, 104)
    tee.lineTo(46, 104)
    tee.closeSubpath()
    p.drawPath(tee)
    p.setPen(_pen(_alpha("#8a1c1c", 0.55), 0.7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(50, 83), 2.6, 2.6)
    p.setPen(_pen(_alpha("#ffffff", 0.07), 0.8))
    for x in (41.5, 58.5):
        p.drawLine(QPointF(x, 70), QPointF(x + (x - 50) * 0.08, 104))

    # neck
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(L["skin_dark"]))
    p.drawRect(QRectF(hx - 5, 54, 10, 12))

    # head
    head = QRectF(hx - 14.5, 15, 29, 43)
    face = QRadialGradient(QPointF(hx - 3 - turn * 3, 30), 26)
    face.setColorAt(0, QColor(L["skin"]).lighter(106))
    face.setColorAt(1, QColor(L["skin_dark"]))
    p.setPen(_pen(_alpha("#5a3a2a", 0.6), 0.7))
    p.setBrush(face)
    p.drawRoundedRect(head, 13, 16)

    # beard: full, dark, a little longer than the chin
    beard = QPainterPath(QPointF(hx - 14.3 + fx * 0.2, 36))
    beard.cubicTo(hx - 14 + fx * 0.2, 52, hx - 9 + fx * 0.4, 64, hx + fx * 0.5, 65)
    beard.cubicTo(hx + 9 + fx * 0.4, 64, hx + 14 + fx * 0.2, 52, hx + 14.3 + fx * 0.2, 36)
    beard.cubicTo(hx + 12, 43, hx + 8 + fx, 44, hx + 5 + fx, 46.5)
    beard.cubicTo(hx + 2 + fx, 45.3, hx - 2 + fx, 45.3, hx - 5 + fx, 46.5)
    beard.cubicTo(hx - 8 + fx, 44, hx - 12, 43, hx - 14.3 + fx * 0.2, 36)
    beard.closeSubpath()
    bg = QLinearGradient(0, 38, 0, 66)
    bg.setColorAt(0, _alpha(L["beard"], 0.82))
    bg.setColorAt(0.3, QColor(L["beard"]))
    bg.setColorAt(1, QColor(L["hair"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawPath(beard)
    p.setPen(_pen(_alpha(L["hair_hi"], 0.55), 0.5))
    for i in range(7):
        x = hx - 9 + i * 3 + fx * 0.4
        p.drawLine(QPointF(x, 54 + (i % 2) * 2), QPointF(x + 0.6, 60 + (i % 3)))

    # mouth, peeking out of the beard
    mx, my = hx + fx * 0.9, 50.5 + pose.look_y * 0.8
    line, opening = _mouth_paths(pose, mx, my, 0.85)
    if opening is not None:
        p.setPen(_pen(L["lips"], 0.8))
        p.setBrush(QColor("#2a0f0b"))
        p.drawPath(opening)
        box = opening.boundingRect()
        if pose.teeth > 0.05 and box.height() > 2:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_alpha("#efe6d8", pose.teeth))
            p.drawRect(QRectF(mx - box.width() * 0.32, box.top() + 0.3, box.width() * 0.64, min(1.6, box.height() * 0.3)))
    else:
        p.setPen(_pen(L["lips"], 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)
    # moustache over the lip
    stache = QPainterPath(QPointF(mx - 7, my + 0.6))
    stache.cubicTo(mx - 5, my - 3.4, mx - 1, my - 3.0, mx, my - 2.2)
    stache.cubicTo(mx + 1, my - 3.0, mx + 5, my - 3.4, mx + 7, my + 0.6)
    stache.cubicTo(mx + 4, my - 1.0, mx - 4, my - 1.0, mx - 7, my + 0.6)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(L["beard"]))
    p.drawPath(stache)

    # nose
    nx = hx + fx * 1.1
    p.setPen(_pen(_alpha("#7a4e3a", 0.8), 0.9))
    p.setBrush(Qt.BrushStyle.NoBrush)
    nose = QPainterPath(QPointF(nx - 0.6, 35))
    nose.cubicTo(nx + 1.2 * (1 - abs(turn)) - turn * 1.5, 41, nx + 2.2 - turn, 43.5, nx + 0.4, 44.2)
    p.drawPath(nose)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_alpha("#6b4030", 0.35))
    p.drawEllipse(QPointF(nx - 2.2, 44.2), 1.2, 0.6)
    p.drawEllipse(QPointF(nx + 2.0, 44.2), 1.2, 0.6)

    # eyes (heavy-lidded) + glasses
    gaze_x, gaze_y = pose.look_x * 2.0, pose.look_y * 1.4
    ey = 35.5
    for side in (-1, 1):
        far = side * turn > 0
        rx = 3.2 * (1 - 0.2 * abs(turn) if far else 1.0) * pose.eye_scale
        _eye(p, pose, hx + side * 6.4 + fx, ey, rx, 2.5 * pose.eye_scale, L, side, gaze_x, gaze_y)
    p.setPen(_pen(_alpha("#8f7a6a", 0.35), 0.5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for side in (-1, 1):
        p.drawArc(QRectF(hx + side * 6.6 + fx - 3.3, ey + 1.2, 6.6, 3), 200 * 16, 140 * 16)
    _brows(p, pose, hx + fx, ey - 4.6, 6.6, 7.2, 1.9, L["brow"], turn, 1.6)
    frame = _pen("#0e0c0b", 1.05)
    p.setPen(frame)
    p.setBrush(_alpha("#bcd4e6", 0.07))
    for side in (-1, 1):
        far = side * turn > 0
        w = 9.4 * (1 - 0.18 * abs(turn) if far else 1.0)
        cx = hx + side * 6.4 + fx
        p.drawRoundedRect(QRectF(cx - w / 2, ey - 4.0, w, 7.4), 1.6, 1.6)
    p.drawLine(QPointF(hx - 1.6 + fx, ey - 1.2), QPointF(hx + 1.6 + fx, ey - 1.2))
    for side in (-1, 1):
        if side * turn < 0.4:
            p.drawLine(QPointF(hx + side * 11.1 + fx, ey - 2.5), QPointF(hx + side * 14.4, ey - 3.0))
    p.setPen(_pen(_alpha("#ffffff", 0.18), 0.6))
    p.drawLine(QPointF(hx - 10 + fx, ey - 3.0), QPointF(hx - 7.6 + fx, ey - 3.3))

    # hair: centre parting, falling straight past the face
    top = QPainterPath(QPointF(hx - 15.5, 40))
    top.cubicTo(hx - 17, 16, hx - 6, 11, hx + turn * 1.5, 12.3)
    top.cubicTo(hx + 6, 11, hx + 17, 16, hx + 15.5, 40)
    top.cubicTo(hx + 15.2, 52 + sway, hx + 16.4, 62 + sway, hx + 17.5 + sway, 72)
    top.lineTo(hx + 12.5 + sway, 70)
    top.cubicTo(hx + 12.9, 58, hx + 13.4, 40, hx + 12.4, 29)
    top.cubicTo(hx + 8, 20, hx + 3, 18.5, hx + turn * 1.5, 16.8)
    top.cubicTo(hx - 3, 18.5, hx - 8, 20, hx - 12.4, 29)
    top.cubicTo(hx - 13.4, 40, hx - 12.9, 58, hx - 12.5 + sway, 70)
    top.lineTo(hx - 17.5 + sway, 72)
    top.cubicTo(hx - 16.4, 62 + sway, hx - 15.2, 52 + sway, hx - 15.5, 40)
    top.closeSubpath()
    hg = QLinearGradient(hx - 16, 0, hx + 16, 0)
    hg.setColorAt(0, QColor(L["hair"]))
    hg.setColorAt(0.45 - turn * 0.1, QColor(L["hair_hi"]))
    hg.setColorAt(1, QColor(L["hair"]))
    p.setPen(_pen(_alpha("#000000", 0.5), 0.5))
    p.setBrush(hg)
    p.drawPath(top)
    p.setPen(_pen(_alpha("#5a4538", 0.45), 0.45))
    for i, x in enumerate((-13.5, -10.5, 10.5, 13.5)):
        s = 1 if x > 0 else -1
        p.drawLine(QPointF(hx + x * 0.95, 26 + i), QPointF(hx + x + s * 1.5 + sway, 66))



# --- Dinesh ---------------------------------------------------------------------------------

def _paint_dinesh(p: QPainter, pose: Pose, L: dict, active: bool) -> None:
    turn = max(-1.0, min(1.0, pose.look_x))
    fx = turn * 3.8
    hx = 50 + turn * 1.4

    _draw_arms(p, "Claude", pose, L, front=False)

    # maroon zip hoodie over a striped polo
    body = _body_shape(66, 29)
    g = QLinearGradient(0, 62, 0, 100)
    g.setColorAt(0, QColor(L["top_hi"]))
    g.setColorAt(1, QColor(L["top"]))
    p.setPen(_pen(L["top_edge"], 1.0))
    p.setBrush(g)
    p.drawPath(body)
    polo = QPainterPath(QPointF(41, 64.5))
    polo.lineTo(59, 64.5)
    polo.lineTo(56, 104)
    polo.lineTo(44, 104)
    polo.closeSubpath()
    p.save()
    p.setClipPath(polo)
    p.fillRect(QRectF(40, 60, 20, 45), QColor(L["shirt"]))
    p.setPen(Qt.PenStyle.NoPen)
    for i, colour in enumerate(("#7d8aa6", "#c9cbd3", "#7d8aa6")):
        for k in range(6):
            p.setBrush(_alpha(colour, 0.8))
            p.drawRect(QRectF(40, 70 + k * 6 + i * 1.3, 20, 0.8))
    p.restore()
    # collar
    p.setPen(_pen("#1a2033", 0.7))
    p.setBrush(QColor("#354166"))
    for side in (-1, 1):
        collar = QPainterPath(QPointF(50, 67))
        collar.lineTo(50 + side * 7, 63.5)
        collar.lineTo(50 + side * 6, 68.5)
        collar.closeSubpath()
        p.drawPath(collar)
    # zip edges and a drawstring
    p.setPen(_pen(_alpha("#d9c3a0", 0.6), 0.6))
    p.drawLine(QPointF(41.5, 67), QPointF(44.5, 104))
    p.drawLine(QPointF(58.5, 67), QPointF(55.5, 104))
    p.setPen(_pen("#e9e2d6", 0.8))
    p.drawLine(QPointF(40.2, 67), QPointF(39.6, 77))

    # neck
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(L["skin_dark"]))
    p.drawRect(QRectF(hx - 5.5, 54, 11, 11))

    # ears
    for side in (-1, 1):
        if side * turn < 0.55:
            p.setBrush(QColor(L["skin_dark"]))
            p.drawEllipse(QPointF(hx + side * 15.2 - turn * 1.6, 37), 2.6, 4.2)

    head = QRectF(hx - 15, 16, 30, 41)
    face = QRadialGradient(QPointF(hx - 3 - turn * 3, 31), 26)
    face.setColorAt(0, QColor(L["skin"]).lighter(108))
    face.setColorAt(1, QColor(L["skin_dark"]))
    p.setPen(_pen(_alpha("#3f2415", 0.6), 0.7))
    p.setBrush(face)
    jaw = QPainterPath(QPointF(head.left(), 30))
    jaw.cubicTo(head.left(), 18, head.right(), 18, head.right(), 30)
    jaw.cubicTo(head.right(), 44, hx + 11 + fx * 0.3, 55, hx + fx * 0.5, 57)
    jaw.cubicTo(hx - 11 + fx * 0.3, 55, head.left(), 44, head.left(), 30)
    p.drawPath(jaw)
    # stubble / short beard
    stubble = QPainterPath(QPointF(hx - 14 + fx * 0.2, 40))
    stubble.cubicTo(hx - 13, 49, hx - 8 + fx * 0.3, 55.5, hx + fx * 0.5, 56.8)
    stubble.cubicTo(hx + 8 + fx * 0.3, 55.5, hx + 13, 49, hx + 14 + fx * 0.2, 40)
    stubble.cubicTo(hx + 10 + fx, 47, hx - 10 + fx, 47, hx - 14 + fx * 0.2, 40)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_alpha(L["beard"], 0.38))
    p.drawPath(stubble)

    # mouth
    mx, my = hx + fx, 49.5 + pose.look_y * 0.8
    line, opening = _mouth_paths(pose, mx, my, 1.0)
    if opening is not None:
        p.setPen(_pen(L["lips"], 0.9))
        p.setBrush(QColor("#300f0b"))
        p.drawPath(opening)
        box = opening.boundingRect()
        p.setPen(Qt.PenStyle.NoPen)
        if pose.teeth > 0.05 and box.height() > 2:
            p.setBrush(_alpha("#f4ede2", pose.teeth))
            p.drawRect(QRectF(mx - box.width() * 0.36, box.top() + 0.2, box.width() * 0.72, min(2.0, box.height() * 0.32)))
        if box.height() > 3:
            p.setBrush(QColor("#b85a52"))
            p.drawEllipse(QPointF(mx, box.bottom() - box.height() * 0.28), box.width() * 0.22, box.height() * 0.18)
    else:
        p.setPen(_pen(L["lips"], 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)
    # thin moustache
    p.setPen(_pen(_alpha(L["beard"], 0.55), 1.4))
    p.drawLine(QPointF(mx - 4.6, my - 3.0 - pose.mouth_curve * 0.6), QPointF(mx + 4.6, my - 3.0 - pose.mouth_curve * 0.6))

    # nose (broader)
    nx = hx + fx * 1.15
    p.setPen(_pen(_alpha("#5a3320", 0.85), 0.9))
    p.setBrush(Qt.BrushStyle.NoBrush)
    nose = QPainterPath(QPointF(nx - 0.4, 34.5))
    nose.cubicTo(nx + 1.6 - turn * 1.4, 40, nx + 3.0 - turn, 42.5, nx + 0.6, 43.4)
    p.drawPath(nose)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_alpha("#4a2716", 0.4))
    p.drawEllipse(QPointF(nx - 2.6, 43.3), 1.4, 0.7)
    p.drawEllipse(QPointF(nx + 2.4, 43.3), 1.4, 0.7)

    # big expressive eyes
    gaze_x, gaze_y = pose.look_x * 2.2, pose.look_y * 1.6
    ey = 35
    for side in (-1, 1):
        far = side * turn > 0
        rx = 3.6 * (1 - 0.2 * abs(turn) if far else 1.0) * pose.eye_scale
        _eye(p, pose, hx + side * 6.8 + fx, ey, rx, 2.9 * pose.eye_scale, L, side, gaze_x, gaze_y)
    _brows(p, pose, hx + fx, ey - 5.2, 6.8, 7.6, 2.3, L["brow"], turn, 3.0)
    if pose.blush > 0.05:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha("#c0504a", pose.blush * 0.35))
        for side in (-1, 1):
            p.drawEllipse(QPointF(hx + side * 9 + fx, 43), 3.6, 2.0)

    # short thick hair, swept up with a side parting
    # thick, swept up and over to one side, a bit of volume on top
    hair = QPainterPath(QPointF(hx - 15.4, 34))
    hair.cubicTo(hx - 18.5, 22, hx - 15, 10, hx - 6, 7.5)
    hair.cubicTo(hx - 1, 5.2, hx + 6, 5.8, hx + 10.5, 8.4)
    hair.cubicTo(hx + 15.5, 11, hx + 19, 18, hx + 15.4, 33)
    hair.cubicTo(hx + 14.6, 28, hx + 13.6, 25.8, hx + 11.5, 24.2)
    hair.cubicTo(hx + 8, 21.5, hx + 3 + fx * 0.3, 20.2, hx - 1 + fx * 0.3, 20.8)
    hair.cubicTo(hx - 5 + fx * 0.3, 19.6, hx - 10, 22.5, hx - 13.8, 31.5)
    hair.closeSubpath()
    hg = QLinearGradient(0, 5, 0, 34)
    hg.setColorAt(0, QColor(L["hair_hi"]))
    hg.setColorAt(0.5, QColor(L["hair"]))
    hg.setColorAt(1, QColor(L["hair"]))
    p.setPen(_pen(_alpha("#000000", 0.5), 0.5))
    p.setBrush(hg)
    p.drawPath(hair)
    # a few swept locks (no stripes)
    p.setPen(_pen(_alpha("#4d3b33", 0.55), 0.55))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for i, (x0, y0) in enumerate(((-9, 12), (-4, 9.5), (2, 8.6), (7, 10))):
        lock = QPainterPath(QPointF(hx + x0, y0))
        lock.quadTo(hx + x0 + 5, y0 + 2 + i * 0.4, hx + x0 + 8.5, y0 + 7.5)
        p.drawPath(lock)
    # sideburns
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(L["hair"]))
    for side in (-1, 1):
        if side * turn < 0.6:
            p.drawRect(QRectF(hx + side * 14.2 - (1.6 if side > 0 else 0) - turn * 0.8, 31, 1.6, 7))



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


def _prop_sparkles(p, pose, agent, t):
    for i, (x, y) in enumerate(((14, 30), (86, 26), (22, 10), (78, 8), (50, 2))):
        tw = 0.5 + 0.5 * math.sin(t * 6 + i * 1.7)
        _star(p, QPointF(x, y), 2.5 + 2.2 * tw, "#fff1a8", 0.35 + 0.65 * tw)


def _prop_chain(p, pose, agent, t):
    """Dinesh's gold chain. It only comes out for victories."""
    hx = 50 + max(-1.0, min(1.0, pose.look_x)) * 1.4
    path = QPainterPath(QPointF(hx - 9, 64))
    path.cubicTo(hx - 8, 76, hx + 8, 76, hx + 9, 64)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(_pen("#7a5a10", 2.4))
    p.drawPath(path)
    p.setPen(_pen("#f2c94c", 1.5))
    p.drawPath(path)
    glint = 0.5 + 0.5 * math.sin(t * 5)
    _star(p, QPointF(hx + 5, 71.5), 1.6 + glint * 1.6, "#fffbe0", 0.6 + 0.4 * glint)


def _prop_yes(p, pose, agent, t):
    k = min(1.0, (math.sin(t * 3) + 1.4) / 2)
    side = -pose.other_side
    x = 50 + side * 36
    p.save()
    p.translate(x, 14)
    p.rotate(-8 * side)
    p.scale(0.9 + 0.1 * k, 0.9 + 0.1 * k)
    p.setFont(_font(11, family="Impact"))
    p.setPen(_pen("#10131a", 3.2))
    path = QPainterPath()
    path.addText(QPointF(-12, 4), _font(11, family="Impact"), "YES.")
    p.setBrush(QColor("#ffe26b"))
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(path)
    p.restore()


def _prop_vein(p, pose, agent, t):
    """The cartoon anger mark, on the forehead."""
    pulse = 1 + 0.18 * math.sin(t * 11)
    side = -pose.other_side
    c = QPointF(50 + side * 9, 22)
    p.save()
    p.translate(c)
    p.scale(pulse, pulse)
    p.setPen(_pen("#e2382f", 1.3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for angle in (0, 90, 180, 270):
        p.save()
        p.rotate(angle + 45)
        arc = QPainterPath(QPointF(0.8, -2.8))
        arc.quadTo(0.6, -0.6, 2.8, -0.8)
        p.drawPath(arc)
        p.restore()
    p.restore()


def _prop_zzz(p, pose, agent, t):
    for i in range(3):
        phase = (t * 0.45 + i / 3) % 1
        p.setFont(_font(6 + i * 2.5))
        p.setPen(_alpha("#bcd3ff", math.sin(phase * math.pi) * 0.9))
        p.drawText(QPointF(66 + phase * 14 + i * 2, 18 - phase * 20 - i * 3), "z")


def _prop_question(p, pose, agent, t):
    p.setFont(_font(15))
    p.setPen(QColor("#f5c542"))
    p.drawText(QPointF(72, 16 + math.sin(t * 4) * 1.5), "?")


def _prop_exclaim(p, pose, agent, t):
    p.setFont(_font(16))
    p.setPen(QColor("#ff8a5c"))
    x = 50 - pose.other_side * 27
    p.drawText(QPointF(x, 16 + math.sin(t * 12) * 1.2), "!")


def _prop_sweat(p, pose, agent, t):
    phase = (t * 0.7) % 1
    c = QPointF(50 - pose.other_side * 15, 26 + phase * 10)
    drop = QPainterPath(QPointF(c.x(), c.y() - 3.6))
    drop.quadTo(c.x() + 2.8, c.y() + 0.8, c.x(), c.y() + 2.2)
    drop.quadTo(c.x() - 2.8, c.y() + 0.8, c.x(), c.y() - 3.6)
    p.setPen(_pen(_alpha("#2f6fa8", 0.8), 0.6))
    p.setBrush(_alpha("#9fd4ff", 0.9 * (1 - phase * 0.6)))
    p.drawPath(drop)


def _prop_mug(p, pose, agent, t):
    """Black coffee, held by whichever hand is up near the face."""
    hand = min((pose.arm_left[1], pose.arm_right[1]), key=lambda h: h[1])
    x, y = hand
    p.setPen(_pen("#050505", 0.8))
    p.setBrush(QColor("#1b1b1f"))
    p.drawRoundedRect(QRectF(x - 3.4, y - 7.5, 6.8, 8.5), 1.2, 1.2)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(x + 2.4, y - 5.6, 3.2, 4), -90 * 16, 180 * 16)
    p.setPen(_pen(_alpha("#c0392b", 0.8), 0.7))
    p.drawLine(QPointF(x - 2, y - 3.5), QPointF(x + 2, y - 3.5))
    for i in range(2):
        phase = (t * 0.6 + i * 0.5) % 1
        p.setPen(_pen(_alpha("#d8dde6", 0.35 * (1 - phase)), 0.6))
        p.drawLine(QPointF(x - 1 + i * 2, y - 8.5 - phase * 5), QPointF(x - 0.2 + i * 2, y - 10 - phase * 5))


def _prop_error(p, pose, agent, t):
    pulse = 1 + 0.12 * math.sin(t * 10)
    c = QPointF(50 - pose.other_side * 30, 14)
    glow = QRadialGradient(c, 10 * pulse)
    glow.setColorAt(0, _alpha("#ff4d4d", 0.45))
    glow.setColorAt(1, _alpha("#ff4d4d", 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(c, 10 * pulse, 10 * pulse)
    p.setBrush(QColor("#e53935"))
    p.setPen(_pen("#ffffff", 0.9))
    p.drawEllipse(c, 5.4 * pulse, 5.4 * pulse)
    p.setFont(_font(8))
    p.setPen(QColor("#ffffff"))
    p.drawText(QRectF(c.x() - 6, c.y() - 6.3, 12, 12), Qt.AlignmentFlag.AlignCenter, "!")


_PROP_PAINTERS = {
    "sparkles": _prop_sparkles, "chain": _prop_chain, "yes": _prop_yes, "vein": _prop_vein, "zzz": _prop_zzz,
    "question": _prop_question, "exclaim": _prop_exclaim, "sweat": _prop_sweat, "mug": _prop_mug,
    "error": _prop_error,
}
