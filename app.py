"""Codex ↔ Claude Workshop.

    python app.py                 # real Codex and Claude Code CLIs
    python app.py --fake-agents   # simulated agents, no usage consumed
    python app.py --demo          # scripted Workshop Theatre demo, no setup needed
    python app.py --demo --record demo.mp4   # …rendered to a video (with its audio)
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from workshop.agents import make_adapters
from workshop.config import Settings
from workshop.orchestrator import Orchestrator
from workshop.project import ensure_protocol_file, start_new_conversation
from workshop.ui.main_window import MainWindow
from workshop.ui.setup_dialog import SetupDialog, SetupResult
from workshop.ui.style import STYLESHEET


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch Codex and Claude Code collaborate on a project.")
    parser.add_argument("--fake-agents", action="store_true", help="use simulated agents (no CLI usage)")
    parser.add_argument("--fake-delay", type=float, default=None,
                        help="seconds per fake-agent step (default 1.6, or 0.9 in --demo)")
    parser.add_argument("--demo", action="store_true", help="run the scripted theatre demo in a temp folder")
    parser.add_argument("--demo-speed", type=float, default=1.0, help="demo speed multiplier (2 = twice as fast)")
    parser.add_argument("--project", help="skip the setup screen and use this project directory")
    parser.add_argument("--prompt", help="project prompt when using --project (starts a new conversation)")
    parser.add_argument("--first", choices=["Codex", "Claude"], default=None, help="first agent with --project")
    parser.add_argument("--record", metavar="MP4", help="record the window and its audio to a video (needs ffmpeg); "
                                                        "quits a few seconds after PROJECT COMPLETE")
    parser.add_argument("--record-full", action="store_true",
                        help="record the whole window instead of Theatre Mode")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv)
    app.setApplicationName("Codex ↔ Claude Workshop")
    app.setStyleSheet(STYLESHEET)
    settings = Settings.load()

    demo_auto_reply = None
    if args.demo:
        from workshop.agents.demo_script import DEMO_FIRST_AGENT, DEMO_PROMPT

        args.fake_agents = True
        # the demo keeps the silent "working" stretches short; the characters do the talking
        args.fake_delay = (args.fake_delay or 0.9) / max(0.1, args.demo_speed)
        demo_auto_reply = max(2.0, 4.0 / max(0.1, args.demo_speed))
        project = Path(args.project or tempfile.mkdtemp(prefix="workshop-demo-")).resolve()
        project.mkdir(parents=True, exist_ok=True)
        setup = SetupResult(project, args.prompt or DEMO_PROMPT, settings.codex_personality,
                            settings.claude_personality, args.first or DEMO_FIRST_AGENT, continue_existing=False)
    elif args.project:
        project = Path(args.project).resolve()
        project.mkdir(parents=True, exist_ok=True)
        setup = SetupResult(
            project_dir=project,
            prompt=args.prompt or "",
            codex_personality=settings.codex_personality,
            claude_personality=settings.claude_personality,
            first_agent=args.first or settings.first_agent,
            continue_existing=not args.prompt and (project / "conversation.md").exists(),
        )
        if not setup.continue_existing and not setup.prompt:
            print("--project needs --prompt unless the project already has a conversation.md", file=sys.stderr)
            return 2
    else:
        dialog = SetupDialog(settings, fake_agents=args.fake_agents)
        if not dialog.exec() or dialog.result_value is None:
            return 0
        setup = dialog.result_value

    if args.fake_delay is None:
        args.fake_delay = 1.6
    protocol_file = ensure_protocol_file(setup.project_dir)
    if settings.kanban_enabled:
        from workshop.kanban import ensure_board

        ensure_board(setup.project_dir)  # management insists
    if not setup.continue_existing:
        start_new_conversation(setup.project_dir, setup.prompt, setup.first_agent)

    orchestrator = Orchestrator(
        setup.project_dir,
        make_adapters(settings, fake=args.fake_agents, fake_delay=args.fake_delay),
        {"Codex": setup.codex_personality, "Claude": setup.claude_personality},
        protocol_file=protocol_file,
    )
    if args.record:
        settings.save = lambda *a, **k: None  # a recording session doesn't change your saved settings
        settings.speech_muted = False
        settings.theatre_mode = not args.record_full
        settings.window_geometry = ""
    window = MainWindow(orchestrator, settings, fake_agents=args.fake_agents, demo=args.demo,
                        demo_auto_reply=demo_auto_reply, pace=True)
    window.show()
    if args.record:
        _start_recording(app, window, orchestrator, Path(args.record))
    orchestrator.start()
    return app.exec()


def _start_recording(app: QApplication, window: MainWindow, orchestrator: Orchestrator, output: Path) -> None:
    from PySide6.QtCore import QTimer

    from workshop import orchestrator as orch
    from workshop.ui.recorder import Recorder

    window.resize(1600, 1000)
    recorder = Recorder(window, output)
    if not hasattr(window.speech, "tap"):
        print("Note: the voices aren't Kokoro, so the video will have sound effects but no speech.", file=sys.stderr)
    print(f"Recording to {output.resolve()} …", flush=True)
    state = {"done": False}

    def finish() -> None:
        if state["done"]:
            return
        state["done"] = True
        path = recorder.finish()
        print(f"Saved {path} ({recorder.frames / recorder.fps:.0f}s)", flush=True)
        orchestrator.shutdown()
        app.quit()

    def on_state(s: str) -> None:
        if s == orch.COMPLETE:
            QTimer.singleShot(11000, finish)  # let the finale play out
        elif s in (orch.STOPPED, orch.NEEDS_ATTENTION):
            QTimer.singleShot(3000, finish)

    orchestrator.state_changed.connect(on_state)
    app.aboutToQuit.connect(finish)  # closing the window early still saves what was recorded
    QTimer.singleShot(15 * 60 * 1000, finish)  # safety net


if __name__ == "__main__":
    sys.exit(main())
