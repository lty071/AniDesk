<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useAppStore, type AppView } from "./stores/app";
import { isTauri } from "./services/platform";
import SeasonPage from "./components/SeasonPage.vue";
import FollowingPage from "./components/FollowingPage.vue";
import ArchivePage from "./components/ArchivePage.vue";
import SettingsPage from "./components/SettingsPage.vue";

const store = useAppStore();
const showAutostartPrompt = ref(false);
const navigation: { id: AppView; label: string; icon: string }[] = [
  { id: "season", label: "本季番剧", icon: "季" },
  { id: "following", label: "我的追更", icon: "追" },
  { id: "archive", label: "已看仓库", icon: "藏" },
  { id: "settings", label: "设置", icon: "设" },
];

const pageTitle = computed(() => navigation.find((item) => item.id === store.activeView)?.label ?? "AniDesk");

onMounted(async () => {
  await store.initialize();
  showAutostartPrompt.value = !store.settings.autostartPrompted;
});

async function answerAutostart(enable: boolean): Promise<void> {
  if (enable && isTauri()) {
    const { enable: enableAutostart } = await import("@tauri-apps/plugin-autostart");
    await enableAutostart();
  }
  await store.saveAppSettings({ ...store.settings, autostartPrompted: true });
  showAutostartPrompt.value = false;
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">A</div>
        <div>
          <strong>AniDesk</strong>
          <small>你的桌面追番站</small>
        </div>
      </div>

      <nav class="main-nav" aria-label="主导航">
        <button
          v-for="item in navigation"
          :key="item.id"
          type="button"
          :class="['nav-item', { active: store.activeView === item.id }]"
          @click="store.activeView = item.id"
        >
          <span class="nav-icon">{{ item.icon }}</span>
          <span>{{ item.label }}</span>
          <span v-if="item.id === 'following' && store.following.length" class="nav-count">{{ store.following.length }}</span>
          <span v-if="item.id === 'archive' && store.archive.length" class="nav-count">{{ store.archive.length }}</span>
        </button>
      </nav>

      <div class="sidebar-foot">
        <div class="status-dot"></div>
        <div>
          <strong>本地数据模式</strong>
          <small>资料仅保存在这台电脑</small>
        </div>
      </div>
    </aside>

    <main class="main-area">
      <header class="topbar">
        <div>
          <p class="eyebrow">ANIME COMPANION</p>
          <h1>{{ pageTitle }}</h1>
        </div>
        <div class="topbar-actions">
          <span v-if="store.syncing" class="sync-state"><i></i>正在同步日程</span>
          <button v-if="store.activeView !== 'settings'" class="icon-button" type="button" title="刷新" @click="store.activeView === 'season' ? store.refreshSeason() : store.syncAllSchedules()">↻</button>
        </div>
      </header>

      <div v-if="store.error" class="toast error-toast">
        <span>{{ store.error }}</span>
        <button type="button" @click="store.clearMessages">×</button>
      </div>
      <div v-if="store.notice" class="toast success-toast">
        <span>{{ store.notice }}</span>
        <button type="button" @click="store.clearMessages">×</button>
      </div>

      <section class="page-content">
        <SeasonPage v-if="store.activeView === 'season'" />
        <FollowingPage v-else-if="store.activeView === 'following'" />
        <ArchivePage v-else-if="store.activeView === 'archive'" />
        <SettingsPage v-else />
      </section>

      <div v-if="showAutostartPrompt" class="modal-backdrop">
        <div class="modal-card first-run-card">
          <span class="eyebrow">WELCOME TO ANIDESK</span>
          <h3>需要开机时自动启动吗？</h3>
          <p>开启后 AniDesk 会在后台驻留托盘，关机重启后也能按时提醒。你可以随时在设置中修改。</p>
          <div class="modal-actions">
            <button type="button" class="secondary-button" @click="answerAutostart(false)">暂不开启</button>
            <button type="button" class="primary-button" @click="answerAutostart(true)">开启自动启动</button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
