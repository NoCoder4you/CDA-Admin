from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def data_path(filename: str) -> Path:
    path = Path(filename)
    if path.is_absolute() or path.parts[:1] == ("JSON",):
        return BASE_DIR / path
    return BASE_DIR / "JSON" / path
