"""Kokoro-82M neural text-to-speech (fully local, via ONNX Runtime).

Model files live in config/cache/tts (see ``python -m workshop.theatre.neural_tts --download``).
Speech is synthesised sentence by sentence on a worker thread and streamed
into a QAudioSink, so the first words play about a second after a line starts.
Because we have the real samples, ``level()`` exposes the live loudness of the
voice, which drives the characters' mouths.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QTimer

from ..config import CONFIG_DIR
from .speech import SpeechEngine

MODEL_DIR = CONFIG_DIR / "cache" / "tts"
MODEL_FILE = MODEL_DIR / "kokoro-v1.0.onnx"
VOICES_FILE = MODEL_DIR / "voices-v1.0.bin"
MODEL_URLS = {
    MODEL_FILE: "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    VOICES_FILE: "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}
SAMPLE_RATE = 24000
ENVELOPE_HOP = 240  # 10 ms loudness frames
DEFAULT_VOICES = {"Codex": "am_michael", "Claude": "af_heart"}
ACCENTS = {"a": "American", "b": "British"}


def models_present() -> bool:
    return MODEL_FILE.exists() and VOICES_FILE.exists()


def voice_label(voice_id: str) -> str:
    """'am_michael' -> 'Michael (American male)'."""
    if len(voice_id) > 3 and voice_id[2] == "_":
        accent = ACCENTS.get(voice_id[0], voice_id[0].upper())
        sex = {"f": "female", "m": "male"}.get(voice_id[1], "")
        return f"{voice_id[3:].capitalize()} ({accent} {sex})".replace(" )", ")")
    return voice_id


def split_for_streaming(text: str, first_max: int = 55) -> list[str]:
    """Sentence chunks; the first chunk is kept short so audio starts quickly."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]
    if not parts:
        return []
    first = parts[0]
    if len(first) > first_max:
        m = re.search(r"[,;:]\s", first[20:])
        if m and len(first) - (20 + m.end()) >= 15:
            cut = 20 + m.end()
            parts = [first[:cut].strip(), first[cut:].strip(), *parts[1:]]
    merged: list[str] = []
    for part in parts:
        if merged and len(merged[-1]) < 30 and len(merged) > 1:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged


