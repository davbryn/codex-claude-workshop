"""Optional local text-to-speech, isolated behind a tiny interface.

Uses Qt's QTextToSpeech (WinRT/SAPI voices on Windows; no cloud account).
If it is unavailable, NullSpeechEngine keeps the app fully working and the
stage falls back to timer-driven talking animations.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal

# Gilfoyle lower and flatter/slower; Dinesh higher and quicker.
AGENT_PITCH = {"Codex": -0.3, "Claude": 0.12}
AGENT_RATE = {"Codex": -0.12, "Claude": 0.12}
PREFERRED_ENGINES = ("winrt", "sapi", "flite", "speechd", "darwin", "macos", "android")


def audio_disabled() -> bool:
    return os.environ.get("WORKSHOP_NO_AUDIO", "") not in ("", "0")


class SpeechEngine(QObject):
    """Interface. ``started``/``finished`` carry the agent name; ``progress``
    carries (agent, characters spoken so far)."""

    started = Signal(str)
    finished = Signal(str)
    progress = Signal(str, int)

    name = "none"

    def available(self) -> bool:
        return False

    def available_voices(self) -> list[str]:
        return []

    def set_voice(self, agent: str, voice: str) -> None:
        pass

    def voice_for(self, agent: str) -> str:
        return ""

    def set_rate(self, rate: float) -> None:
        pass

    def set_volume(self, volume: float) -> None:
        pass

    def speak(self, agent: str, text: str) -> bool:
        """Start speaking; returns False if nothing will be spoken."""
        return False

    def stop(self) -> None:
        pass

    def is_speaking(self) -> bool:
        return False

    def level(self) -> float | None:
        """Live loudness 0..1 of the current speech, or None if the engine can't tell."""
        return None

    def voice_label(self, voice: str) -> str:
        return voice

    def default_voices(self) -> dict[str, str]:
        return {}


class NullSpeechEngine(SpeechEngine):
    name = "silent"


class QtSpeechEngine(SpeechEngine):
    def __init__(self, engine_name: str, parent: QObject | None = None):
        # engine_name is the Qt plugin (winrt/sapi); shown as "Windows voices (winrt)"
        super().__init__(parent)
        from PySide6.QtTextToSpeech import QTextToSpeech

        self._QTextToSpeech = QTextToSpeech
        self.name = f"System voices ({engine_name})"
        self.tts = QTextToSpeech(engine_name, self)
        self._voices = {}
        self._agent_voice: dict[str, str] = {}
        self._current: str | None = None
        self.tts.stateChanged.connect(self._on_state)
        if hasattr(self.tts, "sayingWord"):
            self.tts.sayingWord.connect(self._on_word)
        self._refresh_voices()

    def _refresh_voices(self) -> None:
        self._voices = {v.name(): v for v in self.tts.availableVoices()}

    def available(self) -> bool:
        state = self.tts.state()
        return state != self._QTextToSpeech.State.Error and bool(self._voices or self.tts.availableVoices())

    def available_voices(self) -> list[str]:
        if not self._voices:
            self._refresh_voices()
        return list(self._voices)

    def default_voices(self) -> dict[str, str]:
        """Pick two different voices where possible (a lower one for Codex)."""
        names = self.available_voices()
        if not names:
            return {}
        male = [n for n in names if self._voices[n].gender().name == "Male"]
        female = [n for n in names if self._voices[n].gender().name == "Female"]
        codex = (male or names)[0]
        # Dinesh: a second male voice if there is one (contrast comes from pitch/rate), else anything else
        claude = next((n for n in (male[1:] + female + names) if n != codex), codex)
        return {"Codex": codex, "Claude": claude}

    def set_voice(self, agent: str, voice: str) -> None:
        if voice:
            self._agent_voice[agent] = voice

    def voice_for(self, agent: str) -> str:
        return self._agent_voice.get(agent) or self.default_voices().get(agent, "")

    def set_rate(self, rate: float) -> None:
        self._rate = rate
        self.tts.setRate(max(-1.0, min(1.0, rate)))

    def set_volume(self, volume: float) -> None:
        self.tts.setVolume(max(0.0, min(1.0, volume)))

    def speak(self, agent: str, text: str) -> bool:
        if not text.strip() or not self.available():
            return False
        if self.is_speaking():
            previous, self._current = self._current, None
            self.tts.stop()
            if previous:
                self.finished.emit(previous)
        voice = self._voices.get(self.voice_for(agent))
        if voice is not None:
            self.tts.setVoice(voice)
        self.tts.setPitch(AGENT_PITCH.get(agent, 0.0))
        self.tts.setRate(max(-1.0, min(1.0, getattr(self, "_rate", 0.0) + AGENT_RATE.get(agent, 0.0))))
        self._current = agent
        self.tts.say(text)
        return True

    def stop(self) -> None:
        self.tts.stop()

    def is_speaking(self) -> bool:
        return self.tts.state() == self._QTextToSpeech.State.Speaking

    def _on_state(self, state) -> None:
        S = self._QTextToSpeech.State
        if state == S.Speaking and self._current:
            self.started.emit(self._current)
        elif state in (S.Ready, S.Error) and self._current:
            agent, self._current = self._current, None
            self.finished.emit(agent)

    def _on_word(self, word: str, _id: int, start: int, length: int) -> None:
        if self._current:
            self.progress.emit(self._current, start + length)


def create_speech_engine(parent: QObject | None = None, preference: str = "auto") -> SpeechEngine:
    """Best available local engine, or a silent fallback. Never raises.

    preference: "auto" (neural if installed, else system voices), "neural" or "system".
    """
    if audio_disabled():
        return NullSpeechEngine(parent)
    if preference in ("auto", "neural"):
        try:
            from .neural_tts import KokoroSpeechEngine, models_present

            if models_present():
                import kokoro_onnx  # noqa: F401

                return KokoroSpeechEngine(parent)
        except Exception:
            pass  # not installed / no audio device: fall back to system voices
    try:
        from PySide6.QtTextToSpeech import QTextToSpeech

        engines = QTextToSpeech.availableEngines()
        for name in PREFERRED_ENGINES:
            if name in engines:
                engine = QtSpeechEngine(name, parent)
                if engine.tts.state() != QTextToSpeech.State.Error:
                    return engine
        others = [e for e in engines if e != "mock"]
        if others:
            return QtSpeechEngine(others[0], parent)
    except Exception:  # missing plugin, no audio stack, … – speech is optional
        pass
    return NullSpeechEngine(parent)
