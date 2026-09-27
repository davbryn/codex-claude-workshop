"""Render an episode plan to video, offline, on a virtual clock.

The same StageWidget the live app uses paints every frame, but time is ours:
each frame advances the clock by exactly 1/fps, so there are no pauses, no
dropped frames and no waiting on the agents. Lines are synthesised up front and
placed on the soundtrack exactly where the mouths move.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPen

from ..conversation import AGENTS
from ..kanban import parse as parse_board
from ..theatre.cast import ACCENT, CHARACTER, MOMENTS, status_label
from ..theatre.neural_tts import SAMPLE_RATE
from ..theatre.screens import FileChange, ScreenFeed
from ..theatre.sfx import CACHE_DIR, ensure_effects
from ..theatre.text import clean_for_speech
from ..ui.recorder import find_ffmpeg
from .capture import other_of
from .overlays import exhibit_lines, paint_exhibit, paint_subtitle
from .wheel_paint import paint_big_card, paint_hud, paint_violation, paint_wheel, wheel_angle, wheel_title
from .voice import Voices

MOMENT_SFX = {"dinesh_catches": "yes", "gilfoyle_catches": "blast", "concession": "wahwah", "own_goal": "wahwah",
              "disagreement": "zap", "both_wrong": "oops", "character_development": "chime", "same_solution": "oops"}
TYPE_RATE = 22.0  # diff lines per second (matches the live monitors)


class EpisodeRenderer:
    def __init__(self, plan: dict, events: list[dict], settings=None, fps: int = 25,
                 size: tuple[int, int] = (1280, 720), scale: float = 1.5, progress=print, vertical: bool = False):
        from ..ui.stage import StageWidget

        self.plan = plan
        self.events = {e["id"]: e for e in events}
        self.all_events = events
        self.fps = fps
        self.size = size
        self.scale = scale
        self.out_w, self.out_h = int(size[0] * scale), int(size[1] * scale)
        self.vertical = vertical  # a 1080x1920 Shorts frame around the 16:9 picture
        self.pipe_w, self.pipe_h = (1080, 1920) if vertical else (self.out_w, self.out_h)
        self.saying: tuple[str, str, float] | None = None  # (agent, text, until) for the Shorts captions
        self.progress = progress
        self.sfx_volume = getattr(settings, "sfx_volume", 0.8) if settings is not None else 0.8
        self.voices = Voices(settings, progress)
        self.t = 0.0
        self.frames = 0
        self.audio: list[tuple[float, np.ndarray, float]] = []  # (t, samples@SAMPLE_RATE, gain)
        self.chapters: list[tuple[float, str]] = []
        self.thumbnail: QImage | None = None
        self._thumb_score = -1
        self.overlay = None  # callable(painter, t) drawn over the stage (title cards, lower thirds)
        self.cam: tuple | None = None  # (agent, zoom, since, push): a close-up on his face; None = the room
        self.subtitle: tuple[str, str] | None = None  # (agent, text) shown on close-ups
        self.hud: dict | None = None  # the challenge status bar, once the rules are in
        self.music_spans: list[list[float]] = []  # [start, end] of the music bed
        self.speech_spans: list[tuple[float, float]] = []
        self._speech = None  # (agent, start, duration, envelope, text_len)
        self._typing_until = 0.0
        self._next_key = 0.0
        ensure_effects()

        stage = StageWidget()
        stage.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        stage.resize(*size)
        stage.stop()
        stage.now = lambda: self.t  # the virtual clock
        stage.wake = stage.update  # nothing runs on real timers here
        stage._last = 0.0
        stage.level_source = self._level
        stage.show_on_air = False
        stage.screens = {a: ScreenFeed(a) for a in AGENTS}
        for a in AGENTS:
            stage.set_status(a, "WAITING", status_label(a, "waiting"))
        self.stage = stage
        self.feeds = stage.screens
        self._rng = __import__("random").Random(11)
        for feed in self.feeds.values():
            feed.go_idle(self._rng)

    # -- the clock ---------------------------------------------------------------------------

    def advance(self, seconds: float) -> None:
        for _ in range(max(0, int(round(seconds * self.fps)))):
            self.t += 1.0 / self.fps
            self._frame_hooks()
            self.stage._tick()
            self._write_frame()

    def _frame_hooks(self) -> None:
        if self._speech:
            agent, start, duration, env, length = self._speech
            m = self.stage.models[agent]
            if self.t >= start + duration:
                m.set_talking(False)
                self.stage.finish_speech_reveal(agent)
                self._speech = None
            elif self.t >= start:
                if not m.talking:
                    m.set_talking(True)
                self.stage.speech_progress(agent, max(1, int(length * (self.t - start) / max(0.1, duration - 0.15))))
        if self.t < getattr(self, "_fast_until", 0.0):
            for feed in self.feeds.values():
                if feed.mode == "editor" and feed.revealed < len(feed.lines):
                    feed.revealed = min(float(len(feed.lines)), feed.revealed + 1.5 * TYPE_RATE / self.fps)
        if self.t < self._typing_until and self.t >= self._next_key:
            self.sfx("keys", 0.35)
            self._next_key = self.t + 0.13 + 0.12 * self._rng.random()

    def _level(self, agent: str) -> float | None:
        if not self._speech or self._speech[0] != agent:
            return 0.0
        _, start, _, env, _ = self._speech
        i = int((self.t - start) * 100)
        return float(env[i]) if 0 <= i < len(env) else 0.0

    def _compose(self, bubbles: bool = True) -> QImage:
        image = QImage(self.out_w, self.out_h, QImage.Format.Format_ARGB32)
        image.setDevicePixelRatio(self.scale)
        image.fill(QColor("#07080a"))
        p = QPainter(image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        saved = []
        if not bubbles or self.cam is not None:  # close-ups use subtitles, not bubbles
            saved = [(b, b.kind) for b in self.stage.bubbles.values()]
            for b, _ in saved:
                b.kind = "none"
        if self.cam is not None:
            agent, zoom, since, push = self.cam
            zoom *= 1.0 + push * min(1.0, (self.t - since) / 4.0)  # a slow documentary push-in
            head = self.stage._head_anchor(agent, self.stage._layout())
            w, h = self.size
            p.translate(w / 2, h * 0.36)
            p.scale(zoom, zoom)
            p.translate(-head.x(), -head.y())
        if self.cam is not None:  # a face close-up: no room nameplates bleeding in at the edges
            self.stage._paint_nameplate = lambda *a: None
        self.stage.render(p, QPoint(0, 0))
        self.stage.__dict__.pop("_paint_nameplate", None)
        p.resetTransform()
        for b, kind in saved:
            b.kind = kind
        if self.subtitle is not None and self.cam is not None and not self.vertical:
            paint_subtitle(p, self.size, *self.subtitle)  # (Shorts caption every line underneath instead)
        if self.hud is not None:
            paint_hud(p, self.size, self.hud)
        if self.overlay is not None:
            self.overlay(p, self.t)
        p.end()
        return image

    def _write_frame(self) -> None:
        image = self._compose()
        self._last_image = image
        if self.vertical:
            image = self._verticalize(image)
        self._pipe.stdin.write(bytes(image.constBits())[: self.pipe_w * self.pipe_h * 4])
        self.frames += 1

    def _verticalize(self, frame: QImage) -> QImage:
        from .shorts import paint_short_frame

        canvas = QImage(self.pipe_w, self.pipe_h, QImage.Format.Format_ARGB32)
        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        saying = self.saying if self.saying and self.t <= self.saying[2] else None
        wheel = getattr(self, "_wheel_now", None) if self.overlay is not None else None
        paint_short_frame(p, (self.pipe_w, self.pipe_h), frame, self.plan, saying, wheel)
        p.end()
        return canvas

    # -- sound ----------------------------------------------------------------------------------

    def sfx(self, name: str, gain: float = 1.0) -> None:
        if name == "keys":
            name = f"keys{self._rng.randint(1, 3)}"
        data = _load_wav(CACHE_DIR / f"{name}.wav")
        if data is not None:
            self.audio.append((self.t, data, self.sfx_volume * gain))

    def speak(self, agent: str, text: str, delay: float = 0.0, bubble: bool = True, mood: str | None = None,
              to_camera: bool = False) -> float:
        """Queue a line; returns its duration. The bubble shows ``text``; the voice says a cleaned version."""
        spoken = clean_for_speech(text)
        if shouted(spoken):  # CAPS on screen, but the voice shouldn't spell it out letter by letter
            spoken = re.sub(r"\b[A-Z]{2,}(?:'[A-Z]+)?\b", lambda m: m.group(0).capitalize(), spoken)
            mood = mood if mood in ("outraged", "disagreeing", "annoyed") else "outraged"
        samples, env = self.voices.say(agent, spoken, mood=mood, to_camera=to_camera)
        duration = max(len(samples) / SAMPLE_RATE, len(env) / 100.0, 0.8)
        start = self.t + delay
        if self.voices.available:
            self.audio.append((start, samples, 0.9))
        self.speech_spans.append((start, start + duration))
        self._speech = (agent, start, duration, env, len(text))
        self.saying = (agent, text, start + duration + 0.3)
        if bubble:
            self.stage.show_speech(agent, text, mode="speech")
        return duration + delay

    # -- scenes ---------------------------------------------------------------------------------

    def render(self, video_path: Path) -> Path:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("ffmpeg not found (install it, or `pip install imageio-ffmpeg`)")
        tmp = Path(tempfile.mkdtemp(prefix="workshop-episode-"))
        silent = tmp / "video.mp4"
        self._pipe = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgra",
             "-s", f"{self.pipe_w}x{self.pipe_h}", "-r", str(self.fps), "-i", "-",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", str(silent)],
            stdin=subprocess.PIPE)
        scenes = self.plan["scenes"]
        try:
            for i, scene in enumerate(scenes):
                if scene.get("chapter"):
                    self.chapters.append((self.t, scene["chapter"]))
                getattr(self, f"_scene_{scene['kind']}")(scene)
                if i % 5 == 0:
                    self.progress(f"  rendered {i + 1}/{len(scenes)} scenes ({self.t / 60:.1f} min of video)")
        finally:
            self._pipe.stdin.close()
            self._pipe.wait()
        audio = tmp / "audio.wav"
        self._write_audio(audio)
        video_path = Path(video_path)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest",
                        "-movflags", "+faststart", str(video_path)], check=True)
        return video_path

    def _clear_bubbles(self) -> None:
        for b in self.stage.bubbles.values():
            b.kind, b.text = "none", ""

    def _to_room(self) -> None:
        if self.stage.shot_agent is not None:
            self.stage.set_shot(None)
            self.stage.set_caption(None, "")
            self.advance(0.6)

    def _scene_title(self, scene: dict) -> None:
        title, subtitle = scene["title"], scene.get("subtitle", "")
        disclaimer = self.plan.get("disclaimer", "")
        start = self.t
        self.overlay = lambda p, t: _paint_title(p, self.size, t - start, title, subtitle, disclaimer)
        self.sfx("fanfare", 0.7)
        self.advance(5.5)
        self.overlay = None

    def _scene_card(self, scene: dict) -> None:
        self._to_room()
        self._clear_bubbles()
        duration = max(3.2, min(7.0, 2.2 + sum(len(x) for x in scene.get("lines", [])) / 45))
        self.stage.show_card("human", scene["title"], scene.get("lines", []), scene.get("color", "#7bd88f"),
                             duration=duration)
        self.sfx("human")
        for agent in AGENTS:
            m = self.stage.models[agent]
            m.look_at_human(duration)
            m.react("stare" if m.deadpan else "worried", duration * 0.8)
        self.advance(duration + 0.6)

    def _board_at(self, event_id: int):
        """The board as it was at ``event_id`` (the latest board event at or before it)."""
        text = None
        for e in self.all_events:
            if e["id"] > event_id:
                break
            if e["kind"] == "board":
                text = e["text"]
        return parse_board(text) if text else None

    def _working(self, agent: str, key: str = "coding") -> None:
        other = other_of(agent)
        self.stage.set_active(agent)
        self.stage.set_status(agent, "WORKING", status_label(agent, key))
        self.stage.set_status(other, "WAITING", status_label(other, "waiting"))

    def _scene_screen(self, scene: dict) -> None:
        agent = scene["agent"]
        other = other_of(agent)
        show = scene["show"]
        evs = [self.events[i] for i in show.get("events", []) if i in self.events]
        if not evs:
            return
        self._clear_bubbles()
        board = self._board_at(evs[-1]["id"])
        if board is not None:
            self.stage.set_board(board, tuple(evs[-1].get("moved", ())) if show["type"] == "board" else ())
        feed = self.feeds[agent]
        seconds = 4.5
        if show["type"] == "diff":
            e = evs[0]
            self._working(agent, "coding")
            feed.show_diff(FileChange(e["path"], [tuple(x) for x in e["lines"]], e.get("created", False),
                                      e.get("deleted", False)))
            fast = scene.get("fast")
            typing = min(2.6 if fast else 9.0, len(e["lines"]) / (TYPE_RATE * (2.5 if fast else 1)))
            if fast:
                self._fast_until = self.t + 0.6 + typing  # the monitor types at montage speed
            self._typing_until = self.t + 0.6 + typing
            seconds = max(3.0 if fast else seconds, typing + (1.2 if fast else 2.4))
        elif show["type"] == "board":
            self._working(agent, "planning")
            if board is not None:
                feed.show_board(board, tuple(evs[-1].get("moved", ())))
            seconds = 4.0
        elif show["type"] == "terminal":
            self._working(agent, "testing")
        mw = scene.get("meanwhile")
        if mw in self.events:
            bit = dict(self.events[mw]["bit"], _t0=self.t)
            self.feeds[other].show_bit(bit)
        elif self.feeds[other].mode != "idle":
            self.feeds[other].go_idle(self._rng)
        self.stage.set_shot(agent)
        self.advance(0.7)
        aside = scene.get("aside")
        if aside and aside.get("text"):
            who = aside.get("speaker", agent)
            self.stage.set_caption(who, aside["text"])
            seconds = max(seconds, self.speak(who, aside["text"], delay=0.2, bubble=False) + 1.0)
        if show["type"] == "terminal":
            self._play_terminal(agent, evs)
            seconds = 1.5
        self.advance(seconds)
        self.stage.set_caption(None, "")
        self._typing_until = 0.0

    def _play_terminal(self, agent: str, evs: list[dict]) -> None:
        feed = self.feeds[agent]
        other = other_of(agent)
        for e in evs:
            if e["kind"] == "command":
                feed.command(e["command"])
                self._typing_until = self.t + 0.5
                self.advance(1.1)
            elif e["kind"] in ("tests", "error_output"):
                if feed.mode != "terminal":
                    feed.command("pytest")
                related = [x for x in self.all_events if x["kind"] == "error_output" and x.get("agent") == agent
                           and e["id"] - 12 < x["id"] < e["id"]][-6:]
                for x in related:
                    feed.output(x["line"])
                    self.advance(0.25)
                feed.output(e["line"])
                if e["kind"] == "tests" and not e.get("ok"):
                    self.sfx("buzz")
                    self.stage.badge(f"❌ {e.get('failed') or 'SOME'} FAILED", agent, "#ff6b5b", 2.8)
                    om = self.stage.models[other]
                    om.react("smug" if om.deadpan else "gloating", 3.0)
                    self.stage.models[agent].react("disturbed" if self.stage.models[agent].deadpan else "worried", 3.0)
                self.advance(2.4)

    def _scene_cutaway(self, scene: dict) -> None:
        agent = scene["agent"]
        e = self.events.get(scene.get("event"))
        if not e:
            return
        self._clear_bubbles()
        bit = dict(e["bit"], _t0=self.t)
        self.feeds[agent].show_bit(bit)
        worker = other_of(agent)
        if self.feeds[worker].mode == "idle":
            self.feeds[worker].go_idle(self._rng)
        self.stage.set_shot(agent)
        self.advance(1.4)
        seconds = 3.5
        text = scene.get("text") or bit.get("line", "")
        if text:
            self.stage.set_caption(agent, text)
            seconds = max(seconds, self.speak(agent, text, bubble=False) + 1.2)
        self.advance(seconds)
        self.stage.set_caption(None, "")

    def _scene_line(self, scene: dict) -> None:
        speaker = scene["speaker"]
        listener = other_of(speaker)
        self._to_room()
        self.stage.set_active(speaker)
        self.stage.set_status(speaker, "WORKING", status_label(speaker, "speaking"))
        self.stage.set_status(listener, "WAITING", status_label(listener, "waiting"))
        self._clear_bubbles()
        sm, lm = self.stage.models[speaker], self.stage.models[listener]
        sm.look_at_other(3.0)
        if scene.get("speaker_state"):
            sm.react(scene["speaker_state"], 3.5)
        moment = scene.get("moment")
        if moment in MOMENTS:
            text, colour = MOMENTS[moment]
            self.stage.badge(text, "center", colour, 3.4)
            if MOMENT_SFX.get(moment):
                self.sfx(MOMENT_SFX[moment])
            if moment == "disagreement":
                self.stage.lightning(1.4)
                self.stage.shake(4)
        duration = self.speak(speaker, scene["text"], delay=0.45)
        self.advance(min(duration, 1.3))
        self._consider_thumbnail(moment)
        self.advance(max(0.0, duration - 1.3) + 0.2)
        if scene.get("listener"):
            lm.look_at_other(2.0)
            lm.react(scene["listener"], 2.2)
            self.advance(1.1)
        if scene.get("handoff"):
            self.stage.handoff(speaker, scene["handoff"])
            self.sfx("handoff", 0.8)
            self.advance(0.8)
        self.stage.set_status(speaker, "WAITING", status_label(speaker, "waiting"))

    def _scene_finale(self, scene: dict) -> None:
        self._to_room()
        self._clear_bubbles()
        st = self.stage
        gil, din = st.models["Codex"], st.models["Claude"]
        for a in AGENTS:
            st.models[a].set_base("complete")
            st.set_status(a, "COMPLETE", status_label(a, "complete"))
        st.set_active(None)
        din.react("celebrating", 3.0)
        din.look_at_other(6.0)
        st.confetti(110, only="Claude")
        st.burst("Claude", 22)
        gil.react("pleased", 3.0)
        self.sfx("yes")
        st.show_card("complete", "PROJECT COMPLETE", scene.get("lines", []), "#f2c94c",
                     tagline=scene.get("tagline", "Somehow."))
        if scene.get("short"):
            self.sfx("fanfare")
            self.advance(3.2)
            din.react("highfive", 1.6)
            gil.react("smug", 1.6)
            self.advance(1.4)
            return
        self.advance(0.5)
        self.sfx("fanfare")
        self.advance(2.5)
        din.react("highfive", 2.6)
        self.advance(1.3)
        gil.look_at_other(2.0, speed=1.4)
        gil.react("highfive", 1.6)
        self.advance(1.9)
        gil.react("smug", 3.0)
        self.advance(4.5)
        start = self.t
        self.overlay = lambda p, t: _paint_fade(p, self.size, min(1.0, (t - start) / 1.5))
        self.advance(1.8)
        self.overlay = None

    # -- thumbnail --------------------------------------------------------------------------------

    # -- written scenes -------------------------------------------------------------------------

    def _cut(self, agent: str | None, zoom: float = 2.5, push: float = 0.06) -> None:
        """A hard cut: to his face (agent) or back to the room (None)."""
        if self.stage.shot_agent is not None:
            self.stage.set_shot(None)
            self.stage.shot_blend = 0.0
            self.stage.set_caption(None, "")
        self.cam = (agent, zoom, self.t, push) if agent else None

    def _cut_to_screen(self, agent: str) -> None:
        self.cam = None
        self.stage.set_shot(agent)
        self.stage.shot_blend = 1.0  # hard cut, no push-in

    def _scene_sketch(self, scene: dict) -> None:
        self._clear_bubbles()
        self._cut(None)
        shots = scene.get("shots", [])
        for i, shot in enumerate(shots):
            nxt = shots[i + 1] if i + 1 < len(shots) else {}
            if "say" in shot:
                self._shot_say(shot, nxt)
            elif "react" in shot:
                who = shot["react"]
                self._cut(who, 2.4, 0.08)
                m = self.stage.models[who]
                m.look_at_other(shot["seconds"] + 0.4, speed=1.6 if m.deadpan else None)
                m.react(shot.get("mood") or "stare", shot["seconds"] + 0.6)
                self.advance(min(0.5, shot["seconds"]))
                self._consider_thumbnail("react", shot.get("mood"))
                self.advance(max(0.0, shot["seconds"] - 0.5))
            elif "beat" in shot:
                self._cut(None)
                self._clear_bubbles()
                for a in AGENTS:
                    self.stage.models[a].look_at_other(shot["beat"] + 0.3, speed=1.5)
                self.advance(shot["beat"])
            elif "show" in shot:
                self._shot_show(shot)
            elif "meanwhile" in shot:
                self._shot_meanwhile(shot["meanwhile"])
            elif "sting" in shot:
                self.sfx(shot["sting"])
            elif "caption" in shot:
                self.stage.badge(shot["caption"], "center", "#f2c94c", 2.6)
                self.advance(0.2)
        self._cut(None)
        self._clear_bubbles()
        self.advance(0.35)

    def _shot_say(self, shot: dict, nxt: dict) -> None:
        who = shot["say"]
        other = other_of(who)
        m = self.stage.models[who]
        self._clear_bubbles()
        self.stage.set_active(who)
        if shot.get("to") == "camera":
            self._cut(who, 2.0, 0.05)
            m.look(0.0, 0.0, 30.0)  # straight down the lens
        elif shot.get("frame") == "close":
            self._cut(who, 2.2, 0.05)
            m.look_at_other(30.0)
        else:
            self._cut(None)
            m.look_at_other(30.0)
            self.stage.models[other].look_at_other(4.0)
        if shot.get("mood"):
            m.react(shot["mood"], 30.0)
        self.subtitle = (who, shot["line"])
        duration = self.speak(who, shot["line"], delay=0.08, bubble=self.cam is None, mood=shot.get("mood"),
                              to_camera=shot.get("to") == "camera")
        self.advance(duration)
        m.clear_reaction()
        m._look_until = 0.0
        self.subtitle = None
        # comic timing: a hair of air between lines, a real pause before a silent reaction
        self.advance(0.12 if "say" in nxt else 0.3)

    def _shot_show(self, shot: dict) -> None:
        e = self.events.get(shot["show"])
        if not e:
            return
        if e["kind"] == "bit":
            self._shot_meanwhile(e["id"])
            return
        agent = e.get("agent") or "Codex"
        feed = self.feeds[agent]
        self._clear_bubbles()
        board = self._board_at(e["id"])
        if board is not None:
            self.stage.set_board(board)
        if e["kind"] == "diff":
            feed.show_diff(FileChange(e["path"], [tuple(x) for x in e["lines"]], e.get("created", False),
                                      e.get("deleted", False)))
            typing = min(3.0, len(e["lines"]) / TYPE_RATE)
            self._typing_until = self.t + typing
            self._cut_to_screen(agent)
            self.advance(max(1.6, typing + 0.4))
        else:
            cmd = next((x for x in reversed(self.all_events) if x["kind"] == "command" and x.get("agent") == agent
                        and x["id"] < e["id"]), None)
            feed.command(cmd["command"] if cmd else "python -m unittest")
            self._cut_to_screen(agent)
            self.advance(0.6)
            feed.output(e.get("line", "") or e.get("command", ""))
            if e["kind"] == "tests" and not e.get("ok"):
                self.sfx("buzz", 0.8)
            self.advance(1.4)
        if shot.get("highlight") or shot.get("caption"):
            start = self.t
            lines = exhibit_lines(e, shot.get("highlight", ""))
            caption = shot.get("caption", "")
            self.sfx("tick", 0.9)
            self.overlay = lambda p, t: paint_exhibit(p, self.size, t - start, e, lines, caption)
            self.advance(2.8)
            self.overlay = None
        self._typing_until = 0.0
        self._cut(None)

    def _shot_meanwhile(self, event_id: int) -> None:
        e = self.events.get(event_id)
        if not e or e["kind"] != "bit":
            return
        agent = e["agent"]
        self.feeds[agent].show_bit(dict(e["bit"], _t0=self.t))
        self._clear_bubbles()
        self._cut_to_screen(agent)
        self.stage.badge("MEANWHILE", "center", ACCENT[agent], 1.6)
        self.advance(1.3)
        line = e["bit"].get("line", "")
        if line:
            self.stage.set_caption(agent, line)
            self.advance(self.speak(agent, line, bubble=False) + 0.4)
        else:
            self.advance(2.0)
        self.stage.set_caption(None, "")
        self._cut(None)

    # -- the Wheel of Destiny -------------------------------------------------------------------

    def _scene_challenge_title(self, scene: dict) -> None:
        start = self.t
        self.overlay = lambda p, t: paint_big_card(
            p, self.size, t - start, "GILFOYLE vs DINESH", [("", "Two AI agents. No humans."),
                                                           ("", "The Wheel of Destiny decides everything.")],
            footer=self.plan.get("disclaimer", ""))
        self.sfx("fanfare", 0.8)
        self.advance(4.2)
        self.overlay = None

    def _scene_wheel(self, scene: dict) -> None:
        spin = self.events.get(scene["spin"])
        if not spin:
            return
        self.music(False)
        n = sum(1 for e in self.all_events if e["kind"] == "spin" and e["id"] <= spin["id"])
        title = wheel_title(spin, n)
        duration = 3.6
        start = self.t
        state = {"under": None}

        def overlay(p, t):
            age = t - start
            angle, under = wheel_angle(spin, age, duration)
            landed = (age - duration) if age >= duration else None
            self._wheel_now = (spin, angle, landed, title)  # Shorts draw the wheel full-size instead
            paint_wheel(p, self.size, spin, angle, landed, title)

        self.overlay = overlay
        self.sfx("whir", 0.6)
        frames = int(round((duration + 0.1) * self.fps))
        for _ in range(frames):
            _, under = wheel_angle(spin, self.t - start + 1.0 / self.fps, duration)
            if under != state["under"]:
                state["under"] = under
                self.sfx("tick", 0.45)
            self.advance(1.0 / self.fps)
        result = spin["slices"][spin["result"]]
        self.sfx("blast" if spin["wheel"] in ("language", "limit") else "chime", 0.8)
        self.advance(1.2 if scene.get("short") else 1.8 + min(1.6, len(result.get("rule", "")) / 110))
        self.overlay = None
        self._wheel_now = None
        # their faces, as it sinks in
        for i, line in enumerate(scene.get("reactions", [])):
            who = line["speaker"]
            mood = None
            if spin.get("who") == who and i == 0:
                mood = "worried" if not self.stage.models[who].deadpan else "stare"
            self._shot_say({"say": who, "line": line["text"], "mood": mood,
                            "to": "camera" if i == 0 else "other", "frame": "close"}, {"say": 1})
        self._cut(None)
        self._clear_bubbles()

    def _scene_twist_intro(self, scene: dict) -> None:
        self.music(False)
        self._cut(None)
        self._clear_bubbles()
        start = self.t
        self.overlay = lambda p, t: paint_violation(p, self.size, t - start, "PLOT TWIST",
                                                    "Halfway through the build, the wheel spins again", "#6c2bd9")
        self.sfx("alert")
        self.stage.shake(6)
        for a in AGENTS:
            m = self.stage.models[a]
            m.react("disturbed" if m.deadpan else "worried", 2.4)
        self.advance(2.2)
        self.overlay = None

    def _scene_rules(self, scene: dict) -> None:
        start = self.t
        rows = [("Project", scene["project"]), ("Language", scene["language"]), ("Rule", scene["limit"]),
                ("Gilfoyle codes as", scene["skills"].get("Codex", "")),
                ("Dinesh codes as", scene["skills"].get("Claude", ""))]
        self.overlay = lambda p, t: paint_big_card(p, self.size, t - start, "THE RULES", rows,
                                                   footer="Checked automatically after every turn.")
        self.sfx("alert", 0.5)
        self.advance(5.5)
        self.overlay = None
        self.hud = {"rules": f"{scene['project'].upper()} · {scene['language'].upper()} · {scene['limit'].upper()}",
                    "violations": 0, "tests": "-", "turn": 0}

    def _scene_turn_card(self, scene: dict) -> None:
        self.music(True)
        agent = scene["agent"]
        self._cut(None)
        self._clear_bubbles()
        if self.hud is not None:
            self.hud["turn"] = scene["turn"]
            if scene.get("tests"):
                self.hud["tests"] = scene["tests"]
        self._working(agent, "coding")
        self.stage.models[agent].set_base("coding")
        self.stage.models[other_of(agent)].set_base("waiting")
        self.stage.badge(f"TURN {scene['turn']} · {CHARACTER[agent].upper()}", "center", ACCENT[agent], 1.6)
        self.sfx("handoff", 0.6)
        self.advance(1.5)

    def _scene_confessional(self, scene: dict) -> None:
        who = scene["speaker"]
        if scene.get("label"):
            self.stage.badge(scene["label"], "center", "#f2c94c", 1.4)
        self._shot_say({"say": who, "line": scene["text"], "mood": "smug", "to": "camera", "frame": "close"}, {})
        self._cut(None)

    def _scene_violation(self, scene: dict) -> None:
        check = self.events.get(scene["check"])
        if not check:
            return
        self.music(False)
        if scene.get("twist"):
            self._twist_fallout(scene, check)
            return
        agent = scene["agent"]
        other = other_of(agent)
        v = check["violations"][0]
        detail = f"[{v['rule'].replace('_', ' ')}]  {v['path']}:{v['line']}" if v.get("line") else \
            f"[{v['rule'].replace('_', ' ')}]  {v['path']}"
        start = self.t
        heading = "RULE VIOLATION" if scene["new"] == 1 else f"{scene['new']} RULE VIOLATIONS"
        self._cut(None)
        self._clear_bubbles()
        self.overlay = lambda p, t: paint_violation(p, self.size, t - start, heading, detail)
        self.sfx("alert")
        self.stage.shake(8)
        self.advance(2.2)
        self.overlay = None
        if self.hud is not None:
            self.hud["violations"] = scene["total"]
        exhibit = {"kind": "diff", "path": v["path"], "lines": [["add", v["text"]]]}
        lines = exhibit_lines(exhibit, v["text"][:20])
        start = self.t
        self.overlay = lambda p, t: paint_exhibit(p, self.size, t - start, exhibit, lines,
                                                  f"CAUGHT: {CHARACTER[agent].upper()}")
        self.advance(2.4)
        self.overlay = None
        m = self.stage.models[agent]
        self._cut(agent, 2.4, 0.08)
        m.look_at_other(1.6, speed=1.4)
        m.react("stare" if m.deadpan else "worried", 2.0)
        self.advance(1.3)
        o = self.stage.models[other]
        self._cut(other, 2.4, 0.08)
        o.look_at_other(1.8)
        o.react("smug" if o.deadpan else "gloating", 2.2)
        self._consider_thumbnail("react", "gloating")
        self.sfx("yes" if other == "Claude" else "wahwah", 0.8)
        self.advance(1.6)
        self._cut(None)

    def _twist_fallout(self, scene: dict, check: dict) -> None:
        """The new rule, applied to code that already exists: nobody's fault, everybody's problem."""
        v = check["violations"][0]
        start = self.t
        heading = f"THE NEW RULE BREAKS {scene['new']} LINE{'S' if scene['new'] != 1 else ''}"
        detail = f"[{v['rule'].replace('_', ' ')}]  {v['path']}:{v['line']}" if v.get("line") else v["path"]
        self.overlay = lambda p, t: paint_violation(p, self.size, t - start, heading, detail)
        self.sfx("alert")
        self.advance(2.2)
        self.overlay = None
        if self.hud is not None:
            self.hud["violations"] = scene["total"]
        for who, deadpan_mood, mood in (("Claude", "stare", "outraged"), ("Codex", "stare", "disturbed")):
            m = self.stage.models[who]
            self._cut(who, 2.4, 0.08)
            m.look(0.0, 0.0, 1.6)
            m.react(deadpan_mood if m.deadpan else mood, 2.0)
            self.advance(1.2)
        self.sfx("wahwah", 0.8)
        self.advance(0.6)
        self._cut(None)

    def _scene_cleared(self, scene: dict) -> None:
        agent = scene["agent"]
        if self.hud is not None:
            self.hud["violations"] = scene["total"]
        self._cut(agent, 2.2, 0.05)
        self.stage.badge(f"✓ {scene['fixed']} RULE BREAK{'S' if scene['fixed'] != 1 else ''} FIXED", "center",
                         "#7bd88f", 2.0)
        self.stage.models[agent].react("smug" if self.stage.models[agent].deadpan else "pleased", 2.0)
        self.sfx("chime", 0.8)
        self.advance(1.8)
        self._cut(None)

    def _scene_demo(self, scene: dict) -> None:
        self.music(True)
        agent = next((e["agent"] for e in reversed(self.all_events) if e["kind"] == "entry"), "Codex")
        feed = self.feeds[agent]
        self._clear_bubbles()
        self._cut_to_screen(agent)
        self.stage.badge("THE DEMO", "center", "#7bd88f", 1.6)
        started = False
        for line in scene["lines"]:
            if re.match(r"^\s*(?:\$|>|PS [^>]*>|[A-Za-z]:\\[^>]*>)", line) or not started:
                feed.command(re.sub(r"^\s*(?:\$|>|PS [^>]*>|[A-Za-z]:\\[^>]*>)\s*", "", line))
                self._typing_until = self.t + 0.5
                started = True
                self.advance(0.9)
            else:
                feed.output(line)
                self.advance(0.28)
        self.advance(2.0)
        self._typing_until = 0.0
        self._cut(None)

    def face_still(self, agent: str = "Claude", mood: str = "outraged") -> QImage:
        """A posed close-up (no video written): for thumbnails when the episode had no big reaction shot."""
        self.hud, self.subtitle, self.overlay = None, None, None
        self._clear_bubbles()
        m = self.stage.models[agent]
        m.look(0.0, 0.0, 5.0)
        m.react(mood, 5.0)
        self._cut(agent, 2.2, 0.0)
        for _ in range(int(0.8 * self.fps)):  # let the expression settle
            self.t += 1.0 / self.fps
            self.stage._tick()
        return self._compose(bubbles=False)

    def _consider_thumbnail(self, moment: str | None, mood: str | None = None) -> None:
        score = {"dinesh_catches": 5, "gilfoyle_catches": 5, "disagreement": 4, "own_goal": 4, "both_wrong": 3,
                 "concession": 3}.get(moment or "", 1)
        if moment == "react":  # a face close-up is what thumbnails are made of
            score = {"outraged": 7, "glare": 7, "embarrassed": 6, "surprised": 6, "disturbed": 6, "gloating": 7,
                     "stare": 5}.get(mood or "", 4)
        if score <= self._thumb_score:
            return
        self._thumb_score = score
        hud, subtitle, self.hud, self.subtitle = self.hud, self.subtitle, None, None
        image = self._compose(bubbles=False)  # a clean frame: no half-typed bubble, subtitle or status bar
        self.hud, self.subtitle = hud, subtitle
        self.thumbnail = image

    # -- audio ------------------------------------------------------------------------------------

    def music(self, on: bool) -> None:
        """Start or stop the music bed at the current time."""
        if on and not (self.music_spans and self.music_spans[-1][1] is None):
            self.music_spans.append([self.t, None])
        elif not on and self.music_spans and self.music_spans[-1][1] is None:
            self.music_spans[-1][1] = self.t

    def _music_track(self, n: int) -> np.ndarray:
        from .music import bed

        track = np.zeros(n, np.float32)
        end_of_video = n / SAMPLE_RATE
        for start, end in self.music_spans:
            end = end_of_video if end is None else end
            x = bed(end - start)
            i = int(start * SAMPLE_RATE)
            j = min(n, i + len(x))
            track[i:j] += x[: j - i]
        if not len(track):
            return track
        # duck under speech: down to 30% while anyone talks, with short ramps
        gain = np.ones(n, np.float32)
        for a, b in self.speech_spans:
            i, j = max(0, int((a - 0.1) * SAMPLE_RATE)), min(n, int((b + 0.2) * SAMPLE_RATE))
            gain[i:j] = 0.3
        kernel = np.ones(int(0.12 * SAMPLE_RATE), np.float32)
        kernel /= kernel.sum()
        gain = np.convolve(gain, kernel, mode="same")
        return track * gain * 0.16

    def _write_audio(self, path: Path) -> None:
        n = int((self.frames / self.fps + 1) * SAMPLE_RATE)
        mix = self._music_track(n)
        for t, samples, gain in self.audio:
            start = int(t * SAMPLE_RATE)
            end = min(n, start + len(samples))
            if end > start:
                mix[start:end] += samples[: end - start] * gain
        peak = float(np.max(np.abs(mix))) if len(mix) else 0.0
        if peak > 0.98:
            mix *= 0.98 / peak
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes((mix * 32767).astype(np.int16).tobytes())


_WAV_CACHE: dict[str, np.ndarray | None] = {}


def _load_wav(path: Path) -> np.ndarray | None:
    key = str(path)
    if key not in _WAV_CACHE:
        try:
            with wave.open(key, "rb") as w:
                data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
                rate = w.getframerate()
            if rate != SAMPLE_RATE and len(data) > 1:
                x = np.linspace(0, len(data) - 1, int(len(data) * SAMPLE_RATE / rate))
                data = np.interp(x, np.arange(len(data)), data).astype(np.float32)
            _WAV_CACHE[key] = data
        except (OSError, wave.Error):
            _WAV_CACHE[key] = None
    return _WAV_CACHE[key]


def _font(px: float, bold: bool = False, italic: bool = False, family: str = "Segoe UI") -> QFont:
    f = QFont(family)
    f.setPixelSize(max(1, int(px)))
    f.setBold(bold)
    f.setItalic(italic)
    return f


def _paint_fade(p: QPainter, size: tuple[int, int], k: float) -> None:
    p.fillRect(QRectF(0, 0, *size), QColor(0, 0, 0, int(255 * max(0.0, min(1.0, k)))))


def _paint_title(p: QPainter, size: tuple[int, int], age: float, title: str, subtitle: str, disclaimer: str) -> None:
    w, h = size
    fade_out = max(0.0, min(1.0, (5.5 - age) / 0.6))
    p.save()
    p.setOpacity(fade_out)
    bg = QLinearGradient(0, 0, 0, h)
    bg.setColorAt(0, QColor(8, 8, 10, 235))
    bg.setColorAt(1, QColor(0, 0, 0, 250))
    p.fillRect(QRectF(0, 0, w, h), bg)
    k = min(1.0, age / 0.5)
    # GILFOYLE  vs  DINESH
    names = _font(h * 0.085, bold=True, family="Bahnschrift")
    names.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
    p.setFont(names)
    y = h * 0.26
    gil, vs, din = CHARACTER["Codex"].upper(), "  vs  ", CHARACTER["Claude"].upper()
    fm = p.fontMetrics()
    total = fm.horizontalAdvance(gil + vs + din)
    x = (w - total) / 2 - (1 - k) * 40
    for text, colour in ((gil, ACCENT["Codex"]), (vs, "#8a8378"), (din, ACCENT["Claude"])):
        p.setPen(QColor(colour))
        p.drawText(QPointF(x, y + fm.ascent()), text)
        x += fm.horizontalAdvance(text)
    p.setPen(QPen(QColor("#f2c94c"), 3))
    p.drawLine(QPointF(w * 0.3, y + fm.height() + 18), QPointF(w * 0.7, y + fm.height() + 18))
    p.setOpacity(fade_out * max(0.0, min(1.0, (age - 0.5) / 0.5)))
    p.setFont(_font(h * 0.06, bold=True, family="Bahnschrift"))
    p.setPen(QColor("#f2ede4"))
    p.drawText(QRectF(w * 0.08, y + fm.height() + 34, w * 0.84, h * 0.2),
               int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap), title)
    p.setFont(_font(h * 0.03, italic=True, family="Georgia"))
    p.setPen(QColor("#b9b1a3"))
    p.drawText(QRectF(0, h * 0.64, w, h * 0.06), Qt.AlignmentFlag.AlignHCenter, subtitle)
    if disclaimer:
        p.setOpacity(fade_out * max(0.0, min(1.0, (age - 1.2) / 0.5)))
        p.setFont(_font(h * 0.022))
        p.setPen(QColor("#8f887c"))
        p.drawText(QRectF(w * 0.12, h * 0.84, w * 0.76, h * 0.1),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap), disclaimer)
    p.restore()


def shouted(text: str) -> bool:
    """Is a stretch of this line in capitals (Dinesh losing it)?"""
    caps = re.findall(r"\b[A-Z]{2,}\b", text)
    return sum(len(w) for w in caps if w not in ("OK", "UTF", "CLI", "API", "JSON", "README", "SQL", "ID", "URL")) >= 6
