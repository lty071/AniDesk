import type { Anime, Season } from "../types";
import { httpFetch } from "./platform";
import { monthsForSeason } from "./season";

interface BangumiSubject {
  id: number;
  name: string;
  name_cn?: string;
  summary?: string;
  date?: string;
  images?: { large?: string; common?: string; medium?: string; grid?: string } | null;
}

interface BangumiPage {
  total: number;
  limit: number;
  offset: number;
  data: BangumiSubject[];
}

export interface CatalogProvider {
  listSeason(year: number, season: Season): Promise<Anime[]>;
  search(query: string): Promise<Anime[]>;
}

function statusFromDate(startDate: string): Anime["status"] {
  if (!startDate) return "unknown";
  const start = new Date(`${startDate}T00:00:00`);
  const now = new Date();
  if (start.getTime() > now.getTime()) return "upcoming";
  const ageDays = (now.getTime() - start.getTime()) / 86_400_000;
  return ageDays > 150 ? "finished" : "airing";
}

function mapSubject(subject: BangumiSubject, year: number, season: Season): Anime {
  const timestamp = new Date().toISOString();
  return {
    id: `bgm:${subject.id}`,
    bgmId: subject.id,
    anilistId: null,
    titleCn: subject.name_cn?.trim() || subject.name,
    titleNative: subject.name,
    summary: subject.summary || "",
    coverUrl:
      subject.images?.large || subject.images?.common || subject.images?.medium || subject.images?.grid || "",
    coverData: "",
    seasonYear: year,
    season,
    startDate: subject.date || "",
    status: statusFromDate(subject.date || ""),
    updatedAt: timestamp,
  };
}

export class BangumiCatalogProvider implements CatalogProvider {
  private readonly baseUrl = "https://api.bgm.tv";

  async listSeason(year: number, season: Season): Promise<Anime[]> {
    const pages = await Promise.all(
      monthsForSeason(season).map(async (month) => {
        const url = new URL(`${this.baseUrl}/v0/subjects`);
        url.searchParams.set("type", "2");
        url.searchParams.set("sort", "date");
        url.searchParams.set("year", String(year));
        url.searchParams.set("month", String(month));
        url.searchParams.set("limit", "100");
        const response = await httpFetch(url.toString(), {
          headers: { "User-Agent": "AniDesk/0.1.0 (desktop anime tracker)" },
        });
        if (!response.ok) throw new Error(`Bangumi 返回 ${response.status}`);
        return (await response.json()) as BangumiPage;
      }),
    );
    const deduplicated = new Map<number, Anime>();
    pages.flatMap((page) => page.data).forEach((item) => deduplicated.set(item.id, mapSubject(item, year, season)));
    return [...deduplicated.values()].sort((a, b) => a.startDate.localeCompare(b.startDate));
  }

  async search(query: string): Promise<Anime[]> {
    const response = await httpFetch(`${this.baseUrl}/v0/search/subjects?limit=30`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": "AniDesk/0.1.0 (desktop anime tracker)",
      },
      body: JSON.stringify({ keyword: query, sort: "match", filter: { type: [2], nsfw: false } }),
    });
    if (!response.ok) throw new Error(`Bangumi 搜索失败：${response.status}`);
    const page = (await response.json()) as BangumiPage;
    return page.data.map((item) => {
      const date = item.date ? new Date(`${item.date}T00:00:00`) : new Date();
      const month = date.getMonth() + 1;
      const season: Season = month <= 3 ? "WINTER" : month <= 6 ? "SPRING" : month <= 9 ? "SUMMER" : "FALL";
      return mapSubject(item, date.getFullYear(), season);
    });
  }
}
