import { describe, expect, it } from "vitest";
import { currentSeason, getSeasonForMonth, normalizeTitle } from "./season";

describe("season utilities", () => {
  it.each([
    [1, "WINTER"],
    [3, "WINTER"],
    [4, "SPRING"],
    [7, "SUMMER"],
    [10, "FALL"],
    [12, "FALL"],
  ] as const)("maps month %i to %s", (month, expected) => {
    expect(getSeasonForMonth(month)).toBe(expected);
  });

  it("uses local calendar year and quarter", () => {
    expect(currentSeason(new Date(2026, 7, 14))).toEqual({ year: 2026, season: "SUMMER" });
  });

  it("normalizes punctuation and width", () => {
    expect(normalizeTitle("Ｆｒｉｅｒｅｎ： Beyond Journey! ")).toBe("frierenbeyondjourney");
  });
});
