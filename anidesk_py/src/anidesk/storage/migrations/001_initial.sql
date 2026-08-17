PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  description TEXT NOT NULL,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS anime (
  id TEXT PRIMARY KEY,
  bgm_id INTEGER UNIQUE,
  anilist_id INTEGER,
  title_cn TEXT NOT NULL,
  title_native TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  cover_url TEXT NOT NULL DEFAULT '',
  cover_data TEXT NOT NULL DEFAULT '',
  season_year INTEGER NOT NULL,
  season TEXT NOT NULL,
  start_date TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'unknown',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS follow_records (
  anime_id TEXT PRIMARY KEY REFERENCES anime(id) ON DELETE CASCADE,
  reminder_enabled INTEGER NOT NULL DEFAULT 1,
  reminder_minutes INTEGER,
  manual_air_at TEXT,
  last_reminded_schedule_id TEXT,
  snoozed_until TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS episode_schedules (
  id TEXT PRIMARY KEY,
  anime_id TEXT NOT NULL REFERENCES anime(id) ON DELETE CASCADE,
  episode INTEGER NOT NULL,
  air_at TEXT NOT NULL,
  source TEXT NOT NULL,
  synced_at TEXT NOT NULL,
  UNIQUE(anime_id, episode, source)
);

CREATE TABLE IF NOT EXISTS playback_links (
  id TEXT PRIMARY KEY,
  anime_id TEXT NOT NULL REFERENCES anime(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_default INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL,
  UNIQUE(anime_id, url)
);

CREATE TABLE IF NOT EXISTS archive_records (
  anime_id TEXT PRIMARY KEY REFERENCES anime(id) ON DELETE CASCADE,
  finished_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anime_season ON anime(season_year, season);
CREATE INDEX IF NOT EXISTS idx_schedule_air_at ON episode_schedules(air_at);
