"""Шляхи для портативної папки (БД поруч з exe)."""

from __future__ import annotations

import sys
from pathlib import Path


def app_dir() -> Path:
    """Каталог програми: поруч з exe (збірка) або поточна робоча тека (розробка)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def database_path() -> Path:
    return app_dir() / "spettest.db"
