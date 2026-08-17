<script setup lang="ts">
import { reactive, ref } from "vue";
import AnimeCover from "./AnimeCover.vue";
import { useAppStore } from "../stores/app";
import { openExternal } from "../services/platform";
import type { AniListCandidate, FollowedAnime } from "../types";

const store = useAppStore();
const expanded = ref<string | null>(null);
const linkDrafts = reactive<Record<string, { name: string; url: string }>>({});
const candidates = reactive<Record<string, AniListCandidate[]>>({});
const candidateLoading = ref<string | null>(null);
const archiveDialog = ref<FollowedAnime | null>(null);
const finishedAt = ref(new Date().toISOString().slice(0, 10));
const note = ref("");

function nextSchedule(item: FollowedAnime) {
  if (item.follow.manualAirAt) {
    return { episode: item.schedules[0]?.episode ?? 0, airAt: item.follow.manualAirAt, source: "manual" };
  }
  return item.schedules
    .filter((schedule) => new Date(schedule.airAt).getTime() > Date.now() - 7_200_000)
    .sort((left, right) => left.airAt.localeCompare(right.airAt))[0];
}

function dateTimeLocal(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

async function updateManualTime(animeId: string, value: string): Promise<void> {
  await store.updateFollow(animeId, { manualAirAt: value ? new Date(value).toISOString() : null, lastRemindedScheduleId: null });
}

async function addLink(animeId: string): Promise<void> {
  const draft = linkDrafts[animeId];
  if (!draft) return;
  await store.saveLink(animeId, draft.name, draft.url, false);
  linkDrafts[animeId] = { name: "", url: "" };
}

async function loadCandidates(item: FollowedAnime): Promise<void> {
  candidateLoading.value = item.anime.id;
  try {
    candidates[item.anime.id] = await store.getCandidates(item.anime.id);
  } finally {
    candidateLoading.value = null;
  }
}

async function chooseCandidate(item: FollowedAnime, candidate: AniListCandidate): Promise<void> {
  await store.syncOneSchedule(item.anime.id, candidate);
  candidates[item.anime.id] = [];
}

function openArchive(item: FollowedAnime): void {
  archiveDialog.value = item;
  finishedAt.value = new Date().toISOString().slice(0, 10);
  note.value = "";
}

async function confirmArchive(): Promise<void> {
  if (!archiveDialog.value) return;
  await store.archiveFollowing(archiveDialog.value.anime.id, finishedAt.value, note.value);
  archiveDialog.value = null;
}
</script>

<template>
  <div class="page-stack">
    <section class="section-heading">
      <div>
        <span class="eyebrow">FOLLOWING · {{ store.following.length }}</span>
        <h2>正在追的故事</h2>
        <p>日程每 {{ store.settings.refreshHours }} 小时自动同步。手动时间始终优先。</p>
      </div>
      <button class="secondary-button" type="button" :disabled="store.syncing" @click="store.syncAllSchedules">{{ store.syncing ? '同步中…' : '同步全部日程' }}</button>
    </section>

    <div v-if="store.following.length" class="following-list">
      <article v-for="item in store.following" :key="item.anime.id" class="follow-card panel">
        <AnimeCover :src="item.anime.coverData || item.anime.coverUrl" :title="item.anime.titleCn" compact />
        <div class="follow-main">
          <div class="follow-title-row">
            <div>
              <span v-if="item.anime.anilistId" class="source-tag ok">日程已匹配</span>
              <span v-else class="source-tag warn">需要确认日程</span>
              <h3>{{ item.anime.titleCn }}</h3>
              <p class="native-title">{{ item.anime.titleNative }}</p>
            </div>
            <button class="more-button" type="button" :aria-expanded="expanded === item.anime.id" @click="expanded = expanded === item.anime.id ? null : item.anime.id">•••</button>
          </div>

          <div class="schedule-strip">
            <template v-if="nextSchedule(item)">
              <div class="episode-number">{{ nextSchedule(item)?.episode ? `EP ${nextSchedule(item)?.episode}` : 'NEXT' }}</div>
              <div>
                <strong>{{ new Date(nextSchedule(item)!.airAt).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }) }}</strong>
                <span>{{ new Date(nextSchedule(item)!.airAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }} · {{ nextSchedule(item)?.source === 'manual' ? '手动时间' : 'AniList' }}</span>
              </div>
            </template>
            <template v-else>
              <div class="episode-number muted">?</div>
              <div><strong>暂无未来日程</strong><span>可以自动匹配或填写手动时间</span></div>
            </template>
            <button v-if="item.links.length" class="play-button" type="button" @click="openExternal((item.links.find(link => link.isDefault) || item.links[0])!.url)">▶ 打开播放地址</button>
            <span v-else class="no-link">尚未添加播放地址</span>
          </div>

          <div v-if="expanded === item.anime.id" class="follow-details">
            <div class="details-grid">
              <section>
                <h4>提醒设置</h4>
                <label class="toggle-row">
                  <span><strong>播出提醒</strong><small>系统通知与悬浮卡片</small></span>
                  <input type="checkbox" :checked="item.follow.reminderEnabled" @change="store.updateFollow(item.anime.id, { reminderEnabled: ($event.target as HTMLInputElement).checked })" />
                </label>
                <label class="field-label">单独提前时间（留空使用全局）
                  <div class="suffix-input"><input type="number" min="0" max="1440" :value="item.follow.reminderMinutes ?? ''" @change="store.updateFollow(item.anime.id, { reminderMinutes: ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null })" /><span>分钟</span></div>
                </label>
                <label class="field-label">手动覆盖下一次播出时间
                  <input type="datetime-local" :value="dateTimeLocal(item.follow.manualAirAt)" @change="updateManualTime(item.anime.id, ($event.target as HTMLInputElement).value)" />
                </label>
                <button class="text-button" type="button" :disabled="candidateLoading === item.anime.id" @click="loadCandidates(item)">{{ candidateLoading === item.anime.id ? '查找中…' : '重新选择 AniList 条目' }}</button>
              </section>

              <section>
                <h4>播放地址</h4>
                <ul v-if="item.links.length" class="link-list">
                  <li v-for="link in item.links" :key="link.id">
                    <button type="button" class="link-name" @click="openExternal(link.url)">{{ link.name }} <span v-if="link.isDefault">默认</span></button>
                    <div>
                      <button v-if="!link.isDefault" type="button" title="设为默认" @click="store.saveLink(item.anime.id, link.name, link.url, true)">☆</button>
                      <button type="button" title="删除" @click="store.deleteLink(link.id)">×</button>
                    </div>
                  </li>
                </ul>
                <div class="link-form">
                  <input v-model="(linkDrafts[item.anime.id] ??= { name: '', url: '' }).name" placeholder="平台名称" />
                  <input v-model="linkDrafts[item.anime.id]!.url" type="url" placeholder="https://…" />
                  <button class="secondary-button" type="button" @click="addLink(item.anime.id)">添加</button>
                </div>
              </section>
            </div>

            <div v-if="candidates[item.anime.id]?.length" class="candidate-list">
              <strong>请选择正确的 AniList 条目</strong>
              <button v-for="candidate in candidates[item.anime.id]" :key="candidate.id" type="button" @click="chooseCandidate(item, candidate)">
                <span>{{ candidate.titleNative || candidate.titleRomaji }}</span>
                <small>{{ candidate.startDate || '日期未知' }} · {{ candidate.seasonYear || '年份未知' }}</small>
              </button>
            </div>

            <div class="danger-row">
              <button class="text-button success-text" type="button" @click="openArchive(item)">✓ 我已看完，放入仓库</button>
              <button class="text-button danger-text" type="button" @click="store.unfollow(item.anime.id)">取消追更</button>
            </div>
          </div>
        </div>
      </article>
    </div>

    <div v-else class="empty-state panel">
      <span class="empty-icon">追</span>
      <h3>追更列表还是空的</h3>
      <p>去“本季番剧”挑一部想看的动画吧。</p>
      <button class="primary-button" type="button" @click="store.activeView = 'season'">浏览本季番剧</button>
    </div>

    <div v-if="archiveDialog" class="modal-backdrop" @click.self="archiveDialog = null">
      <form class="modal-card" @submit.prevent="confirmArchive">
        <span class="eyebrow">FINISHED</span>
        <h3>看完《{{ archiveDialog.anime.titleCn }}》</h3>
        <label class="field-label">看完日期<input v-model="finishedAt" type="date" required /></label>
        <label class="field-label">写点感想<textarea v-model="note" rows="5" placeholder="最喜欢的情节、角色，或只是简单记一笔…"></textarea></label>
        <div class="modal-actions"><button type="button" class="secondary-button" @click="archiveDialog = null">取消</button><button type="submit" class="primary-button">保存到仓库</button></div>
      </form>
    </div>
  </div>
</template>
