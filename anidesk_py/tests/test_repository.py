from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from anidesk.domain.models import AppSettings, ArchiveRecord, PlaybackLink, Season
from anidesk.services.timeutil import utc_now_iso


def test_repository_round_trip(repository, anime) -> None:
    repository.upsert_anime(anime)
    repository.follow_anime(anime.id)
    repository.save_playback_link(PlaybackLink("link:1", anime.id, "官网", "https://example.com", 0, True, utc_now_iso()))
    following = repository.get_following()
    assert following[0].anime == anime
    assert following[0].links[0].is_default
    repository.archive_anime(ArchiveRecord(anime.id, "2026-08-15", "很好看", "followed", utc_now_iso()))
    assert not repository.get_following()
    assert repository.get_archive()[0].archive.note == "很好看"
    repository.restore_from_archive(anime.id)
    assert repository.get_following()
    assert not repository.get_archive()


def test_playback_default_and_order(repository, anime) -> None:
    repository.upsert_anime(anime)
    now = utc_now_iso()
    repository.save_playback_link(PlaybackLink("one", anime.id, "一", "https://one.example", 0, True, now))
    repository.save_playback_link(PlaybackLink("two", anime.id, "二", "https://two.example", 1, True, now))
    repository.follow_anime(anime.id)
    links = repository.get_following()[0].links
    assert [link.id for link in links] == ["one", "two"]
    assert [link.id for link in links if link.is_default] == ["two"]
    repository.delete_playback_link("two")
    assert repository.get_following()[0].links[0].is_default


def test_settings_survive_restart(repository) -> None:
    expected = AppSettings(30, False, True, True, 12)
    repository.save_settings(expected)
    assert repository.get_settings() == expected


def test_batch_upsert_rolls_back_on_unique_conflict(repository, anime) -> None:
    conflict = replace(anime, id="other")
    with pytest.raises(sqlite3.IntegrityError):
        repository.upsert_anime([anime, conflict])
    assert repository.get_anime(anime.id) is None


def test_concurrent_writes(repository, anime) -> None:
    values = [replace(anime, id=f"manual:{index}", bgm_id=None, title_cn=f"动画 {index}") for index in range(12)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(repository.upsert_anime, values))
    assert len(repository.get_season(2026, Season.SUMMER)) == 12


def test_database_snapshot_restore(repository, anime, tmp_path: Path) -> None:
    repository.upsert_anime(anime)
    snapshot = tmp_path / "snapshot.db"
    repository.create_database_snapshot(snapshot)
    repository.upsert_anime(replace(anime, title_cn="被修改"))
    repository.restore_database_snapshot(snapshot)
    assert repository.get_anime(anime.id).title_cn == anime.title_cn
