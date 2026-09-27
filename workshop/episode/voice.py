"""Offline voices for the episode: Kokoro renders each line to samples up front (no audio device needed).

If Kokoro isn't installed the episode is still cut, with silent lines timed to a
reading pace and a synthetic mouth envelope, so the pipeline never depends on it.
"""

from __future__ import annotations

import math

import numpy as np

from ..theatre.neural_tts import (CHARACTER_SPEED, DEFAULT_VOICES, ENVELOPE_HOP, MODEL_FILE, SAMPLE_RATE,
                                  VOICES_FILE, models_present, split_for_streaming)


class Voices:
    def __init__(self, settings=None, progress=print):
        self._kokoro = None
        self.error = ""
        self.voices = dict(DEFAULT_VOICES)
        self.speed = 1.0
        if settings is not None:
            for agent, voice in (("Codex", settings.codex_voice), ("Claude", settings.claude_voice)):
                if voice:
                    self.voices[agent] = voice
            self.speed = max(0.6, min(1.6, 1.0 + settings.speech_rate * 0.6))
        if not models_present():
            self.error = "Kokoro model files are missing"
            return
        try:
            import os

            import onnxruntime as ort
            from kokoro_onnx import Kokoro

            options = ort.SessionOptions()
            options.intra_op_num_threads = max(2, min(8, (os.cpu_count() or 4) // 2))
            session = ort.InferenceSession(str(MODEL_FILE), sess_options=options, providers=["CPUExecutionProvider"])
            self._kokoro = Kokoro.from_session(session, str(VOICES_FILE))
            known = set(self._kokoro.get_voices())
            self.voices = {a: (v if v in known else DEFAULT_VOICES[a]) for a, v in self.voices.items()}
        except Exception as exc:
            self.error = str(exc)
            self._kokoro = None
        if self.error:
            progress(f"voices unavailable ({self.error}); the episode will have effects but silent lines")

    @property
    def available(self) -> bool:
        return self._kokoro is not None

    def say(self, agent: str, text: str, mood: str | None = None, to_camera: bool = False
            ) -> tuple[np.ndarray, np.ndarray]:
        """(samples at SAMPLE_RATE float32, mouth level 0..1 per 10 ms), performed rather than read.

        Each sentence is voiced separately so the timing can be shaped: tight gaps
        inside a line, and a held pause before the last sentence (the button).
        Mood sets the pace and energy: Dinesh speeds up when he's outraged or
        gloating, Gilfoyle slows down for a threat.
        """
        if not text.strip():
            return np.zeros(0, np.float32), np.zeros(0, np.float32)
        if self._kokoro is None:
            return self._silent(text)
        pace, gain = delivery(agent, mood, to_camera)
        speed = max(0.5, min(2.0, self.speed * CHARACTER_SPEED.get(agent, 1.0) * pace))
        sentences = split_sentences(text)
        parts = []
        for i, sentence in enumerate(sentences):
            chunks = split_for_streaming(sentence, first_max=180, growth=1.0)
            for chunk in chunks:
                try:
                    samples, _ = self._kokoro.create(chunk, voice=self.voices[agent], speed=speed, lang="en-us")
                except Exception:
                    continue
                parts.append(trim_silence(np.clip(np.asarray(samples, np.float32), -1, 1) * gain))
            if i < len(sentences) - 1:
                parts.append(np.zeros(int(SAMPLE_RATE * pause_before(agent, i + 1, len(sentences))), np.float32))
        if not parts:
            return self._silent(text)
        parts.append(np.zeros(int(SAMPLE_RATE * 0.08), np.float32))
        samples = np.clip(np.concatenate(parts), -1, 1)
        return samples, envelope(samples)

    @staticmethod
    def _silent(text: str) -> tuple[np.ndarray, np.ndarray]:
        seconds = max(1.2, len(text) / 15.0)
        frames = int(seconds * 100)
        level = np.array([0.55 + 0.35 * math.sin(i * 0.9) * math.sin(i * 0.23) for i in range(frames)], np.float32)
        return np.zeros(int(seconds * SAMPLE_RATE), np.float32), np.clip(level, 0, 1)


def envelope(samples: np.ndarray) -> np.ndarray:
    frames = len(samples) // ENVELOPE_HOP
    if not frames:
        return np.zeros(0, np.float32)
    rms = np.sqrt(np.mean(samples[: frames * ENVELOPE_HOP].reshape(frames, ENVELOPE_HOP) ** 2, axis=1))
    # the same loudness curve the live engine uses for the mouth
    return np.where(rms > 0.004, np.minimum(1.0, (rms / 0.16) ** 0.8), 0.0).astype(np.float32)


FAST = {"outraged", "gloating", "celebrating", "surprised", "worried", "disagreeing", "annoyed", "highfive"}
SLOW = {"stare", "glare", "sideeye", "disturbed", "smug", "embarrassed"}


def delivery(agent: str, mood: str | None, to_camera: bool) -> tuple[float, float]:
    """(pace multiplier, gain) for a line."""
    pace, gain = 1.0, 1.0
    if mood in FAST:
        pace, gain = (1.04, 1.05) if agent == "Codex" else (1.14, 1.12)
    elif mood in SLOW:
        pace = 0.9 if agent == "Codex" else 0.95
    if to_camera:
        pace *= 0.96  # confessionals are a little more considered
    return pace, gain


def split_sentences(text: str) -> list[str]:
    import re

    # a sentence ends at . ! ? or … (optionally inside a closing quote) followed by a capital or a number
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])(?:['\"”’])?\s+(?=[A-Z0-9'\"“(])", text.strip()) if p.strip()]
    return parts or [text.strip()]


def pause_before(agent: str, index: int, count: int) -> float:
    """The gap before sentence ``index``: tight inside a line, held before the button."""
    if index == count - 1 and count >= 2:
        return 0.42 if agent == "Codex" else 0.3
    return 0.16 if agent == "Codex" else 0.1


def trim_silence(samples: np.ndarray, threshold: float = 0.01, keep: float = 0.03) -> np.ndarray:
    loud = np.flatnonzero(np.abs(samples) > threshold)
    if not len(loud):
        return samples
    pad = int(SAMPLE_RATE * keep)
    return samples[max(0, loud[0] - pad): loud[-1] + pad]