class KokoroSpeechEngine(SpeechEngine):
    name = "Kokoro neural (local)"

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        import numpy as np  # noqa: F401  (fail early if missing)
        from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices

        self._kokoro = None
        self._load_error: str | None = None
        self._loaded = threading.Event()
        threading.Thread(target=self._load, daemon=True, name="kokoro-load").start()

        fmt = QAudioFormat()
        fmt.setSampleRate(SAMPLE_RATE)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            raise RuntimeError("no audio output device")
        self._sink = QAudioSink(device, fmt, self)
        self._sink.setBufferSize(int(SAMPLE_RATE * 2 * 0.25))
        self._io = None

        self._voices: list[str] = []
        self._agent_voice: dict[str, str] = {}
        self._speed = 1.0
        self._volume = 0.85
        self._lock = threading.Lock()
        self._generation = 0
        self._agent: str | None = None
        self._pending = bytearray()
        self._chunks: list[tuple[int, int, int, int]] = []  # (start_sample, n_samples, char_start, char_len)
        self._envelope: list[float] = []
        self._queued_samples = 0
        self._synth_done = True
        self._started = False
        self._level = 0.0
        self._pump = QTimer(self)
        self._pump.setInterval(15)
        self._pump.timeout.connect(self._on_pump)

    # -- loading -----------------------------------------------------------------

    def _load(self) -> None:
        try:
            import os

            import onnxruntime as ort
            from kokoro_onnx import Kokoro

            # ONNX Runtime grabs every core by default, which is both greedy and (with
            # contention) slower. A few threads keep synthesis faster than real time.
            options = ort.SessionOptions()
            options.intra_op_num_threads = max(2, min(8, (os.cpu_count() or 4) // 3))
            options.inter_op_num_threads = 1
            session = ort.InferenceSession(str(MODEL_FILE), sess_options=options,
                                           providers=["CPUExecutionProvider"])
            self._kokoro = Kokoro.from_session(session, str(VOICES_FILE))
            self._voices = sorted(v for v in self._kokoro.get_voices() if v[:1] in ("a", "b"))
        except Exception as exc:  # corrupt model, missing espeak, …
            self._load_error = str(exc)
        finally:
            self._loaded.set()

    def wait_until_loaded(self, timeout: float = 30.0) -> bool:
        return self._loaded.wait(timeout) and self._kokoro is not None

    # -- interface -------------------------------------------------------------------

    def available(self) -> bool:
        return self._load_error is None and models_present()

    def available_voices(self) -> list[str]:
        if self._voices:
            return list(self._voices)
        return sorted({*DEFAULT_VOICES.values(), "am_puck", "am_fenrir", "bm_george", "bm_fable", "af_bella",
                       "af_nicole", "bf_emma"})

    def voice_label(self, voice: str) -> str:
        return voice_label(voice)

    def default_voices(self) -> dict[str, str]:
        return dict(DEFAULT_VOICES)

    def set_voice(self, agent: str, voice: str) -> None:
        if voice:
            self._agent_voice[agent] = voice

    def voice_for(self, agent: str) -> str:
        voice = self._agent_voice.get(agent) or DEFAULT_VOICES.get(agent, "af_heart")
        return voice if (not self._voices or voice in self._voices) else DEFAULT_VOICES.get(agent, self._voices[0])

    def set_rate(self, rate: float) -> None:
        self._speed = max(0.6, min(1.6, 1.0 + rate * 0.6))

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, volume))
        self._sink.setVolume(self._volume)

    def level(self) -> float:
        return self._level

    def is_speaking(self) -> bool:
        return self._agent is not None

    def speak(self, agent: str, text: str) -> bool:
        if not text.strip() or not self.available():
            return False
        self.stop()
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._agent = agent
            self._pending.clear()
            self._chunks.clear()
            self._envelope.clear()
            self._queued_samples = 0
            self._synth_done = False
            self._started = False
        self._sink.setVolume(self._volume)
        self._io = self._sink.start()
        threading.Thread(target=self._synthesise, args=(generation, text, self.voice_for(agent), self._speed),
                         daemon=True, name="kokoro-say").start()
        self._pump.start()
        return True

    def stop(self) -> None:
        agent = self._agent
        with self._lock:
            self._generation += 1
            self._agent = None
            self._pending.clear()
            self._synth_done = True
        self._pump.stop()
        self._sink.stop()
        self._level = 0.0
        if agent:
            self.finished.emit(agent)

    # -- worker ------------------------------------------------------------------------

    def _synthesise(self, generation: int, text: str, voice: str, speed: float) -> None:
        import numpy as np

        if not self.wait_until_loaded():
            with self._lock:
                if generation == self._generation:
                    self._synth_done = True
            return
        char_pos = 0
        for chunk in split_for_streaming(text):
            if generation != self._generation:
                return
            try:
                samples, _sr = self._kokoro.create(chunk, voice=voice, speed=speed, lang="en-us")
            except Exception:
                char_pos += len(chunk) + 1
                continue
            samples = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
            pause = np.zeros(int(SAMPLE_RATE * 0.12), dtype=np.float32)
            samples = np.concatenate([samples, pause])
            pcm = (samples * 32767).astype(np.int16).tobytes()
            frames = len(samples) // ENVELOPE_HOP
            rms = np.sqrt(np.mean(samples[: frames * ENVELOPE_HOP].reshape(frames, ENVELOPE_HOP) ** 2, axis=1)) \
                if frames else np.zeros(0)
            with self._lock:
                if generation != self._generation:
                    return
                self._chunks.append((self._queued_samples, len(samples), char_pos, len(chunk)))
                self._queued_samples += len(samples)
                self._pending.extend(pcm)
                self._envelope.extend(float(v) for v in rms)
            char_pos += len(chunk) + 1
        with self._lock:
            if generation == self._generation:
                self._synth_done = True

    # -- main-thread pump ----------------------------------------------------------------

    def _on_pump(self) -> None:
        agent = self._agent
        if agent is None or self._io is None:
            self._pump.stop()
            return
        with self._lock:
            free = self._sink.bytesFree()
            if free > 0 and self._pending:
                n = min(free, len(self._pending)) & ~1
                self._io.write(bytes(self._pending[:n]))
                del self._pending[:n]
                if not self._started:
                    self._started = True
                    started = True
                else:
                    started = False
            else:
                started = False
            done = self._synth_done and not self._pending
            total = self._queued_samples
            chunks = list(self._chunks)
            envelope = self._envelope
            played = int(self._sink.processedUSecs() * SAMPLE_RATE / 1_000_000) if self._started else 0
            frame = played // ENVELOPE_HOP
            level = envelope[frame] if 0 <= frame < len(envelope) else 0.0
        if started:
            self.started.emit(agent)
        # loudness → 0..1 for the mouth (speech RMS is typically 0.02–0.25)
        self._level = min(1.0, (level / 0.16) ** 0.8) if level > 0.004 else 0.0
        chars = 0
        for start, n, char_start, char_len in chunks:
            if played >= start + n:
                chars = char_start + char_len
            elif played > start:
                chars = char_start + int(char_len * (played - start) / max(1, n))
                break
        if chars:
            self.progress.emit(agent, chars)
        if done and played >= total - SAMPLE_RATE // 50:
            self._pump.stop()
            self._agent = None
            self._level = 0.0
            self._sink.stop()
            self.finished.emit(agent)


def download_models(progress=print) -> bool:
    """Fetch the Kokoro model files (~340 MB) into config/cache/tts."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for path, url in MODEL_URLS.items():
        if path.exists():
            continue
        tmp = path.with_suffix(path.suffix + ".part")
        progress(f"Downloading {path.name} …")
        started = time.time()
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(path)
        progress(f"  done in {time.time() - started:.0f}s")
    return models_present()


if __name__ == "__main__":
    import sys

    if "--download" in sys.argv:
        ok = download_models()
        print("Kokoro voices ready." if ok else "Download failed.")
    else:
        print(__doc__)
