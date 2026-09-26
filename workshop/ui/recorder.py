"""Record the workshop window (with its own audio) to an MP4 — handy for reviewing the demo on a phone.

Video: the window is grabbed on a timer and piped to ffmpeg as raw frames;
frames are duplicated or skipped against the wall clock so the video stays in
real time even if a grab is slow.

Audio: rather than recording the speakers, we rebuild the soundtrack from what
the app itself plays — the Kokoro voice PCM (via the engine's ``tap``) and the
sound effects (their WAV files, placed at the moment they were triggered).
System (Windows) voices can't be tapped, so with them the video has effects only.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QTimer
from PySide6.QtGui import QImage

AUDIO_RATE = 24000


def find_ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


class Recorder(QObject):
    def __init__(self, window, output: Path, fps: int = 20, size: QSize = QSize(1280, 800), parent=None):
        super().__init__(parent or window)
        self.window = window
        self.output = Path(output).resolve()
        self.fps = fps
        self.size = size
        self.ffmpeg = find_ffmpeg()
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg not found (install it, or `pip install imageio-ffmpeg`)")
        self.tmp = Path(tempfile.mkdtemp(prefix="workshop-rec-"))
        self.video_path = self.tmp / "video.mp4"
        self.start = time.monotonic()
        self.frames = 0
        self.voice: list[tuple[float, bytes, int, float]] = []  # (t, pcm16, rate, volume)
        self._voice_end = 0.0
        self.effects: list[tuple[float, str, float]] = []  # (t, name, volume)
        self.finished = False
        self.proc = subprocess.Popen(
            [self.ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
             "-s", f"{size.width()}x{size.height()}", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", str(self.video_path)],
            stdin=subprocess.PIPE)
        self._hook_audio()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._frame)
        self.timer.start(int(1000 / fps))

    # -- audio taps ---------------------------------------------------------------

    def _now(self) -> float:
        return time.monotonic() - self.start

    def _hook_audio(self) -> None:
        sfx = self.window.sfx
        original = sfx.play

        def play(name: str) -> None:
            if sfx.enabled:
                resolved = name
                original(name)
                self.effects.append((self._now(), resolved, sfx.volume))
            else:
                original(name)

        sfx.play = play
        self.hook_speech(self.window.speech)

    def hook_speech(self, speech) -> None:
        if hasattr(speech, "tap"):
            speech.tap = self._on_voice

    def _on_voice(self, pcm: bytes, rate: int, volume: float) -> None:
        # the sink plays blocks back to back; a block written after a gap starts "now"
        t = max(self._now(), self._voice_end)
        self.voice.append((t, pcm, rate, volume))
        self._voice_end = t + len(pcm) / 2 / rate

    # -- video ----------------------------------------------------------------------

    def _frame(self) -> None:
        if self.finished or self.proc.stdin is None:
            return
        due = int(self._now() * self.fps) + 1
        if due <= self.frames:
            return
        image = self.window.grab().toImage().scaled(self.size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                   Qt.TransformationMode.SmoothTransformation)
        image = image.convertToFormat(QImage.Format.Format_ARGB32)
        data = bytes(image.constBits())[: self.size.width() * self.size.height() * 4]
        try:
            while self.frames < due:  # catch up if a grab was slow
                self.proc.stdin.write(data)
                self.frames += 1
        except (BrokenPipeError, OSError):
            self.finished = True

    # -- finishing ---------------------------------------------------------------------

    def finish(self) -> Path | None:
        if self.finished and not self.proc:
            return None
        self.finished = True
        self.timer.stop()
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        self.proc.wait(timeout=120)
        audio = self.tmp / "audio.wav"
        self._write_audio(audio, self.frames / self.fps)
        subprocess.run([self.ffmpeg, "-y", "-loglevel", "error", "-i", str(self.video_path), "-i", str(audio),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
                        str(self.output)], check=True)
        return self.output

    def _write_audio(self, path: Path, duration: float) -> None:
        import numpy as np

        from ..theatre.sfx import CACHE_DIR

        n = int(duration * AUDIO_RATE) + AUDIO_RATE
        mix = np.zeros(n, dtype=np.float32)

        def place(t: float, samples: np.ndarray, rate: int, gain: float) -> None:
            if rate != AUDIO_RATE and len(samples) > 1:
                x = np.linspace(0, len(samples) - 1, int(len(samples) * AUDIO_RATE / rate))
                samples = np.interp(x, np.arange(len(samples)), samples).astype(np.float32)
            start = int(t * AUDIO_RATE)
            end = min(n, start + len(samples))
            if end > start:
                mix[start:end] += samples[: end - start] * gain

        for t, pcm, rate, volume in self.voice:
            place(t, np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768, rate, volume)
        cache: dict[str, tuple[np.ndarray, int]] = {}
        for t, name, volume in self.effects:
            if name == "keys":
                name = f"keys{1 + int(t * 7) % 3}"
            if name not in cache:
                try:
                    with wave.open(str(CACHE_DIR / f"{name}.wav"), "rb") as w:
                        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
                        cache[name] = (data, w.getframerate())
                except (FileNotFoundError, wave.Error):
                    continue
            data, rate = cache[name]
            place(t, data, rate, volume)
        peak = float(np.max(np.abs(mix))) if len(mix) else 0.0
        if peak > 0.98:
            mix *= 0.98 / peak
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(AUDIO_RATE)
            w.writeframes((mix * 32767).astype(np.int16).tobytes())
