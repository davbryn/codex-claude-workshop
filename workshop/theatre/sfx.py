"""Tiny, original sound effects synthesised at first use (no media assets).

Each effect is a short, quiet WAV rendered with the standard library into
config/cache/sfx and played through QSoundEffect. Everything degrades to
silence if audio is unavailable.
"""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QUrl

from ..config import CONFIG_DIR
from .speech import audio_disabled

RATE = 22050
CACHE_DIR = CONFIG_DIR / "cache" / "sfx"
VERSION = 3  # bump to regenerate cached files


def _note(freq: float, seconds: float, *, wave_shape: str = "sine", attack=0.005, decay=None, gain=1.0,
          slide_to: float | None = None) -> list[float]:
    n = int(RATE * seconds)
    out = []
    phase = 0.0
    decay = decay if decay is not None else seconds * 0.8
    for i in range(n):
        t = i / RATE
        f = freq if slide_to is None else freq + (slide_to - freq) * (i / n)
        phase += 2 * math.pi * f / RATE
        if wave_shape == "sine":
            s = math.sin(phase) + 0.25 * math.sin(2 * phase) + 0.08 * math.sin(3 * phase)
        elif wave_shape == "triangle":
            s = 2 / math.pi * math.asin(math.sin(phase))
        elif wave_shape == "square":
            s = 0.6 if math.sin(phase) >= 0 else -0.6
        else:  # bell
            s = math.sin(phase) + 0.4 * math.sin(2.76 * phase) + 0.2 * math.sin(5.4 * phase)
        env = min(1.0, t / attack) * math.exp(-t / max(decay, 1e-3) * 3)
        out.append(s * env * gain)
    return out


def _mix(*parts: tuple[float, list[float]]) -> list[float]:
    length = max(int(start * RATE) + len(samples) for start, samples in parts)
    buf = [0.0] * length
    for start, samples in parts:
        offset = int(start * RATE)
        for i, s in enumerate(samples):
            buf[offset + i] += s
    return buf


def _noise(seconds: float, gain: float, seed: int = 7) -> list[float]:
    rng = random.Random(seed)
    n = int(RATE * seconds)
    return [(rng.random() * 2 - 1) * gain * math.exp(-i / n * 4) for i in range(n)]


def _blast(seconds: float = 1.1) -> list[float]:
    """A one-second burst of grindcore: distorted power chord, blast beat. (Gilfoyle would approve.)"""
    rng = random.Random(666)
    n = int(RATE * seconds)
    out = []
    p1 = p2 = p3 = 0.0
    for i in range(n):
        t = i / RATE
        p1 += 2 * math.pi * 82.4 / RATE
        p2 += 2 * math.pi * 123.5 / RATE
        p3 += 2 * math.pi * 164.8 / RATE
        saw = lambda ph: ((ph / math.pi) % 2) - 1  # noqa: E731
        chord = saw(p1) + 0.8 * saw(p2) + 0.6 * saw(p3)
        guitar = math.tanh(chord * 4.0) * 0.55
        step = t % 0.0714
        snare = (rng.random() * 2 - 1) * math.exp(-step * 70) * 0.5
        kick = math.sin(2 * math.pi * 55 * step) * math.exp(-step * 45) * 0.7
        env = min(1.0, t / 0.01) * (1.0 if t < seconds - 0.12 else max(0.0, (seconds - t) / 0.12))
        out.append(math.tanh((guitar + snare + kick) * 1.4) * env * 0.9)
    return out


def _wahwah() -> list[float]:
    """The sad trombone of a grudging concession."""
    notes = [(0.0, 392, 0.3), (0.32, 370, 0.3), (0.64, 349, 0.3), (0.96, 330, 0.9)]
    parts = []
    for start, f, dur in notes:
        n = int(RATE * dur)
        samples = []
        phase = 0.0
        for i in range(n):
            t = i / RATE
            vib = 1 + (0.012 * math.sin(2 * math.pi * 6 * t) if dur > 0.5 else 0)
            phase += 2 * math.pi * f * vib / RATE
            s = math.sin(phase) + 0.5 * math.sin(2 * phase) + 0.3 * math.sin(3 * phase) + 0.15 * math.sin(4 * phase)
            env = min(1.0, t / 0.03) * (1 - (t / dur) ** 3)
            samples.append(s * env * 0.28)
        parts.append((start, samples))
    return _mix(*parts)


