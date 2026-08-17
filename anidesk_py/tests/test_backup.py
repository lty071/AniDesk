from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from anidesk.domain.models import ArchiveRecord, BackupKind, PlaybackLink
from anidesk.services.backup import BackupError, BackupService
from anidesk.services.timeutil import utc_now_iso


def seed(repository, anime) -> None:
    anime.cover_data = "data:image/png;base64," + base64.b64encode(b"png-bytes").decode("ascii")
    repository.upsert_anime(anime)
    repository.follow_anime(anime.id)
    repository.save_playback_link(PlaybackLink("link", anime.id, "默认", "https://example.com", 0, True, utc_now_iso()))


def test_following_backup_round_trip(repository, anime, tmp_path: Path) -> None:
    seed(repository, anime)
    service = BackupService(repository, snapshots=tmp_path / "snapshots")
    payload = service.create(BackupKind.FOLLOWING)
    repository.unfollow_anime(anime.id)
    result = service.import_bytes(payload)
    assert result == {"kind": "following", "imported": 0, "merged": 1}
    assert repository.get_following()[0].anime.cover_data.startswith("data:image/png;base64,")
    assert list((tmp_path / "snapshots").glob("before-import-*.anibackup"))


def test_archive_backup_round_trip(repository, anime, tmp_path: Path) -> None:
    repository.upsert_anime(anime)
    repository.archive_anime(ArchiveRecord(anime.id, "2026-08-15", "感想", "manual", utc_now_iso()))
    service = BackupService(repository, snapshots=tmp_path / "snapshots")
    payload = service.create(BackupKind.ARCHIVE)
    repository.delete_archive(anime.id)
    result = service.import_bytes(payload)
    assert result["kind"] == "archive"
    assert repository.get_archive()[0].archive.note == "感想"


def test_manifest_checksum_matches_tauri_shape(repository, anime, tmp_path: Path) -> None:
    seed(repository, anime)
    payload = BackupService(repository, snapshots=tmp_path).create(BackupKind.FOLLOWING)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    unsigned = {key: manifest[key] for key in ("schemaVersion", "kind", "appVersion", "exportedAt", "files", "records")}
    canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":")).encode()
    assert hashlib.sha256(canonical).hexdigest() == manifest["checksum"]


def test_modified_manifest_is_rejected(repository, anime, tmp_path: Path) -> None:
    seed(repository, anime)
    service = BackupService(repository, snapshots=tmp_path)
    payload = service.create(BackupKind.FOLLOWING)
    source = zipfile.ZipFile(io.BytesIO(payload))
    target = io.BytesIO()
    with source, zipfile.ZipFile(target, "w") as output:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "manifest.json":
                manifest = json.loads(content)
                manifest["checksum"] = "0" * 64
                content = json.dumps(manifest).encode()
            output.writestr(info.filename, content)
    with pytest.raises(BackupError, match="清单校验失败"):
        service.import_bytes(target.getvalue())


def test_unsafe_zip_path_is_rejected(repository, tmp_path: Path) -> None:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr("../evil.txt", b"bad")
        archive.writestr("manifest.json", b"{}")
    with pytest.raises(BackupError, match="不安全路径"):
        BackupService(repository, snapshots=tmp_path).import_bytes(target.getvalue())


def test_import_failure_restores_database(repository, anime, tmp_path: Path, monkeypatch) -> None:
    seed(repository, anime)
    service = BackupService(repository, snapshots=tmp_path)
    payload = service.create(BackupKind.FOLLOWING)
    repository.unfollow_anime(anime.id)
    original = repository.save_follow_record

    def fail(record):
        original(record)
        raise RuntimeError("injected failure")

    monkeypatch.setattr(repository, "save_follow_record", fail)
    with pytest.raises(RuntimeError, match="injected failure"):
        service.import_bytes(payload)
    assert repository.get_following() == []
