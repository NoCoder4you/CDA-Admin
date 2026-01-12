from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]


def data_path(filename: str) -> Path:
    return BASE_DIR / filename
