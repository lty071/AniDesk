from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo

from anidesk.domain.models import AppSettings, FollowedAnime, ReminderItem
from anidesk.domain.ports import Repository
from .timeutil import parse_iso, utc_now_iso

TWO_HOURS = timedelta(hours=2)


def _as_utc(current_time: datetime | None) -> datetime:
    now = current_time or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _reminder_item(item: FollowedAnime, schedule_id: str, episode: int, air_at: str, now: datetime) -> ReminderItem:
    default_link = next((link for link in item.links if link.is_default), None)
    if default_link is None and item.links:
        default_link = item.links[0]
    return ReminderItem(
        schedule_id=schedule_id,
        anime_id=item.anime.id,
        title=item.anime.title_cn or item.anime.title_native,
        cover=item.anime.cover_data or item.anime.cover_url,
        episode=episode,
        air_at=air_at,
        default_url=default_link.url if default_link else None,
        links=list(item.links),
        already_aired=now >= parse_iso(air_at),
    )


def due_reminders(
    followed: list[FollowedAnime],
    settings: AppSettings,
    current_time: datetime | None = None,
) -> list[ReminderItem]:
    now = _as_utc(current_time)
    result: list[ReminderItem] = []
    for item in followed:
        follow = item.follow
        if not follow.reminder_enabled:
            continue
        if follow.snoozed_until:
            try:
                if parse_iso(follow.snoozed_until) > now:
                    continue
            except ValueError:
                pass
        valid_schedules = []
        for schedule in item.schedules:
            try:
                if parse_iso(schedule.air_at) >= now - TWO_HOURS:
                    valid_schedules.append(schedule)
            except ValueError:
                continue
        valid_schedules.sort(key=lambda schedule: schedule.air_at)
        automatic = valid_schedules[0] if valid_schedules else None
        if follow.manual_air_at:
            schedule_id = f"manual:{item.anime.id}:{follow.manual_air_at}"
            episode = automatic.episode if automatic else 0
            air_at = follow.manual_air_at
        elif automatic:
            schedule_id = automatic.id
            episode = automatic.episode
            air_at = automatic.air_at
        else:
            continue
        if follow.last_reminded_schedule_id == schedule_id:
            continue
        try:
            air_time = parse_iso(air_at)
        except ValueError:
            continue
        lead = timedelta(minutes=follow.reminder_minutes or settings.reminder_minutes)
        if now < air_time - lead or now > air_time + TWO_HOURS:
            continue
        result.append(_reminder_item(item, schedule_id, episode, air_at, now))
    return sorted(result, key=lambda item: item.air_at)


def daily_updates(
    followed: list[FollowedAnime],
    current_time: datetime | None = None,
    local_timezone: tzinfo | None = None,
) -> list[ReminderItem]:
    """Return every followed episode scheduled for yesterday or today locally."""
    now = _as_utc(current_time)
    local_now = now.astimezone(local_timezone) if local_timezone else now.astimezone()
    visible_dates = {local_now.date() - timedelta(days=1), local_now.date()}
    result: list[ReminderItem] = []
    seen: set[str] = set()

    for item in followed:
        candidates: list[tuple[str, int, str]] = []
        if item.follow.manual_air_at:
            episode = item.schedules[0].episode if item.schedules else 0
            candidates.append(
                (f"manual:{item.anime.id}:{item.follow.manual_air_at}", episode, item.follow.manual_air_at)
            )
        else:
            candidates.extend((schedule.id, schedule.episode, schedule.air_at) for schedule in item.schedules)

        for schedule_id, episode, air_at in candidates:
            if schedule_id in seen:
                continue
            try:
                local_air_time = parse_iso(air_at).astimezone(local_now.tzinfo)
            except ValueError:
                continue
            if local_air_time.date() not in visible_dates:
                continue
            seen.add(schedule_id)
            result.append(_reminder_item(item, schedule_id, episode, air_at, now))

    return sorted(result, key=lambda item: parse_iso(item.air_at))


class ReminderService:
    def __init__(self, repository: Repository, settings: Callable[[], AppSettings]) -> None:
        self.repository = repository
        self.settings = settings

    def check(self, current_time: datetime | None = None) -> list[ReminderItem]:
        items, _updates = self.check_with_updates(current_time)
        return items

    def check_with_updates(
        self, current_time: datetime | None = None
    ) -> tuple[list[ReminderItem], list[ReminderItem]]:
        followed = self.repository.get_following()
        items = due_reminders(followed, self.settings(), current_time)
        updates = daily_updates(followed, current_time)
        for item in items:
            self.repository.update_follow(
                item.anime_id,
                last_reminded_schedule_id=item.schedule_id,
                snoozed_until=None,
            )
        return items, updates

    def snooze(self, item: ReminderItem, minutes: int = 10) -> None:
        until = datetime.now(UTC) + timedelta(minutes=minutes)
        self.repository.update_follow(
            item.anime_id,
            last_reminded_schedule_id=None,
            snoozed_until=until.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        )

    def acknowledge(self, item: ReminderItem) -> None:
        self.repository.update_follow(
            item.anime_id,
            last_reminded_schedule_id=item.schedule_id,
            snoozed_until=None,
        )
