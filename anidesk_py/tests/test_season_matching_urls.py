from __future__ import annotations

from anidesk.domain.models import AniListCandidate, Season
from anidesk.services.matching import best_match, score_candidate
from anidesk.services.season import normalize_title, season_for_month
from anidesk.services.urls import valid_playback_url


def test_season_boundaries() -> None:
    assert season_for_month(1) is Season.WINTER
    assert season_for_month(4) is Season.SPRING
    assert season_for_month(7) is Season.SUMMER
    assert season_for_month(10) is Season.FALL


def test_title_normalization() -> None:
    assert normalize_title("Ｆａｔｅ／Zero!") == normalize_title("fate zero")


def test_matching_accepts_exact_title_date_and_season(anime) -> None:
    candidate = AniListCandidate(11, anime.title_native, "", "", 2026, Season.SUMMER, "2026-07-03", "RELEASING")
    result = score_candidate(anime, candidate)
    assert result.score == 100
    assert result.accepted


def test_matching_rejects_low_confidence(anime) -> None:
    candidate = AniListCandidate(12, "Other", "Other", "", 2026, Season.SUMMER, "2026-08-01", "RELEASING")
    assert not best_match(anime, [candidate]).accepted
    assert best_match(anime, []).candidate is None


def test_only_http_playback_urls_are_valid() -> None:
    assert valid_playback_url("https://example.com/watch")
    assert valid_playback_url("http://localhost:8080")
    assert not valid_playback_url("javascript:alert(1)")
    assert not valid_playback_url("file:///C:/secret")
    assert not valid_playback_url("not a url")
