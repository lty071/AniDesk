from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from anidesk.domain.models import Season

SEASON_MONTHS: dict[Season, tuple[int, ...]] = {
    Season.WINTER: (1, 2, 3),
    Season.SPRING: (4, 5, 6),
    Season.SUMMER: (7, 8, 9),
    Season.FALL: (10, 11, 12),
}

SEASON_LABELS: dict[Season, str] = {
    Season.WINTER: "冬季",
    Season.SPRING: "春季",
    Season.SUMMER: "夏季",
    Season.FALL: "秋季",
}


def season_for_month(month: int) -> Season:
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    if month <= 3:
        return Season.WINTER
    if month <= 6:
        return Season.SPRING
    if month <= 9:
        return Season.SUMMER
    return Season.FALL


def current_season(value: date | datetime | None = None) -> tuple[int, Season]:
    current = value or datetime.now()
    return current.year, season_for_month(current.month)


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def iso_date(year: int | None, month: int | None, day: int | None) -> str:
    if not year or not month or not day:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"
