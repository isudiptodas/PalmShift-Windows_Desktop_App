from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


APP_NAME = "PalmShift"
DEFAULT_SHORTCUTS = {
    "toggle_control": "ctrl+alt+c",
    "toggle_aura": "ctrl+alt+a",
    "aura_water": "ctrl+alt+w",
    "aura_neon": "ctrl+alt+n",
    "aura_ink": "ctrl+alt+i",
    "aura_draw": "ctrl+alt+d",
    "stop_active": "ctrl+alt+x",
}


def app_data_dir() -> Path:
    base = Path.home() / "AppData" / "Local"
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Settings:
    skip_intro: bool = False
    shortcuts: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))
    last_aura_effect: str = "Water"


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or app_data_dir() / "settings.json"
        self.settings = Settings()
        self.load()

    def load(self) -> Settings:
        if not self.path.exists():
            self.save()
            return self.settings

        try:
            data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
            self.settings.skip_intro = bool(data.get("skip_intro", False))
            shortcuts = data.get("shortcuts", {})
            self.settings.shortcuts = {**DEFAULT_SHORTCUTS, **shortcuts}
            effect = str(data.get("last_aura_effect", "Water"))
            self.settings.last_aura_effect = effect if effect in {"Water", "Neon", "Ink", "Draw"} else "Water"
        except (OSError, json.JSONDecodeError, TypeError):
            self.settings = Settings()
            self.save()
        return self.settings

    def save(self) -> None:
        payload = {
            "skip_intro": self.settings.skip_intro,
            "shortcuts": self.settings.shortcuts,
            "last_aura_effect": self.settings.last_aura_effect,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_skip_intro(self, value: bool) -> None:
        self.settings.skip_intro = value
        self.save()

    def set_last_aura_effect(self, value: str) -> None:
        self.settings.last_aura_effect = value
        self.save()

    def set_shortcut(self, action: str, shortcut: str) -> None:
        self.settings.shortcuts[action] = shortcut
        self.save()
