from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from anidesk.domain.models import Anime, AnimeStatus, Season
from anidesk.services.season import SEASON_MONTHS, season_for_month
from anidesk.services.timeutil import utc_now_iso
from .http import checked_response, translate_http_error


class BangumiCatalogProvider:
    base_url = "https://api.bgm.tv"
    page_size = 100

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=8.0),
            headers={"User-Agent": "AniDesk/0.1.2 (desktop anime tracker)"},
            follow_redirects=True,
        )

    def list_season(self, year: int, season: Season) -> list[Anime]:
        try:
            deduplicated: dict[int, Anime] = {}
            for month in SEASON_MONTHS[season]:
                offset = 0
                while True:
                    payload = self._subject_page(
                        {
                            "type": 2,
                            "sort": "date",
                            "year": year,
                            "month": month,
                            "limit": self.page_size,
                            "offset": offset,
                        }
                    )
                    page = payload.get("data", [])
                    for raw in page:
                        anime = self._map_subject(raw, year, season)
                        deduplicated[int(raw["id"])] = anime

                    next_offset = offset + len(page)
                    total = int(payload.get("total") or 0)
                    if not page or (total and next_offset >= total):
                        break
                    if not total and len(page) < self.page_size:
                        break
                    offset = next_offset
            return sorted(deduplicated.values(), key=lambda item: (item.start_date, item.title_cn))
        except Exception as error:
            raise translate_http_error(error, "Bangumi") from error

    def _subject_page(self, params: dict[str, int | str]) -> dict[str, Any]:
        for attempt in range(2):
            try:
                response = checked_response(
                    self._client.get(f"{self.base_url}/v0/subjects", params=params),
                    "Bangumi",
                )
                return response.json()
            except httpx.TimeoutException:
                if attempt:
                    raise
        return {}

    def search(self, query: str) -> list[Anime]:
        query = query.strip()
        if not query:
            return []
        try:
            response = checked_response(
                self._client.post(
                    f"{self.base_url}/v0/search/subjects",
                    params={"limit": 30},
                    json={"keyword": query, "sort": "match", "filter": {"type": [2], "nsfw": False}},
                ),
                "Bangumi",
            )
            result: list[Anime] = []
            for raw in response.json().get("data", []):
                start = self._parse_date(str(raw.get("date") or ""))
                result.append(self._map_subject(raw, start.year, season_for_month(start.month)))
            return result
        except Exception as error:
            raise translate_http_error(error, "Bangumi") from error

    @staticmethod
    def _parse_date(value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return date.today()

    @classmethod
    def _map_subject(cls, raw: dict[str, Any], year: int, season: Season) -> Anime:
        start_date = str(raw.get("date") or "")
        if start_date:
            start = cls._parse_date(start_date)
            age = (date.today() - start).days
            status = AnimeStatus.UPCOMING if age < 0 else AnimeStatus.FINISHED if age > 150 else AnimeStatus.AIRING
        else:
            status = AnimeStatus.UNKNOWN
        images = raw.get("images") or {}
        native = str(raw.get("name") or "")
        return Anime(
            id=f"bgm:{int(raw['id'])}",
            bgm_id=int(raw["id"]),
            anilist_id=None,
            title_cn=str(raw.get("name_cn") or "").strip() or native,
            title_native=native,
            summary=str(raw.get("summary") or ""),
            cover_url=str(images.get("medium") or images.get("common") or images.get("large") or images.get("grid") or ""),
            season_year=year,
            season=season,
            start_date=start_date,
            status=status,
            updated_at=utc_now_iso(),
        )
