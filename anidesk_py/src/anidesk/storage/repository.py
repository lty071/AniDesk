from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from anidesk.domain.models import (
    Anime,
    AnimeStatus,
    AppSettings,
    ArchiveRecord,
    ArchivedAnime,
    EpisodeSchedule,
    FollowRecord,
    FollowedAnime,
    PlaybackLink,
    ScheduleSource,
    Season,
)
from anidesk.platform.paths import database_path as default_database_path
from anidesk.platform.paths import migrate_legacy_database
from anidesk.services.timeutil import utc_now_iso

ANIME_COLUMNS = (
    "id, bgm_id, anilist_id, title_cn, title_native, summary, cover_url, cover_data, "
    "season_year, season, start_date, status, updated_at"
)


class SqliteRepository:
    """Thread-safe repository using a short-lived SQLite connection per operation."""

    def __init__(self, database_path: Path | str | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self._migration_lock = threading.RLock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5.0, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._migration_lock:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            migrate_legacy_database(self.database_path)
            migration = Path(__file__).parent / "migrations" / "001_initial.sql"
            with closing(self._connect()) as connection:
                connection.executescript(migration.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, description, applied_at) VALUES(1, ?, ?)",
                    ("create_initial_schema", utc_now_iso()),
                )
                connection.commit()

    def upsert_anime(self, anime: Anime | Iterable[Anime]) -> None:
        records = [anime] if isinstance(anime, Anime) else list(anime)
        if not records:
            return
        values = [self._anime_values(item) for item in records]
        with self._transaction() as connection:
            connection.executemany(
                """
                INSERT INTO anime(
                  id, bgm_id, anilist_id, title_cn, title_native, summary, cover_url, cover_data,
                  season_year, season, start_date, status, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  bgm_id=excluded.bgm_id, anilist_id=excluded.anilist_id, title_cn=excluded.title_cn,
                  title_native=excluded.title_native, summary=excluded.summary, cover_url=excluded.cover_url,
                  cover_data=excluded.cover_data, season_year=excluded.season_year, season=excluded.season,
                  start_date=excluded.start_date, status=excluded.status, updated_at=excluded.updated_at
                """,
                values,
            )

    def get_anime(self, anime_id: str) -> Anime | None:
        with closing(self._connect()) as connection:
            row = connection.execute(f"SELECT {ANIME_COLUMNS} FROM anime WHERE id=?", (anime_id,)).fetchone()
        return self._map_anime(row) if row else None

    def find_anime_by_external(self, bgm_id: int | None, anilist_id: int | None) -> Anime | None:
        clauses: list[str] = []
        parameters: list[int] = []
        if bgm_id is not None:
            clauses.append("bgm_id=?")
            parameters.append(bgm_id)
        if anilist_id is not None:
            clauses.append("anilist_id=?")
            parameters.append(anilist_id)
        if not clauses:
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                f"SELECT {ANIME_COLUMNS} FROM anime WHERE {' OR '.join(clauses)} LIMIT 1", parameters
            ).fetchone()
        return self._map_anime(row) if row else None

    def get_season(self, year: int, season: Season) -> list[Anime]:
        season_value = Season(str(season)).value
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"SELECT {ANIME_COLUMNS} FROM anime WHERE season_year=? AND season=? ORDER BY start_date, title_cn",
                (year, season_value),
            ).fetchall()
        return [self._map_anime(row) for row in rows]

    def get_following(self) -> list[FollowedAnime]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""SELECT {', '.join(f'a.{item.strip()}' for item in ANIME_COLUMNS.split(','))},
                f.reminder_enabled, f.reminder_minutes, f.manual_air_at, f.last_reminded_schedule_id,
                f.snoozed_until, f.created_at, f.updated_at AS follow_updated_at
                FROM follow_records f JOIN anime a ON a.id=f.anime_id
                ORDER BY a.title_cn"""
            ).fetchall()
            result: list[FollowedAnime] = []
            for row in rows:
                anime = self._map_anime(row)
                follow = FollowRecord(
                    anime_id=anime.id,
                    reminder_enabled=bool(row["reminder_enabled"]),
                    reminder_minutes=row["reminder_minutes"],
                    manual_air_at=row["manual_air_at"],
                    last_reminded_schedule_id=row["last_reminded_schedule_id"],
                    snoozed_until=row["snoozed_until"],
                    created_at=str(row["created_at"]),
                    updated_at=str(row["follow_updated_at"]),
                )
                result.append(
                    FollowedAnime(
                        anime=anime,
                        follow=follow,
                        schedules=self._schedules_for(connection, anime.id),
                        links=self._links_for(connection, anime.id),
                    )
                )
        return result

    def follow_anime(self, anime_id: str) -> None:
        timestamp = utc_now_iso()
        with self._transaction() as connection:
            connection.execute("DELETE FROM archive_records WHERE anime_id=?", (anime_id,))
            connection.execute(
                """INSERT OR IGNORE INTO follow_records(
                anime_id, reminder_enabled, created_at, updated_at
                ) VALUES(?, 1, ?, ?)""",
                (anime_id, timestamp, timestamp),
            )

    def save_follow_record(self, record: FollowRecord) -> None:
        with self._transaction() as connection:
            connection.execute("DELETE FROM archive_records WHERE anime_id=?", (record.anime_id,))
            connection.execute(
                """INSERT INTO follow_records(
                  anime_id, reminder_enabled, reminder_minutes, manual_air_at,
                  last_reminded_schedule_id, snoozed_until, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(anime_id) DO UPDATE SET
                  reminder_enabled=excluded.reminder_enabled,
                  reminder_minutes=excluded.reminder_minutes,
                  manual_air_at=excluded.manual_air_at,
                  last_reminded_schedule_id=excluded.last_reminded_schedule_id,
                  snoozed_until=excluded.snoozed_until,
                  created_at=excluded.created_at,
                  updated_at=excluded.updated_at""",
                (
                    record.anime_id,
                    int(record.reminder_enabled),
                    record.reminder_minutes,
                    record.manual_air_at,
                    record.last_reminded_schedule_id,
                    record.snoozed_until,
                    record.created_at,
                    record.updated_at,
                ),
            )

    def update_follow(self, anime_id: str, **changes: object) -> None:
        columns = {
            "reminder_enabled": "reminder_enabled",
            "reminder_minutes": "reminder_minutes",
            "manual_air_at": "manual_air_at",
            "last_reminded_schedule_id": "last_reminded_schedule_id",
            "snoozed_until": "snoozed_until",
        }
        assignments: list[str] = []
        values: list[object] = []
        for key, value in changes.items():
            if key not in columns:
                raise ValueError(f"unsupported follow field: {key}")
            assignments.append(f"{columns[key]}=?")
            values.append(int(value) if key == "reminder_enabled" and value is not None else value)
        if not assignments:
            return
        assignments.append("updated_at=?")
        values.extend((utc_now_iso(), anime_id))
        with self._transaction() as connection:
            cursor = connection.execute(
                f"UPDATE follow_records SET {', '.join(assignments)} WHERE anime_id=?", values
            )
            if cursor.rowcount != 1:
                raise KeyError(f"follow record not found: {anime_id}")

    def unfollow_anime(self, anime_id: str) -> None:
        with self._transaction() as connection:
            connection.execute("DELETE FROM follow_records WHERE anime_id=?", (anime_id,))

    def replace_schedules(self, anime_id: str, schedules: Iterable[EpisodeSchedule]) -> None:
        records = list(schedules)
        with self._transaction() as connection:
            connection.execute("DELETE FROM episode_schedules WHERE anime_id=?", (anime_id,))
            connection.executemany(
                """INSERT INTO episode_schedules(id, anime_id, episode, air_at, source, synced_at)
                VALUES(?, ?, ?, ?, ?, ?)""",
                [
                    (item.id, anime_id, item.episode, item.air_at, item.source.value, item.synced_at)
                    for item in records
                ],
            )

    def save_playback_link(self, link: PlaybackLink) -> None:
        with self._transaction() as connection:
            if link.is_default:
                connection.execute("UPDATE playback_links SET is_default=0 WHERE anime_id=?", (link.anime_id,))
            connection.execute(
                """INSERT INTO playback_links(id, anime_id, name, url, sort_order, is_default, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, url=excluded.url,
                sort_order=excluded.sort_order, is_default=excluded.is_default, updated_at=excluded.updated_at""",
                (
                    link.id,
                    link.anime_id,
                    link.name,
                    link.url,
                    link.sort_order,
                    int(link.is_default),
                    link.updated_at,
                ),
            )
            default_count = connection.execute(
                "SELECT COUNT(*) FROM playback_links WHERE anime_id=? AND is_default=1", (link.anime_id,)
            ).fetchone()[0]
            if default_count == 0:
                connection.execute(
                    "UPDATE playback_links SET is_default=1 WHERE id=(SELECT id FROM playback_links WHERE anime_id=? ORDER BY sort_order, id LIMIT 1)",
                    (link.anime_id,),
                )

    def delete_playback_link(self, link_id: str) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT anime_id, is_default FROM playback_links WHERE id=?", (link_id,)
            ).fetchone()
            connection.execute("DELETE FROM playback_links WHERE id=?", (link_id,))
            if row and row["is_default"]:
                connection.execute(
                    "UPDATE playback_links SET is_default=1 WHERE id=(SELECT id FROM playback_links WHERE anime_id=? ORDER BY sort_order, id LIMIT 1)",
                    (row["anime_id"],),
                )

    def get_archive(self) -> list[ArchivedAnime]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""SELECT {', '.join(f'a.{item.strip()}' for item in ANIME_COLUMNS.split(','))},
                r.finished_at, r.note, r.source, r.updated_at AS archive_updated_at
                FROM archive_records r JOIN anime a ON a.id=r.anime_id
                ORDER BY r.finished_at DESC, a.title_cn"""
            ).fetchall()
            result = [
                ArchivedAnime(
                    anime=self._map_anime(row),
                    archive=ArchiveRecord(
                        anime_id=str(row["id"]),
                        finished_at=str(row["finished_at"]),
                        note=str(row["note"]),
                        source=str(row["source"]),
                        updated_at=str(row["archive_updated_at"]),
                    ),
                    links=self._links_for(connection, str(row["id"])),
                )
                for row in rows
            ]
        return result

    def archive_anime(self, record: ArchiveRecord) -> None:
        with self._transaction() as connection:
            connection.execute(
                """INSERT INTO archive_records(anime_id, finished_at, note, source, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(anime_id) DO UPDATE SET finished_at=excluded.finished_at,
                note=excluded.note, source=excluded.source, updated_at=excluded.updated_at""",
                (record.anime_id, record.finished_at, record.note, record.source, record.updated_at),
            )
            connection.execute("DELETE FROM follow_records WHERE anime_id=?", (record.anime_id,))

    def restore_from_archive(self, anime_id: str) -> None:
        timestamp = utc_now_iso()
        with self._transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO follow_records(anime_id, reminder_enabled, created_at, updated_at) VALUES(?, 1, ?, ?)",
                (anime_id, timestamp, timestamp),
            )
            connection.execute("DELETE FROM archive_records WHERE anime_id=?", (anime_id,))

    def delete_archive(self, anime_id: str) -> None:
        with self._transaction() as connection:
            connection.execute("DELETE FROM archive_records WHERE anime_id=?", (anime_id,))

    def get_settings(self) -> AppSettings:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT key, value FROM app_settings").fetchall()
        values = {str(row["key"]): json.loads(str(row["value"])) for row in rows}
        return AppSettings(
            reminder_minutes=int(values.get("reminderMinutes", 15)),
            notifications_enabled=bool(values.get("notificationsEnabled", True)),
            floating_window_enabled=bool(values.get("floatingWindowEnabled", True)),
            autostart_prompted=bool(values.get("autostartPrompted", False)),
            refresh_hours=int(values.get("refreshHours", 6)),
        )

    def save_settings(self, settings: AppSettings) -> None:
        timestamp = utc_now_iso()
        values = {
            "reminderMinutes": settings.reminder_minutes,
            "notificationsEnabled": settings.notifications_enabled,
            "floatingWindowEnabled": settings.floating_window_enabled,
            "autostartPrompted": settings.autostart_prompted,
            "refreshHours": settings.refresh_hours,
        }
        with self._transaction() as connection:
            connection.executemany(
                """INSERT INTO app_settings(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                [(key, json.dumps(value, ensure_ascii=False), timestamp) for key, value in values.items()],
            )

    def create_database_snapshot(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as source, closing(sqlite3.connect(path)) as destination:
            source.backup(destination)

    def restore_database_snapshot(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        with closing(sqlite3.connect(path)) as source, closing(self._connect()) as destination:
            source.backup(destination)

    @staticmethod
    def _anime_values(anime: Anime) -> tuple[object, ...]:
        return (
            anime.id,
            anime.bgm_id,
            anime.anilist_id,
            anime.title_cn,
            anime.title_native,
            anime.summary,
            anime.cover_url,
            anime.cover_data,
            anime.season_year,
            anime.season.value,
            anime.start_date,
            anime.status.value,
            anime.updated_at,
        )

    @staticmethod
    def _map_anime(row: sqlite3.Row) -> Anime:
        try:
            season = Season(str(row["season"]))
        except ValueError:
            season = Season.WINTER
        try:
            status = AnimeStatus(str(row["status"]))
        except ValueError:
            status = AnimeStatus.UNKNOWN
        return Anime(
            id=str(row["id"]),
            bgm_id=int(row["bgm_id"]) if row["bgm_id"] is not None else None,
            anilist_id=int(row["anilist_id"]) if row["anilist_id"] is not None else None,
            title_cn=str(row["title_cn"]),
            title_native=str(row["title_native"]),
            summary=str(row["summary"]),
            cover_url=str(row["cover_url"]),
            cover_data=str(row["cover_data"]),
            season_year=int(row["season_year"]),
            season=season,
            start_date=str(row["start_date"]),
            status=status,
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _schedules_for(connection: sqlite3.Connection, anime_id: str) -> list[EpisodeSchedule]:
        rows = connection.execute(
            "SELECT id, anime_id, episode, air_at, source, synced_at FROM episode_schedules WHERE anime_id=? ORDER BY air_at",
            (anime_id,),
        ).fetchall()
        return [
            EpisodeSchedule(
                id=str(row["id"]),
                anime_id=str(row["anime_id"]),
                episode=int(row["episode"]),
                air_at=str(row["air_at"]),
                source=ScheduleSource(str(row["source"])),
                synced_at=str(row["synced_at"]),
            )
            for row in rows
        ]

    @staticmethod
    def _links_for(connection: sqlite3.Connection, anime_id: str) -> list[PlaybackLink]:
        rows = connection.execute(
            "SELECT id, anime_id, name, url, sort_order, is_default, updated_at FROM playback_links WHERE anime_id=? ORDER BY sort_order, id",
            (anime_id,),
        ).fetchall()
        return [
            PlaybackLink(
                id=str(row["id"]),
                anime_id=str(row["anime_id"]),
                name=str(row["name"]),
                url=str(row["url"]),
                sort_order=int(row["sort_order"]),
                is_default=bool(row["is_default"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]
