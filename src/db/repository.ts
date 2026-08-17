import type Database from "@tauri-apps/plugin-sql";
import {
  DEFAULT_SETTINGS,
  type Anime,
  type AppSettings,
  type ArchiveRecord,
  type ArchivedAnime,
  type EpisodeSchedule,
  type FollowedAnime,
  type FollowRecord,
  type PlaybackLink,
  type Season,
} from "../types";

export interface FollowPatch {
  reminderEnabled?: boolean;
  reminderMinutes?: number | null;
  manualAirAt?: string | null;
  lastRemindedScheduleId?: string | null;
  snoozedUntil?: string | null;
}

export interface Repository {
  initialize(): Promise<void>;
  upsertAnime(anime: Anime | Anime[]): Promise<void>;
  getAnime(id: string): Promise<Anime | null>;
  findAnimeByExternal(bgmId: number | null, anilistId: number | null): Promise<Anime | null>;
  getSeason(year: number, season: Season): Promise<Anime[]>;
  getFollowing(): Promise<FollowedAnime[]>;
  followAnime(animeId: string): Promise<void>;
  updateFollow(animeId: string, patch: FollowPatch): Promise<void>;
  unfollowAnime(animeId: string): Promise<void>;
  replaceSchedules(animeId: string, schedules: EpisodeSchedule[]): Promise<void>;
  savePlaybackLink(link: PlaybackLink): Promise<void>;
  deletePlaybackLink(id: string): Promise<void>;
  getArchive(): Promise<ArchivedAnime[]>;
  archiveAnime(record: ArchiveRecord): Promise<void>;
  restoreFromArchive(animeId: string): Promise<void>;
  deleteArchive(animeId: string): Promise<void>;
  getSettings(): Promise<AppSettings>;
  saveSettings(settings: AppSettings): Promise<void>;
}

interface StoredState {
  anime: Anime[];
  follows: FollowRecord[];
  schedules: EpisodeSchedule[];
  links: PlaybackLink[];
  archives: ArchiveRecord[];
  settings: AppSettings;
}

const EMPTY_STATE: StoredState = {
  anime: [],
  follows: [],
  schedules: [],
  links: [],
  archives: [],
  settings: { ...DEFAULT_SETTINGS },
};

const now = () => new Date().toISOString();

function isTauri(): boolean {
  return typeof window !== "undefined" && Boolean(window.__TAURI_INTERNALS__);
}

export async function createRepository(): Promise<Repository> {
  if (!isTauri()) {
    const repository = new LocalRepository();
    await repository.initialize();
    return repository;
  }
  const { default: Database } = await import("@tauri-apps/plugin-sql");
  const db = await Database.load("sqlite:anidesk.db");
  const repository = new SqliteRepository(db);
  await repository.initialize();
  return repository;
}

function mapAnime(row: Record<string, unknown>): Anime {
  return {
    id: String(row.id),
    bgmId: row.bgm_id == null ? null : Number(row.bgm_id),
    anilistId: row.anilist_id == null ? null : Number(row.anilist_id),
    titleCn: String(row.title_cn ?? ""),
    titleNative: String(row.title_native ?? ""),
    summary: String(row.summary ?? ""),
    coverUrl: String(row.cover_url ?? ""),
    coverData: String(row.cover_data ?? ""),
    seasonYear: Number(row.season_year),
    season: String(row.season) as Season,
    startDate: String(row.start_date ?? ""),
    status: String(row.status ?? "unknown") as Anime["status"],
    updatedAt: String(row.updated_at),
  };
}

function mapFollow(row: Record<string, unknown>): FollowRecord {
  return {
    animeId: String(row.anime_id),
    reminderEnabled: Boolean(row.reminder_enabled),
    reminderMinutes: row.reminder_minutes == null ? null : Number(row.reminder_minutes),
    manualAirAt: row.manual_air_at == null ? null : String(row.manual_air_at),
    lastRemindedScheduleId:
      row.last_reminded_schedule_id == null ? null : String(row.last_reminded_schedule_id),
    snoozedUntil: row.snoozed_until == null ? null : String(row.snoozed_until),
    createdAt: String(row.created_at),
    updatedAt: String(row.updated_at),
  };
}

function mapSchedule(row: Record<string, unknown>): EpisodeSchedule {
  return {
    id: String(row.id),
    animeId: String(row.anime_id),
    episode: Number(row.episode),
    airAt: String(row.air_at),
    source: String(row.source) as EpisodeSchedule["source"],
    syncedAt: String(row.synced_at),
  };
}