def _effects() -> dict[str, list[float]]:
    return {
        "handoff": _mix((0, _note(660, 0.12, gain=0.5)), (0.07, _note(988, 0.22, gain=0.45))),
        "chime": _mix((0, _note(1047, 0.5, wave_shape="bell", gain=0.35)),
                      (0.08, _note(1319, 0.5, wave_shape="bell", gain=0.3)),
                      (0.16, _note(1568, 0.7, wave_shape="bell", gain=0.3))),
        "buzz": _mix((0, _note(130, 0.14, wave_shape="square", gain=0.35, decay=0.2)),
                     (0.17, _note(110, 0.2, wave_shape="square", gain=0.35, decay=0.25))),
        "zap": _mix((0, _note(1400, 0.28, wave_shape="triangle", gain=0.3, slide_to=180)),
                    (0, _noise(0.22, 0.18))),
        "alert": _mix((0, _note(880, 0.35, wave_shape="bell", gain=0.4)),
                      (0.28, _note(698, 0.55, wave_shape="bell", gain=0.4))),
        "fanfare": _mix(*[(i * 0.12, _note(f, 0.3 if i < 3 else 1.1, wave_shape="triangle", gain=0.32))
                          for i, f in enumerate((523, 659, 784, 1047))],
                        (0.36, _note(1319, 1.0, wave_shape="bell", gain=0.15))),
        "human": _mix((0, _note(392, 0.16, gain=0.4)), (0.13, _note(523, 0.16, gain=0.4)),
                      (0.26, _note(659, 0.3, gain=0.4))),
        "pop": _note(1200, 0.06, gain=0.25, slide_to=1800, decay=0.05),
        "yes": _mix((0, _note(523, 0.1, wave_shape="triangle", gain=0.35)),
                    (0.08, _note(659, 0.1, wave_shape="triangle", gain=0.35)),
                    (0.16, _note(784, 0.12, wave_shape="triangle", gain=0.38)),
                    (0.26, _note(1047, 0.8, wave_shape="square", gain=0.18)),
                    (0.26, _note(1319, 0.9, wave_shape="bell", gain=0.3))),
        "blast": _blast(),
        "wahwah": _wahwah(),
        "oops": _mix((0, _note(520, 0.16, wave_shape="triangle", gain=0.35, slide_to=440)),
                     (0.14, _note(440, 0.3, wave_shape="triangle", gain=0.35, slide_to=330))),
    }


def _write_wav(path: Path, samples: list[float]) -> None:
    peak = max(1e-6, max(abs(s) for s in samples))
    scale = 0.9 / peak if peak > 0.9 else 1.0
    frames = b"".join(struct.pack("<h", int(max(-1, min(1, s * scale)) * 32000)) for s in samples)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(frames)


def ensure_effects(directory: Path = CACHE_DIR) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / f".v{VERSION}"
    paths = {name: directory / f"{name}.wav" for name in _effects_names()}
    if not marker.exists() or not all(p.exists() for p in paths.values()):
        for name, samples in _effects().items():
            _write_wav(paths[name], samples)
        marker.write_text("ok")
    return paths


def _effects_names() -> list[str]:
    return ["handoff", "chime", "buzz", "zap", "alert", "fanfare", "human", "pop", "oops", "yes", "blast", "wahwah"]


class SoundEffects(QObject):
    """Plays named effects; silently does nothing when disabled or unavailable."""

    def __init__(self, enabled: bool = True, volume: float = 0.5, parent: QObject | None = None):
        super().__init__(parent)
        self.enabled = enabled
        self.volume = volume
        self._effects = {}
        self.available = False
        if audio_disabled():
            return
        try:
            from PySide6.QtMultimedia import QMediaDevices, QSoundEffect

            if not QMediaDevices.audioOutputs():
                return
            for name, path in ensure_effects().items():
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(path)))
                effect.setVolume(volume)
                self._effects[name] = effect
            self.available = True
        except Exception:
            self._effects = {}

    def set_volume(self, volume: float) -> None:
        self.volume = volume
        for effect in self._effects.values():
            effect.setVolume(volume)

    def play(self, name: str) -> None:
        if self.enabled and name in self._effects:
            self._effects[name].play()
