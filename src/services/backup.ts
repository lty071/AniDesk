import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import JSZip from "jszip";
import type { Repository } from "../db/repository";
import type {
  Anime,
  ArchiveBackupRecord,
  BackupKind,
  BackupManifest,
  FollowingBackupRecord,
  PlaybackLink,
} from "../types";
import { fetchCoverData, isTauri } from "./platform";

export interface ImportResult {
  kind: BackupKind;
  imported: number;
  merged: number;
}

type AnyBackupRecord = FollowingBackupRecord | ArchiveBackupRecord;

function bytesFromDataUrl(dataUrl: string): { bytes: Uint8Array; extension: string } | null {
  const match = /^data:([^;,]+);base64,(.+)$/i.exec(dataUrl);
  if (!match) return null;
  const binary = atob(match[2]!);
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  const mime = match[1]!.toLowerCase();
  const extension = mime.includes("png") ? "png" : mime.includes("webp") ? "webp" : "jpg";
  return { bytes, extension };
}

function dataUrlFromBytes(bytes: Uint8Array, filename: string): string {
  const mime = filename.endsWith(".png") ? "image/png" : filename.endsWith(".webp") ? "image/webp" : "image/jpeg";
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return `data:${mime};base64,${btoa(binary)}`;
}

async function sha256(value: Uint8Array | string): Promise<string> {
  const bytes = typeof value === "string" ? new TextEncoder().encode(value) : value;
  const digest = await crypto.subtle.digest("SHA-256", Uint8Array.from(bytes).buffer);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function checksumPayload<T>(manifest: Omit<BackupManifest<T>, "checksum">): string {
  return JSON.stringify({
    schemaVersion: manifest.schemaVersion,
    kind: manifest.kind,
    appVersion: manifest.appVersion,
    exportedAt: manifest.exportedAt,
    files: manifest.files,
    records: manifest.records,
  });
}

function safeZipEntries(zip: JSZip): void {
  for (const filename of Object.keys(zip.files)) {
    if (filename.includes("..") || filename.startsWith("/") || filename.startsWith("\\")) {
      throw new Error(`备份包含不安全路径：${filename}`);
    }
  }
}

async function ensureCover(anime: Anime): Promise<string> {
  if (anime.coverData) return anime.coverData;
  if (!anime.coverUrl) return "";
  try {
    return await fetchCoverData(anime.coverUrl);
  } catch {
    return "";
  }
}

export class BackupService {
  constructor(private readonly repository: Repository) {}

  async create(kind: BackupKind): Promise<Uint8Array> {
    const zip = new JSZip();
    const files: Record<string, string> = {};
    let records: AnyBackupRecord[];
    if (kind === "following") {
      const followed = await this.repository.getFollowing();
      records = await Promise.all(
        followed.map(async (item) => {
          const coverData = await ensureCover(item.anime);
          const decoded = bytesFromDataUrl(coverData);
          const coverFile = decoded ? `covers/${item.anime.id.replace(/[^a-zA-Z0-9_-]/g, "_")}.${decoded.extension}` : null;
          if (decoded && coverFile) {
            zip.file(coverFile, decoded.bytes);
            files[coverFile] = await sha256(decoded.bytes);
          }
          return { ...item, anime: { ...item.anime, coverData: "" }, coverFile };
        }),
      );
    } else {
      const archive = await this.repository.getArchive();
      records = await Promise.all(
        archive.map(async (item) => {
          const coverData = await ensureCover(item.anime);
          const decoded = bytesFromDataUrl(coverData);
          const coverFile = decoded ? `covers/${item.anime.id.replace(/[^a-zA-Z0-9_-]/g, "_")}.${decoded.extension}` : null;
          if (decoded && coverFile) {
            zip.file(coverFile, decoded.bytes);
            files[coverFile] = await sha256(decoded.bytes);
          }
          return { ...item, anime: { ...item.anime, coverData: "" }, coverFile };
        }),
      );
    }
    const unsigned = {
      schemaVersion: 1 as const,
      kind,
      appVersion: "0.1.0",
      exportedAt: new Date().toISOString(),
      files,
      records,
    };
    const manifest: BackupManifest<AnyBackupRecord> = {
      ...unsigned,
      checksum: await sha256(checksumPayload(unsigned)),
    };
    zip.file("manifest.json", JSON.stringify(manifest, null, 2));
    return zip.generateAsync({ type: "uint8array", compression: "DEFLATE", compressionOptions: { level: 6 } });
  }

  async exportToFile(kind: BackupKind): Promise<boolean> {
    const bytes = await this.create(kind);
    const stamp = new Date().toISOString().slice(0, 16).replace(/[T:]/g, "-");
    const filename = `${kind}-${stamp}.anibackup`;
    if (isTauri()) {
      const path = await save({ defaultPath: filename, filters: [{ name: "AniDesk 备份", extensions: ["anibackup"] }] });
      if (!path) return false;
      await invoke("write_backup_file", { path, bytes: Array.from(bytes) });
      return true;
    }
    const blob = new Blob([bytes as BlobPart], { type: "application/octet-stream" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
    return true;
  }

  async chooseImportFile(): Promise<Uint8Array | null> {
    if (!isTauri()) return null;
    const path = await open({ multiple: false, filters: [{ name: "AniDesk 备份", extensions: ["anibackup"] }] });
    if (!path || Array.isArray(path)) return null;
    const bytes = await invoke<number[]>("read_backup_file", { path });
    return Uint8Array.from(bytes);
  }

  async import(bytes: Uint8Array): Promise<ImportResult> {
    if (bytes.byteLength > 200 * 1024 * 1024) throw new Error("备份文件超过 200 MB 限制");
    const zip = await JSZip.loadAsync(bytes);
    safeZipEntries(zip);
    if (Object.keys(zip.files).length > 5000) throw new Error("备份内文件数量异常");
    const manifestEntry = zip.file("manifest.json");
    if (!manifestEntry) throw new Error("备份缺少 manifest.json");
    const manifest = JSON.parse(await manifestEntry.async("text")) as BackupManifest<AnyBackupRecord>;
    if (manifest.schemaVersion !== 1) throw new Error(`不支持的备份版本：${String(manifest.schemaVersion)}`);
    if (manifest.kind !== "following" && manifest.kind !== "archive") throw new Error("备份类型无效");
    if (!Array.isArray(manifest.records) || typeof manifest.files !== "object") throw new Error("备份结构无效");
    const unsigned = {
      schemaVersion: manifest.schemaVersion,
      kind: manifest.kind,
      appVersion: manifest.appVersion,
      exportedAt: manifest.exportedAt,
      files: manifest.files,
      records: manifest.records,
    };
    if ((await sha256(checksumPayload(unsigned))) !== manifest.checksum) throw new Error("备份清单校验失败");
    let totalEmbeddedBytes = 0;
    for (const [filename, expected] of Object.entries(manifest.files)) {
      const entry = zip.file(filename);
      if (!entry) throw new Error(`备份缺少封面文件：${filename}`);
      const fileBytes = await entry.async("uint8array");
      totalEmbeddedBytes += fileBytes.byteLength;
      if (totalEmbeddedBytes > 250 * 1024 * 1024) throw new Error("备份解压后的封面数据过大");
      if ((await sha256(fileBytes)) !== expected) throw new Error(`文件校验失败：${filename}`);
    }

    const snapshot = await this.create(manifest.kind);
    await this.persistImportSnapshot(manifest.kind, snapshot);
    let imported = 0;
    let merged = 0;
    for (const raw of manifest.records) {
      if (!raw?.anime?.id) throw new Error("备份记录缺少番剧标识");
      const record = structuredClone(raw);
      const current =
        (await this.repository.findAnimeByExternal(record.anime.bgmId, record.anime.anilistId)) ||
        (await this.repository.getAnime(record.anime.id));
      const targetId = current?.id ?? record.anime.id;
      if (current) merged += 1;
      else imported += 1;
      const coverFile = record.coverFile;
      if (coverFile) {
        const coverBytes = await zip.file(coverFile)!.async("uint8array");
        record.anime.coverData = dataUrlFromBytes(coverBytes, coverFile);
      }
      const animeToSave = {
        ...(current && current.updatedAt > record.anime.updatedAt ? current : record.anime),
        id: targetId,
        coverData: record.anime.coverData || current?.coverData || "",
      };
      await this.repository.upsertAnime(animeToSave);
      if (manifest.kind === "following") {
        const following = record as FollowingBackupRecord;
        await this.repository.followAnime(targetId);
        const existing = (await this.repository.getFollowing()).find((item) => item.anime.id === targetId);
        if (!existing || following.follow.updatedAt >= existing.follow.updatedAt) {
          await this.repository.updateFollow(targetId, {
            reminderEnabled: following.follow.reminderEnabled,
            reminderMinutes: following.follow.reminderMinutes,
            manualAirAt: following.follow.manualAirAt,
            lastRemindedScheduleId: following.follow.lastRemindedScheduleId,
            snoozedUntil: following.follow.snoozedUntil,
          });
          await this.repository.replaceSchedules(
            targetId,
            following.schedules.map((item) => ({ ...item, animeId: targetId })),
          );
        }
        await this.mergeLinks(targetId, following.links);
      } else {
        const archived = record as ArchiveBackupRecord;
        const existing = (await this.repository.getArchive()).find((item) => item.anime.id === targetId);
        if (!existing || archived.archive.updatedAt >= existing.archive.updatedAt) {
          await this.repository.archiveAnime({ ...archived.archive, animeId: targetId, source: "imported" });
        }
        await this.mergeLinks(targetId, archived.links);
      }
    }
    return { kind: manifest.kind, imported, merged };
  }

  private async mergeLinks(animeId: string, incoming: PlaybackLink[]): Promise<void> {
    const followed = (await this.repository.getFollowing()).find((item) => item.anime.id === animeId);
    const archived = (await this.repository.getArchive()).find((item) => item.anime.id === animeId);
    const existing = followed?.links ?? archived?.links ?? [];
    for (const link of incoming) {
      const sameUrl = existing.find((item) => item.url.toLocaleLowerCase() === link.url.toLocaleLowerCase());
      if (!sameUrl || link.updatedAt >= sameUrl.updatedAt) {
        await this.repository.savePlaybackLink({ ...link, id: sameUrl?.id ?? link.id, animeId });
      }
    }
  }

  private async persistImportSnapshot(kind: BackupKind, bytes: Uint8Array): Promise<void> {
    const filename = `before-import-${kind}-${new Date().toISOString().replace(/[:.]/g, "-")}.anibackup`;
    if (isTauri()) {
      await invoke("save_import_snapshot", { filename, bytes: Array.from(bytes) });
      return;
    }
    try {
      let binary = "";
      bytes.forEach((byte) => (binary += String.fromCharCode(byte)));
      localStorage.setItem("anidesk-last-import-snapshot", btoa(binary));
    } catch {
      // 浏览器预览模式空间不足时不阻断导入。
    }
  }
}