function mapLink(row: Record<string, unknown>): PlaybackLink {
  return {
    id: String(row.id),
    animeId: String(row.anime_id),
    name: String(row.name),
    url: String(row.url),
    sortOrder: Number(row.sort_order),
    isDefault: Boolean(row.is_default),
    updatedAt: String(row.updated_at),
  };
}

function mapArchive(row: Record<string, unknown>): ArchiveRecord {
  return {
    animeId: String(row.anime_id),
    finishedAt: String(row.finished_at),
    note: String(row.note ?? ""),
    source: String(row.source) as ArchiveRecord["source"],
    updatedAt: String(row.updated_at),
  };
}

class SqliteRepository implements Repository {
  constructor(private readonly db: Database) {}

  async initialize(): Promise<void> {
    const statements = [
      `CREATE TABLE IF NOT EXISTS anime (
        id TEXT PRIMARY KEY, bgm_id INTEGER UNIQUE, anilist_id INTEGER,
        title_cn TEXT NOT NULL, title_native TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
        cover_url TEXT NOT NULL DEFAULT '', cover_data TEXT NOT NULL DEFAULT '',
        season_year INTEGER NOT NULL, season TEXT NOT NULL, start_date TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'unknown', updated_at TEXT NOT NULL
      )`,
      `CREATE TABLE IF NOT EXISTS follow_records (
        anime_id TEXT PRIMARY KEY REFERENCES anime(id) ON DELETE CASCADE,
        reminder_enabled INTEGER NOT NULL DEFAULT 1, reminder_minutes INTEGER,
        manual_air_at TEXT, last_reminded_schedule_id TEXT, snoozed_until TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      )`,
      `CREATE TABLE IF NOT EXISTS episode_schedules (
        id TEXT PRIMARY KEY, anime_id TEXT NOT NULL REFERENCES anime(id) ON DELETE CASCADE,
        episode INTEGER NOT NULL, air_at TEXT NOT NULL, source TEXT NOT NULL, synced_at TEXT NOT NULL,
        UNIQUE(anime_id, episode, source)
      )`,
      `CREATE TABLE IF NOT EXISTS playback_links (
        id TEXT PRIMARY KEY, anime_id TEXT NOT NULL REFERENCES anime(id) ON DELETE CASCADE,
        name TEXT NOT NULL, url TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
        is_default INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL,
        UNIQUE(anime_id, url)
      )`,
      `CREATE TABLE IF NOT EXISTS archive_records (
        anime_id TEXT PRIMARY KEY REFERENCES anime(id) ON DELETE CASCADE,
        finished_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', source TEXT NOT NULL, updated_at TEXT NOT NULL
      )`,
      `CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
      )`,
      "CREATE INDEX IF NOT EXISTS idx_anime_season ON anime(season_year, season)",
      "CREATE INDEX IF NOT EXISTS idx_schedule_air_at ON episode_schedules(air_at)",
    ];
    for (const statement of statements) await this.db.execute(statement);
  }

  async upsertAnime(value: Anime | Anime[]): Promise<void> {
    const animeList = Array.isArray(value) ? value : [value];
    for (const anime of animeList) {
      await this.db.execute(
        `INSERT INTO anime
          (id,bgm_id,anilist_id,title_cn,title_native,summary,cover_url,cover_data,season_year,season,start_date,status,updated_at)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
         ON CONFLICT(id) DO UPDATE SET
          bgm_id=excluded.bgm_id,
          anilist_id=COALESCE(excluded.anilist_id, anime.anilist_id),
          title_cn=excluded.title_cn,title_native=excluded.title_native,summary=excluded.summary,
          cover_url=excluded.cover_url,
          cover_data=CASE WHEN excluded.cover_data='' THEN anime.cover_data ELSE excluded.cover_data END,
          season_year=excluded.season_year,season=excluded.season,start_date=excluded.start_date,
          status=excluded.status,updated_at=excluded.updated_at`,
        [
          anime.id,
          anime.bgmId,
          anime.anilistId,
          anime.titleCn,
          anime.titleNative,
          anime.summary,
          anime.coverUrl,
          anime.coverData,
          anime.seasonYear,
          anime.season,
          anime.startDate,
          anime.status,
          anime.updatedAt,
        ],
      );
    }
  }

  async getAnime(id: string): Promise<Anime | null> {
    const rows = await this.db.select<Record<string, unknown>[]>("SELECT * FROM anime WHERE id=$1", [id]);
    return rows[0] ? mapAnime(rows[0]) : null;
  }

