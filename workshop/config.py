"""Local app configuration (``config/settings.json``) and personality presets
(``config/personalities.json``). Project conversations never live here."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .agents.claude import DEFAULT_CLAUDE_ARGS
from .agents.codex import DEFAULT_CODEX_ARGS
from .theatre.avatar_state import DEFAULT_PERSONAS, Persona

THEME_VERSION = 2  # bump when the cast/theme defaults change

APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = APP_DIR / "config"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
PERSONALITIES_PATH = CONFIG_DIR / "personalities.json"


@dataclass
class Settings:
    last_project_directory: str = ""
    last_prompt: str = ""
    last_preset: str = "Gilfoyle & Dinesh"
    first_agent: str = "Codex"
    codex_personality: str = ""
    claude_personality: str = ""
    codex_command: str = "codex"
    codex_args: list[str] = field(default_factory=lambda: list(DEFAULT_CODEX_ARGS))
    claude_command: str = "claude"
    claude_args: list[str] = field(default_factory=lambda: list(DEFAULT_CLAUDE_ARGS))
    window_geometry: str = ""  # hex of QWidget.saveGeometry()
    # Workshop Theatre
    animations: bool = True
    reduced_motion: bool = False
    typewriter: bool = True
    theatre_mode: bool = False
    rivalry_mode: bool = True
    speech_enabled: bool = True
    speech_engine: str = "auto"  # auto | neural | system
    speech_muted: bool = False
    codex_voice: str = ""
    claude_voice: str = ""
    speech_rate: float = 0.1
    speech_volume: float = 0.85
    sfx_enabled: bool = True
    sfx_volume: float = 0.8
    # Silicon Valley cast (Codex = Gilfoyle, Claude = Dinesh)
    cast_enabled: bool = True
    hostility: str = "Gilfoyle & Dinesh"
    petty_scoreboard: bool = True
    comic_timing: bool = True
    camera_cuts: bool = True  # cut to the working agent's monitor, full-size
    kanban_enabled: bool = True  # management's shared KANBAN.md, with asides spoken while they work
    theme_version: int = THEME_VERSION

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()
        known = {f.name for f in fields(cls)}
        settings = cls(**{k: v for k, v in data.items() if k in known and k != "theme_version"})
        settings.theme_version = int(data.get("theme_version", 0) or 0)
        settings._migrate_theme()
        return settings

    def _migrate_theme(self) -> None:
        """Older settings predate the cast: move them onto Gilfoyle & Dinesh once (voices included)."""
        if self.theme_version >= THEME_VERSION:
            return
        if self.theme_version < 1:
            from .theatre.cast import PERSONALITY

            self.last_preset = "Gilfoyle & Dinesh"
            self.codex_personality = PERSONALITY["Codex"]
            self.claude_personality = PERSONALITY["Claude"]
            self.codex_voice = self.claude_voice = ""
            self.speech_rate = 0.0
            self.cast_enabled = True
        if self.theme_version < 2:
            # effects are now normalised; the old default volume made them inaudible under the voices
            self.sfx_volume = max(self.sfx_volume, 0.8)
        self.theme_version = THEME_VERSION

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def _load_raw(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_personalities(path: Path = PERSONALITIES_PATH) -> dict[str, dict[str, str]]:
    """``{preset name: {"Codex": text, "Claude": text}}``"""
    return {
        name: {"Codex": p.get("Codex", ""), "Claude": p.get("Claude", "")}
        for name, p in _load_raw(path).items()
        if isinstance(p, dict)
    }


def load_personas(preset: str, path: Path = PERSONALITIES_PATH) -> dict[str, Persona]:
    """Visual persona (animation style/energy) for each agent in a preset; defaults if absent."""
    raw = _load_raw(path).get(preset, {})
    persona = raw.get("persona", {}) if isinstance(raw, dict) else {}
    return {agent: Persona.from_dict(persona.get(agent), DEFAULT_PERSONAS[agent]) for agent in DEFAULT_PERSONAS}


def save_personality_preset(name: str, codex: str, claude: str, path: Path = PERSONALITIES_PATH) -> None:
    presets = _load_raw(path)
    entry = presets.get(name, {}) if isinstance(presets.get(name), dict) else {}
    entry.update({"Codex": codex, "Claude": claude})
    presets[name] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(presets, indent=2, ensure_ascii=False), encoding="utf-8")
