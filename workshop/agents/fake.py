from __future__ import annotations

import sys
from pathlib import Path

from .base import AgentAdapter, LaunchSpec


class FakeAdapter(AgentAdapter):
    """Launches :mod:`workshop.agents.fake_agent` as a real child process."""

    def __init__(self, name: str, delay: float = 1.5, behavior: str = "normal", complete_after: int = 3):
        super().__init__(command=sys.executable)
        self.name = name
        self.delay = delay
        self.behavior = behavior
        self.complete_after = complete_after

    def build_launch(self, project_dir: Path, prompt: str) -> LaunchSpec:
        script = Path(__file__).with_name("fake_agent.py")
        return LaunchSpec(
            program=sys.executable,
            args=[
                "-u",
                str(script),
                "--name", self.name,
                "--dir", str(project_dir),
                "--delay", str(self.delay),
                "--behavior", self.behavior,
                "--complete-after", str(self.complete_after),
            ],
            stdin=prompt,
            env={"PYTHONIOENCODING": "utf-8"},
        )
