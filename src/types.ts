export type Season = "WINTER" | "SPRING" | "SUMMER" | "FALL";
export type AnimeStatus = "upcoming" | "airing" | "finished" | "unknown";
export type ScheduleSource = "anilist" | "manual";
export type BackupKind = "following" | "archive";

export interface Anime {
  id: string;
  bgmId: number | null;
  anilistId: number | null;
  titleCn: string;
  titleNative: string;
  summary: string;
  coverUrl: string;
  coverData: string;
  seasonYear: number;
  season: Season;
  startDate: string;
  status: AnimeStatus;
  updatedAt: string;
}

export interface FollowRecord {
  animeId: string;
  reminderEnabled: boolean;
  reminderMinutes: number | null;
  manualAirAt: string | null;
  lastRemindedScheduleId: string | null;
  snoozedUntil: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface EpisodeSchedule {
  id: string;
  animeId: string;
  episode: number;
  airAt: string;
  source: ScheduleSource;
  syncedAt: string;
}

export interface PlaybackLink {
  id: string;
  animeId: string;
  name: string;
  url: string;
  sortOrder: number;
  isDefault: boolean;
  updatedAt: string;
}

export interface ArchiveRecord {
  animeId: string;
  finishedAt: string;
  note: string;
  source: "followed" | "searched" | "manual" | "imported";
  updatedAt: string;
}

export interface FollowedAnime {
  anime: Anime;
  follow: FollowRecord;
  schedules: EpisodeSchedule[];
  links: PlaybackLink[];
}

export interface ArchivedAnime {
  anime: Anime;
  archive: ArchiveRecord;
  links: PlaybackLink[];
}

export interface AppSettings {
  reminderMinutes: number;
  notificationsEnabled: boolean;
  floatingWindowEnabled: boolean;
  autostartPrompted: boolean;
  refreshHours: number;
}

export const DEFAULT_SETTINGS: AppSettings = {
  reminderMinutes: 15,
  notificationsEnabled: true,
  floatingWindowEnabled: true,
  autostartPrompted: false,
  refreshHours: 6,
};

export interface AniListCandidate {
  id: number;
  titleNative: string;
  titleRomaji: string;
  titleEnglish: string;
  seasonYear: number | null;
  season: Season | null;
  startDate: string;
  status: string;
  nextAiringEpisode: { episode: number; airAt: string } | null;
}

export interface MatchResult {
  candidate: AniListCandidate | null;
  score: number;
  accepted: boolean;
  reasons: string[];
}

export interface ReminderItem {
  scheduleId: string;
  animeId: string;
  title: string;
  cover: string;
  episode: number;
  airAt: string;
  defaultUrl: string | null;
  links: PlaybackLink[];
  alreadyAired: boolean;
}

export interface BackupManifest<T> {
  schemaVersion: 1;
  kind: BackupKind;
  appVersion: string;
  exportedAt: string;
  checksum: string;
  files: Record<string, string>;
  records: T[];
}

export interface FollowingBackupRecord {
  anime: Anime;
  follow: FollowRecord;
  schedules: EpisodeSchedule[];
  links: PlaybackLink[];
  coverFile: string | null;
}

export interface ArchiveBackupRecord {
  anime: Anime;
  archive: ArchiveRecord;
  links: PlaybackLink[];
  coverFile: string | null;
}
