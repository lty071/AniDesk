from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Season(StrEnum):
    WINTER = "WINTER"
    SPRING = "SPRING"
    SUMMER = "SUMMER"
    FALL = "FALL"


class AnimeStatus(StrEnum):
    UPCOMING = "upcoming"
    AIRING = "airing"
    FINISHED = "finished"
    UNKNOWN = "unknown"


class ScheduleSource(StrEnum):
    ANILIST = "anilist"
    MANUAL = "manual"


class BackupKind(StrEnum):
    FOLLOWING = "following"
    ARCHIVE = "archive"


@dataclass(slots=True)
class Anime:
    id: str
    bgm_id: int | None
    anilist_id: int | None
    title_cn: str
    title_native: str
    summary: str = ""
    cover_url: str = ""
    cover_data: str = ""
    season_year: int = 0
    season: Season = Season.WINTER
    start_date: str = ""
    status: AnimeStatus = AnimeStatus.UNKNOWN
    updated_at: str = ""


@dataclass(slots=True)
class FollowRecord:
    anime_id: str
    reminder_enabled: bool = True
    reminder_minutes: int | None = None
    manual_air_at: str | None = None
    last_reminded_schedule_id: str | None = None
    snoozed_until: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class EpisodeSchedule:
    id: str
    anime_id: str
    episode: int
    air_at: str
    source: ScheduleSource = ScheduleSource.ANILIST
    synced_at: str = ""


@dataclass(slots=True)
class PlaybackLink:
    id: str
    anime_id: str
    name: str
    url: str
    sort_order: int = 0
    is_default: bool = False
    updated_at: str = ""


@dataclass(slots=True)
class ArchiveRecord:
    anime_id: str
    finished_at: str
    note: str = ""
    source: str = "manual"
    updated_at: str = ""


@dataclass(slots=True)
class FollowedAnime:
    anime: Anime
    follow: FollowRecord
    schedules: list[EpisodeSchedule] = field(default_factory=list)
    links: list[PlaybackLink] = field(default_factory=list)


@dataclass(slots=True)
class ArchivedAnime:
    anime: Anime
    archive: ArchiveRecord
    links: list[PlaybackLink] = field(default_factory=list)


@dataclass(slots=True)
class AppSettings:
    reminder_minutes: int = 15
    notifications_enabled: bool = True
    floating_window_enabled: bool = True
    autostart_prompted: bool = False
    refresh_hours: int = 6


@dataclass(slots=True)
class AniListCandidate:
    id: int
    title_native: str
    title_romaji: str
    title_english: str
    season_year: int | None
    season: Season | None
    start_date: str
    status: str
    next_airing_episode: tuple[int, str] | None = None


@dataclass(slots=True)
class MatchResult:
    candidate: AniListCandidate | None
    score: int
    accepted: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReminderItem:
    schedule_id: str
    anime_id: str
    title: str
    cover: str
    episode: int
    air_at: str
    default_url: str | None
    links: list[PlaybackLink]
    already_aired: bool
