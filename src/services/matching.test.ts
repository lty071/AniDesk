import { describe, expect, it } from "vitest";
import type { AniListCandidate, Anime } from "../types";
import { bestMatch, scoreCandidate } from "./matching";

const anime: Anime = {
  id: "bgm:1",
  bgmId: 1,
  anilistId: null,
  titleCn: "葬送的芙莉莲",
  titleNative: "葬送のフリーレン",
  summary: "",
  coverUrl: "",
  coverData: "",
  seasonYear: 2023,
  season: "FALL",
  startDate: "2023-09-29",
  status: "finished",
  updatedAt: "2026-01-01T00:00:00.000Z",
};

const matching: AniListCandidate = {
  id: 154587,
  titleNative: "葬送のフリーレン",
  titleRomaji: "Sousou no Frieren",
  titleEnglish: "Frieren: Beyond Journey's End",
  seasonYear: 2023,
  season: "FALL",
  startDate: "2023-09-29",
  status: "FINISHED",
  nextAiringEpisode: null,
};

describe("AniList candidate matching", () => {
  it("accepts an exact title, date and season match", () => {
    const result = scoreCandidate(anime, matching);
    expect(result.score).toBe(100);
    expect(result.accepted).toBe(true);
  });

  it("does not accept a season-only match", () => {
    const result = scoreCandidate(anime, { ...matching, titleNative: "完全不同的动画", startDate: "2023-12-01" });
    expect(result.score).toBe(10);
    expect(result.accepted).toBe(false);
  });

  it("chooses the highest-scoring candidate", () => {
    const weak = { ...matching, id: 2, titleNative: "别的动画", startDate: "2023-11-01" };
    expect(bestMatch(anime, [weak, matching]).candidate?.id).toBe(matching.id);
  });
});
