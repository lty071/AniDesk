import { markRaw, ref } from "vue";
import { defineStore } from "pinia";
import type { Repository } from "../db/repository";
import { createRepository } from "../db/repository";
import type {
  Anime,
  AniListCandidate,
  AppSettings,
  ArchivedAnime,
  FollowedAnime,
  PlaybackLink,
  Season,
} from "../types";
import { DEFAULT_SETTINGS } from "../types";
import { BackupService } from "../services/backup";
import { BangumiCatalogProvider } from "../services/catalog";
import { bestMatch } from "../services/matching";
import { fetchCoverData, validPlaybackUrl } from "../services/platform";
import { AniListScheduleProvider } from "../services/schedule";
import { currentSeason } from "../services/season";
import { ReminderService } from "../services/reminder";

export type AppView = "season" | "following" | "archive" | "settings";

const timestamp = () => new Date().toISOString();

export const useAppStore = defineStore("app", () => {
  const initialSeason = currentSeason();
  const activeView = ref<AppView>("season");
  const seasonYear = ref(initialSeason.year);
  const season = ref<Season>(initialSeason.season);
  const catalog = ref<Anime[]>([]);
  const following = ref<FollowedAnime[]>([]);
  const archive = ref<ArchivedAnime[]>([]);
  const searchResults = ref<Anime[]>([]);
  const settings = ref<AppSettings>({ ...DEFAULT_SETTINGS });
  const loading = ref(false);
  const syncing = ref(false);
  const error = ref("");
  const notice = ref("");
  const lastCatalogSync = ref<string | null>(null);
  let repository: Repository;
  let reminders: ReminderService | null = null;
  let scheduleRefreshTimer: ReturnType<typeof setInterval> | null = null;
  const catalogProvider = new BangumiCatalogProvider();
  const scheduleProvider = new AniListScheduleProvider();

  async function initialize(): Promise<void> {
    repository = markRaw(await createRepository());
    settings.value = await repository.getSettings();
    await reloadCollections();
    catalog.value = await repository.getSeason(seasonYear.value, season.value);
    reminders = markRaw(new ReminderService(repository, () => settings.value));
    reminders.start();
    scheduleRefreshTimer = setInterval(() => void syncAllSchedules(), settings.value.refreshHours * 3_600_000);
    await refreshSeason();
    void syncAllSchedules();
  }

  async function reloadCollections(): Promise<void> {
    [following.value, archive.value] = await Promise.all([repository.getFollowing(), repository.getArchive()]);
  }

  async function refreshSeason(): Promise<void> {
    loading.value = true;
    error.value = "";
    try {
      const remote = await catalogProvider.listSeason(seasonYear.value, season.value);
      await repository.upsertAnime(remote);
      catalog.value = await repository.getSeason(seasonYear.value, season.value);
      lastCatalogSync.value = timestamp();
    } catch (reason) {
      catalog.value = await repository.getSeason(seasonYear.value, season.value);
      error.value = catalog.value.length
        ? "网络刷新失败，正在显示上次缓存。"
        : reason instanceof Error
          ? reason.message
          : "季度目录加载失败";
    } finally {
      loading.value = false;
    }
  }

  async function changeSeason(year: number, nextSeason: Season): Promise<void> {
    seasonYear.value = year;
    season.value = nextSeason;
    catalog.value = await repository.getSeason(year, nextSeason);
    await refreshSeason();
  }

  async function follow(anime: Anime): Promise<void> {
    error.value = "";
    await repository.upsertAnime(anime);
    await repository.followAnime(anime.id);
    void cacheCover(anime);
    await reloadCollections();
    await syncOneSchedule(anime.id);
    notice.value = `已追更《${anime.titleCn}》`;
  }

  async function unfollow(animeId: string): Promise<void> {
    await repository.unfollowAnime(animeId);
    await reloadCollections();
  }

  async function cacheCover(anime: Anime): Promise<void> {
    if (anime.coverData || !anime.coverUrl) return;
    try {
      const coverData = await fetchCoverData(anime.coverUrl);
      await repository.upsertAnime({ ...anime, coverData, updatedAt: timestamp() });
      await reloadCollections();
    } catch {
      // 远程封面仍可展示，缓存失败不影响主流程。
    }
  }

  async function syncOneSchedule(animeId: string, selected?: AniListCandidate): Promise<boolean> {
    const current = await repository.getAnime(animeId);
    if (!current) return false;
    try {
      let candidate = selected ?? null;
      if (!candidate && current.anilistId == null) {
        const result = bestMatch(current, await scheduleProvider.findCandidates(current));
        candidate = result.accepted ? result.candidate : null;
        if (!candidate) return false;
      }
      const anilistId = candidate?.id ?? current.anilistId;
      if (anilistId == null) return false;
      if (current.anilistId !== anilistId) {
        await repository.upsertAnime({ ...current, anilistId, updatedAt: timestamp() });
      }
      await repository.replaceSchedules(animeId, await scheduleProvider.getSchedule(animeId, anilistId));
      await reloadCollections();
      return true;
    } catch (reason) {
      error.value = reason instanceof Error ? reason.message : "日程同步失败";
      return false;
    }
  }

  async function getCandidates(animeId: string): Promise<AniListCandidate[]> {
    const anime = await repository.getAnime(animeId);
    return anime ? scheduleProvider.findCandidates(anime) : [];
  }

  async function syncAllSchedules(): Promise<void> {
    if (syncing.value) return;
    syncing.value = true;
    try {
      const items = await repository.getFollowing();
      for (const item of items) await syncOneSchedule(item.anime.id);
    } finally {
      syncing.value = false;
    }
  }

  async function updateFollow(
    animeId: string,
    patch: Parameters<Repository["updateFollow"]>[1],
  ): Promise<void> {
    await repository.updateFollow(animeId, patch);
    await reloadCollections();
  }

  async function saveLink(animeId: string, name: string, url: string, makeDefault: boolean): Promise<void> {
    if (!validPlaybackUrl(url)) throw new Error("请输入有效的 HTTP/HTTPS 地址");
    const owner = following.value.find((item) => item.anime.id === animeId) ?? archive.value.find((item) => item.anime.id === animeId);
    const existing = owner?.links.find((item) => item.url.toLocaleLowerCase() === url.toLocaleLowerCase());
    const link: PlaybackLink = {
      id: existing?.id ?? crypto.randomUUID(),
      animeId,
      name: name.trim() || new URL(url).hostname,
      url,
      sortOrder: existing?.sortOrder ?? owner?.links.length ?? 0,
      isDefault: makeDefault || !owner?.links.length,
      updatedAt: timestamp(),
    };
    await repository.savePlaybackLink(link);
    await reloadCollections();
  }

  async function deleteLink(id: string): Promise<void> {
    await repository.deletePlaybackLink(id);
    await reloadCollections();
  }

  async function archiveFollowing(animeId: string, finishedAt: string, note: string): Promise<void> {
    await repository.archiveAnime({ animeId, finishedAt, note, source: "followed", updatedAt: timestamp() });
    await reloadCollections();
  }

  async function saveArchive(animeId: string, finishedAt: string, note: string, source: "searched" | "manual"): Promise<void> {
    await repository.archiveAnime({ animeId, finishedAt, note, source, updatedAt: timestamp() });
    await reloadCollections();
  }

  async function restoreArchive(animeId: string): Promise<void> {
    await repository.restoreFromArchive(animeId);
    await reloadCollections();
    void syncOneSchedule(animeId);
  }

  async function deleteArchive(animeId: string): Promise<void> {
    await repository.deleteArchive(animeId);
    await reloadCollections();
  }

  async function searchAnime(query: string): Promise<void> {
    if (!query.trim()) {
      searchResults.value = [];
      return;
    }
    loading.value = true;
    try {
      searchResults.value = await catalogProvider.search(query.trim());
    } finally {
      loading.value = false;
    }
  }

  async function addSearchedToArchive(anime: Anime): Promise<void> {
    await repository.upsertAnime(anime);
    void cacheCover(anime);
    await saveArchive(anime.id, new Date().toISOString().slice(0, 10), "", "searched");
  }

  async function addManualAnime(input: { titleCn: string; titleNative: string; coverData: string; finishedAt: string; note: string }): Promise<void> {
    const current = currentSeason(new Date(`${input.finishedAt}T00:00:00`));
    const anime: Anime = {
      id: crypto.randomUUID(),
      bgmId: null,
      anilistId: null,
      titleCn: input.titleCn.trim(),
      titleNative: input.titleNative.trim(),
      summary: "",
      coverUrl: "",
      coverData: input.coverData,
      seasonYear: current.year,
      season: current.season,
      startDate: "",
      status: "finished",
      updatedAt: timestamp(),
    };
    await repository.upsertAnime(anime);
    await saveArchive(anime.id, input.finishedAt, input.note, "manual");
  }

  async function updateArchiveNote(animeId: string, finishedAt: string, note: string): Promise<void> {
    const current = archive.value.find((item) => item.anime.id === animeId);
    if (!current) return;
    await repository.archiveAnime({ ...current.archive, finishedAt, note, updatedAt: timestamp() });
    await reloadCollections();
  }

  async function saveAppSettings(next: AppSettings): Promise<void> {
    settings.value = { ...next };
    await repository.saveSettings(settings.value);
    if (scheduleRefreshTimer) clearInterval(scheduleRefreshTimer);
    scheduleRefreshTimer = setInterval(() => void syncAllSchedules(), settings.value.refreshHours * 3_600_000);
  }

  function backupService(): BackupService {
    return new BackupService(repository);
  }

  function clearMessages(): void {
    error.value = "";
    notice.value = "";
  }

  return {
    activeView,
    seasonYear,
    season,
    catalog,
    following,
    archive,
    searchResults,
    settings,
    loading,
    syncing,
    error,
    notice,
    lastCatalogSync,
    initialize,
    reloadCollections,
    refreshSeason,
    changeSeason,
    follow,
    unfollow,
    syncOneSchedule,
    getCandidates,
    syncAllSchedules,
    updateFollow,
    saveLink,
    deleteLink,
    archiveFollowing,
    saveArchive,
    restoreArchive,
    deleteArchive,
    searchAnime,
    addSearchedToArchive,
    addManualAnime,
    updateArchiveNote,
    saveAppSettings,
    backupService,
    clearMessages,
  };
});