  async findAnimeByExternal(bgmId: number | null, anilistId: number | null): Promise<Anime | null> {
    if (bgmId != null) {
      const rows = await this.db.select<Record<string, unknown>[]>("SELECT * FROM anime WHERE bgm_id=$1", [bgmId]);
      if (rows[0]) return mapAnime(rows[0]);
    }
    if (anilistId != null) {
      const rows = await this.db.select<Record<string, unknown>[]>("SELECT * FROM anime WHERE anilist_id=$1", [
        anilistId,
      ]);
      if (rows[0]) return mapAnime(rows[0]);
    }
    return null;
  }

  async getSeason(year: number, season: Season): Promise<Anime[]> {
    const rows = await this.db.select<Record<string, unknown>[]>(
      "SELECT * FROM anime WHERE season_year=$1 AND season=$2 ORDER BY start_date, title_cn",
      [year, season],
    );
    return rows.map(mapAnime);
  }

  async getFollowing(): Promise<FollowedAnime[]> {
    const [animeRows, followRows, scheduleRows, linkRows] = await Promise.all([
      this.db.select<Record<string, unknown>[]>(
        "SELECT a.* FROM anime a JOIN follow_records f ON f.anime_id=a.id ORDER BY f.created_at DESC",
      ),
      this.db.select<Record<string, unknown>[]>("SELECT * FROM follow_records"),
      this.db.select<Record<string, unknown>[]>("SELECT * FROM episode_schedules ORDER BY air_at"),
      this.db.select<Record<string, unknown>[]>("SELECT * FROM playback_links ORDER BY sort_order, name"),
    ]);
    const follows = followRows.map(mapFollow);
    const schedules = scheduleRows.map(mapSchedule);
    const links = linkRows.map(mapLink);
    return animeRows.map((row) => {
      const anime = mapAnime(row);
      return {
        anime,
        follow: follows.find((item) => item.animeId === anime.id)!,
        schedules: schedules.filter((item) => item.animeId === anime.id),
        links: links.filter((item) => item.animeId === anime.id),
      };
    });
  }

  async followAnime(animeId: string): Promise<void> {
    const timestamp = now();
    await this.db.execute(
      `INSERT INTO follow_records
        (anime_id,reminder_enabled,reminder_minutes,manual_air_at,last_reminded_schedule_id,snoozed_until,created_at,updated_at)
       VALUES ($1,1,NULL,NULL,NULL,NULL,$2,$2) ON CONFLICT(anime_id) DO NOTHING`,
      [animeId, timestamp],
    );
    await this.db.execute("DELETE FROM archive_records WHERE anime_id=$1", [animeId]);
  }

  async updateFollow(animeId: string, patch: FollowPatch): Promise<void> {
    const current = (await this.getFollowing()).find((item) => item.anime.id === animeId)?.follow;
    if (!current) return;
    const next = { ...current, ...patch, updatedAt: now() };
    await this.db.execute(
      `UPDATE follow_records SET reminder_enabled=$1,reminder_minutes=$2,manual_air_at=$3,
       last_reminded_schedule_id=$4,snoozed_until=$5,updated_at=$6 WHERE anime_id=$7`,
      [
        next.reminderEnabled ? 1 : 0,
        next.reminderMinutes,
        next.manualAirAt,
        next.lastRemindedScheduleId,
        next.snoozedUntil,
        next.updatedAt,
        animeId,
      ],
    );
  }

  async unfollowAnime(animeId: string): Promise<void> {
    await this.db.execute("DELETE FROM follow_records WHERE anime_id=$1", [animeId]);
  }

  async replaceSchedules(animeId: string, schedules: EpisodeSchedule[]): Promise<void> {
    await this.db.execute("DELETE FROM episode_schedules WHERE anime_id=$1 AND source='anilist'", [animeId]);
    for (const schedule of schedules) {
      await this.db.execute(
        `INSERT INTO episode_schedules (id,anime_id,episode,air_at,source,synced_at)
         VALUES ($1,$2,$3,$4,$5,$6)
         ON CONFLICT(id) DO UPDATE SET air_at=excluded.air_at,synced_at=excluded.synced_at`,
        [schedule.id, schedule.animeId, schedule.episode, schedule.airAt, schedule.source, schedule.syncedAt],
      );
    }
  }

