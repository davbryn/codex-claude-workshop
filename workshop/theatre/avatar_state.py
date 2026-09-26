"""Avatar animation: theatrical states → a smoothly animated, renderable Pose.

States are UI reactions to public events (process status, public text, test
output). They are not claims about what a model "feels".

Layers, highest priority first:
  talking   – mouth/gesture animation while an entry is performed
  reaction  – a transient expression (pleased, glare, sideeye, …) that expires
  base      – from process status (waiting, reading, coding, …)

Every face/arm value eases toward its target and the body runs on small
springs (chair bounces, overshooting tilts, hair sway), so expressions morph
instead of snapping. Two animation philosophies matter for the cast:
"deadpan" (Gilfoyle: almost motionless, eyebrow-sized reactions, slow
sideways looks) and "expressive" (Dinesh: big faces, big hands, bounces).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

STATES = (
    "idle", "waiting", "reading", "thinking", "coding", "reviewing", "talking", "pleased",
    "celebrating", "confused", "annoyed", "disagreeing", "embarrassed", "error", "sleeping",
    "complete", "smug", "surprised",
    # character beats (Gilfoyle & Dinesh)
    "gloating", "outraged", "glare", "sideeye", "stare", "disturbed", "worried", "highfive",
)

REACTION_SECONDS = {
    "pleased": 3.0, "celebrating": 3.6, "confused": 3.0, "annoyed": 3.2, "disagreeing": 4.0,
    "embarrassed": 3.6, "error": 2.6, "smug": 2.8, "surprised": 1.6, "talking": 0.0,
    "gloating": 3.4, "outraged": 3.0, "glare": 2.6, "sideeye": 2.8, "stare": 3.2, "disturbed": 3.0,
    "worried": 3.0, "highfive": 2.2,
}

# How fast the eyes/head travel to a new look target (per second). A slow
# sideways glance is most of Gilfoyle's comedy.
LOOK_SPEED = {"sideeye": 1.4, "stare": 2.0}


@dataclass
class Persona:
    animation_style: str = "neutral"  # deadpan | expressive | confident | dramatic | calm | neutral
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

    @property
    def deadpan(self) -> bool:
        return self.animation_style in ("deadpan", "calm")


DEFAULT_PERSONAS = {
    "Codex": Persona("deadpan", idle_energy=0.12, reaction_strength=0.3),
    "Claude": Persona("expressive", idle_energy=0.7, reaction_strength=1.0),
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
    "coding": {"lid_top": 0.3, "brow_angle": 0.22, "brow_raise": -0.1, "mouth_curve": 0.0, "mouth_width": 0.75,
               "code_rain": 1.0, "glow": 0.9},
    "reviewing": {"lid_top": 0.4, "lid_bottom": 0.12, "brow_angle": 0.3, "brow_raise": 0.25, "mouth_curve": -0.1,
                  "mouth_asym": 0.35, "glow": 0.7},
    "talking": {"brow_raise": 0.2, "mouth_curve": 0.2, "glow": 0.8},
    "pleased": {"happy": 0.7, "brow_raise": 0.35, "mouth_curve": 0.85, "mouth_width": 1.1, "blush": 0.2},
    "celebrating": {"happy": 1.0, "brow_raise": 0.7, "mouth_curve": 1.0, "mouth_open": 0.8, "mouth_width": 1.35,
                    "teeth": 1.0, "blush": 0.3},
    "complete": {"happy": 1.0, "brow_raise": 0.6, "mouth_curve": 1.0, "mouth_open": 0.7, "mouth_width": 1.3,
                 "teeth": 1.0, "blush": 0.3},
    "confused": {"eye_scale": 1.12, "pupil": 0.8, "brow_raise": 0.5, "brow_angle": -0.45, "brow_asym": 0.6,
                 "mouth_curve": -0.15, "mouth_wave": 1.0, "mouth_width": 0.9},
    "annoyed": {"lid_top": 0.35, "lid_slant": 0.7, "brow_angle": 0.7, "brow_raise": -0.3, "mouth_curve": -0.35,
                "mouth_width": 0.8, "steam": 0.4},
    "disagreeing": {"lid_top": 0.25, "lid_slant": 1.0, "brow_angle": 1.0, "brow_raise": -0.4, "mouth_curve": -0.7,
                    "mouth_open": 0.3, "mouth_width": 1.1, "steam": 0.8},
    "embarrassed": {"lid_top": 0.45, "brow_angle": -0.7, "brow_raise": 0.35, "mouth_curve": -0.1,
                    "mouth_wave": 1.0, "mouth_width": 0.8, "blush": 0.8},
    "error": {"eye_scale": 1.2, "pupil": 0.7, "brow_raise": 0.8, "brow_angle": -0.6, "mouth_curve": -0.45,
              "mouth_open": 0.6, "mouth_width": 0.6, "glitch": 1.0, "glow": 1.0},
    "sleeping": {"eye_open": 0.0, "brow_raise": -0.2, "mouth_curve": 0.05, "mouth_open": 0.18, "mouth_width": 0.55,
                 "glow": 0.1},
    "smug": {"lid_top": 0.38, "brow_asym": 1.0, "mouth_curve": 0.55, "mouth_asym": 0.9, "mouth_width": 0.95},
    "surprised": {"eye_scale": 1.25, "pupil": 0.7, "brow_raise": 1.0, "mouth_open": 0.7, "mouth_width": 0.55,
                  "mouth_curve": 0.0},
    "gloating": {"happy": 0.55, "lid_top": 0.15, "brow_raise": 0.55, "brow_asym": 0.6, "mouth_curve": 1.0,
                 "mouth_open": 0.5, "mouth_width": 1.4, "teeth": 1.0, "mouth_asym": 0.25},
    "outraged": {"eye_scale": 1.25, "pupil": 0.72, "brow_raise": 0.9, "brow_angle": -0.35, "mouth_curve": -0.5,
                 "mouth_open": 0.65, "mouth_width": 0.95, "steam": 0.8},
    "glare": {"lid_top": 0.4, "lid_slant": 0.8, "brow_angle": 0.85, "brow_raise": -0.35, "mouth_curve": -0.45,
              "mouth_width": 0.75},
    "sideeye": {"lid_top": 0.5, "brow_asym": 0.35, "mouth_curve": -0.05, "mouth_width": 0.8},
    "stare": {"lid_top": 0.42, "mouth_curve": 0.0, "mouth_width": 0.75},
    "disturbed": {"lid_top": 0.2, "brow_raise": 0.3, "brow_angle": -0.3, "mouth_curve": -0.25, "mouth_wave": 0.6,
                  "mouth_width": 0.8},
    "worried": {"eye_scale": 1.1, "brow_raise": 0.6, "brow_angle": -0.75, "mouth_curve": -0.3, "mouth_wave": 0.5,
                "mouth_width": 0.8},
    "highfive": {"happy": 0.8, "brow_raise": 0.6, "mouth_curve": 1.0, "mouth_open": 0.5, "mouth_width": 1.25,
                 "teeth": 1.0},
}

# Gilfoyle's face barely moves: for the deadpan style these REPLACE the shared expressions.
DEADPAN = {
    "idle": {"lid_top": 0.18, "mouth_curve": 0.0, "mouth_width": 0.85},
    "waiting": {"lid_top": 0.20, "mouth_curve": 0.0, "mouth_width": 0.85},
    "talking": {"lid_top": 0.16, "mouth_curve": 0.0},
    "pleased": {"lid_top": 0.21, "mouth_curve": 0.3, "mouth_asym": 0.7, "brow_asym": 0.3},
    "smug": {"lid_top": 0.28, "mouth_curve": 0.38, "mouth_asym": 0.95, "brow_asym": 0.55},
    "gloating": {"lid_top": 0.26, "mouth_curve": 0.45, "mouth_asym": 1.0, "brow_asym": 0.6},
    "celebrating": {"lid_top": 0.16, "mouth_curve": 0.4, "mouth_asym": 0.6, "brow_asym": 0.25},
    "complete": {"lid_top": 0.16, "mouth_curve": 0.35, "mouth_asym": 0.6, "brow_asym": 0.25},
    "annoyed": {"lid_top": 0.36, "brow_angle": 0.25, "brow_raise": -0.1, "mouth_curve": -0.1, "mouth_width": 0.8},
    "disagreeing": {"lid_top": 0.31, "brow_angle": 0.3, "mouth_curve": -0.1, "mouth_width": 0.8},
    "embarrassed": {"lid_top": 0.36, "mouth_curve": -0.1, "mouth_width": 0.75},
    "surprised": {"lid_top": 0.01, "brow_raise": 0.35},
    "outraged": {"lid_top": 0.16, "brow_raise": 0.35, "mouth_curve": -0.1},
    "error": {"lid_top": 0.24, "brow_raise": 0.15, "mouth_curve": -0.05, "mouth_width": 0.8},
    "confused": {"lid_top": 0.21, "brow_asym": 0.6, "mouth_curve": -0.05},
    "glare": {"lid_top": 0.36, "brow_angle": 0.35, "mouth_curve": -0.1},
    "sideeye": {"lid_top": 0.38, "brow_asym": 0.35},
    "stare": {"lid_top": 0.31},
    "disturbed": {"lid_top": 0.16, "brow_raise": 0.2, "mouth_curve": -0.15},
    "worried": {"lid_top": 0.21, "brow_raise": 0.1},
    "highfive": {"lid_top": 0.21, "mouth_curve": 0.2, "mouth_asym": 0.5},
    "coding": {"lid_top": 0.26, "brow_angle": 0.15, "mouth_curve": 0.0, "mouth_width": 0.8},
    "reading": {"lid_top": 0.24, "mouth_curve": 0.0, "mouth_width": 0.8},
    "reviewing": {"lid_top": 0.36, "brow_angle": 0.2, "mouth_curve": -0.05, "mouth_width": 0.8},
    "thinking": {"lid_top": 0.26, "brow_asym": 0.3, "mouth_curve": 0.0, "mouth_width": 0.8},
    "sleeping": {"eye_open": 0.0, "mouth_curve": 0.0, "mouth_width": 0.7},
}

ARMS = {
    "idle": "rest", "waiting": "rest", "reading": "chin", "thinking": "chin", "coding": "typing",
    "reviewing": "chin", "talking": "gesture", "pleased": "rest", "celebrating": "up", "complete": "up",
    "confused": "shrug", "annoyed": "cross", "disagreeing": "point", "embarrassed": "cover", "error": "what",
    "sleeping": "rest", "smug": "cross", "surprised": "what", "gloating": "fist", "outraged": "what",
    "glare": "cross", "sideeye": "rest", "stare": "rest", "disturbed": "rest", "worried": "chin",
    "highfive": "highfive",
}
# Gilfoyle keeps his hands where they are.
DEADPAN_ARMS = {"reading": "typing", "reviewing": "chin", "thinking": "chin", "celebrating": "rest",
                "complete": "rest", "confused": "rest", "annoyed": "rest", "disagreeing": "rest",
                "embarrassed": "rest", "error": "rest", "surprised": "rest", "gloating": "cross",
                "outraged": "rest", "highfive": "lift", "smug": "cross", "worried": "rest"}

PROPS = {
    "celebrating": ("sparkles",), "complete": ("sparkles", "chain"), "gloating": ("yes", "chain"),
    "confused": ("question",), "disagreeing": ("vein",), "outraged": ("vein", "exclaim"), "glare": ("vein",),
    "embarrassed": ("sweat",), "worried": ("sweat",), "error": ("error",), "sleeping": ("zzz",),
    "surprised": ("exclaim",), "highfive": ("sparkles",),
}
DEADPAN_PROPS = {"sleeping": ("zzz",), "confused": ("question",)}
ALL_PROPS = ("sparkles", "chain", "yes", "question", "vein", "sweat", "error", "zzz", "exclaim", "mug")

TILT = {"confused": 7.0, "embarrassed": -4.0, "sleeping": -9.0, "thinking": 3.0, "worried": -3.0,
        "disturbed": -2.5}


@dataclass
class Pose:
    state: str = "idle"
    # body
    bob: float = 0.0
    squash: float = 1.0
    tilt: float = 0.0
    shake: float = 0.0
    lean: float = 0.0
    wobble: float = 0.0  # hair sway (degrees)
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
    arm_left: tuple = ((24.0, 86.0), (40.0, 90.0), True)
    arm_right: tuple = ((76.0, 86.0), (60.0, 90.0), True)
    props: dict = field(default_factory=dict)  # prop -> alpha
    time: float = 0.0
    other_side: int = 1

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
    """Elbow, hand and front/back for one arm of a seated character (100-unit box, desk top ≈ y 90)."""
    sign = -1 if left else 1
    toward = (sign > 0) == (other_side > 0)  # this arm is on the other character's side
    if arms == "typing":
        k = math.sin(t * 15 + (0 if left else math.pi)) * 1.2
        return (50 + sign * 25, 86), (50 + sign * 10, 90 + k), True
    if arms == "rest":
        return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True
    if arms == "up":
        wave = math.sin(t * 9 + (0 if left else 1.3)) * 2.5
        return (50 + sign * 31, 54), (50 + sign * 29 + wave, 33), True
    if arms == "fist":
        if toward:
            return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True
        pump = abs(math.sin(t * 7)) * 5
        return (50 + sign * 30, 64), (50 + sign * 24, 46 - pump), True
    if arms == "what":
        wob = math.sin(t * 6 + (0 if left else 1)) * 1.5
        return (50 + sign * 31, 80), (50 + sign * 39, 67 + wob), True
    if arms == "cross":
        return (50 + sign * 24, 82), (50 - sign * 12, 79), True
    if arms == "chin":
        if left:
            return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True
        return (50 + sign * 22, 80), (50 + sign * 6, 59), True
    if arms == "cover":
        if left:
            return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True
        return (50 + sign * 24, 66), (50 + sign * 6, 38), True
    if arms == "shrug":
        return (50 + sign * 30, 80), (50 + sign * 36, 70), True
    if arms == "point":
        if toward:
            return (50 + sign * 32, 72), (50 + sign * 45, 63), True
        return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True
    if arms == "highfive":
        if toward:
            return (50 + sign * 34, 58), (50 + sign * 44, 40), True
        return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True
    if arms == "lift":  # a barely-reciprocated high five
        if toward:
            return (50 + sign * 27, 80), (50 + sign * 30, 70), True
        return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True
    if arms == "catch":
        return (50 + sign * 25, 74), (50 + sign * 13, 62), True
    if arms == "stretch":
        return (50 + sign * 30, 42), (50 + sign * 11, 26), False
    if arms == "mug":
        if toward:
            return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True
        return (50 + sign * 24, 80), (50 + sign * 9, 62), True
    if arms == "gesture":
        lift = beat if (left == beat_left) else beat * 0.3
        return (50 + sign * (26 + 3 * lift), 84 - 6 * lift), (50 + sign * (14 + 12 * lift), 89 - 16 * lift), True
    return (50 + sign * 25, 86), (50 + sign * 11, 90.5), True


class AvatarModel:
    """Time-based animation for one agent. ``other_side`` is -1 if the other
    agent sits to the left, +1 if to the right."""

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
        self.arms = {True: arm_target(agent, "rest", True, 0, other_side),
                     False: arm_target(agent, "rest", False, 0, other_side)}
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
        self._look_speed = 10.0
        self._gesture: tuple[str, float] | None = None  # (arms, until)
        self._next_fidget = 14 + self.rng.random() * 10
        self._beat = 0.0
        self._beat_left = True
        self._last_level = 0.0
        self._last_beat = 0.0

    @property
    def deadpan(self) -> bool:
        return self.persona.deadpan

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
        if state in LOOK_SPEED:
            self._look_speed = LOOK_SPEED[state]
            self._look_override = None
        if self.deadpan:
            # Gilfoyle: no bounces, no shakes. At most the tiniest settle.
            if state in ("smug", "gloating"):
                self.vtilt += 6 * self.other_side
            return
        if state in ("error", "disagreeing", "annoyed", "outraged", "glare"):
            self._shake_at, self._shake_amp = self.t, 1.6 * strength
        if state in ("celebrating", "complete"):
            for i in range(3):
                self.hop(0.8 * strength, delay=i * 0.4)
        elif state in ("gloating", "highfive"):
            self.hop(0.45 * strength)
            self.hop(0.3 * strength, delay=0.45)
        elif state in ("pleased", "smug"):
            self.hop(0.2 * strength)
        elif state in ("surprised", "outraged"):
            self.hop(0.35 * strength, anticipation=False)
        elif state == "disagreeing":
            self.hop(0.2 * strength, anticipation=False)

    def hop(self, strength: float = 0.5, delay: float = 0.0, anticipation: bool = True) -> None:
        """Queue a bounce in the chair; with anticipation the body dips first."""
        start = self.t + delay
        if anticipation:
            self._hops.append((start, -strength))  # dip marker
            start += 0.11
        self._hops.append((start, strength))

    def gesture(self, arms: str, seconds: float = 0.8) -> None:
        if self.deadpan and arms in ("point", "catch", "up", "what", "fist"):
            arms = "lift" if arms in ("point", "catch") else "rest"
        self._gesture = (arms, self.t + seconds)

    def nudge_wobble(self, amount: float) -> None:
        self.vwobble += amount * (0.3 if self.deadpan else 1.0)

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

    def look(self, x: float, y: float = 0.0, seconds: float = 2.5, speed: float | None = None) -> None:
        self._look_override = (max(-1, min(1, x)), max(-1, min(1, y)))
        self._look_until = self.t + seconds
        self._look_speed = speed if speed is not None else (5.0 if self.deadpan else 10.0)

    def look_at_other(self, seconds: float = 2.5, speed: float | None = None) -> None:
        self.look(self.other_side * 1.0, 0.0, seconds, speed)

    def look_at_monitor(self, seconds: float = 2.5) -> None:
        self.look(-self.other_side * 0.85, 0.3, seconds)

    def look_at_human(self, seconds: float = 4.0) -> None:
        self.look(self.other_side * 0.35, 0.05, seconds)

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
        style = self.persona.animation_style
        strength = 0.55 + 0.6 * self.persona.reaction_strength
        if self.deadpan:
            if state in DEADPAN:
                target.update(DEADPAN[state])
            else:
                for key, value in EXPRESSIONS.get(state, {}).items():
                    target[key] = FACE_DEFAULTS[key] + (value - FACE_DEFAULTS[key]) * 0.35
            arms = DEADPAN_ARMS.get(state, ARMS.get(state, "rest"))
            props = DEADPAN_PROPS.get(state, ())
        else:
            target.update(EXPRESSIONS.get(state, {}))
            if style == "confident":
                if state == "pleased":
                    target.update(happy=0.25, mouth_asym=0.8, brow_asym=0.8, lid_top=0.3)
                if state in ("idle", "waiting"):
                    target.update(brow_asym=0.25, mouth_asym=0.2)
            if style in ("dramatic", "expressive"):
                strength *= 1.15
            for key in ("brow_raise", "brow_angle", "brow_asym", "mouth_curve", "lid_slant", "blush"):
                target[key] = target[key] * strength if key != "mouth_curve" else target[key] * min(1.2, strength)
            arms = ARMS.get(state, "rest")
            props = PROPS.get(state, ())
        if self._gesture and self.t < self._gesture[1]:
            arms = self._gesture[0]
            if arms == "mug":
                props = (*props, "mug")
        elif self._gesture:
            self._gesture = None
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
            if level > 0.72 and self._last_level <= 0.72 and t - self._last_beat > (0.9 if self.deadpan else 0.45):
                self._beat_left = not self._beat_left
                self._last_beat = t
            self._last_level = level
        else:
            self.talk_level += (0 - self.talk_level) * min(1.0, dt * 12)
        beat = max(0.0, 1 - (t - self._last_beat) / 0.55) if self.talking else 0.0
        self._beat = beat * (0.3 if self.deadpan else 1.0)

        target, arms, props, strength = self._targets()
        rate = min(1.0, dt * (6 if self.deadpan else 9))
        for key, value in target.items():
            self.face[key] += (value - self.face[key]) * rate
        for name in ALL_PROPS:
            want = 1.0 if name in props else 0.0
            self.props[name] += (want - self.props[name]) * min(1.0, dt * 6)
        for left in (True, False):
            elbow, hand, front = arm_target(self.agent, arms, left, t, self.other_side, self._beat, self._beat_left)
            (ex, ey), (hx, hy), _ = self.arms[left]
            k = min(1.0, dt * (14 if arms in ("typing", "gesture", "fist", "up") else 8) * (0.6 if self.deadpan else 1))
            self.arms[left] = ((ex + (elbow[0] - ex) * k, ey + (elbow[1] - ey) * k),
                               (hx + (hand[0] - hx) * k, hy + (hand[1] - hy) * k), front)

        # blinks and glances
        if t >= self._blink_at:
            self._blink_until = t + 0.14
            self._blink_at = t + (0.25 if self.rng.random() < 0.18 else 2.2 + self.rng.random() * 4.0)
            if self.deadpan:
                self._blink_at += 1.5  # he doesn't blink much either
        state = self.expression_state()
        if t >= self._next_glance:
            if self.deadpan:
                choices = [(self.other_side, 0.0), (-self.other_side * 0.85, 0.3)]
            else:
                choices = [(self.other_side, 0.0), (-self.other_side * 0.7, 0.1), (0.0, 0.3),
                           (self.other_side * 0.5, -0.4)]
            self._glance = self.rng.choice(choices)
            self._glance_until = t + 0.8 + self.rng.random() * 1.2
            self._next_glance = t + (9 - 6 * self.persona.idle_energy) + self.rng.random() * 5
            if self.deadpan and self._glance[0] == self.other_side:
                self._look_speed = LOOK_SPEED["sideeye"]
        look = self._look_target(state, motion)
        k = min(1.0, dt * self._look_speed)
        self.look_x += (look[0] - self.look_x) * k
        self.look_y += (look[1] - self.look_y) * k
        if abs(look[0] - self.look_x) < 0.03 and state not in LOOK_SPEED:
            self._look_speed = 5.0 if self.deadpan else 10.0

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
        if t < self._glance_until and state in ("idle", "waiting", "pleased", "smug", "coding", "reading"):
            return self._glance
        wander = motion or 0.4
        monitor = -self.other_side * 0.85
        return {
            "reading": (monitor + math.sin(t * 1.7) * 0.1 * wander, 0.3),
            "reviewing": (monitor + math.sin(t * 1.1) * 0.12 * wander, 0.25),
            "coding": (monitor + math.sin(t * 0.7) * 0.05, 0.35),
            "thinking": (0.2 * self.other_side * -1, -0.5),
            "annoyed": (self.other_side * 0.9, 0.0),
            "disagreeing": (self.other_side * 1.0, 0.0),
            "smug": (self.other_side * 0.9, 0.0),
            "gloating": (self.other_side * 1.0, -0.05),
            "outraged": (self.other_side * 1.0, 0.0),
            "glare": (self.other_side * 1.0, 0.05),
            "sideeye": (self.other_side * 1.0, 0.05),
            "stare": (self.other_side * 1.0, 0.0),
            "highfive": (self.other_side * 1.0, -0.1),
            "disturbed": (self.other_side * 0.6, 0.1),
            "worried": (self.other_side * 0.3, 0.1),
            "embarrassed": (-self.other_side * 0.9, 0.45),
            "sleeping": (0.0, 0.5),
            "confused": (math.sin(t * 2.3) * 0.5 * wander, -0.2),
        }.get(state, (0.0, 0.05))

    def _fidget(self) -> None:
        if self.deadpan:
            choice = self.rng.choice(["mug", "sideeye", "mug", "none"])
            if choice == "mug":
                self.gesture("mug", 2.4)
            elif choice == "sideeye":
                self.look(self.other_side, 0.05, 2.2, speed=LOOK_SPEED["sideeye"])
            return
        choice = self.rng.choice(["stretch", "look", "hop", "glance"])
        if choice == "stretch":
            self.gesture("stretch", 1.6)
            self.vsquash += 0.6
        elif choice == "look":
            self.look(-self.other_side * 0.9, -0.1, 0.9)
            self._glance = (self.other_side, 0.0)
            self._glance_until = self.t + 1.8
        elif choice == "hop":
            self.hop(0.18)
        else:
            self.look_at_other(1.2)
        self.vwobble += self.rng.choice((-1, 1)) * 40

    def _simulate_body(self, dt: float, state: str, strength: float) -> None:
        t = self.t
        # chair bounces (with a dip first)
        remaining = []
        for when, power in self._hops:
            if t >= when:
                if power < 0:
                    self.vsquash -= 1.2 * -power
                elif self.y > -0.5:
                    self.vy = -70 * power
                    self.vsquash += 0.9 * power
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
                self.vsquash -= min(1.6, impact / 70)
                self.vwobble += impact * 0.6
        acc = -320 * self.squash - 14 * self.vsquash
        self.vsquash += acc * dt
        self.squash += self.vsquash * dt
        tilt_target = TILT.get(state, 0.0) * strength * (0.4 if self.deadpan else 1.0)
        if state in ("disagreeing", "annoyed", "glare", "outraged") and not self.deadpan:
            tilt_target = self.other_side * 3 * strength
        acc = -70 * (self.tilt - tilt_target) - 8 * self.vtilt
        self.vtilt += acc * dt
        self.tilt += self.vtilt * dt
        # hair sway, driven by body and head motion
        acc = -90 * self.wobble - 6 * self.vwobble - self.vy * 0.6 - self.vtilt * 2.0
        self.vwobble += acc * dt
        self.wobble += self.vwobble * dt

    # -- pose ---------------------------------------------------------------------------

    def pose(self) -> Pose:
        t = self.t
        f = self.face
        motion = self.motion if self.enabled else 0.0
        state = self.effective_state()
        p = Pose(state=state, time=t, other_side=self.other_side)
        for key in FACE_DEFAULTS:
            setattr(p, key, f[key])
        blink = 1.0
        if self.enabled and t < self._blink_until:
            blink = 0.08
        p.eye_open = min(f["eye_open"], blink)
        p.look_x, p.look_y = self.look_x, self.look_y
        p.lean = self.look_x * (0.8 if self.deadpan else 1.8) * motion
        if self.talk_level > 0.02:
            p.mouth_open = max(p.mouth_open, 0.06 + (0.55 if self.deadpan else 0.9) * self.talk_level)
            p.mouth_width = p.mouth_width * (0.9 + 0.15 * self.talk_level)
            p.brow_raise += (0.08 if self.deadpan else 0.3) * self._beat
        energy = 0.4 + 0.9 * self.persona.idle_energy
        breathe = math.sin(t * (1.4 + energy)) * 0.7 * energy * motion
        if self.expression_state() == "sleeping":
            breathe = math.sin(t * 0.9) * 1.4 * motion
        talk_bob = self.talk_level * (0.3 if self.deadpan else 1.0) * math.sin(t * 9) * motion
        p.bob = (self.y + breathe - talk_bob) * (1 if motion else 0)
        p.squash = 1.0 + self.squash * 0.06 * motion
        p.tilt = self.tilt * motion
        since = t - self._shake_at
        p.shake = (math.sin(since * 55) * self._shake_amp * math.exp(-since * 6) if since < 0.8 else 0.0) * motion
        p.wobble = self.wobble * motion
        p.arm_left = self.arms[True]
        p.arm_right = self.arms[False]
        p.props = {k: v for k, v in self.props.items() if v > 0.02}
        return p


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
