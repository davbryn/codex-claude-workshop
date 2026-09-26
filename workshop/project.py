"""Project directory validation and workshop file initialisation.

Never overwrites existing project files: the protocol goes into
AGENT_README.md, and an existing conversation.md is backed up before a new
conversation is started.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from .conversation import new_conversation_text

CONVERSATION_FILE = "conversation.md"
PROTOCOL_FILE = "AGENT_README.md"
TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / PROTOCOL_FILE
APP_DIR = Path(__file__).resolve().parent.parent


def _sensitive_directories() -> list[Path]:
    home = Path.home()
    dirs = [home, home.parent, APP_DIR]
    for name in ("Desktop", "Documents", "Downloads", "OneDrive", "Pictures", "Music", "Videos"):
        dirs.append(home / name)
    for var in ("OneDrive", "USERPROFILE", "SystemRoot", "ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(var):
            dirs.append(Path(os.environ[var]))
    return dirs


def safety_warning(project_dir: Path) -> str | None:
    """Return a warning if agents should not casually be pointed at this directory."""
    resolved = project_dir.resolve()
    if resolved.parent == resolved:
        return f"{resolved} is a drive root."
    for sensitive in _sensitive_directories():
        try:
            if resolved == sensitive.resolve():
                return f"{resolved} is a broad system or user folder, not a project directory."
        except OSError:
            continue
    return None


def is_effectively_empty(project_dir: Path) -> bool:
    return not any(p for p in project_dir.iterdir() if p.name not in (".git",))


def ensure_protocol_file(project_dir: Path) -> str:
    target = project_dir / PROTOCOL_FILE
    if not target.exists():
        shutil.copyfile(TEMPLATE_PATH, target)
    return PROTOCOL_FILE


def backup_conversation(project_dir: Path) -> Path | None:
    path = project_dir / CONVERSATION_FILE
    if not path.exists():
        return None
    backup = project_dir / f"conversation.{datetime.now():%Y%m%d-%H%M%S}.bak.md"
    path.rename(backup)
    return backup


def start_new_conversation(project_dir: Path, prompt: str, first_agent: str) -> Path:
    """Create a fresh conversation.md (backing up any existing one)."""
    backup_conversation(project_dir)
    path = project_dir / CONVERSATION_FILE
    path.write_text(new_conversation_text(prompt, first_agent), encoding="utf-8", newline="\n")
    return path
