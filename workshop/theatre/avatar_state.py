"""Avatar animation: theatrical states → a smoothly animated, renderable Pose.

States are UI reactions to public events (process status, public text, test
output). They are not claims about what a model "feels".

Layers, highest priority first:
  talking   – mouth/gesture animation while an entry is performed
  reaction  – a transient expression (pleased, disagreeing, …) that expires
  base      – from process status (waiting, reading, coding, …)

Every face/arm value eases toward its target, and the body runs on small
springs (jumps with anticipation, squash-and-stretch, overshooting tilts, a
wobbling sprout/antenna), so expressions morph instead of snapping.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

STATES = (
    "idle", "waiting", "reading", "thinking", "coding", "reviewing", "talking", "pleased",
    "celebrating", "confused", "annoyed", "disagreeing", "embarrassed", "error", "sleeping",
    "complete", "smug", "surprised",
)

REACTION_SECONDS = {
    "pleased": 3.0, "celebrating": 3.6, "confused": 3.0, "annoyed": 3.2, "disagreeing": 4.0,
    "embarrassed": 3.6, "error": 2.6, "smug": 2.8, "surprised": 1.6, "talking": 0.0,
}


@dataclass
class Persona:
    animation_style: str = "neutral"  # confident | dramatic | calm | neutral
    idle_energy: float = 0.5  # 0..1: breathing, glance and fidget frequency
    reaction_strength: float = 0.6  # 0..1: how big reactions look

    @classmethod
    def from_dict(cls, data: dict | None, default: "Persona") -> "Persona":
        if not data:
            return default
        return cls(
            animation_style=str(data.get("animation_style", default.animation_style)),
            idle_energy=_clamp(float(data.get("idle_energy", default.idle_energy))),
            reaction_strength=_clamp(float(data.get("reaction_strength", default.reaction_strength))),
        )


DEFAULT_PERSONAS = {
    "Codex": Persona("confident", idle_energy=0.3, reaction_strength=0.5),
    "Claude": Persona("dramatic", idle_energy=0.7, reaction_strength=0.9),
}

# --- expression targets ---------------------------------------------------------

FACE_DEFAULTS = dict(
    eye_open=1.0, eye_scale=1.0, lid_top=0.0, lid_bottom=0.0, lid_slant=0.0, happy=0.0, pupil=1.0,
    brow_raise=0.0, brow_angle=0.0, brow_asym=0.0,
    mouth_curve=0.15, mouth_width=1.0, mouth_open=0.0, mouth_asym=0.0, mouth_wave=0.0, teeth=0.0,
    blush=0.0, code_rain=0.0, glitch=0.0, steam=0.0, glow=0.3,
)

EXPRESSIONS: dict[str, dict] = {
    "idle": {},
    "waiting": {"mouth_curve": 0.1},
    "reading": {"lid_top": 0.18, "brow_raise": 0.15, "mouth_curve": 0.0, "mouth_width": 0.8, "glow": 0.6},
    "thinking": {"brow_raise": 0.35, "brow_angle": -0.15, "mouth_curve": -0.05, "mouth_width": 0.7,
                 "mouth_asym": 0.45, "glow": 0.6},
    "coding": {"lid_top": 0.35, "brow_angle": 0.22, "brow_raise": -0.1, "mouth_curve": 0.0, "mouth_width": 0.75,
               "code_rain": 1.0, "glow": 0.9},
    "reviewing": {"lid_top": 0.45, "lid_bottom": 0.15, "brow_angle": 0.3, "brow_raise": 0.25, "mouth_curve": -0.1,
                  "mouth_asym": 0.35, "glow": 0.7},
    "talking": {"brow_raise": 0.2, "mouth_curve": 0.25, "glow": 0.8},
    "pleased": {"happy": 1.0, "brow_raise": 0.35, "mouth_curve": 0.85, "mouth_width": 1.1, "blush": 0.35},
    "celebrating": {"happy": 1.0, "brow_raise": 0.7, "mouth_curve": 1.0, "mouth_open": 0.8, "mouth_width": 1.35,
                    "teeth": 1.0, "blush": 0.45},
    "complete": {"happy": 1.0, "brow_raise": 0.6, "mouth_curve": 1.0, "mouth_open": 0.7, "mouth_width": 1.3,
                 "teeth": 1.0, "blush": 0.4},
    "confused": {"eye_scale": 1.15, "pupil": 0.75, "brow_raise": 0.5, "brow_angle": -0.45, "brow_asym": 0.6,
                 "mouth_curve": -0.15, "mouth_wave": 1.0, "mouth_width": 0.9},
    "annoyed": {"lid_top": 0.35, "lid_slant": 0.7, "brow_angle": 0.7, "brow_raise": -0.3, "mouth_curve": -0.35,
                "mouth_width": 0.8, "steam": 0.55},
    "disagreeing": {"lid_top": 0.25, "lid_slant": 1.0, "brow_angle": 1.0, "brow_raise": -0.4, "mouth_curve": -0.75,
                    "mouth_open": 0.25, "mouth_width": 1.1, "steam": 1.0},
    "embarrassed": {"lid_top": 0.45, "brow_angle": -0.7, "brow_raise": 0.35, "mouth_curve": -0.1,
                    "mouth_wave": 1.0, "mouth_width": 0.8, "blush": 1.0},
    "error": {"eye_scale": 1.2, "pupil": 0.6, "brow_raise": 0.8, "brow_angle": -0.6, "mouth_curve": -0.45,
              "mouth_open": 0.6, "mouth_width": 0.6, "glitch": 1.0, "glow": 1.0},
    "sleeping": {"eye_open": 0.0, "brow_raise": -0.2, "mouth_curve": 0.05, "mouth_open": 0.18, "mouth_width": 0.55,
                 "glow": 0.1},
    "smug": {"lid_top": 0.42, "brow_asym": 1.0, "mouth_curve": 0.5, "mouth_asym": 0.9, "mouth_width": 0.9},
    "surprised": {"eye_scale": 1.25, "pupil": 0.65, "brow_raise": 1.0, "mouth_open": 0.7, "mouth_width": 0.55,
                  "mouth_curve": 0.0},
}

ARMS = {
    "idle": "down", "waiting": "down", "reading": "chin", "thinking": "chin", "coding": "typing",
    "reviewing": "chin", "talking": "gesture", "pleased": "hips", "celebrating": "up", "complete": "wave",
    "confused": "shrug", "annoyed": "hips", "disagreeing": "point", "embarrassed": "cover", "error": "up",
    "sleeping": "down", "smug": "hips", "surprised": "up",
}

PROPS = {
    "reading": ("sparks",), "thinking": ("sparks",), "coding": ("keyboard", "sparks"), "reviewing": ("magnifier",),
    "celebrating": ("sparkles",), "complete": ("sparkles",), "confused": ("question",), "disagreeing": ("bolt",),
    "embarrassed": ("sweat",), "error": ("error",), "sleeping": ("zzz",), "surprised": ("exclaim",),
}
ALL_PROPS = ("sparks", "keyboard", "magnifier", "sparkles", "question", "bolt", "sweat", "error", "zzz", "exclaim")

TILT = {"confused": 9.0, "embarrassed": -5.0, "sleeping": -7.0, "thinking": 4.0}


@dataclass
class Pose:
    state: str = "idle"
    # body
    bob: float = 0.0
    squash: float = 1.0
    tilt: float = 0.0
    shake: float = 0.0
    lean: float = 0.0
    wobble: float = 0.0  # sprout / antenna angle (degrees)
    # eyes
    eye_open: float = 1.0
    eye_scale: float = 1.0
    lid_top: float = 0.0
    lid_bottom: float = 0.0
    lid_slant: float = 0.0
    happy: float = 0.0
    pupil: float = 1.0
    look_x: float = 0.0
    look_y: float = 0.0
    # brows
    brow_raise: float = 0.0
    brow_angle: float = 0.0
    brow_asym: float = 0.0
    # mouth
    mouth_curve: float = 0.15
    mouth_width: float = 1.0
    mouth_open: float = 0.0
    mouth_asym: float = 0.0
    mouth_wave: float = 0.0
    teeth: float = 0.0
    # extras
    blush: float = 0.0
    code_rain: float = 0.0
    glitch: float = 0.0
    steam: float = 0.0
    glow: float = 0.3
    # arms: ((elbow_x, elbow_y), (hand_x, hand_y), in_front) for left, right
    arm_left: tuple = ((23.0, 84.0), (23.0, 90.0), False)
    arm_right: tuple = ((77.0, 84.0), (77.0, 90.0), False)
    props: dict = field(default_factory=dict)  # prop -> alpha
    time: float = 0.0

    @property
    def mouth(self) -> str:
        """A coarse label for the current mouth shape (handy for tests/debugging)."""
        if self.mouth_asym > 0.5 and self.mouth_open < 0.3:
            return "smug"
        if self.mouth_open > 0.3:
            return "grin" if self.teeth > 0.5 else "open"
        if self.mouth_wave > 0.5:
            return "wavy"
        if self.mouth_curve > 0.4:
            return "smile"
        if self.mouth_curve < -0.4:
            return "frown"
        return "flat"

    @property
    def eyes(self) -> str:
        if self.eye_open < 0.2:
            return "closed"
        if self.happy > 0.5:
            return "happy"
        if self.lid_slant > 0.4:
            return "angry"
        return "squint" if self.lid_top > 0.3 else "normal"


def arm_target(agent: str, arms: str, left: bool, t: float, other_side: int, beat: float = 0.0,
               beat_left: bool = True) -> tuple[tuple[float, float], tuple[float, float], bool]:
    """Elbow, hand and front/back for one arm of ``agent`` in a named arm pose."""
    sign = -1 if left else 1
    codex = agent == "Codex"
    down_y = 90 if codex else 88
    if arms == "typing":
        k = math.sin(t * 15 + (0 if left else math.pi)) * 1.4
        return (50 + sign * 21, 86), (50 + sign * 9, 91 + k), True
    if arms == "up":
        wave = math.sin(t * 9 + (0 if left else 1.3)) * 2.5
        return (50 + sign * 34, 60), (50 + sign * 37 + wave, 44), False
    if arms == "wave":
        if left:
            return (50 + sign * 30, 80), (50 + sign * 27, 88), False
        wave = math.sin(t * 8) * 4
        return (50 + sign * 34, 60), (50 + sign * 35 + wave, 43), False
    if arms == "hips":
        return (50 + sign * 33, 81), (50 + sign * 20, 87), False
    if arms == "chin":
        if left:
            return (50 + sign * 29, 83), (50 + sign * 24, 91), False
        return (50 + sign * 31, 84), (50 + sign * 11, 70 if codex else 76), True
    if arms == "cover":
        return (50 + sign * 30, 70), (50 + sign * 14, 47 if codex else 51), True
    if arms == "shrug":
        return (50 + sign * 33, 83), (50 + sign * 41, 71), False
    if arms == "point":
        if (sign > 0) == (other_side > 0):
            return (50 + sign * 36, 69), (50 + sign * 47, 60), False
        return (50 + sign * 33, 81), (50 + sign * 20, 87), False
    if arms == "catch":
        return (50 + sign * 30, 66), (50 + sign * 17, 46), True
    if arms == "stretch":
        return (50 + sign * 25, 50), (50 + sign * 14, 30), False
    if arms == "gesture":
        lift = beat if (left == beat_left) else beat * 0.25
        return (50 + sign * (29 + 4 * lift), 82 - 10 * lift), (50 + sign * (30 + 10 * lift), 88 - 26 * lift), False
    sway = math.sin(t * 1.3 + (0 if left else 1)) * 0.8
    return (50 + sign * 29, 84), (50 + sign * 27 + sway, down_y), False


class AvatarModel:
    """Time-based animation for one agent. ``other_side`` is -1 if the other
    agent stands to the left, +1 if to the right."""

    def __init__(self, agent: str, persona: Persona | None = None, other_side: int = 1, seed: int | None = None):
        self.agent = agent
        self.persona = persona or DEFAULT_PERSONAS.get(agent, Persona())
        self.other_side = other_side
        self.rng = random.Random(seed if seed is not None else hash(agent))
        self.t = 0.0
        self.base = "idle"
        self.base_since = 0.0
        self.reaction: str | None = None
        self.reaction_until: float | None = None
        self.reaction_started = 0.0
        self.talking = False
        self.talk_level = 0.0
        self.voice_level: float | None = None  # live loudness from the speech engine
        self.motion = 1.0  # 0 = reduced motion
        self.enabled = True
        self.face = dict(FACE_DEFAULTS)
        self.props = {name: 0.0 for name in ALL_PROPS}
        self.arms = {True: arm_target(agent, "down", True, 0, other_side),
                     False: arm_target(agent, "down", False, 0, other_side)}
        # springs
        self.y = 0.0
        self.vy = 0.0
        self.squash = 0.0
        self.vsquash = 0.0
        self.tilt = 0.0
        self.vtilt = 0.0
        self.wobble = 0.0
        self.vwobble = 0.0
        self.look_x = 0.0
        self.look_y = 0.0
        self._hops: list[tuple[float, float]] = []  # (time, strength)
        self._shake_at = -10.0
        self._shake_amp = 0.0
        self._blink_at = 1.5 + self.rng.random() * 3
        self._blink_until = 0.0
        self._glance_until = 0.0
        self._next_glance = 3 + self.rng.random() * 6
        self._glance: tuple[float, float] = (0.0, 0.0)
        self._look_override: tuple[float, float] | None = None
        self._look_until = 0.0
        self._gesture: tuple[str, float] | None = None  # (arms, until)
        self._next_fidget = 14 + self.rng.random() * 10
        self._beat = 0.0
        self._beat_left = True
        self._last_level = 0.0
        self._last_beat = 0.0

    # -- control ------------------------------------------------------------------

    def set_base(self, state: str) -> None:
        if state != self.base:
            self.base = state
            self.base_since = self.t

    def react(self, state: str, seconds: float | None = -1.0) -> None:
        """Show a transient reaction. seconds=None holds it until release()."""
        if state in ("idle", None):
            return
        self.reaction = state
        self.reaction_started = self.t
        if seconds == -1.0:
            seconds = REACTION_SECONDS.get(state, 3.0) * (0.8 + 0.4 * self.persona.reaction_strength)
        self.reaction_until = None if seconds is None else self.t + seconds
        strength = 0.55 + 0.6 * self.persona.reaction_strength
        if state in ("error", "disagreeing", "annoyed"):
            self._shake_at, self._shake_amp = self.t, 2.4 * strength
        if state in ("celebrating", "complete"):
            hops = 3 if self.persona.animation_style != "calm" else 1
            for i in range(hops):
                self.hop(0.9 * strength, delay=i * 0.42)
        elif state in ("pleased", "smug"):
            self.hop(0.35 * strength)
        elif state == "surprised":
            self.hop(0.55 * strength, anticipation=False)
        elif state == "disagreeing":
            self.hop(0.3 * strength, anticipation=False)

    def hop(self, strength: float = 0.5, delay: float = 0.0, anticipation: bool = True) -> None:
        """Queue a jump; with anticipation the body crouches first."""
        start = self.t + delay
        if anticipation:
            self._hops.append((start, -strength))  # crouch marker
            start += 0.11
        self._hops.append((start, strength))

    def gesture(self, arms: str, seconds: float = 0.8) -> None:
        self._gesture = (arms, self.t + seconds)

    def nudge_wobble(self, amount: float) -> None:
        self.vwobble += amount

    def release(self, after: float | None = None) -> None:
        if self.reaction is None:
            return
        duration = after if after is not None else REACTION_SECONDS.get(self.reaction, 3.0)
        self.reaction_until = self.t + duration

    def clear_reaction(self) -> None:
        self.reaction = None
        self.reaction_until = None

    def set_talking(self, talking: bool) -> None:
        self.talking = talking
        if not talking:
            self.voice_level = None

    def look(self, x: float, y: float = 0.0, seconds: float = 2.5) -> None:
        self._look_override = (max(-1, min(1, x)), max(-1, min(1, y)))
        self._look_until = self.t + seconds

    def look_at_other(self, seconds: float = 2.5) -> None:
        self.look(self.other_side * 1.0, 0.0, seconds)

    def look_at_human(self, seconds: float = 4.0) -> None:
        self.look(self.other_side * 0.35, 0.45, seconds)

    def effective_state(self) -> str:
        if self.talking:
            return "talking"
        if self.reaction:
            return self.reaction
        return self.base

    def expression_state(self) -> str:
        if self.reaction:
            return self.reaction
        return "talking" if self.talking else self.base

    def is_animating(self) -> bool:
        return bool(
            self.talking or self.reaction or self._hops or abs(self.vy) > 0.5 or abs(self.y) > 0.2
            or abs(self.vsquash) > 0.02 or abs(self.vwobble) > 0.5 or self.t - self._shake_at < 0.8
            or self._gesture or self.base in ("coding", "reading", "reviewing", "thinking", "complete")
        )

    # -- simulation ----------------------------------------------------------------------

    def _targets(self) -> tuple[dict, str, tuple[str, ...], float]:
        state = self.expression_state()
        target = dict(FACE_DEFAULTS)
        target.update(EXPRESSIONS.get(state, {}))
        style = self.persona.animation_style
        if style == "confident":
            if state == "pleased":
                target.update(happy=0.25, mouth_asym=0.8, brow_asym=0.8, lid_top=0.3)
            if state in ("idle", "waiting"):
                target.update(brow_asym=0.25, mouth_asym=0.2)
            if state in ("celebrating", "complete"):
                target["brow_asym"] = 0.5
        strength = 0.55 + 0.6 * self.persona.reaction_strength
        if style == "dramatic":
            strength *= 1.15
        for key in ("brow_raise", "brow_angle", "brow_asym", "mouth_curve", "lid_slant", "blush"):
            target[key] = target[key] * strength if key != "mouth_curve" else target[key] * min(1.2, strength)
        arms = ARMS.get(state, "down")
        if self._gesture and self.t < self._gesture[1]:
            arms = self._gesture[0]
        elif self._gesture:
            self._gesture = None
        props = PROPS.get(state, ())
        return target, arms, props, strength

    def update(self, dt: float) -> None:
        dt = max(0.0, dt)
        # integrate in small steps so the springs stay stable for any frame time
        while dt > 0.05:
            self._step(0.05)
            dt -= 0.05
        if dt > 0:
            self._step(dt)

    def _step(self, dt: float) -> None:
        self.t += dt
        t = self.t
        if self.reaction and self.reaction_until is not None and t >= self.reaction_until:
            self.reaction = None
            self.reaction_until = None
        motion = self.motion if self.enabled else 0.0

        # talking: follow the real voice loudness when we have it
        if self.talking:
            if self.voice_level is not None:
                level = self.voice_level
            else:
                level = max(0.0, 0.55 + 0.45 * math.sin(t * 17) * math.sin(t * 5.3 + 1.1))
            attack = 30 if level > self.talk_level else 12
            self.talk_level += (level - self.talk_level) * min(1.0, dt * attack)
            if level > 0.72 and self._last_level <= 0.72 and t - self._last_beat > 0.45:
                self._beat_left = not self._beat_left
                self._last_beat = t
            self._last_level = level
        else:
            self.talk_level += (0 - self.talk_level) * min(1.0, dt * 12)
        self._beat = max(0.0, 1 - (t - self._last_beat) / 0.55) if self.talking else 0.0

        target, arms, props, strength = self._targets()
        rate = min(1.0, dt * 9)
        for key, value in target.items():
            self.face[key] += (value - self.face[key]) * rate
        for name in ALL_PROPS:
            want = 1.0 if name in props else 0.0
            self.props[name] += (want - self.props[name]) * min(1.0, dt * 6)
        for left in (True, False):
            elbow, hand, front = arm_target(self.agent, arms, left, t, self.other_side, self._beat, self._beat_left)
            (ex, ey), (hx, hy), _ = self.arms[left]
            k = min(1.0, dt * (14 if arms in ("typing", "gesture") else 8))
            self.arms[left] = ((ex + (elbow[0] - ex) * k, ey + (elbow[1] - ey) * k),
                               (hx + (hand[0] - hx) * k, hy + (hand[1] - hy) * k), front)

        # blinks and glances
        if t >= self._blink_at:
            self._blink_until = t + 0.14
            self._blink_at = t + (0.25 if self.rng.random() < 0.18 else 2.2 + self.rng.random() * 4.0)
        state = self.expression_state()
        if t >= self._next_glance:
            choices = [(self.other_side, 0.0), (-self.other_side * 0.7, 0.1), (0.0, 0.5), (self.other_side * 0.5, -0.4)]
            self._glance = self.rng.choice(choices)
            self._glance_until = t + 0.8 + self.rng.random() * 1.2
            self._next_glance = t + (9 - 6 * self.persona.idle_energy) + self.rng.random() * 5
        look = self._look_target(state, motion)
        k = min(1.0, dt * 10)
        self.look_x += (look[0] - self.look_x) * k
        self.look_y += (look[1] - self.look_y) * k

        # idle fidgets
        if motion and state in ("idle", "waiting") and not self.talking and t >= self._next_fidget:
            self._fidget()
            self._next_fidget = t + (22 - 12 * self.persona.idle_energy) + self.rng.random() * 12

        # body springs
        if motion:
            self._simulate_body(dt, state, strength)
        else:
            self.y = self.vy = self.squash = self.vsquash = self.tilt = self.vtilt = 0.0
            self.wobble = self.vwobble = 0.0
            self._hops.clear()

    def _look_target(self, state: str, motion: float) -> tuple[float, float]:
        t = self.t
        if self._look_override and t < self._look_until:
            return self._look_override
        if t < self._glance_until and state in ("idle", "waiting", "pleased", "smug"):
            return self._glance
        wander = motion or 0.4
        return {
            "reading": (math.sin(t * 1.7) * 0.5 * wander, 0.35),
            "reviewing": (math.sin(t * 1.1) * 0.8 * wander, 0.25),
            "coding": (math.sin(t * 0.7) * 0.15, 0.6),
            "thinking": (0.3 * self.other_side * -1, -0.55),
            "annoyed": (self.other_side * 0.9, 0.0),
            "disagreeing": (self.other_side * 1.0, 0.0),
            "smug": (self.other_side * 0.9, 0.0),
            "embarrassed": (-self.other_side * 0.9, 0.45),
            "sleeping": (0.0, 0.3),
            "confused": (math.sin(t * 2.3) * 0.6 * wander, -0.2),
        }.get(state, (0.0, 0.0))

    def _fidget(self) -> None:
        choice = self.rng.choice(["stretch", "look", "hop", "wobble"])
        if choice == "stretch":
            self.gesture("stretch", 1.3)
            self.vsquash += 0.9
        elif choice == "look":
            self.look(-self.other_side * 0.9, -0.1, 0.9)
            self._glance = (self.other_side, 0.0)
            self._glance_until = self.t + 1.8
        elif choice == "hop":
            self.hop(0.25)
        self.vwobble += self.rng.choice((-1, 1)) * 60

    def _simulate_body(self, dt: float, state: str, strength: float) -> None:
        t = self.t
        # jumps (with a crouch first)
        remaining = []
        for when, power in self._hops:
            if t >= when:
                if power < 0:
                    self.vsquash -= 1.6 * -power  # crouch
                elif self.y > -0.5:
                    self.vy = -95 * power
                    self.vsquash += 1.2 * power  # stretch on take-off
            else:
                remaining.append((when, power))
        self._hops = remaining
        gravity = 520.0
        if self.y < 0 or self.vy < 0:
            self.vy += gravity * dt
            self.y += self.vy * dt
            if self.y >= 0:
                impact = self.vy
                self.y, self.vy = 0.0, 0.0
                self.vsquash -= min(2.2, impact / 55)  # squash on landing
                self.vwobble += impact * 0.9
        # squash spring
        acc = -320 * self.squash - 14 * self.vsquash
        self.vsquash += acc * dt
        self.squash += self.vsquash * dt
        # tilt spring (overshoots a little)
        tilt_target = TILT.get(state, 0.0) * strength
        if state in ("disagreeing", "annoyed"):
            tilt_target = self.other_side * 4 * strength
        acc = -70 * (self.tilt - tilt_target) - 8 * self.vtilt
        self.vtilt += acc * dt
        self.tilt += self.vtilt * dt
        # sprout / antenna wobble, driven by body motion
        acc = -110 * self.wobble - 5 * self.vwobble - self.vy * 0.9 - self.vtilt * 2.5
        self.vwobble += acc * dt
        self.wobble += self.vwobble * dt

    # -- pose ---------------------------------------------------------------------------

    def pose(self) -> Pose:
        t = self.t
        f = self.face
        motion = self.motion if self.enabled else 0.0
        state = self.effective_state()
        p = Pose(state=state, time=t)
        for key in FACE_DEFAULTS:
            setattr(p, key, f[key])
        # blink closes whatever the eyes are doing
        blink = 1.0
        if self.enabled and t < self._blink_until:
            blink = 0.08
        p.eye_open = min(f["eye_open"], blink)
        p.look_x, p.look_y = self.look_x, self.look_y
        p.lean = self.look_x * 1.6 * motion
        # talking mouth + emphasis
        if self.talk_level > 0.02:
            p.mouth_open = max(p.mouth_open, 0.08 + 0.9 * self.talk_level)
            p.mouth_width = p.mouth_width * (0.9 + 0.15 * self.talk_level)
            p.brow_raise += 0.25 * self._beat
        # body
        energy = 0.4 + 0.9 * self.persona.idle_energy
        breathe = math.sin(t * (1.6 + energy)) * 1.1 * energy * motion
        if self.expression_state() == "sleeping":
            breathe = math.sin(t * 0.9) * 1.8 * motion
        p.bob = (self.y + breathe - self.talk_level * 1.2 * math.sin(t * 9) * motion) * (1 if motion else 0)
        p.squash = 1.0 + self.squash * 0.1 * motion
        p.tilt = self.tilt * motion
        since = t - self._shake_at
        p.shake = (math.sin(since * 55) * self._shake_amp * math.exp(-since * 6) if since < 0.8 else 0.0) * motion
        p.wobble = self.wobble * motion
        p.arm_left = self.arms[True]
        p.arm_right = self.arms[False]
        p.props = {k: v for k, v in self.props.items() if v > 0.02}
        if not self.enabled:
            p.props.pop("sparks", None)
        return p


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
