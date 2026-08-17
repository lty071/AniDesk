from __future__ import annotations

import json

import httpx
import pytest

from anidesk.domain.models import Season
from anidesk.providers import AniListScheduleProvider, BangumiCatalogProvider
from anidesk.providers.http import ProviderError


def test_bangumi_deduplicates_months() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": 1, "name": "Test", "name_cn": "测试", "date": "2026-07-01", "images": {}}]})

    provider = BangumiCatalogProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    result = provider.list_season(2026, Season.SUMMER)
    assert len(result) == 1
    assert result[0].title_cn == "测试"


def test_bangumi_paginates_until_total_and_prefers_medium_cover() -> None:
    july_offsets: list[int] = []

    def subject(identifier: int) -> dict[str, object]:
        return {
            "id": identifier,
            "name": f"Anime {identifier}",
            "name_cn": f"动画 {identifier}",
            "date": "2026-07-01",
            "images": {
                "large": f"https://example.test/{identifier}/large.jpg",
                "medium": f"https://example.test/{identifier}/medium.jpg",
            },
        }

    def handler(request: httpx.Request) -> httpx.Response:
        month = int(request.url.params["month"])
        offset = int(request.url.params["offset"])
        if month != 7:
            return httpx.Response(200, json={"total": 0, "data": []})
        july_offsets.append(offset)
        data = [subject(index) for index in range(offset, min(offset + 100, 101))]
        return httpx.Response(200, json={"total": 101, "data": data})

    provider = BangumiCatalogProvider(httpx.Client(transport=httpx.MockTransport(handler)))

    result = provider.list_season(2026, Season.SUMMER)

    assert len(result) == 101
    assert july_offsets == [0, 100]
    assert result[0].cover_url.endswith("/medium.jpg")


def test_bangumi_retries_one_transient_page_timeout() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, json={"total": 0, "data": []})

    provider = BangumiCatalogProvider(httpx.Client(transport=httpx.MockTransport(handler)))

    assert provider.list_season(2026, Season.SUMMER) == []
    assert attempts == 4


def test_anilist_maps_candidate_and_schedule(anime) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "Candidates" in body["query"]:
            return httpx.Response(200, json={"data": {"Page": {"media": [{"id": 9, "title": {"native": anime.title_native, "romaji": "Test", "english": None}, "seasonYear": 2026, "season": "SUMMER", "status": "RELEASING", "startDate": {"year": 2026, "month": 7, "day": 1}, "nextAiringEpisode": {"episode": 2, "airingAt": 1786752000}}]}}})
        assert "notYetAired: true" not in body["query"]
        return httpx.Response(200, json={"data": {"Media": {"airingSchedule": {"nodes": [{"episode": 2, "airingAt": 1786752000}]}}}})

    provider = AniListScheduleProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.find_candidates(anime)[0].season is Season.SUMMER
    assert provider.get_schedule(anime.id, 9)[0].id == "anilist:9:2"


def test_timeout_has_friendly_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    provider = BangumiCatalogProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError, match="超时"):
        provider.list_season(2026, Season.SUMMER)
