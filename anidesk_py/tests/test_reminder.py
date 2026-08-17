from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from anidesk.domain.models import AppSettings, EpisodeSchedule, FollowRecord, FollowedAnime, PlaybackLink
from anidesk.services.reminder import daily_updates, due_reminders


def followed(anime, now: datetime, *, manual: str | None = None, last: str | None = None, snoozed: str | None = None):
    air = (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    schedule = EpisodeSchedule("schedule:1", anime.id, 4, air, synced_at=air)
    return FollowedAnime(
        anime,
        FollowRecord(anime.id, True, None, manual, last, snoozed, air, air),
        [schedule],
        [PlaybackLink("link", anime.id, "默认", "https://example.com", 0, True, air)],
    )


def test_default_lead_and_no_duplicate(anime) -> None:
    now = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    item = followed(anime, now)
    reminders = due_reminders([item], AppSettings(), now)
    assert reminders[0].episode == 4
    assert reminders[0].default_url == "https://example.com"
    item.follow.last_reminded_schedule_id = "schedule:1"
    assert due_reminders([item], AppSettings(), now) == []


def test_manual_time_wins(anime) -> None:
    now = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    manual = (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
    reminders = due_reminders([followed(anime, now, manual=manual)], AppSettings(), now)
    assert reminders[0].schedule_id.startswith("manual:")
    assert reminders[0].air_at == manual


def test_snooze_and_two_hour_window(anime) -> None:
    now = datetime(2026, 8, 15, 8, 0, tzinfo=UTC)
    snoozed = (now + timedelta(minutes=9)).isoformat().replace("+00:00", "Z")
    assert due_reminders([followed(anime, now, snoozed=snoozed)], AppSettings(), now) == []
    old = (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z")
    assert due_reminders([followed(anime, now, manual=old)], AppSettings(), now) == []


def test_daily_updates_contains_yesterday_and_today_in_local_timezone(anime) -> None:
    local_timezone = timezone(timedelta(hours=8))
    now = datetime(2026, 8, 16, 4, 0, tzinfo=UTC)
    item = followed(anime, now)
    item.follow.reminder_enabled = False
    item.schedules = [
        EpisodeSchedule("too-old", anime.id, 1, "2026-08-14T04:00:00Z"),
        EpisodeSchedule("yesterday", anime.id, 2, "2026-08-15T12:00:00Z"),
        EpisodeSchedule("today", anime.id, 3, "2026-08-16T15:00:00Z"),
        EpisodeSchedule("tomorrow", anime.id, 4, "2026-08-16T17:00:00Z"),
    ]

    updates = daily_updates([item], now, local_timezone)

    assert [update.schedule_id for update in updates] == ["yesterday", "today"]
    assert updates[0].already_aired
    assert not updates[1].already_aired
