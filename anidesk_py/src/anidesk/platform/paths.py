from __future__ import annotations

import os
import shutil
from pathlib import Path


def app_data_dir(create: bool = True) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    target = base / "AniDesk"
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def database_path() -> Path:
    return app_data_dir() / "anidesk.db"


def backup_dir() -> Path:
    target = app_data_dir() / "backups"
    target.mkdir(parents=True, exist_ok=True)
    return target


def cover_cache_dir() -> Path:
    target = app_data_dir() / "covers"
    target.mkdir(parents=True, exist_ok=True)
    return target


def log_dir() -> Path:
    target = app_data_dir() / "logs"
    target.mkdir(parents=True, exist_ok=True)
    return target


def migrate_legacy_database(target: Path) -> Path | None:
    """Copy a legacy Tauri database only when the Python database is absent."""
    if target.exists():
        return None
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates = (
        roaming / "com.anidesk.desktop" / "anidesk.db",
        local / "com.anidesk.desktop" / "anidesk.db",
    )
    source = next((item for item in candidates if item.is_file()), None)
    if source is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot = backup_dir() / "legacy-tauri-before-python.db"
    shutil.copy2(source, snapshot)
    shutil.copy2(source, target)
    return snapshot
