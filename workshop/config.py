"""Local app configuration (``config/settings.json``) and personality presets
(``config/personalities.json``). Project conversations never live here."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .agents.claude import DEFAULT_CLAUDE_ARGS
from .agents.codex import DEFAULT_CODEX_ARGS

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = APP_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
PERSONALITIES_PATH = CONFIG_DIR / "personalities.json"
ASSETS_DIR = APP_DIR / "assets"


@dataclass
class Settings:
    last_project_directory: str = ""
    last_prompt: str = ""
    last_preset: str = "Rivals"
    first_agent: str = "Codex"
    codex_personality: str = ""
    claude_personality: str = ""
    codex_command: str = "codex"
    codex_args: list[str] = field(default_factory=lambda: list(DEFAULT_CODEX_ARGS))
    claude_command: str = "claude"
    claude_args: list[str] = field(default_factory=lambda: list(DEFAULT_CLAUDE_ARGS))
    window_geometry: str = ""  # hex of QWidget.saveGeometry()

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def load_personalities(path: Path = PERSONALITIES_PATH) -> dict[str, dict[str, str]]:
    """``{preset name: {"Codex": text, "Claude": text}}``"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {name: {"Codex": p.get("Codex", ""), "Claude": p.get("Claude", "")} for name, p in data.items()}


def save_personality_preset(name: str, codex: str, claude: str, path: Path = PERSONALITIES_PATH) -> None:
    presets = load_personalities(path)
    presets[name] = {"Codex": codex, "Claude": claude}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")
