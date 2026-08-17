<script setup lang="ts">
import { computed, ref } from "vue";
import AnimeCover from "./AnimeCover.vue";
import { useAppStore } from "../stores/app";
import { SEASON_LABELS } from "../services/season";
import type { Anime, Season } from "../types";

const store = useAppStore();
const query = ref("");
const statusFilter = ref<"all" | Anime["status"]>("all");
const seasons = Object.entries(SEASON_LABELS) as [Season, string][];
const yearOptions = computed(() => [store.seasonYear - 1, store.seasonYear, store.seasonYear + 1]);
const followedIds = computed(() => new Set(store.following.map((item) => item.anime.id)));
const filtered = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase();
  return store.catalog.filter((item) => {
    const matchesText = !keyword || `${item.titleCn} ${item.titleNative}`.toLocaleLowerCase().includes(keyword);
    const matchesStatus = statusFilter.value === "all" || item.status === statusFilter.value;
    return matchesText && matchesStatus;
  });
});

function statusLabel(status: Anime["status"]): string {
  return { upcoming: "即将开播", airing: "放送中", finished: "已完结", unknown: "待确认" }[status];
}
</script>

<template>
  <div class="page-stack">
    <section class="hero-panel">
      <div>
        <span class="pill accent-pill">{{ store.seasonYear }} · {{ SEASON_LABELS[store.season] }}</span>
        <h2>把这个季度，<em>好好追完。</em></h2>
        <p>浏览当季新番，选择想看的作品。AniDesk 会在下一集播出前提醒你。</p>
      </div>
      <div class="hero-stat">
        <strong>{{ store.catalog.length }}</strong>
        <span>部当季作品</span>
      </div>
    </section>

    <section class="toolbar panel">
      <label class="search-box">
        <span>⌕</span>
        <input v-model="query" type="search" placeholder="搜索中文名或原名…" />
      </label>
      <select :value="store.seasonYear" aria-label="年份" @change="store.changeSeason(Number(($event.target as HTMLSelectElement).value), store.season)">
        <option v-for="year in yearOptions" :key="year" :value="year">{{ year }} 年</option>
      </select>
      <select :value="store.season" aria-label="季度" @change="store.changeSeason(store.seasonYear, ($event.target as HTMLSelectElement).value as Season)">
        <option v-for="[value, label] in seasons" :key="value" :value="value">{{ label }}</option>
      </select>
      <select v-model="statusFilter" aria-label="状态筛选">
        <option value="all">全部状态</option>
        <option value="upcoming">即将开播</option>
        <option value="airing">放送中</option>
        <option value="finished">已完结</option>
      </select>
    </section>

    <div v-if="store.loading && !store.catalog.length" class="loading-grid">
      <div v-for="index in 8" :key="index" class="skeleton-card"></div>
    </div>
    <div v-else-if="filtered.length" class="anime-grid">
      <article v-for="anime in filtered" :key="anime.id" class="anime-card">
        <AnimeCover :src="anime.coverData || anime.coverUrl" :title="anime.titleCn" />
        <div class="anime-card-body">
          <div class="card-meta">
            <span :class="['status-badge', anime.status]">{{ statusLabel(anime.status) }}</span>
            <span>{{ anime.startDate || '日期待定' }}</span>
          </div>
          <h3 :title="anime.titleCn">{{ anime.titleCn }}</h3>
          <p class="native-title" :title="anime.titleNative">{{ anime.titleNative }}</p>
          <button v-if="!followedIds.has(anime.id)" class="primary-button full-button" type="button" @click="store.follow(anime)">＋ 加入追更</button>
          <button v-else class="secondary-button full-button" type="button" @click="store.activeView = 'following'">✓ 正在追更</button>
        </div>
      </article>
    </div>
    <div v-else class="empty-state panel">
      <span class="empty-icon">季</span>
      <h3>{{ query ? '没有找到匹配作品' : '本季度目录暂无缓存' }}</h3>
      <p>{{ query ? '换一个关键词试试。' : '请检查网络后点击刷新。' }}</p>
    </div>
  </div>
</template>
