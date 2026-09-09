from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import threading
import time

from anidesk.domain.models import Anime, AniListCandidate, EpisodeSchedule, ScheduleSource, Season
from anidesk.services.season import iso_date
from anidesk.services.timeutil import utc_now_iso
from .http import ProviderError, checked_response, translate_http_error


class AniListScheduleProvider:
    endpoint = "https://graphql.anilist.co"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=httpx.Timeout(15.0, connect=8.0))
        self._request_lock = threading.Lock()
        self._next_request = 0.0
        self._cooldown = 0.0

    def _post(self, query, variables):
        with self._request_lock:
            if time.monotonic() < self._cooldown:
                raise ProviderError("AniList 暂时不可用，稍后自动重试")
            for attempt in range(2):
                time.sleep(max(0, self._next_request - time.monotonic()))
                self._next_request = time.monotonic() + 2.1
                try:
                    response = self._client.post(self.endpoint,
                        headers={"Accept": "application/json", "Content-Type": "application/json"},
                        json={"query": query, "variables": variables})
                except httpx.TransportError:
                    if attempt == 0:
                        self._next_request = time.monotonic() + 2
                        continue
                    self._cooldown = time.monotonic() + 60
                    raise
                if response.status_code == 429:
                    try:
                        delay = max(60, float(response.headers.get("Retry-After", "60")))
                    except ValueError:
                        delay = 60
                    self._cooldown = time.monotonic() + delay
                elif response.status_code >= 500:
                    if attempt == 0:
                        self._next_request = time.monotonic() + 2
                        continue
                    self._cooldown = time.monotonic() + 60
                return response

    def _graphql(self, query: str, variables: dict[str, object]) -> dict[str, Any]:
        try:
            response = checked_response(
                self._post(query, variables),
                "AniList",
            )
            payload = response.json()
            errors = payload.get("errors") or []
            if errors:
                raise ProviderError("；".join(str(item.get("message") or "AniList 查询失败") for item in errors))
            data = payload.get("data")
            if not isinstance(data, dict):
                raise ProviderError("AniList 返回了空数据")
            return data
        except Exception as error:
            raise translate_http_error(error, "AniList") from error

    def find_candidates(self, anime: Anime) -> list[AniListCandidate]:
        query = """
        query Candidates($search: String!, $seasonYear: Int) {
          Page(page: 1, perPage: 10) {
            media(type: ANIME, search: $search, seasonYear: $seasonYear, sort: SEARCH_MATCH) {
              id title { native romaji english } seasonYear season status
              startDate { year month day }
              nextAiringEpisode { episode airingAt }
            }
          }
        }
        """
        data = self._graphql(
            query,
            {"search": anime.title_native or anime.title_cn, "seasonYear": anime.season_year},
        )
        media = ((data.get("Page") or {}).get("media") or [])
        return [self._map_candidate(item) for item in media]

    def get_schedule(self, anime_id: str, anilist_id: int) -> list[EpisodeSchedule]:
        query = """
        query Schedule($id: Int!, $since: Int!, $page: Int!) {
          Page(page: $page, perPage: 50) {
            pageInfo { hasNextPage }
            airingSchedules(mediaId: $id, airingAt_greater: $since, sort: TIME) {
              episode airingAt
            }
          }
        }
        """
        # Query near the current date instead of the first page of a series'
        # entire history. Three days includes yesterday in every local timezone
        # and across DST changes, retaining the floating window's daily updates.
        since = int((datetime.now(UTC) - timedelta(days=3)).timestamp()) - 1
        nodes: dict[int, dict[str, Any]] = {}
        page = 1
        while True:
            data = self._graphql(query, {"id": anilist_id, "since": since, "page": page})
            result = data.get("Page") or {}
            batch = result.get("airingSchedules") or []
            for node in batch:
                nodes[int(node["episode"])] = node
            if not batch or not (result.get("pageInfo") or {}).get("hasNextPage"):
                break
            page += 1
        synced_at = utc_now_iso()
        return [
            EpisodeSchedule(
                id=f"anilist:{anilist_id}:{int(node['episode'])}",
                anime_id=anime_id,
                episode=int(node["episode"]),
                air_at=self._epoch_iso(int(node["airingAt"])),
                source=ScheduleSource.ANILIST,
                synced_at=synced_at,
            )
            for node in sorted(nodes.values(), key=lambda node: (int(node["airingAt"]), int(node["episode"])))
        ]

    @staticmethod
    def _epoch_iso(value: int) -> str:
        return datetime.fromtimestamp(value, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @classmethod
    def _map_candidate(cls, media: dict[str, Any]) -> AniListCandidate:
        title = media.get("title") or {}
        start = media.get("startDate") or {}
        next_episode = media.get("nextAiringEpisode")
        season_raw = media.get("season")
        try:
            season = Season(str(season_raw)) if season_raw else None
        except ValueError:
            season = None
        return AniListCandidate(
            id=int(media["id"]),
            title_native=str(title.get("native") or ""),
            title_romaji=str(title.get("romaji") or ""),
            title_english=str(title.get("english") or ""),
            season_year=int(media["seasonYear"]) if media.get("seasonYear") is not None else None,
            season=season,
            start_date=iso_date(start.get("year"), start.get("month"), start.get("day")),
            status=str(media.get("status") or "UNKNOWN"),
            next_airing_episode=(
                (int(next_episode["episode"]), cls._epoch_iso(int(next_episode["airingAt"])))
                if next_episode
                else None
            ),
        )
