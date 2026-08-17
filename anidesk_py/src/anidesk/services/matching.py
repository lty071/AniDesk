from __future__ import annotations

from datetime import date

from anidesk.domain.models import Anime, AniListCandidate, MatchResult
from .season import normalize_title


def _day_difference(left: str, right: str) -> int | None:
    if not left or not right:
        return None
    try:
        return abs((date.fromisoformat(left) - date.fromisoformat(right)).days)
    except ValueError:
        return None


def score_candidate(anime: Anime, candidate: AniListCandidate) -> MatchResult:
    score = 0
    reasons: list[str] = []
    source_names = {normalize_title(value) for value in (anime.title_native, anime.title_cn) if value}
    candidate_names = {
        normalize_title(value)
        for value in (candidate.title_native, candidate.title_romaji, candidate.title_english)
        if value
    }
    if source_names & candidate_names:
        score += 70
        reasons.append("标题完全一致")
    days = _day_difference(anime.start_date, candidate.start_date)
    if days is not None and days <= 7:
        score += 20
        reasons.append("首播日期相差不超过 7 天")
    if anime.season_year == candidate.season_year and anime.season == candidate.season:
        score += 10
        reasons.append("季度一致")
    return MatchResult(candidate=candidate, score=score, accepted=score >= 80, reasons=reasons)


def best_match(anime: Anime, candidates: list[AniListCandidate]) -> MatchResult:
    if not candidates:
        return MatchResult(candidate=None, score=0, accepted=False, reasons=["没有候选条目"])
    return max((score_candidate(anime, item) for item in candidates), key=lambda result: result.score)
