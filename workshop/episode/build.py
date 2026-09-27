"""Cut a captured session into an episode: plan → render → package.

    python -m workshop.episode <project>            # re-cut from the saved log
    python -m workshop.episode <project> --plan-only

Output in ``<project>/.workshop/episode/``: episode.mp4 (1080p), title.txt,
description.md (with YouTube chapters), thumbnail.png and script.json (the plan,
every scene tied to the logged events it came from). Nothing is uploaded.
"""

from __future__ import annotations

import json
from pathlib import Path

from .capture import EPISODE_DIR, read_events
from .plan import plan_cut

PARODY_NOTE = ("A fan homage to HBO's Silicon Valley; not affiliated with or endorsed by HBO or anyone involved "
               "with the show. Gilfoyle is played by OpenAI Codex, Dinesh by Anthropic Claude Code.")


def episode_dir(project_dir: Path) -> Path:
    return Path(project_dir) / EPISODE_DIR


def make_plan(project_dir: Path, progress=print, writers: bool = False, settings=None,
              target_seconds: float = 210.0) -> dict:
    """The cut; with ``writers`` each agent then punches up its own character's lines (real CLI calls)."""
    out = episode_dir(project_dir)
    events = read_events(out / "events.jsonl")
    if not any(e["kind"] == "entry" for e in events):
        raise RuntimeError("no agent turns were captured for this project; nothing to cut")
    if any(e["kind"] == "spin" for e in events):  # a Wheel of Destiny challenge: its own format, no writers
        from .challenge_plan import plan_challenge

        plan = plan_challenge(events, project_dir)
        progress(f"plan: challenge episode, {len(plan['scenes'])} scenes")
        return plan
    plan = plan_cut(events, target_seconds=target_seconds)
    progress(f"plan: {len(plan['scenes'])} scenes from {len(events)} logged events "
             f"(about {plan['estimated_seconds'] / 60:.1f} min)")
    if writers:
        from ..agents import make_adapters
        from .writers import punch_up

        if settings is None:
            from ..config import Settings

            settings = Settings.load()
        from .scenes import write_episode

        adapters = make_adapters(settings, fake=False)
        written = write_episode(events, adapters, progress=progress, log_dir=out)
        if written is not None:
            return written
        progress("writers' room: falling back to the edited cut, punched up line by line")
        plan = punch_up(plan, events, adapters, progress=progress, log_dir=out)
    return plan


def build_episode(project_dir: Path, progress=print, plan: dict | None = None, settings=None,
                  writers: bool = False) -> Path:
    from PySide6.QtWidgets import QApplication

    from .render import EpisodeRenderer

    if QApplication.instance() is None:
        raise RuntimeError("build_episode needs a QApplication")
    out = episode_dir(project_dir)
    events = read_events(out / "events.jsonl")
    if settings is None:
        from ..config import Settings

        settings = Settings.load()
    plan = plan or make_plan(project_dir, progress, writers=writers, settings=settings)
    (out / "script.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    renderer = EpisodeRenderer(plan, events, settings=settings, progress=progress)
    video = renderer.render(out / "episode.mp4")
    seconds = renderer.frames / renderer.fps
    progress(f"rendered {seconds / 60:.1f} min")
    title = youtube_title(plan)
    (out / "title.txt").write_text(title + "\n", encoding="utf-8")
    (out / "description.md").write_text(description(plan, renderer.chapters, events), encoding="utf-8")
    if renderer.thumbnail is not None:
        make_thumbnail(renderer.thumbnail, plan).save(str(out / "thumbnail.png"))
    return video


def youtube_title(plan: dict) -> str:
    if plan.get("format") == "challenge":
        title = f"AI vs AI: {plan['title'].rstrip('.')} | Wheel of Destiny"
    elif plan.get("project"):  # a written episode has its own title
        title = f"{plan['title']} | Gilfoyle & Dinesh Build {_title_case(plan['project'])}"
    else:
        title = f"Gilfoyle & Dinesh Build {_title_case(plan['title'])}"
    return title if len(title) <= 100 else title[:97] + "…"


def _title_case(text: str) -> str:
    small = {"a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with"}
    words = text.split()
    return " ".join(w if (w.isupper() or any(c.isupper() for c in w[1:])) else
                    (w if i and w.lower() in small else w[:1].upper() + w[1:]) for i, w in enumerate(words))


def _stamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def description(plan: dict, chapters: list[tuple[float, str]], events: list[dict]) -> str:
    lines = [plan.get("logline", "").strip(), "", plan.get("disclaimer", ""), ""]
    # YouTube wants chapters starting at 0:00, at least three, each at least ten seconds long
    kept: list[tuple[float, str]] = []
    for t, name in chapters:
        if kept and t - kept[-1][0] < 10:
            continue
        kept.append((t, name))
    if kept and len(kept) >= 3:
        kept[0] = (0.0, kept[0][1])
        lines.append("Chapters")
        lines += [f"{_stamp(t)} {name}" for t, name in kept]
        lines.append("")
    tests = [e for e in events if e["kind"] == "tests" and e.get("ok") and e.get("passed")]
    if tests:
        lines.append(f"Final result: {tests[-1]['passed']} tests passing.")
    lines += ["", "Made with codex-claude-workshop: two AI coding agents take turns in one shared file; "
                  "the GUI is the referee.", "", PARODY_NOTE, ""]
    return "\n".join(lines)


def make_thumbnail(frame, plan: dict):
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

    from ..theatre.cast import ACCENT

    image = frame.scaled(1280, 720, Qt.AspectRatioMode.IgnoreAspectRatio,
                         Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGB32)
    image.setDevicePixelRatio(1.0)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    shade = QLinearGradient(0, 0, 0, 720)
    shade.setColorAt(0, QColor(0, 0, 0, 200))
    shade.setColorAt(0.35, QColor(0, 0, 0, 40))
    shade.setColorAt(1, QColor(0, 0, 0, 0))
    p.fillRect(QRectF(0, 0, 1280, 720), shade)
    font = QFont("Impact")
    font.setPixelSize(118)
    p.setFont(font)
    x = 36.0
    for text, colour in (("GILFOYLE ", ACCENT["Codex"]), ("vs ", "#ffffff"), ("DINESH", ACCENT["Claude"])):
        p.setPen(QColor(0, 0, 0))
        for dx, dy in ((-4, 0), (4, 0), (0, -4), (0, 4), (5, 6)):
            p.drawText(int(x + dx), 126 + dy, text)
        p.setPen(QColor(colour))
        p.drawText(int(x), 126, text)
        x += p.fontMetrics().horizontalAdvance(text)
    sub = QFont("Bahnschrift")
    sub.setPixelSize(46)
    sub.setBold(True)
    p.setFont(sub)
    p.setPen(QColor("#f2c94c"))
    p.drawText(QRectF(40, 140, 1200, 60), Qt.AlignmentFlag.AlignLeft, plan["title"].upper()[:48])
    if plan.get("project"):
        sub.setPixelSize(30)
        p.setFont(sub)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(42, 196, 1200, 44), Qt.AlignmentFlag.AlignLeft, plan["project"].upper()[:60])
    p.end()
    return image
