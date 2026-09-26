"""The Workshop Theatre stage: Gilfoyle and Dinesh at their desks in the hacker house.

Pure presentation. The Director (workshop/theatre/director.py) decides what
happens; the stage only draws the set, the characters, bubbles, cards and
effects, and keeps a frame timer running only while something moves.

The set (wall, server rack, whiteboard, banner, window, back desk) and the
foreground desks are rendered once per size into cached pixmaps; per frame we
only draw what animates (LEDs, monitor text, characters, bubbles, effects).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QTextOption,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..conversation import AGENTS
from ..theatre.avatar_state import AvatarModel, Persona
from ..theatre.cast import ACCENT, CHARACTER
from .avatar_paint import paint_avatar

FRAME_ACTIVE_MS = 50
FRAME_IDLE_MS = 110
MONO = "Consolas"

BUBBLE = {
    "Codex": {"fill": "#f3e4e1", "edge": "#b8433a", "ink": "#1d1414"},
    "Claude": {"fill": "#e4e7ff", "edge": "#5a7fe0", "ink": "#141726"},
}
SCREEN = {"Codex": "#57e389", "Claude": "#7fb2ff"}


def _c(color, alpha: float | None = None) -> QColor:
    c = QColor(color)
    if alpha is not None:
        c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def _font(px: float, bold: bool = False, italic: bool = False, family: str = "Segoe UI") -> QFont:
    f = QFont(family)
    f.setPixelSize(max(6, int(px)))
    f.setBold(bold)
    f.setItalic(italic)
    return f


def _pen(color, width: float, alpha: float | None = None) -> QPen:
    pen = QPen(_c(color, alpha), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _ease_out(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _ease_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


class BubbleText:
    """Test/compat helper: ``panel.bubble.text()`` returns the full bubble text."""

    def __init__(self):
        self._text = ""

    def text(self) -> str:
        return self._text


@dataclass
class AgentView:
    """Per-agent display data (also the compatibility surface for tests)."""

    agent: str
    state: str = "WAITING"  # orchestrator agent state (A_*)
    label: str = "☕ WAITING"
    activity: str = ""
    turns: int = 0
    bubble: BubbleText = field(default_factory=BubbleText)


@dataclass
class Bubble:
    text: str = ""
    kind: str = "none"  # speech | status | none
    born: float = 0.0
    shown: float = 0.0  # characters revealed
    mode: str = "instant"  # instant | typewriter | speech
    speech_chars: int = 0


@dataclass
class Badge:
    text: str
    color: str
    anchor: str  # agent name or "center"
    born: float
    duration: float = 2.6
    style: str = "chip"  # chip | caption


@dataclass
class Card:
    kind: str  # human | waiting | complete
    title: str
    lines: list[str]
    color: str
    born: float
    duration: float | None = None
    footer: str = ""
    tagline: str = ""


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    rot: float
    vrot: float
    color: str
    size: float
    life: float
    age: float = 0.0
    shape: str = "rect"


class StageWidget(QWidget):
    def __init__(self, personas: dict[str, Persona] | None = None, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(300)
        personas = personas or {}
        self.models = {
            "Codex": AvatarModel("Codex", personas.get("Codex"), other_side=1),
            "Claude": AvatarModel("Claude", personas.get("Claude"), other_side=-1),
        }
        self.views = {a: AgentView(a) for a in AGENTS}
        self.bubbles = {a: Bubble() for a in AGENTS}
        self.badges: list[Badge] = []
        self.cards: dict[str, Card] = {}
        self.particles: list[Particle] = []
        self.orbs: list[tuple[str, str, float]] = []
        self.lightning_until = 0.0
        self.human_light_until = 0.0
        self.active_agent: str | None = None
        self.on_air = False
        self.show_on_air = True  # the window header has its own LIVE light outside Theatre Mode
        self.paused = False
        self.spot = {a: 0.25 for a in AGENTS}
        self.animations = True
        self.reduced_motion = False
        self.typewriter = True
        self.typewriter_cps = 95.0
        self.rng = random.Random(3)
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last = self.now()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(FRAME_IDLE_MS)
        self._geom: dict[str, QRectF] = {}
        self._backdrop: QPixmap | None = None
        self._backdrop_size: tuple[int, int] = (0, 0)
        self._desks: QPixmap | None = None
        self.cam_zoom = 1.0
        self.cam_x = 0.0
        self.shake_amp = 0.0
        self.shake_at = -10.0
        self.sweep_until = 0.0
        self.level_source = None  # callable(agent) -> float | None (live voice loudness)
        self.motes = [(self.rng.random(), self.rng.random(), self.rng.uniform(0.6, 1.6), self.rng.random())
                      for _ in range(22)]
        self._code_lines = {a: self._fake_code_widths(a) for a in AGENTS}

    # -- time / animation settings -------------------------------------------

    def now(self) -> float:
        return self._clock.elapsed() / 1000.0

    def set_motion(self, animations: bool, reduced: bool, typewriter: bool) -> None:
        self.animations, self.reduced_motion, self.typewriter = animations, reduced, typewriter
        for m in self.models.values():
            m.enabled = animations
            m.motion = 0.0 if (reduced or not animations) else 1.0
        self.wake()

    def set_persona(self, agent: str, persona: Persona) -> None:
        self.models[agent].persona = persona

    def wake(self) -> None:
        if not self._timer.isActive() or self._timer.interval() != FRAME_ACTIVE_MS:
            self._timer.start(FRAME_ACTIVE_MS)
        self.update()

    def stop(self) -> None:
        self._timer.stop()

    def hideEvent(self, event) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        self._last = self.now()
        self._timer.start(FRAME_ACTIVE_MS)
        super().showEvent(event)

    def _busy(self) -> bool:
        t = self.now()
        return bool(
            any(m.is_animating() for m in self.models.values())
            or self.particles
            or self.orbs
            or self.badges
            or t < self.lightning_until
            or any(b.kind == "speech" and b.shown < len(b.text) for b in self.bubbles.values())
            or any(abs(self.spot[a] - self._spot_target(a)) > 0.01 for a in AGENTS)
            or any(t - c.born < 0.6 or (c.duration and t - c.born < c.duration + 0.5) for c in self.cards.values())
            or t - max((b.born for b in self.bubbles.values()), default=-9) < 0.4
            or abs(self.cam_zoom - 1.0) > 0.002 or abs(self.cam_x) > 0.5 or t < self.sweep_until
            or t - self.shake_at < 0.7
        )

    def _tick(self) -> None:
        t = self.now()
        dt = min(0.1, max(0.0, t - self._last))
        self._last = t
        for agent, m in self.models.items():
            if m.talking and self.level_source is not None:
                m.voice_level = self.level_source(agent)
            m.update(dt)
        speaker = next((a for a, m in self.models.items() if m.talking), None)
        motion = self.animations and not self.reduced_motion
        want_zoom = 1.03 if (speaker and motion) else 1.0
        want_x = 0.0
        if speaker and motion and speaker in self._geom:
            want_x = (self.width() / 2 - self._geom[speaker].center().x()) * 0.05
        k = min(1.0, dt * 1.6)
        self.cam_zoom += (want_zoom - self.cam_zoom) * k
        self.cam_x += (want_x - self.cam_x) * k
        for agent, b in self.bubbles.items():
            if b.kind == "speech" and b.shown < len(b.text):
                if b.mode == "typewriter" and self.typewriter and self.animations:
                    b.shown = min(len(b.text), b.shown + dt * self.typewriter_cps)
                elif b.mode == "speech" and self.typewriter and self.animations:
                    lead = len(b.text) * (b.speech_chars / max(1, len(b.text)))
                    b.shown = max(b.shown, min(len(b.text), lead + 6))
                else:
                    b.shown = len(b.text)
        for a in AGENTS:
            target = self._spot_target(a)
            self.spot[a] += (target - self.spot[a]) * min(1.0, dt * 4)
        self.badges = [b for b in self.badges if t - b.born < b.duration]
        self.orbs = [o for o in self.orbs if t - o[2] < 1.1]
        for kind in [k for k, c in self.cards.items() if c.duration is not None and t - c.born > c.duration + 0.5]:
            del self.cards[kind]
        alive = []
        for pt in self.particles:
            pt.age += dt
            pt.vy += 380 * dt
            pt.vx *= 0.99
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
            pt.rot += pt.vrot * dt
            if pt.age < pt.life and pt.y < self.height() + 20:
                alive.append(pt)
        self.particles = alive
        self.update()
        interval = FRAME_ACTIVE_MS if self._busy() else FRAME_IDLE_MS
        if self.reduced_motion:
            interval = 120 if self._busy() else 400
        if not self.animations and not self._busy():
            self._timer.stop()
        elif self._timer.interval() != interval:
            self._timer.setInterval(interval)

    def _spot_target(self, agent: str) -> float:
        if self.models[agent].talking or agent == self.active_agent:
            return 1.0
        return 0.22

    # -- director API --------------------------------------------------------

    def set_active(self, agent: str | None) -> None:
        self.active_agent = agent
        self.wake()

    def set_status(self, agent: str, orch_state: str, label: str) -> None:
        view = self.views[agent]
        view.state, view.label = orch_state, label
        self.wake()

    def set_activity(self, agent: str, text: str) -> None:
        self.views[agent].activity = text
        self.update()

    def set_turns(self, agent: str, turns: int) -> None:
        self.views[agent].turns = turns

    def show_speech(self, agent: str, text: str, mode: str = "typewriter") -> None:
        b = self.bubbles[agent]
        b.text, b.kind, b.born, b.mode, b.speech_chars = text, "speech", self.now(), mode, 0
        b.shown = 0.0 if (mode != "instant" and self.typewriter and self.animations) else len(text)
        self.views[agent].bubble._text = text
        self.wake()

    def speech_progress(self, agent: str, chars: int) -> None:
        self.bubbles[agent].speech_chars = chars

    def finish_speech_reveal(self, agent: str) -> None:
        b = self.bubbles[agent]
        b.shown = len(b.text)

    def show_status(self, agent: str, text: str) -> None:
        b = self.bubbles[agent]
        if b.kind == "status" and b.text == text:
            return
        b.text, b.kind, b.born, b.shown, b.mode = text, "status", self.now(), len(text), "instant"
        self.views[agent].bubble._text = text
        self.wake()

    def badge(self, text: str, anchor: str = "center", color: str = "#f5c542", duration: float = 2.6,
              style: str | None = None) -> None:
        style = style or ("caption" if anchor == "center" else "chip")
        self.badges = [b for b in self.badges if not (b.anchor == anchor and b.text == text)]
        self.badges.append(Badge(text, color, anchor, self.now(), duration, style))
        self.wake()

    def shake(self, amount: float = 6.0) -> None:
        if self.animations and not self.reduced_motion:
            self.shake_amp, self.shake_at = amount, self.now()
            self.wake()

    def light_sweep(self, seconds: float = 7.0) -> None:
        if self.animations and not self.reduced_motion:
            self.sweep_until = self.now() + seconds
            self.wake()

    def lightning(self, seconds: float = 1.3) -> None:
        """Tension: a glare line between the two of them."""
        self.lightning_until = self.now() + seconds
        self.wake()

    def handoff(self, source: str, target: str) -> None:
        if self.animations and not self.reduced_motion:
            self.orbs.append((source, target, self.now()))
        self.wake()

    def burst(self, agent: str, count: int = 18) -> None:
        if not self.animations or self.reduced_motion or agent not in self._geom:
            return
        head = self._head_anchor(agent)
        colours = ["#fff1a8", "#f2c94c", "#ffffff", ACCENT[agent]]
        for _ in range(count):
            a = self.rng.uniform(-math.pi, 0)
            speed = self.rng.uniform(140, 300)
            self.particles.append(Particle(head.x(), head.y() - 30, math.cos(a) * speed, math.sin(a) * speed, 0,
                                           self.rng.uniform(-6, 6), self.rng.choice(colours),
                                           self.rng.uniform(3, 6), self.rng.uniform(0.7, 1.2), shape="star"))
        self.wake()

    def confetti(self, count: int = 170, only: str | None = None) -> None:
        """Confetti everywhere, or (funnier) only over one character."""
        if not self.animations or self.reduced_motion:
            return
        w = max(1, self.width())
        lo, hi = 0.0, float(w)
        if only in self._geom:
            r = self._geom[only]
            lo, hi = r.left() + r.width() * 0.15, r.right() - r.width() * 0.15
        colours = ["#f2c94c", "#ffffff", "#7bd88f", "#6f9dff", "#e0564b", "#ffd166"]
        for _ in range(count):
            self.particles.append(Particle(
                self.rng.uniform(lo, hi), self.rng.uniform(-self.height() * 0.6, -10),
                self.rng.uniform(-40, 40), self.rng.uniform(40, 160), self.rng.uniform(0, 6.28),
                self.rng.uniform(-8, 8), self.rng.choice(colours), self.rng.uniform(5, 9),
                self.rng.uniform(3.5, 5.5), shape=self.rng.choice(["rect", "rect", "circle"])))
        self.wake()

    def show_card(self, kind: str, title: str, lines: list[str], color: str, duration: float | None = None,
                  footer: str = "", tagline: str = "") -> None:
        self.cards[kind] = Card(kind, title, lines, color, self.now(), duration, footer, tagline)
        if kind == "human":
            self.human_light_until = self.now() + (duration or 4)
        self.wake()

    def update_card_footer(self, kind: str, footer: str) -> None:
        if kind in self.cards:
            self.cards[kind].footer = footer
            self.update()

    def hide_card(self, kind: str) -> None:
        self.cards.pop(kind, None)
        self.update()

    def avatar_rect(self, agent: str) -> QRectF | None:
        return self._geom.get(agent)

    # -- layout ------------------------------------------------------------------

    def _layout(self) -> dict:
        w, h = float(self.width()), float(self.height())
        size = max(150.0, min(h * 0.84, w * 0.29))
        desk_top = h - max(44.0, h * 0.13)
        centres = {"Codex": w * 0.26, "Claude": w * 0.74}
        rects = {a: QRectF(centres[a] - size / 2, desk_top + size * 0.105 - size, size, size) for a in AGENTS}
        self._geom = rects
        return {"w": w, "h": h, "floor": desk_top, "desk": desk_top, "size": size, "cx": centres, "rects": rects}

    def _head_anchor(self, agent: str, L: dict | None = None) -> QPointF:
        r = (L["rects"] if L else self._geom).get(agent)
        if r is None:
            return QPointF(0, 0)
        return QPointF(r.center().x(), r.top() + r.height() * 0.36)

    # -- painting ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        L = self._layout()
        t = self.now()
        self._ensure_caches(L)
        p.save()
        self._apply_camera(p, L, t)
        p.drawPixmap(0, 0, self._backdrop)
        self._paint_live_set(p, L, t)
        self._paint_motes(p, L, t)
        if t < self.human_light_until:
            self._paint_human_light(p, L, t)
        for agent in AGENTS:
            self._paint_character_light(p, L, agent)
        for agent in AGENTS:
            model = self.models[agent]
            paint_avatar(p, L["rects"][agent], agent, model.pose(), active=agent == self.active_agent, layer="body")
        p.drawPixmap(0, 0, self._desks)
        self._paint_monitors(p, L, t)
        for agent in AGENTS:
            paint_avatar(p, L["rects"][agent], agent, self.models[agent].pose(), layer="front")
        if t < self.lightning_until:
            self._paint_tension(p, L, t)
        for source, target, born in self.orbs:
            self._paint_paper_ball(p, L, source, target, t - born)
        p.restore()
        for agent in AGENTS:
            self._paint_nameplate(p, L, agent, t)
        if self.show_on_air:
            self._paint_on_air(p, L, t)
        for agent in AGENTS:
            self._paint_bubble(p, L, agent, t)
        for card in self.cards.values():
            self._paint_card(p, L, card, t)
        self._paint_badges(p, L, t)
        self._paint_particles(p)
        p.end()

    def _apply_camera(self, p: QPainter, L: dict, t: float) -> None:
        dx = dy = 0.0
        since = t - self.shake_at
        if since < 0.7:
            decay = math.exp(-since * 6) * self.shake_amp
            dx = math.sin(since * 70) * decay
            dy = math.cos(since * 53) * decay * 0.6
        if abs(self.cam_zoom - 1.0) < 0.001 and abs(self.cam_x) < 0.3 and not dx:
            return
        cx, cy = L["w"] / 2, L["desk"] * 0.6
        p.translate(cx + self.cam_x + dx, cy + dy)
        p.scale(self.cam_zoom, self.cam_zoom)
        p.translate(-cx, -cy)

    # -- the set (cached) -------------------------------------------------------------

    def _ensure_caches(self, L: dict) -> None:
        size = (max(1, int(L["w"])), max(1, int(L["h"])))
        if self._backdrop is not None and self._backdrop_size == size:
            return
        self._backdrop_size = size
        self._backdrop = QPixmap(*size)
        painter = QPainter(self._backdrop)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._paint_room(painter, L)
        painter.end()
        self._desks = QPixmap(*size)
        self._desks.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self._desks)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._paint_desks(painter, L)
        painter.end()

    def _paint_room(self, p: QPainter, L: dict) -> None:
        w, h, desk = L["w"], L["h"], L["desk"]
        # a dim, warm, slightly grim wall
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0, QColor("#17130f"))
        bg.setColorAt(0.6, QColor("#221b16"))
        bg.setColorAt(1, QColor("#120e0b"))
        p.fillRect(QRectF(0, 0, w, h), bg)
        p.setPen(_pen("#ffffff", 1, 0.018))
        for i in range(1, 14):
            x = w * i / 14 + (i % 3) * 5
            p.drawLine(QPointF(x, 0), QPointF(x, h))
        # shelf line along the wall
        shelf_y = h * 0.52
        p.fillRect(QRectF(0, shelf_y, w, h * 0.012), QColor("#2e241c"))

        # --- left: Gilfoyle's server rack, "ANTON"
        rack = QRectF(w * 0.005, h * 0.03, w * 0.11, h * 0.82)
        g = QLinearGradient(rack.left(), 0, rack.right(), 0)
        g.setColorAt(0, QColor("#0b0c0e"))
        g.setColorAt(0.5, QColor("#1a1c20"))
        g.setColorAt(1, QColor("#0d0e11"))
        p.setPen(_pen("#000000", 1.2))
        p.setBrush(g)
        p.drawRect(rack)
        units = 11
        uh = rack.height() * 0.8 / units
        for i in range(units):
            r = QRectF(rack.left() + rack.width() * 0.08, rack.top() + rack.height() * 0.1 + i * uh,
                       rack.width() * 0.84, uh * 0.8)
            p.setPen(_pen("#2a2d33", 0.8))
            p.setBrush(QColor("#15171b"))
            p.drawRect(r)
            p.setPen(_pen("#23262b", 0.6))
            for k in range(6):
                x = r.left() + r.width() * (0.4 + k * 0.09)
                p.drawLine(QPointF(x, r.top() + 2), QPointF(x, r.bottom() - 2))
        label = QRectF(rack.left() + rack.width() * 0.12, rack.top() + rack.height() * 0.025, rack.width() * 0.76,
                       rack.height() * 0.055)
        p.setPen(_pen("#8c1d1d", 1))
        p.setBrush(QColor("#140606"))
        p.drawRect(label)
        f = _font(max(8, label.height() * 0.62), bold=True, family=MONO)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 140)
        p.setFont(f)
        p.setPen(QColor("#ff4a3d"))
        p.drawText(label, Qt.AlignmentFlag.AlignCenter, "ANTON")
        self._rack = rack
        self._rack_units = [(rack.left() + rack.width() * 0.13, rack.top() + rack.height() * 0.1 + i * uh + uh * 0.4)
                            for i in range(units)]
        # cables drooping out of the rack
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, colour in enumerate(("#1f3b73", "#6b1a1a", "#1c1c1c", "#2f5a2f", "#1c1c1c")):
            y0 = rack.top() + rack.height() * (0.2 + i * 0.12)
            path = QPainterPath(QPointF(rack.right(), y0))
            path.cubicTo(rack.right() + w * 0.04, y0 + h * 0.2, rack.right() + w * 0.02 + i * 9, h * 0.8,
                         rack.right() + w * 0.06 + i * 14, h)
            p.setPen(_pen(colour, 2.2))
            p.drawPath(path)

        # --- banner: HACKER HOSTEL
        banner = QRectF(w * 0.135, h * 0.05, w * 0.12, h * 0.28)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0f1a12"))
        path = QPainterPath(banner.topLeft())
        path.lineTo(banner.topRight())
        path.lineTo(banner.right(), banner.bottom())
        path.lineTo(banner.center().x(), banner.bottom() - banner.height() * 0.12)
        path.lineTo(banner.left(), banner.bottom())
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(_pen("#3c5a42", 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setFont(_font(max(9, banner.width() * 0.15), bold=True, family="Impact"))
        p.setPen(QColor("#d8d1bd"))
        p.drawText(QRectF(banner.left(), banner.top() + banner.height() * 0.12, banner.width(), banner.height() * 0.5),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, "HACKER\nHOSTEL")
        # a little pipe-and-leaf mark
        cx, cy = banner.center().x(), banner.top() + banner.height() * 0.66
        s = banner.width() * 0.13
        p.setPen(_pen("#5fc46a", max(1.4, s * 0.22)))
        p.drawLine(QPointF(cx - s, cy + s * 0.6), QPointF(cx + s * 0.6, cy - s * 0.4))
        p.setBrush(QColor("#5fc46a"))
        p.setPen(Qt.PenStyle.NoPen)
        leaf = QPainterPath(QPointF(cx + s * 0.4, cy - s * 0.3))
        leaf.quadTo(cx + s * 1.4, cy - s * 1.6, cx + s * 1.1, cy - s * 0.1)
        leaf.quadTo(cx + s * 0.9, cy + s * 0.2, cx + s * 0.4, cy - s * 0.3)
        p.drawPath(leaf)

        # --- centre: the whiteboard
        wb = QRectF(w * 0.39, h * 0.06, w * 0.22, h * 0.42)
        p.setPen(_pen("#6f6a62", 2.0))
        g = QLinearGradient(wb.topLeft(), wb.bottomRight())
        g.setColorAt(0, QColor("#cfcbc2"))
        g.setColorAt(1, QColor("#aaa59b"))
        p.setBrush(g)
        p.drawRect(wb)
        p.setPen(_pen("#8a857c", 1.0))
        p.drawLine(QPointF(wb.left(), wb.bottom() + 3), QPointF(wb.right(), wb.bottom() + 3))
        marker = "Segoe Print"
        p.setFont(_font(max(10, wb.height() * 0.1), family=marker))
        p.setPen(QColor("#3a4a6a"))
        p.drawText(QRectF(wb.left() + wb.width() * 0.05, wb.top() + wb.height() * 0.02, wb.width() * 0.9,
                          wb.height() * 0.2), Qt.AlignmentFlag.AlignLeft, "Pied Piper")
        # a boxes-and-arrows diagram
        p.setPen(_pen("#3a4a6a", 1.2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        bx, by, bs = wb.left() + wb.width() * 0.08, wb.top() + wb.height() * 0.32, wb.width() * 0.07
        nodes = [(0.2, 0.0), (0.0, 0.3), (0.4, 0.3), (0.0, 0.6), (0.4, 0.6)]
        pts = [QPointF(bx + nx * wb.width(), by + ny * wb.height()) for nx, ny in nodes]
        for a, b in ((0, 1), (0, 2), (1, 3), (2, 4)):
            p.drawLine(pts[a] + QPointF(bs / 2, bs), pts[b] + QPointF(bs / 2, 0))
        for pt in pts:
            p.drawRect(QRectF(pt.x(), pt.y(), bs, bs * 0.8))
        p.setFont(_font(max(8, wb.height() * 0.075), family=marker))
        for i, line in enumerate(("- Build", "- Test", "- Ship?", "- Probably")):
            p.drawText(QPointF(wb.left() + wb.width() * 0.6, wb.top() + wb.height() * (0.36 + i * 0.13)), line)
        p.setPen(QColor("#8a2a2a"))
        p.setFont(_font(max(7, wb.height() * 0.06), family=marker))
        p.drawText(QPointF(wb.left() + wb.width() * 0.06, wb.bottom() - wb.height() * 0.05), "Weissman: 5.2")
        self._whiteboard = wb

        # --- right: a night window with blinds and a poster
        win = QRectF(w * 0.8, h * 0.06, w * 0.14, h * 0.36)
        p.setPen(_pen("#3a3129", 3))
        g = QLinearGradient(0, win.top(), 0, win.bottom())
        g.setColorAt(0, QColor("#0e1a2e"))
        g.setColorAt(1, QColor("#1b2a44"))
        p.setBrush(g)
        p.drawRect(win)
        p.setPen(_pen("#8894a8", 1.4, 0.55))
        y = win.top() + 4
        while y < win.bottom() - 2:
            p.drawLine(QPointF(win.left() + 2, y), QPointF(win.right() - 2, y))
            y += max(4.0, win.height() / 18)
        poster = QRectF(w * 0.66, h * 0.09, w * 0.1, h * 0.25)
        p.setPen(_pen("#000000", 1))
        p.setBrush(QColor("#2b2f3a"))
        p.drawRect(poster)
        p.setFont(_font(max(8, poster.width() * 0.13), bold=True, family="Impact"))
        p.setPen(QColor("#e8b04a"))
        p.drawText(poster.adjusted(4, 6, -4, -4), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   "ALWAYS\nBE\nSHIPPING")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c("#e8b04a", 0.8))
        p.drawEllipse(QPointF(poster.center().x(), poster.bottom() - poster.height() * 0.2), poster.width() * 0.12,
                      poster.width() * 0.12)

        # --- the back desk: little monitors, a lamp, cans, a penguin
        back_y = h * 0.56
        p.setBrush(QColor("#3a2c21"))
        p.setPen(_pen("#1a130d", 1))
        p.drawRect(QRectF(w * 0.33, back_y, w * 0.34, h * 0.03))
        p.fillRect(QRectF(w * 0.34, back_y + h * 0.03, w * 0.32, h * 0.3), QColor("#140f0b"))
        for i, x in enumerate((0.36, 0.52)):
            mon = QRectF(w * x, back_y - h * 0.13, w * 0.1, h * 0.12)
            p.setPen(_pen("#050505", 2))
            p.setBrush(QColor("#0a0f16"))
            p.drawRect(mon)
            p.fillRect(QRectF(mon.center().x() - 3, mon.bottom(), 6, h * 0.012), QColor("#111"))
            rng = random.Random(i + 4)
            for k in range(7):
                p.fillRect(QRectF(mon.left() + 5 + rng.random() * 8, mon.top() + 5 + k * mon.height() / 8,
                                  mon.width() * (0.2 + rng.random() * 0.55), 1.6),
                           _c("#6fd08c" if i == 0 else "#7fb2ff", 0.55))
        self._back_monitors = [QRectF(w * x, back_y - h * 0.13, w * 0.1, h * 0.12) for x in (0.36, 0.52)]
        # desk lamp
        base = QPointF(w * 0.485, back_y)
        p.setPen(_pen("#1c1c1c", 3))
        p.drawLine(base, base + QPointF(-w * 0.012, -h * 0.13))
        p.drawLine(base + QPointF(-w * 0.012, -h * 0.13), base + QPointF(w * 0.02, -h * 0.19))
        shade = QPainterPath(base + QPointF(w * 0.012, -h * 0.215))
        shade.lineTo(base + QPointF(w * 0.045, -h * 0.17))
        shade.lineTo(base + QPointF(w * 0.012, -h * 0.155))
        shade.closeSubpath()
        p.setBrush(QColor("#2a2a2a"))
        p.drawPath(shade)
        self._lamp = base + QPointF(w * 0.03, -h * 0.16)
        # cans and a penguin
        for i, (x, colour) in enumerate(((0.345, "#b3191f"), (0.47, "#1e5fa8"), (0.635, "#d6d6d6"))):
            can = QRectF(w * x, back_y - h * 0.05, w * 0.012, h * 0.05)
            p.setPen(_pen("#000000", 0.8))
            p.setBrush(QColor(colour))
            p.drawRoundedRect(can, 2, 2)
        px_, py_ = w * 0.615, back_y
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#111111"))
        p.drawEllipse(QPointF(px_, py_ - h * 0.03), w * 0.01, h * 0.032)
        p.drawEllipse(QPointF(px_, py_ - h * 0.068), w * 0.008, h * 0.018)
        p.setBrush(QColor("#f1f1f1"))
        p.drawEllipse(QPointF(px_, py_ - h * 0.026), w * 0.006, h * 0.022)
        p.setBrush(QColor("#f2b233"))
        p.drawEllipse(QPointF(px_, py_ - h * 0.064), w * 0.004, h * 0.005)
        # vignette
        v = QRadialGradient(QPointF(w / 2, h * 0.45), max(w, h) * 0.75)
        v.setColorAt(0.55, _c("#000000", 0.0))
        v.setColorAt(1, _c("#000000", 0.55))
        p.fillRect(QRectF(0, 0, w, h), v)

    def _paint_desks(self, p: QPainter, L: dict) -> None:
        w, h, desk = L["w"], L["h"], L["desk"]
        # one long cheap desk running across the foreground
        top = QRectF(-10, desk - h * 0.012, w + 20, h * 0.03)
        g = QLinearGradient(0, top.top(), 0, top.bottom())
        g.setColorAt(0, QColor("#5a4431"))
        g.setColorAt(1, QColor("#3a2b1f"))
        p.setPen(_pen("#1e150e", 1))
        p.setBrush(g)
        p.drawRect(top)
        front = QRectF(-10, top.bottom(), w + 20, h - top.bottom() + 10)
        g = QLinearGradient(0, front.top(), 0, front.bottom())
        g.setColorAt(0, QColor("#2a1f16"))
        g.setColorAt(1, QColor("#120d09"))
        p.setBrush(g)
        p.drawRect(front)
        p.setPen(_pen("#000000", 1, 0.4))
        p.drawLine(QPointF(0, top.bottom() + 1), QPointF(w, top.bottom() + 1))
        # keyboards in front of each character
        for agent in AGENTS:
            r = L["rects"][agent]
            kb = QRectF(r.center().x() - r.width() * 0.2, desk - h * 0.018, r.width() * 0.4, h * 0.022)
            p.setPen(_pen("#050505", 1))
            p.setBrush(QColor("#1b1c20"))
            p.drawRoundedRect(kb, 3, 3)
            p.setPen(_pen("#34363d", 1))
            for k in range(1, 12):
                x = kb.left() + kb.width() * k / 12
                p.drawLine(QPointF(x, kb.top() + 2), QPointF(x, kb.bottom() - 2))
        # clutter: pizza box, mugs, cans
        pizza = QRectF(w * 0.4, desk - h * 0.035, w * 0.2, h * 0.04)
        p.setPen(_pen("#6d5234", 1))
        p.setBrush(QColor("#c9a574"))
        box = QPainterPath(QPointF(pizza.left(), pizza.bottom()))
        box.lineTo(pizza.left() + pizza.width() * 0.06, pizza.top())
        box.lineTo(pizza.right() - pizza.width() * 0.06, pizza.top())
        box.lineTo(pizza.right(), pizza.bottom())
        box.closeSubpath()
        p.drawPath(box)
        p.setFont(_font(max(8, pizza.height() * 0.55), bold=True, family="Impact"))
        p.setPen(QColor("#9b2a1c"))
        p.drawText(pizza, Qt.AlignmentFlag.AlignCenter, "PIZZA")
        for agent, colour in (("Codex", "#141414"), ("Claude", "#e8e2d6")):
            r = L["rects"][agent]
            side = -1 if agent == "Codex" else 1
            mug = QRectF(r.center().x() - side * r.width() * 0.34 - w * 0.013, desk - h * 0.06, w * 0.026, h * 0.05)
            p.setPen(_pen("#000000", 1))
            p.setBrush(QColor(colour))
            p.drawRoundedRect(mug, 2, 2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(mug.right() - 2, mug.top() + mug.height() * 0.2, mug.width() * 0.5, mug.height() * 0.5),
                      -90 * 16, 180 * 16)
            if agent == "Claude":
                p.setPen(_pen("#5fc46a", 1.4))
                p.drawLine(QPointF(mug.left() + 4, mug.center().y()), QPointF(mug.right() - 4, mug.center().y() - 3))
        can = QRectF(L["rects"]["Codex"].center().x() + L["rects"]["Codex"].width() * 0.3, desk - h * 0.065,
                     w * 0.014, h * 0.06)
        p.setPen(_pen("#000000", 1))
        p.setBrush(QColor("#161616"))
        p.drawRoundedRect(can, 2, 2)
        p.setPen(_pen("#c0392b", 2))
        p.drawLine(QPointF(can.left() + 2, can.center().y()), QPointF(can.right() - 2, can.center().y() - 4))
        # each character's own monitor, on the outer side, angled toward him
        self._monitors = {}
        for agent in AGENTS:
            r = L["rects"][agent]
            side = -1 if agent == "Codex" else 1
            mw, mh = r.width() * 0.34, r.height() * 0.3
            x = r.center().x() + side * r.width() * 0.42
            mon = QRectF(x - mw / 2, desk - mh - h * 0.02, mw, mh)
            # stand
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#0c0c0e"))
            p.drawRect(QRectF(mon.center().x() - 4, mon.bottom(), 8, h * 0.02))
            p.drawRoundedRect(QRectF(mon.center().x() - mw * 0.18, desk - h * 0.008, mw * 0.36, h * 0.01), 2, 2)
            # we see it at an angle: a trapezoid, with the screen facing the character
            near, far = (mon.right(), mon.left()) if side < 0 else (mon.left(), mon.right())
            body = QPainterPath(QPointF(far, mon.top() + mh * 0.08))
            body.lineTo(near, mon.top())
            body.lineTo(near, mon.bottom())
            body.lineTo(far, mon.bottom() - mh * 0.08)
            body.closeSubpath()
            p.setPen(_pen("#000000", 1.4))
            p.setBrush(QColor("#0b0c0f"))
            p.drawPath(body)
            self._monitors[agent] = (mon, side)

    # -- live parts of the set ------------------------------------------------------

    @staticmethod
    def _fake_code_widths(agent: str) -> list[tuple[float, float]]:
        rng = random.Random(11 if agent == "Codex" else 23)
        return [(rng.random() * 0.25, 0.25 + rng.random() * 0.6) for _ in range(40)]

    def _paint_live_set(self, p: QPainter, L: dict, t: float) -> None:
        # Anton's LEDs
        p.setPen(Qt.PenStyle.NoPen)
        busy = self.on_air and not self.paused
        for i, (x, y) in enumerate(getattr(self, "_rack_units", [])):
            for k, colour in enumerate(("#39d98a", "#f5c542", "#ff4a3d", "#4aa8ff")):
                on = ((int(t * (6 if busy else 1.5)) * 7 + i * 5 + k * 3) % 11) < (6 if busy else 3)
                p.setBrush(_c(colour, 0.95 if on else 0.15))
                p.drawEllipse(QPointF(x + k * self._rack.width() * 0.07, y), 1.6, 1.6)

    def _paint_monitors(self, p: QPainter, L: dict, t: float) -> None:
        for agent, (mon, side) in getattr(self, "_monitors", {}).items():
            active = agent == self.active_agent
            colour = SCREEN[agent]
            glow = 0.9 if active else 0.45
            near = mon.right() if side < 0 else mon.left()
            # the lit edge of the screen we can just see
            edge = QRectF(near - (4 if side < 0 else 0), mon.top() + 3, 4, mon.height() - 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_c(colour, 0.55 * glow))
            p.drawRect(edge)
            # screen light spilling toward the character
            r = L["rects"][agent]
            spill = QRadialGradient(QPointF(near, mon.center().y()), r.width() * 0.45)
            spill.setColorAt(0, _c(colour, 0.14 * glow))
            spill.setColorAt(1, _c(colour, 0.0))
            p.setBrush(spill)
            p.drawEllipse(QPointF(near, mon.center().y()), r.width() * 0.45, r.width() * 0.4)
        # the back monitors scroll while someone works
        if self.active_agent:
            for i, mon in enumerate(getattr(self, "_back_monitors", [])):
                agent = "Codex" if i == 0 else "Claude"
                if agent != self.active_agent:
                    continue
                offset = int(t * 5) % 8
                p.fillRect(mon.adjusted(2, 2, -2, -2), QColor("#070b10"))
                lines = self._code_lines[agent]
                for k in range(7):
                    indent, width = lines[(k + offset) % len(lines)]
                    p.fillRect(QRectF(mon.left() + 5 + indent * mon.width(), mon.top() + 5 + k * mon.height() / 8,
                                      mon.width() * width * 0.8, 1.6), _c(SCREEN[agent], 0.8))

    def _paint_character_light(self, p: QPainter, L: dict, agent: str) -> None:
        k = self.spot[agent]
        if k < 0.05:
            return
        r = L["rects"][agent]
        c = QPointF(r.center().x(), r.top() + r.height() * 0.45)
        g = QRadialGradient(c, r.width() * 0.62)
        g.setColorAt(0, _c("#ffd9a0", 0.05 * k))
        g.setColorAt(1, _c("#ffd9a0", 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, r.width() * 0.62, r.width() * 0.62)

    def _paint_motes(self, p: QPainter, L: dict, t: float) -> None:
        if not self.animations or self.reduced_motion or not hasattr(self, "_lamp"):
            return
        lamp = self._lamp
        p.setPen(Qt.PenStyle.NoPen)
        cone = QPainterPath(lamp)
        cone.lineTo(lamp + QPointF(L["w"] * 0.1, L["h"] * 0.3))
        cone.lineTo(lamp + QPointF(-L["w"] * 0.05, L["h"] * 0.3))
        cone.closeSubpath()
        g = QLinearGradient(lamp, lamp + QPointF(0, L["h"] * 0.3))
        g.setColorAt(0, _c("#ffd99a", 0.16))
        g.setColorAt(1, _c("#ffd99a", 0.0))
        p.setBrush(g)
        p.drawPath(cone)
        for fx, fy, r, phase in self.motes:
            y = lamp.y() + ((fy + t * 0.015 * r) % 1.0) * L["h"] * 0.3
            spread = (y - lamp.y()) * 0.5
            x = lamp.x() + (fx - 0.3) * spread + math.sin(t * 0.6 + phase * 6) * 4
            a = 0.12 + 0.2 * (0.5 + 0.5 * math.sin(t * 1.5 + phase * 9))
            p.setBrush(_c("#fff1d0", a))
            p.drawEllipse(QPointF(x, y), r, r)

    def _paint_on_air(self, p: QPainter, L: dict, t: float) -> None:
        w = L["w"]
        rect = QRectF(w / 2 - 44, 6, 88, 20)
        lit = self.on_air and not self.paused
        pulse = 0.75 + 0.25 * math.sin(t * 2.4) if lit else 0.0
        if lit:
            glow = QRadialGradient(rect.center(), 60)
            glow.setColorAt(0, _c("#ff3b3b", 0.2 * pulse))
            glow.setColorAt(1, _c("#ff3b3b", 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(rect.center(), 60, 24)
        p.setPen(_pen("#ff5a5a" if lit else "#4a2a2e", 1.3, 0.9 if lit else 1))
        p.setBrush(_c("#2a0d10" if lit else "#16121a", 0.9))
        p.drawRoundedRect(rect, 5, 5)
        p.setFont(_font(11, bold=True))
        p.setPen(_c("#ff7070" if lit else "#5a3a40"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "⏸ PAUSED" if self.paused else "● LIVE")

    def _paint_human_light(self, p: QPainter, L: dict, t: float) -> None:
        k = min(1.0, (self.human_light_until - t) / 0.6)
        w, h = L["w"], L["h"]
        g = QRadialGradient(QPointF(w / 2, h * 0.4), w * 0.28)
        g.setColorAt(0, _c(ACCENT["Human"], 0.14 * k))
        g.setColorAt(1, _c(ACCENT["Human"], 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(w / 2, h * 0.4), w * 0.28, h * 0.5)

    def _paint_tension(self, p: QPainter, L: dict, t: float) -> None:
        a = self._head_anchor("Codex", L)
        b = self._head_anchor("Claude", L)
        size = L["size"]
        start = QPointF(a.x() + size * 0.14, a.y() - size * 0.02)
        end = QPointF(b.x() - size * 0.14, b.y() - size * 0.02)
        rng = random.Random(int(t * 14))
        pts = [start]
        n = 12
        for i in range(1, n):
            f = i / n
            pts.append(QPointF(start.x() + (end.x() - start.x()) * f,
                               start.y() + (end.y() - start.y()) * f + rng.uniform(-1, 1) * size * 0.03))
        pts.append(end)
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        k = min(1.0, (self.lightning_until - t) / 0.3) * (0.6 + 0.4 * rng.random())
        p.setBrush(Qt.BrushStyle.NoBrush)
        for width, colour, alpha in ((8, "#ff4a3d", 0.12), (2.2, "#ff8f7a", 0.8), (1, "#fff1ec", 0.9)):
            p.setPen(_pen(colour, width, alpha * k))
            p.drawPath(path)

    def _paint_paper_ball(self, p: QPainter, L: dict, source: str, target: str, age: float) -> None:
        """Handoffs: a crumpled sticky note lobbed across the room."""
        f = _ease_out(age / 0.9)
        a, b = self._head_anchor(source, L), self._head_anchor(target, L)
        ctrl = QPointF((a.x() + b.x()) / 2, min(a.y(), b.y()) - L["size"] * 0.45)
        pt = QPointF((1 - f) ** 2 * a.x() + 2 * (1 - f) * f * ctrl.x() + f * f * b.x(),
                     (1 - f) ** 2 * a.y() + 2 * (1 - f) * f * ctrl.y() + f * f * b.y())
        fade = 1.0 if age < 0.9 else max(0.0, 1 - (age - 0.9) / 0.2)
        p.save()
        p.translate(pt)
        p.rotate(age * 720)
        r = 7.5
        p.setPen(_pen("#8a7a3a", 1, fade))
        p.setBrush(_c("#f7e27a", fade))
        path = QPainterPath(QPointF(r, 0))
        for i in range(1, 9):
            ang = i * math.pi / 4.5
            rr = r * (0.8 + 0.25 * ((i * 7) % 3) / 2)
            path.lineTo(math.cos(ang) * rr, math.sin(ang) * rr)
        path.closeSubpath()
        p.drawPath(path)
        p.setPen(_pen("#b59a2e", 0.8, fade))
        p.drawLine(QPointF(-3, -2), QPointF(2, 3))
        p.restore()

    # -- labels ------------------------------------------------------------------------

    def _paint_nameplate(self, p: QPainter, L: dict, agent: str, t: float) -> None:
        view = self.views[agent]
        w, h = L["w"], L["h"]
        accent = ACCENT[agent]
        left = agent == "Codex"
        active = agent == self.active_agent or self.models[agent].talking
        margin = 16
        name_font = _font(max(18, h * 0.055), bold=True, family="Bahnschrift")
        name_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
        sub_font = _font(max(11, h * 0.03), bold=True, family="Bahnschrift")
        fm_n, fm_s = QFontMetricsF(name_font), QFontMetricsF(sub_font)
        name = CHARACTER[agent].upper()
        align = Qt.AlignmentFlag.AlignLeft if left else Qt.AlignmentFlag.AlignRight
        base_y = h - margin - fm_s.height() * 2.2
        box_w = max(fm_n.horizontalAdvance(name), 180.0)
        x = margin if left else w - margin - box_w
        # soft dark backing so it reads over the desk
        g = QLinearGradient(0, base_y - fm_n.height(), 0, h)
        g.setColorAt(0, _c("#000000", 0.0))
        g.setColorAt(1, _c("#000000", 0.55))
        p.fillRect(QRectF(0 if left else w * 0.55, base_y - fm_n.height() * 1.2, w * 0.45, h), g)
        p.setFont(name_font)
        p.setPen(_c(accent, 1.0 if active else 0.85))
        p.drawText(QRectF(x, base_y - fm_n.height(), box_w, fm_n.height()), align | Qt.AlignmentFlag.AlignBottom, name)
        p.setFont(sub_font)
        p.setPen(_c(accent, 0.8))
        p.drawText(QRectF(x, base_y, box_w, fm_s.height()), align | Qt.AlignmentFlag.AlignTop, f"({agent})")
        # status label + public activity (factual)
        p.setFont(_font(max(10, h * 0.024), bold=True))
        status = view.label + (f"  ·  {view.activity}" if view.activity else "")
        colour = {"⚠": "#ff6b6b", "✓": "#8fd9ff", "⏸": "#f5c542", "👀": "#f5c542"}.get(view.label[:1], "#c9c2b4")
        fm = QFontMetricsF(p.font())
        status = fm.elidedText(status, Qt.TextElideMode.ElideRight, w * 0.4)
        p.setPen(_c(colour))
        p.drawText(QRectF(x if left else w - margin - w * 0.4, base_y + fm_s.height() + 2, w * 0.4, fm.height() + 2),
                   align | Qt.AlignmentFlag.AlignTop, status)
        if active:
            pulse = 0.5 + 0.5 * math.sin(t * 5)
            dot = QPointF(x + fm_n.horizontalAdvance(name) + 12 if left else w - margin - fm_n.horizontalAdvance(name) - 12,
                          base_y - fm_n.height() * 0.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_c(accent, 0.25 + 0.35 * pulse))
            p.drawEllipse(dot, 7, 7)
            p.setBrush(_c(accent))
            p.drawEllipse(dot, 3.5, 3.5)

    def _paint_bubble(self, p: QPainter, L: dict, agent: str, t: float) -> None:
        b = self.bubbles[agent]
        if b.kind == "none" or not b.text:
            return
        if any(c.kind in ("waiting", "complete", "human") for c in self.cards.values()):
            return  # the centre card has the floor
        w, h = L["w"], L["h"]
        head = L["rects"][agent]
        anchor = self._head_anchor(agent, L)
        speech = b.kind == "speech"
        left = agent == "Codex"
        style = BUBBLE[agent]
        gap = head.width() * 0.16
        # each character owns his half of the room: bubbles never cross the middle
        room = (w / 2 - 10) - (anchor.x() + gap) if left else (anchor.x() - gap) - (w / 2 + 10)
        max_w = max(160.0, min(w * 0.3, 430.0 if speech else 300.0, room + head.width() * 0.25))
        pad_x, pad_y = (15.0, 11.0) if speech else (11.0, 7.0)
        text = b.text
        sizes = (15.5, 14.5, 13.5, 12.5, 11.5) if speech else (12.0,)
        top_limit = 34.0
        available = max(40.0, anchor.y() - head.height() * 0.05 - top_limit)
        for px in sizes:
            font = _font(px, bold=speech and agent == "Claude" and False, family=MONO if speech else "Segoe UI",
                         italic=not speech)
            fm = QFontMetricsF(font)
            rect_text = fm.boundingRect(QRectF(0, 0, max_w - pad_x * 2, 4000), int(Qt.TextFlag.TextWordWrap), text)
            if rect_text.height() + pad_y * 2 <= available + head.height() * 0.3:
                break
        text_w = min(max_w - pad_x * 2, max(rect_text.width(), 40))
        text_h = min(rect_text.height(), available + head.height() * 0.3 - pad_y * 2)
        bw, bh = text_w + pad_x * 2, text_h + pad_y * 2
        # beside the head, toward the middle of the room (but not past it)
        x = anchor.x() + gap if left else anchor.x() - gap - bw
        x = min(x, w / 2 - 10 - bw) if left else max(x, w / 2 + 10)
        x = max(10.0, min(w - bw - 10, x))
        y = max(top_limit, anchor.y() - head.height() * 0.3 - bh * 0.6)
        rect = QRectF(x, y, bw, bh)

        appear = _ease_back((t - b.born) / 0.28) if self.animations and not self.reduced_motion else 1.0
        other = "Claude" if left else "Codex"
        dim = 0.85 if (self.models[other].talking and not self.models[agent].talking) else 1.0
        p.save()
        origin = QPointF(rect.left() if left else rect.right(), rect.bottom())
        p.translate(origin)
        if speech and agent == "Claude" and self.animations:
            p.rotate(-0.8)  # Dinesh's bubbles are slightly less composed
        s = 0.85 + 0.15 * appear
        p.scale(s, s)
        p.translate(-origin)
        p.setOpacity(max(0.0, min(1.0, appear)) * dim)
        radius = 10 if agent == "Codex" else 16
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        tail_base = QPointF(rect.left() + 26 if left else rect.right() - 26, rect.bottom() - 2)
        tip = QPointF(anchor.x() + (head.width() * 0.08 if left else -head.width() * 0.08), anchor.y() - head.height() * 0.08)
        tail = QPainterPath(tail_base + QPointF(-10, 0))
        tail.quadTo(tail_base + QPointF(-2, 10), tip)
        tail.quadTo(tail_base + QPointF(6, 8), tail_base + QPointF(10, 0))
        tail.closeSubpath()
        path = path.united(tail)
        if speech:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_c("#000000", 0.35))
            p.drawPath(path.translated(0, 4))
            p.setBrush(_c(style["fill"]))
            p.setPen(_pen(style["edge"], 2.0))
            p.drawPath(path)
            p.setPen(_c(style["ink"]))
        else:
            p.setPen(_pen(ACCENT[agent], 1.2, 0.55))
            p.setBrush(_c("#17120f", 0.9))
            p.drawPath(path)
            p.setPen(_c("#b9b1a3"))
        p.setFont(font)
        shown = text if b.shown >= len(text) else text[: int(b.shown)]
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        text_rect = QRectF(rect.left() + pad_x, rect.top() + pad_y, text_w, text_h)
        p.save()
        p.setClipRect(text_rect.adjusted(-2, -2, 2, 2))
        p.drawText(text_rect, shown, option)
        p.restore()
        if not speech:
            dots = "." * (1 + int(t * 2.5) % 3)
            p.setPen(_c(ACCENT[agent], 0.8))
            p.drawText(QRectF(rect.right() - pad_x - 4, rect.top() + pad_y - 1, 30, text_h + 2),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "" if text.endswith("…") else dots)
        p.restore()

    def _paint_card(self, p: QPainter, L: dict, card: Card, t: float) -> None:
        w, h = L["w"], L["h"]
        cw = max(260.0, min(w * 0.36, 500.0))
        age = t - card.born
        fade_in = _ease_back(age / 0.35) if self.animations else 1.0
        fade_out = 1.0
        if card.duration is not None:
            fade_out = max(0.0, min(1.0, (card.duration + 0.5 - age) / 0.5))
        title_font = _font(17, bold=True, family="Bahnschrift")
        title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
        tag_font = _font(26, italic=True, family="Georgia")
        body_font = _font(12.5, family=MONO)
        fm_t, fm_b, fm_g = QFontMetricsF(title_font), QFontMetricsF(body_font), QFontMetricsF(tag_font)
        body = "\n".join(card.lines)
        body_rect = fm_b.boundingRect(QRectF(0, 0, cw - 36, 2000), int(Qt.TextFlag.TextWordWrap), body)
        footer_h = 22 if card.footer else 0
        tag_h = fm_g.height() + 6 if card.tagline else 0
        ch = 20 + fm_t.height() + tag_h + 8 + body_rect.height() + footer_h + 18
        ch = min(ch, h - 30)
        rect = QRectF(w / 2 - cw / 2, max(30.0, h * 0.42 - ch / 2), cw, ch)
        p.save()
        p.setOpacity(max(0.0, min(1.0, fade_in)) * fade_out)
        c = rect.center()
        p.translate(c)
        k = 0.9 + 0.1 * min(1.0, fade_in)
        p.scale(k, k)
        p.translate(-c)
        pulse = 0.6 + 0.4 * math.sin(t * 3) if card.kind == "waiting" else 1.0
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c("#000000", 0.45))
        p.drawRoundedRect(rect.translated(0, 6), 10, 10)
        bg = QLinearGradient(0, rect.top(), 0, rect.bottom())
        bg.setColorAt(0, _c("#1d1814", 0.97))
        bg.setColorAt(1, _c("#120e0b", 0.97))
        p.setBrush(bg)
        p.setPen(_pen(card.color, 1.8, 0.55 + 0.45 * pulse))
        p.drawRoundedRect(rect, 10, 10)
        y = rect.top() + 14
        p.setFont(title_font)
        p.setPen(_c(card.color))
        p.drawText(QRectF(rect.left() + 18, y, cw - 36, fm_t.height() + 4),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, card.title)
        y += fm_t.height() + 6
        if card.tagline:
            p.setFont(tag_font)
            p.setPen(_c("#efe6d4"))
            p.drawText(QRectF(rect.left() + 18, y, cw - 36, fm_g.height() + 2), Qt.AlignmentFlag.AlignHCenter,
                       card.tagline)
            y += tag_h
        p.setFont(body_font)
        p.setPen(_c("#ddd5c6"))
        option = QTextOption(Qt.AlignmentFlag.AlignHCenter)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        p.drawText(QRectF(rect.left() + 18, y + 4, cw - 36, rect.bottom() - y - footer_h - 12), body, option)
        if card.footer:
            p.setFont(_font(11.5, bold=True))
            p.setPen(_c(card.color, 0.9))
            p.drawText(QRectF(rect.left() + 12, rect.bottom() - footer_h - 10, cw - 24, footer_h),
                       Qt.AlignmentFlag.AlignCenter, card.footer)
        p.restore()

    def _paint_badges(self, p: QPainter, L: dict, t: float) -> None:
        stacks: dict[str, int] = {}
        for badge in self.badges:
            age = t - badge.born
            idx = stacks.get(badge.anchor, 0)
            stacks[badge.anchor] = idx + 1
            caption = badge.style == "caption"
            font = _font(16 if caption else 12, bold=True, family="Bahnschrift")
            font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 118 if caption else 106)
            fm = QFontMetricsF(font)
            bw = fm.horizontalAdvance(badge.text) + (34 if caption else 22)
            bh = 32 if caption else 24
            if badge.anchor in L["rects"]:
                head = self._head_anchor(badge.anchor, L)
                r = L["rects"][badge.anchor]
                outward = -1 if badge.anchor == "Codex" else 1
                x = head.x() + outward * (r.width() * 0.3 + bw / 2)
                x = max(bw / 2 + 8, min(L["w"] - bw / 2 - 8, x))
                y = head.y() - r.height() * 0.1 + idx * 30
                travel = 14
            else:
                x, y = L["w"] / 2, L["h"] * 0.62 + idx * 40
                travel = 0
            rise = _ease_out(age / badge.duration) * travel if self.animations else 0
            slide = (1 - _ease_out(age / 0.35)) * 30 if (caption and self.animations) else 0
            pop = _ease_back(age / 0.3) if (self.animations and not caption) else 1
            alpha = min(1.0, (badge.duration - age) / 0.5, age / 0.15 if caption else 1.0)
            rect = QRectF(x - bw / 2 + slide, y - bh / 2 - rise, bw, bh)
            p.save()
            p.setOpacity(max(0.0, alpha))
            c = rect.center()
            p.translate(c)
            p.scale(pop, pop)
            p.translate(-c)
            p.setPen(Qt.PenStyle.NoPen)
            if caption:
                # a lower-third caption: black tape, coloured type, a coloured edge
                p.setBrush(_c("#000000", 0.85))
                p.drawRect(rect)
                p.setBrush(_c(badge.color))
                p.drawRect(QRectF(rect.left(), rect.top(), 5, rect.height()))
                p.setFont(font)
                p.setPen(_c(badge.color))
                p.drawText(rect.adjusted(6, 0, 0, 0), Qt.AlignmentFlag.AlignCenter, badge.text)
            else:
                p.setBrush(_c("#000000", 0.35))
                p.drawRoundedRect(rect.translated(0, 3), 6, 6)
                p.setBrush(_c(badge.color))
                p.drawRoundedRect(rect, 6, 6)
                p.setFont(font)
                p.setPen(_c("#15120f"))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, badge.text)
            p.restore()

    def _paint_particles(self, p: QPainter) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self.particles:
            fade = max(0.0, min(1.0, (pt.life - pt.age) / 0.6))
            p.save()
            p.translate(pt.x, pt.y)
            p.rotate(math.degrees(pt.rot))
            p.setBrush(_c(pt.color, fade))
            if pt.shape == "circle":
                p.drawEllipse(QPointF(0, 0), pt.size * 0.4, pt.size * 0.4)
            elif pt.shape == "star":
                path = QPainterPath(QPointF(0, -pt.size))
                for i in range(1, 8):
                    a = i * math.pi / 4
                    rr = pt.size if i % 2 == 0 else pt.size * 0.35
                    path.lineTo(math.sin(a) * rr, -math.cos(a) * rr)
                path.closeSubpath()
                p.drawPath(path)
            else:
                p.drawRect(QRectF(-pt.size / 2, -pt.size / 4, pt.size, pt.size / 2 * abs(math.cos(pt.rot * 2)) + 1))
            p.restore()
