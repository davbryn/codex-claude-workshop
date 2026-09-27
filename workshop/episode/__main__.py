"""python -m workshop.episode <project> [--plan-only]: cut an episode from a captured session."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cut a captured workshop session into an episode.")
    parser.add_argument("project", help="the project directory (it has .workshop/episode/events.jsonl)")
    parser.add_argument("--plan-only", action="store_true", help="print the episode plan and stop")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    project = Path(args.project).resolve()
    from .build import build_episode, make_plan

    if args.plan_only:
        print(json.dumps(make_plan(project), indent=2, ensure_ascii=False))
        return 0
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])  # noqa: F841  (the stage paints with Qt)
    out = build_episode(project)
    print(f"episode ready: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
