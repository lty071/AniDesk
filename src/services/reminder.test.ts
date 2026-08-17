import { describe, expect, it } from "vitest";
import type { FollowedAnime } from "../types";
import { DEFAULT_SETTINGS } from "../types";
import { dueReminders } from "./reminder";

const now = new Date("2026-08-14T12:00:00.000Z");

function followed(overrides: Partial<FollowedAnime["follow"]> = {}): FollowedAnime {
  return {
    anime: {
      id: "bgm:1", bgmId: 1, anilistId: 1, titleCn: "测试动画", titleNative: "Test", summary: "",
      coverUrl: "", coverData: "", seasonYear: 2026, season: "SUMMER", startDate: "2026-07-01",
      status: "airing", updatedAt: now.toISOString(),
    },
    follow: {
      animeId: "bgm:1", reminderEnabled: true, reminderMinutes: null, manualAirAt: null,
      lastRemindedScheduleId: null, snoozedUntil: null, createdAt: now.toISOString(), updatedAt: now.toISOString(),
      ...overrides,
    },
    schedules: [{
      id: "anilist:1:5", animeId: "bgm:1", episode: 5, airAt: "2026-08-14T12:10:00.000Z",
      source: "anilist", syncedAt: now.toISOString(),
    }],
    links: [{ id: "link", animeId: "bgm:1", name: "官方", url: "https://example.com", sortOrder: 0, isDefault: true, updatedAt: now.toISOString() }],
  };
}

describe("reminder scheduling", () => {
  it("fires inside the default 15-minute lead window", () => {
    const result = dueReminders([followed()], DEFAULT_SETTINGS, now);
    expect(result).toHaveLength(1);
    expect(result[0]?.episode).toBe(5);
  });

  it("honors a per-title lead override", () => {
    expect(dueReminders([followed({ reminderMinutes: 5 })], DEFAULT_SETTINGS, now)).toHaveLength(0);
  });

  it("manual time overrides the automatic schedule", () => {
    const result = dueReminders([followed({ manualAirAt: "2026-08-14T12:05:00.000Z" })], DEFAULT_SETTINGS, now);
    expect(result[0]?.scheduleId.startsWith("manual:")).toBe(true);
  });

  it("does not repeat, fire while snoozed, or fire after two hours", () => {
    expect(dueReminders([followed({ lastRemindedScheduleId: "anilist:1:5" })], DEFAULT_SETTINGS, now)).toHaveLength(0);
    expect(dueReminders([followed({ snoozedUntil: "2026-08-14T12:10:00.000Z" })], DEFAULT_SETTINGS, now)).toHaveLength(0);
    const late = new Date("2026-08-14T14:10:01.000Z");
    expect(dueReminders([followed()], DEFAULT_SETTINGS, late)).toHaveLength(0);
  });
});
