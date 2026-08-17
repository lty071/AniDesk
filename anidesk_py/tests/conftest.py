from __future__ import annotations

from pathlib import Path

import pytest

from anidesk.domain.models import Anime, AnimeStatus, Season
from anidesk.services.timeutil import utc_now_iso
from anidesk.storage import SqliteRepository


@pytest.fixture
def repository(tmp_path: Path) -> SqliteRepository:
    value = SqliteRepository(tmp_path / "anidesk.db")
    value.initialize()
    return value


@pytest.fixture
def anime() -> Anime:
    return Anime(
        id="bgm:1",
        bgm_id=1,
        anilist_id=None,
        title_cn="测试动画",
        title_native="テストアニメ",
        summary="summary",
        cover_url="https://example.test/cover.jpg",
        season_year=2026,
        season=Season.SUMMER,
        start_date="2026-07-01",
        status=AnimeStatus.AIRING,
        updated_at=utc_now_iso(),
    )
