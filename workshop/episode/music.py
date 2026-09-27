"""A synthesized music bed for episodes: a light, bouncy loop (no samples, no licences).

96 BPM, four bars in A minor (Am–F–C–G): kick, snare, hats, a plucked bass and a
soft arpeggio. It is mixed low and ducked under speech by the renderer.
"""

from __future__ import annotations

import numpy as np

RATE = 24000
BPM = 96
BEAT = 60.0 / BPM
NOTES = {"A2": 110.0, "F2": 87.31, "C3": 130.81, "G2": 98.0, "A3": 220.0, "C4": 261.63, "E4": 329.63, "F3": 174.61,
         "A4": 440.0, "G3": 196.0, "B3": 246.94, "D4": 293.66, "G4": 392.0}
CHORDS = [("A2", ["A3", "C4", "E4", "C4"]), ("F2", ["F3", "A3", "C4", "A3"]), ("C3", ["C4", "E4", "G4", "E4"]),
          ("G2", ["G3", "B3", "D4", "B3"])]


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / RATE
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _tone(freq: float, seconds: float, shape: str = "sine", decay: float = 0.25, attack: float = 0.004) -> np.ndarray:
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    if shape == "pluck":  # a warm, slightly square bass
        wave = np.sign(np.sin(2 * np.pi * freq * t)) * 0.35 + np.sin(2 * np.pi * freq * t) * 0.65
    elif shape == "bell":
        wave = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2.01 * t)
    else:
        wave = np.sin(2 * np.pi * freq * t)
    return (wave * _env(n, attack, decay)).astype(np.float32)


def _kick() -> np.ndarray:
    n = int(0.25 * RATE)
    t = np.arange(n) / RATE
    freq = 50 + 90 * np.exp(-t * 30)
    return (np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t * 14)).astype(np.float32)


def _noise(seconds: float, decay: float, seed: int, highpass: bool = True) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * RATE)
    x = rng.standard_normal(n).astype(np.float32)
    if highpass:
        x = np.diff(x, prepend=0.0)
    return x * np.exp(-np.arange(n) / RATE / decay).astype(np.float32)


def loop() -> np.ndarray:
    """Four bars, ready to tile."""
    bars = 4
    n = int(bars * 4 * BEAT * RATE)
    out = np.zeros(n + RATE, np.float32)

    def put(at: float, x: np.ndarray, gain: float) -> None:
        i = int(at * RATE)
        out[i:i + len(x)] += x[: max(0, len(out) - i)] * gain

    kick, snare, hat = _kick(), _noise(0.18, 0.06, 1) * 0.5, _noise(0.05, 0.015, 2)
    for bar, (bass, arp) in enumerate(CHORDS):
        t0 = bar * 4 * BEAT
        for beat in range(4):
            at = t0 + beat * BEAT
            put(at, kick, 0.9 if beat in (0, 2) else 0.0)
            if beat in (1, 3):
                put(at, snare, 0.55)
            put(at, hat, 0.18)
            put(at + BEAT / 2, hat, 0.12)
            put(at, _tone(NOTES[bass], BEAT * 0.9, "pluck", decay=0.22), 0.32)
            put(at + BEAT * 0.75, _tone(NOTES[bass] * 2, BEAT * 0.3, "pluck", decay=0.08), 0.12)
        for step in range(8):  # eighth-note arpeggio
            put(t0 + step * BEAT / 2, _tone(NOTES[arp[step % 4]], BEAT * 0.6, "bell", decay=0.18), 0.09)
    out = out[:n]
    return out / max(1e-6, float(np.max(np.abs(out)))) * 0.9


_LOOP: np.ndarray | None = None


def bed(seconds: float) -> np.ndarray:
    """The loop, tiled to ``seconds``, with a short fade in and out."""
    global _LOOP
    if _LOOP is None:
        _LOOP = loop()
    n = int(seconds * RATE)
    if n <= 0:
        return np.zeros(0, np.float32)
    reps = n // len(_LOOP) + 1
    out = np.tile(_LOOP, reps)[:n].copy()
    fade = min(n // 2, int(0.6 * RATE))
    if fade:
        out[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        out[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return out
