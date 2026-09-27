"""Codex CLI adapter.

Verified against ``codex-cli 0.156.1``::

    codex exec [OPTIONS] [PROMPT]   # PROMPT "-" (or omitted) reads stdin

Progress goes to stderr, the final agent message to stdout.
"""

from __future__ import annotations

from pathlib import Path

import os
import sys

from .base import AgentAdapter, LaunchSpec

# See pyshim/sitecustomize.py: lets Python's temp folders work inside Codex's Windows sandbox.
PYSHIM_DIR = Path(__file__).resolve().parent / "pyshim"

# On Windows, codex 0.156 silently downgrades `--sandbox workspace-write` to
# read-only unless a Windows sandbox mode is configured.
DEFAULT_CODEX_ARGS = ["--sandbox", "workspace-write"] + (
    ["-c", 'windows.sandbox="unelevated"'] if sys.platform == "win32" else []
)

# winget installs the binary under a platform-suffixed name and may not create
# a `codex` alias; prefer that real .exe over any .cmd shim.
_FALLBACK_PATHS = [
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenAI.Codex_Microsoft.Winget.Source_8wekyb3d8bbwe\codex-x86_64-pc-windows-msvc.exe",
    r"%APPDATA%\npm\codex.cmd",
]


class CodexAdapter(AgentAdapter):
    name = "Codex"
    progress_on_stderr = True

    def __init__(self, command: str = "codex", extra_args: list[str] | None = None):
        super().__init__(command, DEFAULT_CODEX_ARGS if extra_args is None else extra_args)

    def build_launch(self, project_dir: Path, prompt: str) -> LaunchSpec:
        path = self.resolve_executable(_FALLBACK_PATHS)
        args = [
            "exec",
            "--color", "never",
            "--skip-git-repo-check",
            "--cd", str(project_dir),
            *self.extra_args,
            "-",  # read the prompt from stdin
        ]
        env = {}
        if sys.platform == "win32":
            existing = os.environ.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(PYSHIM_DIR) + (os.pathsep + existing if existing else "")
        return self.make_spec(path, args, stdin=prompt, env=env)

    # Told to Codex every turn, so nobody (Dinesh included) mistakes the sandbox for incompetence.
    environment_note = (
        "Your shell commands run in a Windows sandbox with no network access: creating a venv, temporary "
        "folders and pytest's tmp_path all work, but downloading packages (pip install from PyPI) will fail. "
        "If the project needs a package installed, say so plainly in your entry and put a To do card on the "
        "kanban board for Claude, whose environment can install it."
    )
