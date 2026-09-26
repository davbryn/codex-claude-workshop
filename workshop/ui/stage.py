"""The Workshop Theatre stage: one painted scene with both characters.

Pure presentation. The Director (workshop/theatre/director.py) decides what
happens; the stage only draws avatars, bubbles, cards and effects, and keeps
a frame timer running only while something is actually moving.
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
from .avatar_paint import paint_avatar
from .theme import ACCENTS, BUBBLE_FILL, BUBBLE_EDGE

FRAME_ACTIVE_MS = 50
FRAME_IDLE_MS = 110


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


@dataclass
class Card:
    kind: str  # human | waiting | complete
    title: str
    lines: list[str]
    color: str
    born: float
    duration: float | None = None
    footer: str = ""


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
        self._lit: QPixmap | None = None
        self._lit_key = None
        # camera, shake, ambience
        self.cam_zoom = 1.0
        self.cam_x = 0.0
        self.shake_amp = 0.0
        self.shake_at = -10.0
        self.sweep_until = 0.0
        self.level_source = None  # callable(agent) -> float | None (live voice loudness)
        self.motes = {a: [(self.rng.random(), self.rng.random(), self.rng.uniform(0.6, 1.8), self.rng.random())
                          for _ in range(16)] for a in AGENTS}

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
        want_zoom = 1.045 if (speaker and motion) else 1.0
        want_x = 0.0
        if speaker and motion and speaker in self._geom:
            want_x = (self.width() / 2 - self._geom[speaker].center().x()) * 0.07
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

    def badge(self, text: str, anchor: str = "center", color: str = "#f5c542", duration: float = 2.6) -> None:
        self.badges = [b for b in self.badges if not (b.anchor == anchor and b.text == text)]
        self.badges.append(Badge(text, color, anchor, self.now(), duration))
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
        self.lightning_until = self.now() + seconds
        self.wake()

    def handoff(self, source: str, target: str) -> None:
        if self.animations and not self.reduced_motion:
            self.orbs.append((source, target, self.now()))
        self.wake()

    def burst(self, agent: str, count: int = 18) -> None:
        if not self.animations or self.reduced_motion or agent not in self._geom:
            return
        head = self._geom[agent]
        cx, cy = head.center().x(), head.top() + head.height() * 0.2
        colours = ["#fff1a8", "#7dffc4", "#ffc89e", "#ffffff"]
        for _ in range(count):
            a = self.rng.uniform(-math.pi, 0)
            speed = self.rng.uniform(140, 300)
            self.particles.append(Particle(cx, cy, math.cos(a) * speed, math.sin(a) * speed, 0, self.rng.uniform(-6, 6),
                                           self.rng.choice(colours), self.rng.uniform(3, 6), self.rng.uniform(0.7, 1.2),
                                           shape="star"))
        self.wake()

    def confetti(self, count: int = 170) -> None:
        if not self.animations or self.reduced_motion:
            return
        w = max(1, self.width())
        colours = ["#39d98a", "#7dffc4", "#f39a6b", "#ffd166", "#8fb8ff", "#ff7aa8", "#ffffff"]
        for _ in range(count):
            self.particles.append(Particle(
                self.rng.uniform(0, w), self.rng.uniform(-self.height() * 0.6, -10),
                self.rng.uniform(-60, 60), self.rng.uniform(40, 160), self.rng.uniform(0, 6.28),
                self.rng.uniform(-8, 8), self.rng.choice(colours), self.rng.uniform(5, 10),
                self.rng.uniform(3.5, 5.5), shape=self.rng.choice(["rect", "rect", "circle"])))
        self.wake()

    def show_card(self, kind: str, title: str, lines: list[str], color: str, duration: float | None = None,
                  footer: str = "") -> None:
        self.cards[kind] = Card(kind, title, lines, color, self.now(), duration, footer)
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
        floor_y = h - max(58.0, h * 0.15)
        size = max(96.0, min(h * 0.5, w * 0.22, 340.0))
        centres = {"Codex": w * 0.27, "Claude": w * 0.73}
        rects = {a: QRectF(centres[a] - size / 2, floor_y - size, size, size) for a in AGENTS}
        self._geom = rects
        return {"w": w, "h": h, "floor": floor_y, "size": size, "cx": centres, "rects": rects}

    # -- painting ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        L = self._layout()
        t = self.now()
        p.save()
        self._apply_camera(p, L, t)
        self._paint_backdrop(p, L, t)
        self._paint_motes(p, L, t)
        if t < self.sweep_until:
            self._paint_sweep(p, L, t)
        if t < self.human_light_until:
            self._paint_human_light(p, L, t)
        for agent in AGENTS:
            self._paint_shadow(p, L, agent)
        for agent in AGENTS:
            model = self.models[agent]
            paint_avatar(p, L["rects"][agent], agent, model.pose(), active=agent == self.active_agent)
        if t < self.lightning_until:
            self._paint_lightning(p, L, t)
        for source, target, born in self.orbs:
            self._paint_orb(p, L, source, target, t - born)
        for agent in AGENTS:
            self._paint_nameplate(p, L, agent, t)
        for agent in AGENTS:
            self._paint_bubble(p, L, agent, t)
        p.restore()
        for card in self.cards.values():
            self._paint_card(p, L, card, t)
        self._paint_badges(p, L, t)
        self._paint_particles(p)
        p.end()

    def _apply_camera(self, p: QPainter, L: dict, t: float) -> None:
        """Gentle push-in toward the speaker, plus decaying screen shake."""
        dx = dy = 0.0
        since = t - self.shake_at
        if since < 0.7:
            decay = math.exp(-since * 6) * self.shake_amp
            dx = math.sin(since * 70) * decay
            dy = math.cos(since * 53) * decay * 0.6
        if abs(self.cam_zoom - 1.0) < 0.001 and abs(self.cam_x) < 0.3 and not dx:
            return
        cx, cy = L["w"] / 2, L["floor"] * 0.8
        p.translate(cx + self.cam_x + dx, cy + dy)
        p.scale(self.cam_zoom, self.cam_zoom)
        p.translate(-cx, -cy)

    def _paint_motes(self, p: QPainter, L: dict, t: float) -> None:
        if not self.animations or self.reduced_motion:
            return
        size, floor = L["size"], L["floor"]
        p.setPen(Qt.PenStyle.NoPen)
        for agent in AGENTS:
            k = self.spot[agent]
            if k < 0.3:
                continue
            cx = L["cx"][agent]
            for fx, fy, r, phase in self.motes[agent]:
                y = floor - ((fy + t * 0.02 * r) % 1.0) * floor * 0.95
                spread = size * (0.12 + 0.66 * (y / floor))
                x = cx + (fx - 0.5) * 2 * spread + math.sin(t * 0.6 + phase * 6) * 6
                a = (0.10 + 0.18 * (0.5 + 0.5 * math.sin(t * 1.5 + phase * 9))) * k
                p.setBrush(_c("#fff4dc", a))
                p.drawEllipse(QPointF(x, y), r, r)

    def _paint_sweep(self, p: QPainter, L: dict, t: float) -> None:
        w, floor = L["w"], L["floor"]
        fade = min(1.0, (self.sweep_until - t) / 1.2)
        p.setPen(Qt.PenStyle.NoPen)
        for i, (x0, colour) in enumerate(((w * 0.08, ACCENTS["Codex"]), (w * 0.92, ACCENTS["Claude"]),
                                         (w * 0.5, "#ffe08a"))):
            angle = math.sin(t * (1.1 + i * 0.35) + i * 2) * 0.55
            length = floor * 1.25
            tip = QPointF(x0 + math.sin(angle) * length, math.cos(angle) * length)
            half = 0.16 * length
            nx, ny = math.cos(angle) * half, -math.sin(angle) * half
            beam = QPainterPath(QPointF(x0, 0))
            beam.lineTo(tip.x() + nx, tip.y() + ny)
            beam.lineTo(tip.x() - nx, tip.y() - ny)
            beam.closeSubpath()
            g = QLinearGradient(QPointF(x0, 0), tip)
            g.setColorAt(0, _c(colour, 0.22 * fade))
            g.setColorAt(1, _c(colour, 0.0))
            p.setBrush(g)
            p.drawPath(beam)

    def _paint_backdrop(self, p: QPainter, L: dict, t: float) -> None:
        # The wall/floor never change between frames: render them once per size.
        size = (int(L["w"]), int(L["h"]))
        if self._backdrop is None or self._backdrop_size != size:
            self._backdrop = QPixmap(*size)
            self._backdrop_size = size
            painter = QPainter(self._backdrop)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._paint_static_backdrop(painter, L)
            painter.end()
        # Spotlights only change during handoffs; cache the lit backdrop by intensity.
        key = (size, tuple(round(self.spot[a], 2) for a in AGENTS))
        if self._lit is None or self._lit_key != key:
            self._lit = QPixmap(self._backdrop)
            self._lit_key = key
            painter = QPainter(self._lit)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for agent in AGENTS:
                self._paint_spotlight(painter, L, agent)
            painter.end()
        p.drawPixmap(0, 0, self._lit)
        self._paint_on_air(p, L, t)

    def _paint_static_backdrop(self, p: QPainter, L: dict) -> None:
        w, h, floor = L["w"], L["h"], L["floor"]
        bg = QLinearGradient(0, 0, 0, floor)
        bg.setColorAt(0, QColor("#0f1420"))
        bg.setColorAt(1, QColor("#171e2d"))
        p.fillRect(QRectF(0, 0, w, floor), bg)
        # back wall panels
        p.setPen(QPen(_c("#ffffff", 0.025), 1))
        step = max(60.0, w / 16)
        x = step / 2
        while x < w:
            p.drawLine(QPointF(x, 0), QPointF(x, floor))
            x += step
        # soft wall glows in each agent's colour
        for agent, cx in L["cx"].items():
            g = QRadialGradient(QPointF(cx, floor * 0.55), w * 0.3)
            g.setColorAt(0, _c(ACCENTS[agent], 0.05))
            g.setColorAt(1, _c(ACCENTS[agent], 0.0))
            p.fillRect(QRectF(0, 0, w, floor), g)
        # floor
        fg = QLinearGradient(0, floor, 0, h)
        fg.setColorAt(0, QColor("#202838"))
        fg.setColorAt(1, QColor("#0c1017"))
        p.fillRect(QRectF(0, floor, w, h - floor), fg)
        p.setPen(QPen(_c("#8fb8ff", 0.16), 1.2))
        p.drawLine(QPointF(0, floor), QPointF(w, floor))
        vp = QPointF(w / 2, floor - h * 0.9)
        p.setPen(QPen(_c("#ffffff", 0.035), 1))
        for i in range(-8, 9):
            x = w / 2 + i * w / 9
            dx = x - vp.x()
            k = (h - vp.y()) / (floor - vp.y())
            p.drawLine(QPointF(x, floor), QPointF(vp.x() + dx * k, h))

    def _paint_on_air(self, p: QPainter, L: dict, t: float) -> None:
        w = L["w"]
        sw, sh = 92.0, 24.0
        rect = QRectF(w / 2 - sw / 2, 12, sw, sh)
        lit = self.on_air and not self.paused
        pulse = 0.75 + 0.25 * math.sin(t * 2.4) if lit else 0.0
        if lit:
            glow = QRadialGradient(rect.center(), 70)
            glow.setColorAt(0, _c("#ff3b3b", 0.22 * pulse))
            glow.setColorAt(1, _c("#ff3b3b", 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(rect.center(), 70, 30)
        p.setPen(QPen(_c("#ff5a5a" if lit else "#4a2a2e", 0.9 if lit else 1), 1.5))
        p.setBrush(_c("#2a0d10" if lit else "#16121a"))
        p.drawRoundedRect(rect, 6, 6)
        p.setFont(_font(12, bold=True))
        p.setPen(_c("#ff7070" if lit else "#5a3a40", 1.0 if lit else 0.9))
        label = "⏸ PAUSED" if self.paused else "● ON AIR"
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

    def _paint_spotlight(self, p: QPainter, L: dict, agent: str) -> None:
        k = self.spot[agent]
        if k < 0.02:
            return
        cx, floor, size = L["cx"][agent], L["floor"], L["size"]
        cone = QPainterPath(QPointF(cx - size * 0.12, 0))
        cone.lineTo(cx + size * 0.12, 0)
        cone.lineTo(cx + size * 0.78, floor)
        cone.lineTo(cx - size * 0.78, floor)
        cone.closeSubpath()
        g = QLinearGradient(0, 0, 0, floor)
        g.setColorAt(0, _c(ACCENTS[agent], 0.0))
        g.setColorAt(0.25, _c("#fff6e8", 0.035 * k))
        g.setColorAt(1, _c(ACCENTS[agent], 0.13 * k))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(cone)
        pool = QRadialGradient(QPointF(cx, floor + 4), size * 0.8)
        pool.setColorAt(0, _c(ACCENTS[agent], 0.30 * k))
        pool.setColorAt(1, _c(ACCENTS[agent], 0.0))
        p.setBrush(pool)
        p.drawEllipse(QPointF(cx, floor + 4), size * 0.85, size * 0.13)

    def _paint_human_light(self, p: QPainter, L: dict, t: float) -> None:
        k = min(1.0, (self.human_light_until - t) / 0.6)
        w, floor = L["w"], L["floor"]
        g = QRadialGradient(QPointF(w / 2, floor * 0.45), w * 0.28)
        g.setColorAt(0, _c("#8fb8ff", 0.16 * k))
        g.setColorAt(1, _c("#8fb8ff", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(w / 2, floor * 0.45), w * 0.28, floor * 0.5)

    def _paint_shadow(self, p: QPainter, L: dict, agent: str) -> None:
        pose_bob = self.models[agent].pose().bob if self.animations else 0
        rect = L["rects"][agent]
        lift = max(0.0, -pose_bob) / 12
        width = rect.width() * (0.46 - lift * 0.1)
        g = QRadialGradient(QPointF(rect.center().x(), L["floor"] + 2), width)
        g.setColorAt(0, _c("#000000", 0.55 - lift * 0.2))
        g.setColorAt(1, _c("#000000", 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(rect.center().x(), L["floor"] + 2), width, rect.width() * 0.07)

    def _head_anchor(self, L: dict, agent: str) -> QPointF:
        r = L["rects"][agent]
        return QPointF(r.center().x(), r.top() + r.height() * 0.3)

    def _paint_lightning(self, p: QPainter, L: dict, t: float) -> None:
        a = self._head_anchor(L, "Codex")
        b = self._head_anchor(L, "Claude")
        size = L["size"]
        start = QPointF(a.x() + size * 0.42, a.y())
        end = QPointF(b.x() - size * 0.42, b.y())
        seed = int(t * 18)
        rng = random.Random(seed)
        pts = [start]
        n = 9
        for i in range(1, n):
            f = i / n
            x = start.x() + (end.x() - start.x()) * f
            y = start.y() + (end.y() - start.y()) * f + rng.uniform(-1, 1) * size * 0.14
            pts.append(QPointF(x, y))
        pts.append(end)
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        remaining = self.lightning_until - t
        k = min(1.0, remaining / 0.3) * (0.6 + 0.4 * rng.random())
        p.setBrush(Qt.BrushStyle.NoBrush)
        for width, colour, alpha in ((14, "#ffd54a", 0.12), (7, "#ffd54a", 0.35), (2.6, "#fffbe6", 1.0)):
            pen = QPen(_c(colour, alpha * k), width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawPath(path)
        mid = QPointF((start.x() + end.x()) / 2, min(start.y(), end.y()) - size * 0.28)
        p.setFont(_font(max(16, size * 0.15), bold=True))
        p.setPen(_c("#ffd54a", k))
        p.drawText(QRectF(mid.x() - 40, mid.y() - 20, 80, 40), Qt.AlignmentFlag.AlignCenter, "⚔")

    def _paint_orb(self, p: QPainter, L: dict, source: str, target: str, age: float) -> None:
        f = _ease_out(age / 0.9)
        a, b = self._head_anchor(L, source), self._head_anchor(L, target)
        ctrl = QPointF((a.x() + b.x()) / 2, min(a.y(), b.y()) - L["size"] * 0.6)

        def at(u: float) -> QPointF:
            return QPointF((1 - u) ** 2 * a.x() + 2 * (1 - u) * u * ctrl.x() + u * u * b.x(),
                           (1 - u) ** 2 * a.y() + 2 * (1 - u) * u * ctrl.y() + u * u * b.y())

        colour = ACCENTS[target]
        fade = 1.0 if age < 0.9 else max(0.0, 1 - (age - 0.9) / 0.2)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(10, 0, -1):
            u = max(0.0, f - i * 0.025)
            pt = at(u)
            p.setBrush(_c(colour, 0.05 * (10 - i) / 10 * fade + 0.02))
            p.drawEllipse(pt, 5 + (10 - i) * 0.6, 5 + (10 - i) * 0.6)
        pt = at(f)
        glow = QRadialGradient(pt, 22)
        glow.setColorAt(0, _c("#ffffff", 0.9 * fade))
        glow.setColorAt(0.3, _c(colour, 0.7 * fade))
        glow.setColorAt(1, _c(colour, 0))
        p.setBrush(glow)
        p.drawEllipse(pt, 22, 22)

    def _paint_nameplate(self, p: QPainter, L: dict, agent: str, t: float) -> None:
        view = self.views[agent]
        cx, floor = L["cx"][agent], L["floor"]
        accent = ACCENTS[agent]
        active = agent == self.active_agent or self.models[agent].talking
        name_font = _font(13, bold=True)
        label_font = _font(11.5, bold=True)
        fm_n, fm_l = QFontMetricsF(name_font), QFontMetricsF(label_font)
        name = agent.upper()
        label = view.label
        pad = 12
        width = fm_n.horizontalAdvance(name) * 1.25 + fm_l.horizontalAdvance(label) + pad * 3 + 10
        rect = QRectF(cx - width / 2, floor + 10, width, 26)
        p.setPen(QPen(_c(accent, 0.9 if active else 0.35), 1.4))
        p.setBrush(_c("#0e131b", 0.92))
        p.drawRoundedRect(rect, 13, 13)
        dot = QPointF(rect.left() + pad, rect.center().y())
        if active:
            pulse = 0.5 + 0.5 * math.sin(t * 5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_c(accent, 0.25 + 0.35 * pulse))
            p.drawEllipse(dot, 6, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_c(accent, 1.0 if active else 0.45))
        p.drawEllipse(dot, 3.4, 3.4)
        p.setFont(name_font)
        p.setPen(_c(accent))
        name_rect = QRectF(dot.x() + 9, rect.top(), fm_n.horizontalAdvance(name) * 1.25, rect.height())
        # letter-spaced name
        name_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 125)
        p.setFont(name_font)
        p.drawText(name_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, name)
        p.setFont(label_font)
        colour = {"⚠": "#ff6b6b", "✓": "#8fd9ff", "⏸": "#f5c542", "👀": "#f5c542"}.get(label[:1], "#c9d1d9")
        p.setPen(_c(colour))
        label_rect = QRectF(name_rect.right() + pad * 0.6, rect.top(), rect.right() - name_rect.right() - pad, rect.height())
        p.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
        # activity line (public, observable status only)
        if view.activity:
            p.setFont(_font(11, family="Consolas"))
            p.setPen(_c("#8b93a1"))
            fm = QFontMetricsF(p.font())
            text = fm.elidedText(view.activity, Qt.TextElideMode.ElideRight, L["w"] * 0.42)
            p.drawText(QRectF(cx - L["w"] * 0.22, rect.bottom() + 3, L["w"] * 0.44, 16),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)
        # turn count pip
        p.setFont(_font(10.5, bold=True))
        p.setPen(_c("#6f7887"))
        p.drawText(QRectF(rect.right() + 8, rect.top(), 90, rect.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   f"{view.turns} turn{'s' if view.turns != 1 else ''}")

    def _paint_bubble(self, p: QPainter, L: dict, agent: str, t: float) -> None:
        b = self.bubbles[agent]
        if b.kind == "none" or not b.text:
            return
        head = L["rects"][agent]
        cx = head.center().x()
        top_limit = 44.0
        bottom = head.top() + head.height() * 0.06 - 14
        available = bottom - top_limit
        if available < 30:
            return
        appear = _ease_back((t - b.born) / 0.28) if self.animations and not self.reduced_motion else 1.0
        speech = b.kind == "speech"
        max_w = min(L["w"] * 0.44, 540.0) if speech else min(L["w"] * 0.34, 320.0)
        pad_x, pad_y = (16.0, 12.0) if speech else (12.0, 7.0)
        text = b.text
        font = _font(14.5 if speech else 12.5, italic=not speech)
        for px in ((14.5, 13.5, 12.5, 11.5) if speech else (12.5,)):
            font = _font(px, italic=not speech)
            fm = QFontMetricsF(font)
            rect_text = fm.boundingRect(QRectF(0, 0, max_w - pad_x * 2, 4000),
                                        int(Qt.TextFlag.TextWordWrap), text)
            if rect_text.height() + pad_y * 2 <= available:
                break
        fm = QFontMetricsF(font)
        text_w = min(max_w - pad_x * 2, max(rect_text.width(), 40))
        text_h = min(rect_text.height(), available - pad_y * 2)
        bw, bh = text_w + pad_x * 2, text_h + pad_y * 2
        x = max(10.0, min(L["w"] - bw - 10, cx - bw / 2 + (L["w"] / 2 - cx) * 0.12))
        rect = QRectF(x, bottom - bh, bw, bh)

        p.save()
        if any(c.kind in ("waiting", "complete") for c in self.cards.values()):
            p.restore()
            return  # the centre card has the floor
        other = "Claude" if agent == "Codex" else "Codex"
        dim = 0.85 if (self.models[other].talking and not self.models[agent].talking) else 1.0
        origin = QPointF(cx, bottom + 8)
        p.translate(origin)
        p.scale(0.85 + 0.15 * appear, 0.85 + 0.15 * appear)
        p.translate(-origin)
        p.setOpacity(max(0.0, min(1.0, appear)) * dim)
        tail_x = max(rect.left() + 22, min(rect.right() - 22, cx))
        path = QPainterPath()
        path.addRoundedRect(rect, 16 if speech else 13, 16 if speech else 13)
        tail = QPainterPath(QPointF(tail_x - 11, rect.bottom() - 1))
        tail.quadTo(tail_x - 2, rect.bottom() + 8, tail_x - 4 + (cx - tail_x) * 0.3, rect.bottom() + 17)
        tail.quadTo(tail_x + 6, rect.bottom() + 6, tail_x + 11, rect.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)
        if speech:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_c("#000000", 0.35))
            p.drawPath(path.translated(0, 4))
            fill = QLinearGradient(0, rect.top(), 0, rect.bottom())
            fill.setColorAt(0, _c(BUBBLE_FILL[agent]).lighter(104))
            fill.setColorAt(1, _c(BUBBLE_FILL[agent]))
            p.setBrush(fill)
            p.setPen(QPen(_c(BUBBLE_EDGE[agent]), 1.6))
            p.drawPath(path)
            p.setPen(_c("#1a1d23"))
        else:
            p.setPen(QPen(_c(ACCENTS[agent], 0.45), 1.2))
            p.setBrush(_c("#1b212c", 0.92))
            p.drawPath(path)
            p.setPen(_c("#aab3c0"))
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
            p.setPen(_c(ACCENTS[agent], 0.8))
            p.drawText(QRectF(rect.right() - pad_x - 4, rect.top() + pad_y - 1, 30, text_h + 2),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, "" if text.endswith("…") else dots)
        p.restore()

    def _paint_card(self, p: QPainter, L: dict, card: Card, t: float) -> None:
        w, floor = L["w"], L["floor"]
        size = L["size"]
        gap = (L["cx"]["Claude"] - L["cx"]["Codex"]) - size * 0.95
        cw = max(240.0, min(gap, 470.0))
        age = t - card.born
        fade_in = _ease_back(age / 0.35) if self.animations else 1.0
        fade_out = 1.0
        if card.duration is not None:
            fade_out = max(0.0, min(1.0, (card.duration + 0.5 - age) / 0.5))
        title_font = _font(15, bold=True)
        body_font = _font(12.5)
        fm_t, fm_b = QFontMetricsF(title_font), QFontMetricsF(body_font)
        body = "\n".join(card.lines)
        body_rect = fm_b.boundingRect(QRectF(0, 0, cw - 36, 2000), int(Qt.TextFlag.TextWordWrap), body)
        footer_h = 22 if card.footer else 0
        ch = 20 + fm_t.height() + 8 + body_rect.height() + footer_h + 18
        ch = min(ch, floor - 60)
        rect = QRectF(w / 2 - cw / 2, max(50.0, floor - size * 0.62 - ch / 2), cw, ch)
        p.save()
        p.setOpacity(max(0.0, min(1.0, fade_in)) * fade_out)
        c = rect.center()
        p.translate(c)
        k = 0.9 + 0.1 * min(1.0, fade_in)
        p.scale(k, k)
        p.translate(-c)
        pulse = 0.6 + 0.4 * math.sin(t * 3) if card.kind == "waiting" else 1.0
        glow = QRadialGradient(c, cw * 0.75)
        glow.setColorAt(0, _c(card.color, 0.16 * pulse))
        glow.setColorAt(1, _c(card.color, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, cw * 0.75, ch * 0.9)
        p.setBrush(_c("#000000", 0.4))
        p.drawRoundedRect(rect.translated(0, 5), 16, 16)
        bg = QLinearGradient(0, rect.top(), 0, rect.bottom())
        bg.setColorAt(0, _c("#1f2636", 0.97))
        bg.setColorAt(1, _c("#141a26", 0.97))
        p.setBrush(bg)
        p.setPen(QPen(_c(card.color, 0.55 + 0.45 * pulse), 1.8))
        p.drawRoundedRect(rect, 16, 16)
        p.setFont(title_font)
        p.setPen(_c(card.color))
        p.drawText(QRectF(rect.left() + 18, rect.top() + 14, cw - 36, fm_t.height() + 4),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, card.title)
        p.setFont(body_font)
        p.setPen(_c("#dfe5ee"))
        option = QTextOption(Qt.AlignmentFlag.AlignHCenter)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        body_top = rect.top() + 14 + fm_t.height() + 10
        p.drawText(QRectF(rect.left() + 18, body_top, cw - 36, rect.bottom() - body_top - footer_h - 10), body, option)
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
            font = _font(13, bold=True)
            font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
            fm = QFontMetricsF(font)
            bw = fm.horizontalAdvance(badge.text) + 26
            if badge.anchor in L["rects"]:
                # beside the head, on the outer side (away from the other agent)
                r = L["rects"][badge.anchor]
                outward = -1 if badge.anchor == "Codex" else 1
                x = r.center().x() + outward * (r.width() * 0.52 + bw / 2)
                x = max(bw / 2 + 8, min(L["w"] - bw / 2 - 8, x))
                y = r.top() + r.height() * 0.32 + idx * 34
                travel = 18
            else:
                x, y = L["w"] / 2, 70 + idx * 34
                travel = 8
            rise = _ease_out(age / badge.duration) * travel if self.animations else 0
            pop = _ease_back(age / 0.3) if self.animations else 1
            alpha = min(1.0, (badge.duration - age) / 0.5)
            rect = QRectF(x - bw / 2, y - 14 - rise, bw, 28)
            p.save()
            p.setOpacity(max(0.0, alpha))
            c = rect.center()
            p.translate(c)
            p.scale(pop, pop)
            p.translate(-c)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(_c("#000000", 0.35))
            p.drawRoundedRect(rect.translated(0, 3), 14, 14)
            p.setBrush(_c(badge.color))
            p.drawRoundedRect(rect, 14, 14)
            p.setPen(QPen(_c("#ffffff", 0.35), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 13, 13)
            p.setFont(font)
            p.setPen(_c("#15181e"))
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

