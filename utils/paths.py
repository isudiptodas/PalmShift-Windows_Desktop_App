from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    """Resolve files both during development and from a PyInstaller bundle."""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base_path / relative_path


def recordings_dir() -> Path:
    path = Path.home() / "Videos" / "PalmShift"
    path.mkdir(parents=True, exist_ok=True)
    return path
