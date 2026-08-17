<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import type { UnlistenFn } from "@tauri-apps/api/event";
import AnimeCover from "./AnimeCover.vue";
import type { ReminderItem } from "../types";
import { createRepository, type Repository } from "../db/repository";
import { ReminderService } from "../services/reminder";
import { openExternal } from "../services/platform";
import { DEFAULT_SETTINGS } from "../types";

const items = ref<ReminderItem[]>([]);
const index = ref(0);
const now = ref(Date.now());
let repository: Repository;
let service: ReminderService;
let unlisten: UnlistenFn | null = null;
let timer: ReturnType<typeof setInterval> | null = null;

const current = computed(() => items.value[index.value] ?? null);
const countdown = computed(() => {
  if (!current.value) return "";
  const delta = new Date(current.value.airAt).getTime() - now.value;
  if (delta <= 0) return "已经播出";
  const minutes = Math.ceil(delta / 60_000);
  return minutes < 60 ? `${minutes} 分钟后播出` : `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分后播出`;
});

onMounted(async () => {
  repository = await createRepository();
  const settings = await repository.getSettings().catch(() => DEFAULT_SETTINGS);
  service = new ReminderService(repository, () => settings);
  try {
    const pending = JSON.parse(localStorage.getItem("anidesk-pending-reminders") || "[]") as ReminderItem[];
    if (Array.isArray(pending)) items.value = pending;
  } catch {
    items.value = [];
  }
  const { listen } = await import("@tauri-apps/api/event");
  unlisten = await listen<ReminderItem[]>("reminder:show", (event) => {
    items.value = event.payload;
    index.value = 0;
    now.value = Date.now();
  });
  timer = setInterval(() => (now.value = Date.now()), 30_000);
});

onBeforeUnmount(() => {
  unlisten?.();
  if (timer) clearInterval(timer);
});

async function hide(): Promise<void> {
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  await getCurrentWindow().hide();
}

async function play(url: string | null): Promise<void> {
  if (url) await openExternal(url);
}

async function snooze(): Promise<void> {
  if (!current.value) return;
  await service.snooze(current.value, 10);
  await hide();
}
</script>

<template>
  <div v-if="current" class="reminder-shell">
    <div class="reminder-drag" data-tauri-drag-region>
      <span data-tauri-drag-region>ANIDESK REMINDER</span>
      <button type="button" aria-label="隐藏" @click="hide">×</button>
    </div>
    <div class="reminder-content">
      <AnimeCover :src="current.cover" :title="current.title" compact />
      <div class="reminder-copy">
        <span class="reminder-status">{{ countdown }}</span>
        <h2>{{ current.title }}</h2>
        <p>{{ current.episode ? `第 ${current.episode} 集` : '新一集' }} · {{ new Date(current.airAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }}</p>
        <div class="reminder-actions">
          <button class="overlay-play" type="button" :disabled="!current.defaultUrl" @click="play(current.defaultUrl)">▶ {{ current.defaultUrl ? '打开播放地址' : '未设置地址' }}</button>
          <button type="button" @click="snooze">10 分钟后提醒</button>
        </div>
      </div>
    </div>
    <div v-if="items.length > 1" class="reminder-pager">
      <button type="button" :disabled="index === 0" @click="index--">‹</button><span>{{ index + 1 }} / {{ items.length }}</span><button type="button" :disabled="index === items.length - 1" @click="index++">›</button>
    </div>
  </div>
</template>
