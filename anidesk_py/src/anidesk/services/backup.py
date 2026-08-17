from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from anidesk import __version__
from anidesk.domain.models import (
    Anime,
    AnimeStatus,
    AppSettings,
    ArchiveRecord,
    ArchivedAnime,
    BackupKind,
    EpisodeSchedule,
    FollowRecord,
    FollowedAnime,
    PlaybackLink,
    ScheduleSource,
    Season,
)
from anidesk.domain.ports import Repository
from anidesk.platform.paths import backup_dir
from .covers import CoverCache
from .timeutil import utc_now_iso

MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_FILES = 5000
MAX_EXPANDED_COVER_BYTES = 250 * 1024 * 1024


class BackupError(ValueError):
    pass


def _json_bytes(value: object, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8")


def _checksum_payload(unsigned: dict[str, Any]) -> str:
    return hashlib.sha256(_json_bytes(unsigned)).hexdigest()


def _anime_dict(anime: Anime) -> dict[str, Any]:
    return {
        "id": anime.id,
        "bgmId": anime.bgm_id,
        "anilistId": anime.anilist_id,
        "titleCn": anime.title_cn,
        "titleNative": anime.title_native,
        "summary": anime.summary,
        "coverUrl": anime.cover_url,
        "coverData": anime.cover_data,
        "seasonYear": anime.season_year,
        "season": anime.season.value,
        "startDate": anime.start_date,
        "status": anime.status.value,
        "updatedAt": anime.updated_at,
    }


def _follow_dict(record: FollowRecord) -> dict[str, Any]:
    return {
        "animeId": record.anime_id,
        "reminderEnabled": record.reminder_enabled,
        "reminderMinutes": record.reminder_minutes,
        "manualAirAt": record.manual_air_at,
        "lastRemindedScheduleId": record.last_reminded_schedule_id,
        "snoozedUntil": record.snoozed_until,
        "createdAt": record.created_at,
        "updatedAt": record.updated_at,
    }


def _schedule_dict(record: EpisodeSchedule) -> dict[str, Any]:
    return {
        "id": record.id,
        "animeId": record.anime_id,
        "episode": record.episode,
        "airAt": record.air_at,
        "source": record.source.value,
        "syncedAt": record.synced_at,
    }


def _link_dict(record: PlaybackLink) -> dict[str, Any]:
    return {
        "id": record.id,
        "animeId": record.anime_id,
        "name": record.name,
        "url": record.url,
        "sortOrder": record.sort_order,
        "isDefault": record.is_default,
        "updatedAt": record.updated_at,
    }


def _archive_dict(record: ArchiveRecord) -> dict[str, Any]:
    return {
        "animeId": record.anime_id,
        "finishedAt": record.finished_at,
        "note": record.note,
        "source": record.source,
        "updatedAt": record.updated_at,
    }


def _anime_from(raw: dict[str, Any]) -> Anime:
    required = ("id", "titleCn", "titleNative", "seasonYear", "season", "status", "updatedAt")
    if any(key not in raw for key in required):
        raise BackupError("备份记录缺少番剧字段")
    try:
        return Anime(
            id=str(raw["id"]),
            bgm_id=int(raw["bgmId"]) if raw.get("bgmId") is not None else None,
            anilist_id=int(raw["anilistId"]) if raw.get("anilistId") is not None else None,
            title_cn=str(raw["titleCn"]),
            title_native=str(raw["titleNative"]),
            summary=str(raw.get("summary") or ""),
            cover_url=str(raw.get("coverUrl") or ""),
            cover_data=str(raw.get("coverData") or ""),
            season_year=int(raw["seasonYear"]),
            season=Season(str(raw["season"])),
            start_date=str(raw.get("startDate") or ""),
            status=AnimeStatus(str(raw["status"])),
            updated_at=str(raw["updatedAt"]),
        )
    except (TypeError, ValueError) as error:
        raise BackupError("番剧记录字段无效") from error


def _follow_from(raw: dict[str, Any], anime_id: str) -> FollowRecord:
    try:
        return FollowRecord(
            anime_id=anime_id,
            reminder_enabled=bool(raw.get("reminderEnabled", True)),
            reminder_minutes=int(raw["reminderMinutes"]) if raw.get("reminderMinutes") is not None else None,
            manual_air_at=str(raw["manualAirAt"]) if raw.get("manualAirAt") is not None else None,
            last_reminded_schedule_id=(
                str(raw["lastRemindedScheduleId"]) if raw.get("lastRemindedScheduleId") is not None else None
            ),
            snoozed_until=str(raw["snoozedUntil"]) if raw.get("snoozedUntil") is not None else None,
            created_at=str(raw["createdAt"]),
            updated_at=str(raw["updatedAt"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BackupError("追更记录字段无效") from error


def _schedule_from(raw: dict[str, Any], anime_id: str) -> EpisodeSchedule:
    try:
        return EpisodeSchedule(
            id=str(raw["id"]),
            anime_id=anime_id,
            episode=int(raw["episode"]),
            air_at=str(raw["airAt"]),
            source=ScheduleSource(str(raw["source"])),
            synced_at=str(raw["syncedAt"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BackupError("日程记录字段无效") from error


def _link_from(raw: dict[str, Any], anime_id: str) -> PlaybackLink:
    try:
        return PlaybackLink(
            id=str(raw["id"]),
            anime_id=anime_id,
            name=str(raw["name"]),
            url=str(raw["url"]),
            sort_order=int(raw.get("sortOrder", 0)),
            is_default=bool(raw.get("isDefault", False)),
            updated_at=str(raw["updatedAt"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BackupError("播放地址字段无效") from error


def _archive_from(raw: dict[str, Any], anime_id: str) -> ArchiveRecord:
    try:
        return ArchiveRecord(
            anime_id=anime_id,
            finished_at=str(raw["finishedAt"]),
            note=str(raw.get("note") or ""),
            source=str(raw.get("source") or "imported"),
            updated_at=str(raw["updatedAt"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise BackupError("仓库记录字段无效") from error


class BackupService:
    def __init__(
        self,
        repository: Repository,
        covers: CoverCache | None = None,
        snapshots: Path | None = None,
    ) -> None:
        self.repository = repository
        self.covers = covers
        self.snapshots = snapshots or backup_dir()
        self.snapshots.mkdir(parents=True, exist_ok=True)

    def create(self, kind: BackupKind) -> bytes:
        records: list[dict[str, Any]] = []
        files: dict[str, str] = {}
        embedded: dict[str, bytes] = {}
        source: list[FollowedAnime] | list[ArchivedAnime]
        source = self.repository.get_following() if kind is BackupKind.FOLLOWING else self.repository.get_archive()
        for item in source:
            cover_bytes, extension = self._cover_bytes(item.anime)
            cover_file: str | None = None
            if cover_bytes:
                safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", item.anime.id)
                cover_file = f"covers/{safe_id}.{extension}"
                embedded[cover_file] = cover_bytes
                files[cover_file] = hashlib.sha256(cover_bytes).hexdigest()
            anime = replace(item.anime, cover_data="")
            if kind is BackupKind.FOLLOWING:
                followed = item
                assert isinstance(followed, FollowedAnime)
                records.append(
                    {
                        "anime": _anime_dict(anime),
                        "follow": _follow_dict(followed.follow),
                        "schedules": [_schedule_dict(value) for value in followed.schedules],
                        "links": [_link_dict(value) for value in followed.links],
                        "coverFile": cover_file,
                    }
                )
            else:
                archived = item
                assert isinstance(archived, ArchivedAnime)
                records.append(
                    {
                        "anime": _anime_dict(anime),
                        "archive": _archive_dict(archived.archive),
                        "links": [_link_dict(value) for value in archived.links],
                        "coverFile": cover_file,
                    }
                )
        unsigned = {
            "schemaVersion": 1,
            "kind": kind.value,
            "appVersion": __version__,
            "exportedAt": utc_now_iso(),
            "files": files,
            "records": records,
        }
        manifest = {**unsigned, "checksum": _checksum_payload(unsigned)}
        target = io.BytesIO()
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for filename, content in embedded.items():
                archive.writestr(filename, content)
            archive.writestr("manifest.json", _json_bytes(manifest, pretty=True))
        payload = target.getvalue()
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise BackupError("备份文件超过 200 MB 限制")
        return payload

    def export_file(self, kind: BackupKind, path: Path) -> Path:
        if path.suffix.lower() != ".anibackup":
            path = path.with_suffix(".anibackup")
        path.write_bytes(self.create(kind))
        return path

    def import_file(self, path: Path) -> dict[str, Any]:
        if path.suffix.lower() != ".anibackup":
            raise BackupError("仅能读取 .anibackup 文件")
        if path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise BackupError("备份文件超过 200 MB 限制")
        return self.import_bytes(path.read_bytes())

    def import_bytes(self, payload: bytes) -> dict[str, Any]:
        manifest, archive_files = self._validate(payload)
        kind = BackupKind(str(manifest["kind"]))
        parsed_records = self._parse_records(kind, manifest["records"], archive_files)
        stamp = utc_now_iso().replace(":", "-").replace(".", "-")
        backup_bytes = self.create(kind)
        (self.snapshots / f"before-import-{kind.value}-{stamp}.anibackup").write_bytes(backup_bytes)
        database_snapshot = self.snapshots / f"before-import-{kind.value}-{stamp}.db"
        self.repository.create_database_snapshot(database_snapshot)
        try:
            imported, merged = self._apply(kind, parsed_records)
        except Exception:
            self.repository.restore_database_snapshot(database_snapshot)
            raise
        return {"kind": kind.value, "imported": imported, "merged": merged}

    def _validate(self, payload: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
        if len(payload) > MAX_ARCHIVE_BYTES:
            raise BackupError("备份文件超过 200 MB 限制")
        try:
            archive = zipfile.ZipFile(io.BytesIO(payload), "r")
        except zipfile.BadZipFile as error:
            raise BackupError("备份不是有效的 ZIP 文件") from error
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                raise BackupError("备份内文件数量异常")
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise BackupError("备份包含重复文件名")
            for name in names:
                path = PurePosixPath(name.replace("\\", "/"))
                if name.startswith(("/", "\\")) or "\\" in name or ".." in path.parts or path.is_absolute():
                    raise BackupError(f"备份包含不安全路径：{name}")
            if "manifest.json" not in names:
                raise BackupError("备份缺少 manifest.json")
            try:
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise BackupError("备份清单不是有效的 UTF-8 JSON") from error
            if manifest.get("schemaVersion") != 1:
                raise BackupError(f"不支持的备份版本：{manifest.get('schemaVersion')}")
            if manifest.get("kind") not in {"following", "archive"}:
                raise BackupError("备份类型无效")
            if not isinstance(manifest.get("records"), list) or not isinstance(manifest.get("files"), dict):
                raise BackupError("备份结构无效")
            unsigned = {
                "schemaVersion": manifest["schemaVersion"],
                "kind": manifest["kind"],
                "appVersion": manifest.get("appVersion"),
                "exportedAt": manifest.get("exportedAt"),
                "files": manifest["files"],
                "records": manifest["records"],
            }
            if _checksum_payload(unsigned) != manifest.get("checksum"):
                raise BackupError("备份清单校验失败")
            total = 0
            files: dict[str, bytes] = {}
            for filename, expected in manifest["files"].items():
                if filename not in names:
                    raise BackupError(f"备份缺少封面文件：{filename}")
                info = archive.getinfo(filename)
                total += info.file_size
                if total > MAX_EXPANDED_COVER_BYTES:
                    raise BackupError("备份解压后的封面数据过大")
                content = archive.read(filename)
                if hashlib.sha256(content).hexdigest() != expected:
                    raise BackupError(f"文件校验失败：{filename}")
                files[filename] = content
            return manifest, files

    def _parse_records(
        self,
        kind: BackupKind,
        raw_records: list[dict[str, Any]],
        files: dict[str, bytes],
    ) -> list[dict[str, Any]]:
        parsed: list[dict[str, Any]] = []
        for raw in raw_records:
            if not isinstance(raw, dict) or not isinstance(raw.get("anime"), dict):
                raise BackupError("备份记录缺少番剧标识")
            anime = _anime_from(raw["anime"])
            cover_file = raw.get("coverFile")
            if cover_file:
                if cover_file not in files:
                    raise BackupError(f"备份缺少封面文件：{cover_file}")
                suffix = Path(str(cover_file)).suffix.lower()
                mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
                anime.cover_data = f"data:{mime};base64,{base64.b64encode(files[cover_file]).decode('ascii')}"
            links_raw = raw.get("links")
            if not isinstance(links_raw, list):
                raise BackupError("播放地址列表无效")
            record: dict[str, Any] = {"anime": anime, "links": [_link_from(item, anime.id) for item in links_raw]}
            if kind is BackupKind.FOLLOWING:
                if not isinstance(raw.get("follow"), dict) or not isinstance(raw.get("schedules"), list):
                    raise BackupError("追更备份结构无效")
                record["follow"] = _follow_from(raw["follow"], anime.id)
                record["schedules"] = [_schedule_from(item, anime.id) for item in raw["schedules"]]
            else:
                if not isinstance(raw.get("archive"), dict):
                    raise BackupError("仓库备份结构无效")
                record["archive"] = _archive_from(raw["archive"], anime.id)
            parsed.append(record)
        return parsed

    def _apply(self, kind: BackupKind, records: list[dict[str, Any]]) -> tuple[int, int]:
        imported = 0
        merged = 0
        for record in records:
            incoming: Anime = record["anime"]
            current = self.repository.find_anime_by_external(incoming.bgm_id, incoming.anilist_id)
            current = current or self.repository.get_anime(incoming.id)
            target_id = current.id if current else incoming.id
            imported += int(current is None)
            merged += int(current is not None)
            preferred = current if current and current.updated_at > incoming.updated_at else incoming
            anime = replace(
                preferred,
                id=target_id,
                cover_data=incoming.cover_data or (current.cover_data if current else ""),
            )
            self.repository.upsert_anime(anime)
            if kind is BackupKind.FOLLOWING:
                incoming_follow: FollowRecord = replace(record["follow"], anime_id=target_id)
                existing = next(
                    (item for item in self.repository.get_following() if item.anime.id == target_id), None
                )
                if existing is None or incoming_follow.updated_at >= existing.follow.updated_at:
                    self.repository.save_follow_record(incoming_follow)
                    self.repository.replace_schedules(
                        target_id,
                        [replace(item, anime_id=target_id) for item in record["schedules"]],
                    )
            else:
                incoming_archive: ArchiveRecord = replace(
                    record["archive"], anime_id=target_id, source="imported"
                )
                existing = next((item for item in self.repository.get_archive() if item.anime.id == target_id), None)
                if existing is None or incoming_archive.updated_at >= existing.archive.updated_at:
                    self.repository.archive_anime(incoming_archive)
            self._merge_links(target_id, record["links"])
        return imported, merged

    def _merge_links(self, anime_id: str, incoming: list[PlaybackLink]) -> None:
        followed = next((item for item in self.repository.get_following() if item.anime.id == anime_id), None)
        archived = next((item for item in self.repository.get_archive() if item.anime.id == anime_id), None)
        existing = followed.links if followed else archived.links if archived else []
        by_url = {item.url.casefold(): item for item in existing}
        for link in incoming:
            same = by_url.get(link.url.casefold())
            if same is None or link.updated_at >= same.updated_at:
                self.repository.save_playback_link(
                    replace(link, id=same.id if same else link.id, anime_id=anime_id)
                )

    def _cover_bytes(self, anime: Anime) -> tuple[bytes | None, str]:
        if anime.cover_data.startswith("data:"):
            match = re.match(r"^data:([^;,]+);base64,(.+)$", anime.cover_data, flags=re.IGNORECASE)
            if match:
                mime = match.group(1).lower()
                extension = "png" if "png" in mime else "webp" if "webp" in mime else "jpg"
                try:
                    return base64.b64decode(match.group(2), validate=True), extension
                except ValueError:
                    pass
        if self.covers and anime.cover_url:
            try:
                path = self.covers.get(anime.cover_url)
                if path:
                    return path.read_bytes(), path.suffix.lower().lstrip(".") or "jpg"
            except Exception:
                return None, "jpg"
        return None, "jpg"
