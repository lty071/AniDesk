import type { Repository } from "../db/repository";
import type { AppSettings, FollowedAnime, ReminderItem } from "../types";
import { isTauri } from "./platform";

const TWO_HOURS = 2 * 60 * 60 * 1000;

export function dueReminders(
  followed: FollowedAnime[],
  settings: AppSettings,
  currentTime = new Date(),
): ReminderItem[] {
  const currentMs = currentTime.getTime();
  const result: ReminderItem[] = [];
  for (const item of followed) {
    if (!item.follow.reminderEnabled) continue;
    if (item.follow.snoozedUntil && new Date(item.follow.snoozedUntil).getTime() > currentMs) continue;
    const automatic = item.schedules
      .filter((schedule) => new Date(schedule.airAt).getTime() >= currentMs - TWO_HOURS)
      .sort((left, right) => left.airAt.localeCompare(right.airAt))[0];
    const schedule = item.follow.manualAirAt
      ? {
          id: `manual:${item.anime.id}:${item.follow.manualAirAt}`,
          episode: automatic?.episode ?? 0,
          airAt: item.follow.manualAirAt,
        }
      : automatic;
    if (!schedule || item.follow.lastRemindedScheduleId === schedule.id) continue;
    const airMs = new Date(schedule.airAt).getTime();
    if (!Number.isFinite(airMs)) continue;
    const lead = (item.follow.reminderMinutes ?? settings.reminderMinutes) * 60_000;
    if (currentMs < airMs - lead || currentMs > airMs + TWO_HOURS) continue;
    const defaultLink = item.links.find((link) => link.isDefault) ?? item.links[0] ?? null;
    result.push({
      scheduleId: schedule.id,
      animeId: item.anime.id,
      title: item.anime.titleCn || item.anime.titleNative,
      cover: item.anime.coverData || item.anime.coverUrl,
      episode: schedule.episode,
      airAt: schedule.airAt,
      defaultUrl: defaultLink?.url ?? null,
      links: item.links,
      alreadyAired: currentMs >= airMs,
    });
  }
  return result.sort((left, right) => left.airAt.localeCompare(right.airAt));
}

export class ReminderService {
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly repository: Repository,
    private readonly getSettings: () => AppSettings,
  ) {}

  start(): void {
    if (this.timer) return;
    void this.check();
    this.timer = setInterval(() => void this.check(), 60_000);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  async check(): Promise<ReminderItem[]> {
    const followed = await this.repository.getFollowing();
    const items = dueReminders(followed, this.getSettings());
    if (!items.length) return [];
    const settings = this.getSettings();
    if (isTauri()) {
      if (settings.notificationsEnabled) await this.sendNotifications(items);
      if (settings.floatingWindowEnabled) await this.showOverlay(items);
    }
    for (const item of items) {
      await this.repository.updateFollow(item.animeId, {
        lastRemindedScheduleId: item.scheduleId,
        snoozedUntil: null,
      });
    }
    return items;
  }

  async snooze(item: ReminderItem, minutes = 10): Promise<void> {
    await this.repository.updateFollow(item.animeId, {
      lastRemindedScheduleId: null,
      snoozedUntil: new Date(Date.now() + minutes * 60_000).toISOString(),
    });
  }

  private async sendNotifications(items: ReminderItem[]): Promise<void> {
    const notification = await import("@tauri-apps/plugin-notification");
    let allowed = await notification.isPermissionGranted();
    if (!allowed) allowed = (await notification.requestPermission()) === "granted";
    if (!allowed) return;
    for (const item of items) {
      const body = item.alreadyAired
        ? `${item.episode ? `第 ${item.episode} 集` : "新一集"}已经播出`
        : `${item.episode ? `第 ${item.episode} 集` : "新一集"}将在 ${new Date(item.airAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} 播出`;
      notification.sendNotification({ title: item.title, body });
    }
  }

  private async showOverlay(items: ReminderItem[]): Promise<void> {
    localStorage.setItem("anidesk-pending-reminders", JSON.stringify(items));
    const [{ emitTo }, { currentMonitor, getAllWindows, LogicalPosition }] = await Promise.all([
      import("@tauri-apps/api/event"),
      import("@tauri-apps/api/window"),
    ]);
    const overlay = (await getAllWindows()).find((window) => window.label === "reminder");
    if (!overlay) return;
    await emitTo("reminder", "reminder:show", items);
    const monitor = await currentMonitor();
    if (monitor) {
      const scale = monitor.scaleFactor;
      const width = 400;
      const x = monitor.position.x / scale + monitor.size.width / scale - width - 24;
      const y = monitor.position.y / scale + 24;
      await overlay.setPosition(new LogicalPosition(x, y));
    }
    await overlay.show();
    await overlay.setFocus();
  }
}