  async savePlaybackLink(link: PlaybackLink): Promise<void> {
    if (link.isDefault) {
      await this.db.execute("UPDATE playback_links SET is_default=0 WHERE anime_id=$1", [link.animeId]);
    }
    await this.db.execute(
      `INSERT INTO playback_links (id,anime_id,name,url,sort_order,is_default,updated_at)
       VALUES ($1,$2,$3,$4,$5,$6,$7)
       ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url,sort_order=excluded.sort_order,
       is_default=excluded.is_default,updated_at=excluded.updated_at`,
      [link.id, link.animeId, link.name, link.url, link.sortOrder, link.isDefault ? 1 : 0, link.updatedAt],
    );
  }

  async deletePlaybackLink(id: string): Promise<void> {
    await this.db.execute("DELETE FROM playback_links WHERE id=$1", [id]);
  }

  async getArchive(): Promise<ArchivedAnime[]> {
    const [animeRows, archiveRows, linkRows] = await Promise.all([
      this.db.select<Record<string, unknown>[]>(
        "SELECT a.* FROM anime a JOIN archive_records r ON r.anime_id=a.id ORDER BY r.finished_at DESC",
      ),
      this.db.select<Record<string, unknown>[]>("SELECT * FROM archive_records"),
      this.db.select<Record<string, unknown>[]>("SELECT * FROM playback_links ORDER BY sort_order, name"),
    ]);
    const archives = archiveRows.map(mapArchive);
    const links = linkRows.map(mapLink);
    return animeRows.map((row) => {
      const anime = mapAnime(row);
      return {
        anime,
        archive: archives.find((item) => item.animeId === anime.id)!,
        links: links.filter((item) => item.animeId === anime.id),
      };
    });
  }

  async archiveAnime(record: ArchiveRecord): Promise<void> {
    await this.db.execute(
      `INSERT INTO archive_records (anime_id,finished_at,note,source,updated_at)
       VALUES ($1,$2,$3,$4,$5)
       ON CONFLICT(anime_id) DO UPDATE SET finished_at=excluded.finished_at,note=excluded.note,
       source=excluded.source,updated_at=excluded.updated_at`,
      [record.animeId, record.finishedAt, record.note, record.source, record.updatedAt],
    );
    await this.db.execute("DELETE FROM follow_records WHERE anime_id=$1", [record.animeId]);
  }

  async restoreFromArchive(animeId: string): Promise<void> {
    await this.followAnime(animeId);
  }

  async deleteArchive(animeId: string): Promise<void> {
    await this.db.execute("DELETE FROM archive_records WHERE anime_id=$1", [animeId]);
  }

  async getSettings(): Promise<AppSettings> {
    const rows = await this.db.select<Record<string, unknown>[]>("SELECT value FROM app_settings WHERE key='general'");
    if (!rows[0]) return { ...DEFAULT_SETTINGS };
    return { ...DEFAULT_SETTINGS, ...(JSON.parse(String(rows[0].value)) as Partial<AppSettings>) };
  }

  async saveSettings(settings: AppSettings): Promise<void> {
    await this.db.execute(
      `INSERT INTO app_settings (key,value,updated_at) VALUES ('general',$1,$2)
       ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at`,
      [JSON.stringify(settings), now()],
    );
  }
}

class LocalRepository implements Repository {
  private readonly storageKey = "anidesk-dev-state-v1";
  private state: StoredState = structuredClone(EMPTY_STATE);

  async initialize(): Promise<void> {
    const raw = typeof localStorage === "undefined" ? null : localStorage.getItem(this.storageKey);
    if (raw) {
      try {
        this.state = { ...structuredClone(EMPTY_STATE), ...(JSON.parse(raw) as StoredState) };
      } catch {
        this.state = structuredClone(EMPTY_STATE);
      }
    }
  }

  private persist(): void {
    if (typeof localStorage !== "undefined") localStorage.setItem(this.storageKey, JSON.stringify(this.state));
  }

  async upsertAnime(value: Anime | Anime[]): Promise<void> {
    const animeList = Array.isArray(value) ? value : [value];
    for (const anime of animeList) {
      const index = this.state.anime.findIndex((item) => item.id === anime.id);
      if (index >= 0) {
        const previous = this.state.anime[index]!;
        this.state.anime[index] = {
          ...previous,
          ...anime,
          anilistId: anime.anilistId ?? previous.anilistId,
          coverData: anime.coverData || previous.coverData,
        };
      } else this.state.anime.push(anime);
    }
    this.persist();
  }

