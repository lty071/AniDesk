from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing
from pathlib import Path


def application_dir() -> Path:
    """Use the EXE location, never the working directory or onefile extraction directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def app_data_dir(create: bool = True) -> Path:
    target = application_dir() / "data"
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
    """Copy legacy data into a new portable installation without changing the source."""
    if target.exists():
        return None
    roaming = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates = (
        local / "AniDesk" / "anidesk.db",
        roaming / "com.anidesk.desktop" / "anidesk.db",
        local / "com.anidesk.desktop" / "anidesk.db",
    )
    source = next((item for item in candidates if item.is_file()), None)
    if source is None:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshots = target.parent / "backups"
    snapshots.mkdir(parents=True, exist_ok=True)
    # SQLite backup includes committed WAL data, unlike copying the .db alone.
    # Publish the new database last, so a failed migration can safely be retried.
    with tempfile.TemporaryDirectory(prefix="migration-", dir=target.parent) as staging:
        temporary = Path(staging) / "anidesk.db"
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(temporary)) as destination:
                original.backup(destination)
        for name in ("covers", "backups"):
            _copy_missing_files(source.parent / name, target.parent / name)
        snapshot = snapshots / "legacy-before-portable.db"
        if not snapshot.exists():
            shutil.copy2(temporary, snapshot)
        temporary.replace(target)
    return snapshot


def _copy_missing_files(source: Path, destination: Path) -> None:
    if not source.is_dir():
        return
    for item in source.rglob("*"):
        if item.is_file() and not item.is_symlink():
            target = destination / item.relative_to(source)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
