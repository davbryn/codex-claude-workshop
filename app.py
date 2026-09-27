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
    parser.add_argument("--headless", action="store_true",
                        help="run the workshop with no window (needs --project or --demo); it is recorded for an episode")
    parser.add_argument("--episode", action="store_true",
                        help="after PROJECT COMPLETE, cut the session into an episode (<project>/.workshop/episode/)")
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
    if args.headless:
        return _run_headless(app, orchestrator, settings, args, demo=args.demo)
    if args.record:
        settings.save = lambda *a, **k: None  # a recording session doesn't change your saved settings
        settings.speech_muted = False
        settings.theatre_mode = not args.record_full
        settings.window_geometry = ""
    window = MainWindow(orchestrator, settings, fake_agents=args.fake_agents, demo=args.demo,
                        demo_auto_reply=demo_auto_reply, pace=True)
    window.show()
    from workshop.episode.capture import SessionCapture

    # every run is recorded, so any session can be cut into an episode later
    window._capture = SessionCapture(orchestrator, side_bits=window.director._bits, drive_bits=False, parent=window)
    if args.episode:
        _build_episode_on_complete(app, orchestrator, setup.project_dir, quit_after=False,
                                   writers=not args.fake_agents)
    from workshop.watchdog import FreezeWatchdog

    # If the window ever stops responding, record exactly where (see .workshop/logs/freeze-*.log).
    watchdog = FreezeWatchdog(setup.project_dir / ".workshop" / "logs", parent=window)
    app.aboutToQuit.connect(watchdog.stop)
    app._freeze_watchdog = watchdog
    if args.record:
        _start_recording(app, window, orchestrator, Path(args.record))
    orchestrator.start()
    return app.exec()


def _run_headless(app: QApplication, orchestrator: Orchestrator, settings: Settings, args, demo: bool) -> int:
    """No window: the agents build the project, everything is recorded, then (optionally) an episode is cut."""
    import time

    from PySide6.QtCore import QTimer

    from workshop import orchestrator as orch
    from workshop.episode.capture import SessionCapture
    from workshop.theatre.banter import make_prompt_theatre
    from workshop.theatre.sidebits import SideBits

    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    orchestrator.prompt_theatre = make_prompt_theatre(settings)
    real = not args.fake_agents
    bits = SideBits(orchestrator.adapters) if (real and settings.side_bits_enabled) else None
    if bits is not None:
        bits.log_dir = orchestrator.project_dir / ".workshop" / "logs"
    scripted = None
    if demo:
        from workshop.agents.demo_files import DEMO_BITS

        scripted = DEMO_BITS
    capture = SessionCapture(orchestrator, side_bits=bits, drive_bits=True, scripted_bits=scripted)
    started = time.monotonic()

    def say(text: str) -> None:
        print(f"[{int(time.monotonic() - started) // 60:02d}:{int(time.monotonic() - started) % 60:02d}] {text}",
              flush=True)

    orchestrator.turn_started.connect(lambda agent, n: say(f"{agent} turn {n} started"))
    orchestrator.turn_finished.connect(lambda agent, code: say(f"{agent} turn finished (exit {code})"))
    orchestrator.message.connect(lambda level, text: say(f"{level}: {text.splitlines()[0][:160]}"))

    def on_state(state: str) -> None:
        if state == orch.WAITING_HUMAN and not orchestrator.is_busy():
            # nobody is watching: management is out of office
            from workshop.conversation import parse_conversation

            signal = orchestrator.last_signal
            turns = [t for t in parse_conversation(orchestrator.conversation_text()) if t.speaker != "Human"]
            last = turns[-1] if turns else None
            agent = (last.handoff if last and last.handoff else
                     ("Claude" if last and last.speaker == "Codex" else "Codex"))
            say(f"human decision requested ({(signal.detail if signal else '')[:120]}); answering for management")
            QTimer.singleShot(500, lambda: orchestrator.submit_human_turn(
                "Management is out of office (this is a headless run). Make the call yourselves, "
                "write down what you decided and why, and carry on.", agent, title="Out of office"))
        elif state == orch.COMPLETE:
            say("PROJECT COMPLETE")
        elif state in (orch.STOPPED, orch.NEEDS_ATTENTION):
            say(f"stopped: {state}. The log so far is kept; you can still cut an episode from it.")
            QTimer.singleShot(1000, app.quit)

    orchestrator.state_changed.connect(on_state)
    if args.episode:
        _build_episode_on_complete(app, orchestrator, orchestrator.project_dir, quit_after=True, say=say,
                                   writers=not args.fake_agents)
    else:
        orchestrator.state_changed.connect(lambda s: QTimer.singleShot(1500, app.quit) if s == orch.COMPLETE else None)
    say(f"headless workshop in {orchestrator.project_dir}")
    orchestrator.start()
    code = app.exec()
    capture.deleteLater()
    if bits is not None:
        bits.shutdown()
    return code


def _build_episode_on_complete(app: QApplication, orchestrator: Orchestrator, project: Path, quit_after: bool,
                               say=print, writers: bool = True) -> None:
    from PySide6.QtCore import QTimer

    from workshop import orchestrator as orch

    def build() -> None:
        from workshop.episode.build import build_episode

        say("cutting the episode…")
        try:
            # the writers' room makes real CLI calls; fake-agent sessions keep their scripted lines
            out = build_episode(project, progress=say, writers=writers)
            say(f"episode ready: {out}")
        except Exception as exc:  # the workshop itself succeeded; the edit failing shouldn't hide that
            say(f"episode build failed: {exc}")
        if quit_after:
            app.quit()

    orchestrator.state_changed.connect(lambda s: QTimer.singleShot(2000, build) if s == orch.COMPLETE else None)


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
        watchdog = getattr(app, "_freeze_watchdog", None)
        if watchdog is not None:
            watchdog.stop()  # muxing the video blocks the UI on purpose; that isn't a freeze
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