  async getAnime(id: string): Promise<Anime | null> {
    return structuredClone(this.state.anime.find((item) => item.id === id) ?? null);
  }

  async findAnimeByExternal(bgmId: number | null, anilistId: number | null): Promise<Anime | null> {
    const found = this.state.anime.find(
      (item) => (bgmId != null && item.bgmId === bgmId) || (anilistId != null && item.anilistId === anilistId),
    );
    return structuredClone(found ?? null);
  }

  async getSeason(year: number, season: Season): Promise<Anime[]> {
    return structuredClone(
      this.state.anime
        .filter((item) => item.seasonYear === year && item.season === season)
        .sort((a, b) => a.startDate.localeCompare(b.startDate)),
    );
  }

  async getFollowing(): Promise<FollowedAnime[]> {
    return structuredClone(
      this.state.follows
        .map((follow) => {
          const anime = this.state.anime.find((item) => item.id === follow.animeId);
          if (!anime) return null;
          return {
            anime,
            follow,
            schedules: this.state.schedules.filter((item) => item.animeId === anime.id),
            links: this.state.links
              .filter((item) => item.animeId === anime.id)
              .sort((a, b) => a.sortOrder - b.sortOrder),
          };
        })
        .filter((item): item is FollowedAnime => Boolean(item)),
    );
  }

  async followAnime(animeId: string): Promise<void> {
    if (!this.state.follows.some((item) => item.animeId === animeId)) {
      const timestamp = now();
      this.state.follows.push({
        animeId,
        reminderEnabled: true,
        reminderMinutes: null,
        manualAirAt: null,
        lastRemindedScheduleId: null,
        snoozedUntil: null,
        createdAt: timestamp,
        updatedAt: timestamp,
      });
    }
    this.state.archives = this.state.archives.filter((item) => item.animeId !== animeId);
    this.persist();
  }

  async updateFollow(animeId: string, patch: FollowPatch): Promise<void> {
    const follow = this.state.follows.find((item) => item.animeId === animeId);
    if (follow) Object.assign(follow, patch, { updatedAt: now() });
    this.persist();
  }

  async unfollowAnime(animeId: string): Promise<void> {
    this.state.follows = this.state.follows.filter((item) => item.animeId !== animeId);
    this.persist();
  }

  async replaceSchedules(animeId: string, schedules: EpisodeSchedule[]): Promise<void> {
    this.state.schedules = [
      ...this.state.schedules.filter((item) => !(item.animeId === animeId && item.source === "anilist")),
      ...schedules,
    ];
    this.persist();
  }

  async savePlaybackLink(link: PlaybackLink): Promise<void> {
    if (link.isDefault) {
      this.state.links
        .filter((item) => item.animeId === link.animeId)
        .forEach((item) => (item.isDefault = false));
    }
    const index = this.state.links.findIndex((item) => item.id === link.id);
    if (index >= 0) this.state.links[index] = link;
    else this.state.links.push(link);
    this.persist();
  }

  async deletePlaybackLink(id: string): Promise<void> {
    this.state.links = this.state.links.filter((item) => item.id !== id);
    this.persist();
  }

  async getArchive(): Promise<ArchivedAnime[]> {
    return structuredClone(
      this.state.archives
        .map((archive) => {
          const anime = this.state.anime.find((item) => item.id === archive.animeId);
          return anime
            ? { anime, archive, links: this.state.links.filter((item) => item.animeId === anime.id) }
            : null;
        })
        .filter((item): item is ArchivedAnime => Boolean(item))
        .sort((a, b) => b.archive.finishedAt.localeCompare(a.archive.finishedAt)),
    );
  }

  async archiveAnime(record: ArchiveRecord): Promise<void> {
    const index = this.state.archives.findIndex((item) => item.animeId === record.animeId);
    if (index >= 0) this.state.archives[index] = record;
    else this.state.archives.push(record);
    this.state.follows = this.state.follows.filter((item) => item.animeId !== record.animeId);
    this.persist();
  }

  async restoreFromArchive(animeId: string): Promise<void> {
    await this.followAnime(animeId);
  }

  async deleteArchive(animeId: string): Promise<void> {
    this.state.archives = this.state.archives.filter((item) => item.animeId !== animeId);
    this.persist();
  }

  async getSettings(): Promise<AppSettings> {
    return structuredClone({ ...DEFAULT_SETTINGS, ...this.state.settings });
  }

  async saveSettings(settings: AppSettings): Promise<void> {
    this.state.settings = structuredClone(settings);
    this.persist();
  }
}
