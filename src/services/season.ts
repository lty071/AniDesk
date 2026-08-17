import type { Season } from "../types";

const SEASON_MONTHS: Record<Season, number[]> = {
  WINTER: [1, 2, 3],
  SPRING: [4, 5, 6],
  SUMMER: [7, 8, 9],
  FALL: [10, 11, 12],
};

export const SEASON_LABELS: Record<Season, string> = {
  WINTER: "冬季",
  SPRING: "春季",
  SUMMER: "夏季",
  FALL: "秋季",
};

export function getSeasonForMonth(month: number): Season {
  if (month <= 3) return "WINTER";
  if (month <= 6) return "SPRING";
  if (month <= 9) return "SUMMER";
  return "FALL";
}

export function currentSeason(date = new Date()): { year: number; season: Season } {
  return { year: date.getFullYear(), season: getSeasonForMonth(date.getMonth() + 1) };
}

export function monthsForSeason(season: Season): number[] {
  return [...SEASON_MONTHS[season]];
}

export function normalizeTitle(value: string): string {
  return value
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/[\s\p{P}\p{S}]/gu, "");
}

export function isoDate(parts: { year?: number | null; month?: number | null; day?: number | null }): string {
  if (!parts.year || !parts.month || !parts.day) return "";
  return `${parts.year.toString().padStart(4, "0")}-${parts.month.toString().padStart(2, "0")}-${parts.day
    .toString()
    .padStart(2, "0")}`;
}
