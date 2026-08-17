import type { AniListCandidate, Anime, MatchResult } from "../types";
import { normalizeTitle } from "./season";

function dayDifference(left: string, right: string): number | null {
  if (!left || !right) return null;
  const delta = Math.abs(new Date(left).getTime() - new Date(right).getTime());
  return Math.round(delta / 86_400_000);
}

export function scoreCandidate(anime: Anime, candidate: AniListCandidate): MatchResult {
  let score = 0;
  const reasons: string[] = [];
  const sourceNames = [anime.titleNative, anime.titleCn].map(normalizeTitle).filter(Boolean);
  const candidateNames = [candidate.titleNative, candidate.titleRomaji, candidate.titleEnglish]
    .map(normalizeTitle)
    .filter(Boolean);
  if (sourceNames.some((name) => candidateNames.includes(name))) {
    score += 70;
    reasons.push("标题完全一致");
  }
  const days = dayDifference(anime.startDate, candidate.startDate);
  if (days != null && days <= 7) {
    score += 20;
    reasons.push("首播日期相差不超过 7 天");
  }
  if (anime.seasonYear === candidate.seasonYear && anime.season === candidate.season) {
    score += 10;
    reasons.push("季度一致");
  }
  return { candidate, score, accepted: score >= 80, reasons };
}

export function bestMatch(anime: Anime, candidates: AniListCandidate[]): MatchResult {
  if (!candidates.length) return { candidate: null, score: 0, accepted: false, reasons: ["没有候选条目"] };
  return candidates.map((item) => scoreCandidate(anime, item)).sort((a, b) => b.score - a.score)[0]!;
}
