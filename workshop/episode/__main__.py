"""python -m workshop.episode <project> [--plan-only]: cut an episode from a captured session."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cut a captured workshop session into an episode.")
    parser.add_argument("project", help="the project directory (it has .workshop/episode/events.jsonl)")
    parser.add_argument("--plan-only", action="store_true", help="write script.json and stop (no render)")
    parser.add_argument("--verbatim", action="store_true",
                        help="skip the writers' room: every line exactly as the agents wrote it (no CLI calls)")
    parser.add_argument("--script", help="render this script.json instead of planning (e.g. after editing it)")
    parser.add_argument("--minutes", type=float, default=3.5, help="target running time (default 3.5)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    project = Path(args.project).resolve()
    from .build import build_episode, episode_dir, make_plan

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])  # noqa: F841  (the stage paints with Qt; the writers' room uses QProcess)
    if args.script:
        plan = json.loads(Path(args.script).read_text(encoding="utf-8"))
    else:
        plan = make_plan(project, writers=not args.verbatim, target_seconds=args.minutes * 60)
    if args.plan_only:
        path = episode_dir(project) / "script.json"
        path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"script: {path}")
        return 0
    out = build_episode(project, plan=plan)
    print(f"episode ready: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
