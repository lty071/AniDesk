import type { AniListCandidate, Anime, EpisodeSchedule, Season } from "../types";
import { httpFetch } from "./platform";
import { isoDate } from "./season";

interface GraphQlResponse<T> {
  data?: T;
  errors?: { message: string }[];
}

interface AniListMedia {
  id: number;
  title: { native?: string | null; romaji?: string | null; english?: string | null };
  seasonYear?: number | null;
  season?: Season | null;
  startDate: { year?: number | null; month?: number | null; day?: number | null };
  status?: string | null;
  nextAiringEpisode?: { episode: number; airingAt: number } | null;
}

export interface ScheduleProvider {
  findCandidates(anime: Anime): Promise<AniListCandidate[]>;
  getSchedule(animeId: string, anilistId: number): Promise<EpisodeSchedule[]>;
}

async function graphql<T>(query: string, variables: Record<string, unknown>): Promise<T> {
  const response = await httpFetch("https://graphql.anilist.co", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ query, variables }),
  });
  if (!response.ok) throw new Error(`AniList 返回 ${response.status}`);
  const payload = (await response.json()) as GraphQlResponse<T>;
  if (payload.errors?.length) throw new Error(payload.errors.map((item) => item.message).join("；"));
  if (!payload.data) throw new Error("AniList 返回了空数据");
  return payload.data;
}

function mapCandidate(media: AniListMedia): AniListCandidate {
  return {
    id: media.id,
    titleNative: media.title.native || "",
    titleRomaji: media.title.romaji || "",
    titleEnglish: media.title.english || "",
    seasonYear: media.seasonYear ?? null,
    season: media.season ?? null,
    startDate: isoDate(media.startDate),
    status: media.status || "UNKNOWN",
    nextAiringEpisode: media.nextAiringEpisode
      ? {
          episode: media.nextAiringEpisode.episode,
          airAt: new Date(media.nextAiringEpisode.airingAt * 1000).toISOString(),
        }
      : null,
  };
}

export class AniListScheduleProvider implements ScheduleProvider {
  async findCandidates(anime: Anime): Promise<AniListCandidate[]> {
    const query = `
      query Candidates($search: String!, $seasonYear: Int) {
        Page(page: 1, perPage: 10) {
          media(type: ANIME, search: $search, seasonYear: $seasonYear, sort: SEARCH_MATCH) {
            id title { native romaji english } seasonYear season status
            startDate { year month day }
            nextAiringEpisode { episode airingAt }
          }
        }
      }`;
    const data = await graphql<{ Page: { media: AniListMedia[] } }>(query, {
      search: anime.titleNative || anime.titleCn,
      seasonYear: anime.seasonYear,
    });
    return data.Page.media.map(mapCandidate);
  }

  async getSchedule(animeId: string, anilistId: number): Promise<EpisodeSchedule[]> {
    const query = `
      query Schedule($id: Int!) {
        Media(id: $id, type: ANIME) {
          airingSchedule(notYetAired: true, perPage: 50) {
            nodes { episode airingAt }
          }
        }
      }`;
    const data = await graphql<{ Media: { airingSchedule: { nodes: { episode: number; airingAt: number }[] } } }>(
      query,
      { id: anilistId },
    );
    const syncedAt = new Date().toISOString();
    return data.Media.airingSchedule.nodes.map((node) => ({
      id: `anilist:${anilistId}:${node.episode}`,
      animeId,
      episode: node.episode,
      airAt: new Date(node.airingAt * 1000).toISOString(),
      source: "anilist",
      syncedAt,
    }));
  }
}
