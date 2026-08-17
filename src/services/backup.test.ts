import { describe, expect, it } from "vitest";
import JSZip from "jszip";
import { createRepository } from "../db/repository";
import type { Anime } from "../types";
import { BackupService } from "./backup";

const anime: Anime = {
  id: "bgm:42", bgmId: 42, anilistId: 4242, titleCn: "备份测试", titleNative: "Backup Test",
  summary: "", coverUrl: "", coverData: "data:image/png;base64,iVBORw0KGgo=", seasonYear: 2026,
  season: "SUMMER", startDate: "2026-07-01", status: "airing", updatedAt: "2026-08-14T00:00:00.000Z",
};

describe(".anibackup", () => {
  it("round-trips following data and embedded cover", async () => {
    const source = await createRepository();
    await source.upsertAnime(anime);
    await source.followAnime(anime.id);
    await source.savePlaybackLink({
      id: "link-1", animeId: anime.id, name: "官方", url: "https://example.com/watch", sortOrder: 0,
      isDefault: true, updatedAt: "2026-08-14T00:00:00.000Z",
    });
    const bytes = await new BackupService(source).create("following");

    const target = await createRepository();
    const result = await new BackupService(target).import(bytes);
    const restored = await target.getFollowing();
    expect(result).toEqual({ kind: "following", imported: 1, merged: 0 });
    expect(restored[0]?.anime.titleCn).toBe("备份测试");
    expect(restored[0]?.anime.coverData.startsWith("data:image/png;base64,")).toBe(true);
    expect(restored[0]?.links[0]?.url).toBe("https://example.com/watch");
  });

  it("rejects a modified manifest", async () => {
    const source = await createRepository();
    await source.upsertAnime(anime);
    await source.followAnime(anime.id);
    const bytes = await new BackupService(source).create("following");
    const zip = await JSZip.loadAsync(bytes);
    const manifest = JSON.parse(await zip.file("manifest.json")!.async("text")) as { checksum: string };
    manifest.checksum = "0".repeat(64);
    zip.file("manifest.json", JSON.stringify(manifest));
    const tampered = await zip.generateAsync({ type: "uint8array" });
    const target = await createRepository();
    await expect(new BackupService(target).import(tampered)).rejects.toThrow("校验失败");
  });
});
