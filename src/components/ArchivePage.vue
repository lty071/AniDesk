<script setup lang="ts">
import { ref } from "vue";
import AnimeCover from "./AnimeCover.vue";
import { useAppStore } from "../stores/app";
import type { ArchivedAnime } from "../types";

const store = useAppStore();
const mode = ref<"none" | "search" | "manual">("none");
const query = ref("");
const editing = ref<ArchivedAnime | null>(null);
const editFinishedAt = ref("");
const editNote = ref("");
const manual = ref({
  titleCn: "",
  titleNative: "",
  coverData: "",
  finishedAt: new Date().toISOString().slice(0, 10),
  note: "",
});

async function search(): Promise<void> {
  await store.searchAnime(query.value);
}

function imageSelected(event: Event): void {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => (manual.value.coverData = String(reader.result));
  reader.readAsDataURL(file);
}

async function addManual(): Promise<void> {
  await store.addManualAnime(manual.value);
  manual.value = { titleCn: "", titleNative: "", coverData: "", finishedAt: new Date().toISOString().slice(0, 10), note: "" };
  mode.value = "none";
}

function edit(item: ArchivedAnime): void {
  editing.value = item;
  editFinishedAt.value = item.archive.finishedAt;
  editNote.value = item.archive.note;
}

async function saveEdit(): Promise<void> {
  if (!editing.value) return;
  await store.updateArchiveNote(editing.value.anime.id, editFinishedAt.value, editNote.value);
  editing.value = null;
}
</script>

<template>
  <div class="page-stack">
    <section class="section-heading">
      <div>
        <span class="eyebrow">ARCHIVE · {{ store.archive.length }}</span>
        <h2>看过的，都值得留下</h2>
        <p>保存看完的日期和那一刻的感受。</p>
      </div>
      <div class="button-group">
        <button class="secondary-button" type="button" @click="mode = mode === 'search' ? 'none' : 'search'">从 Bangumi 搜索</button>
        <button class="primary-button" type="button" @click="mode = mode === 'manual' ? 'none' : 'manual'">＋ 手动添加</button>
      </div>
    </section>

    <section v-if="mode === 'search'" class="panel add-panel">
      <div class="inline-search"><input v-model="query" placeholder="输入过去看过的动画名称" @keyup.enter="search" /><button class="primary-button" type="button" @click="search">搜索</button></div>
      <div v-if="store.searchResults.length" class="search-results">
        <article v-for="anime in store.searchResults" :key="anime.id">
          <AnimeCover :src="anime.coverUrl" :title="anime.titleCn" compact />
          <div><strong>{{ anime.titleCn }}</strong><small>{{ anime.titleNative }} · {{ anime.startDate }}</small></div>
          <button class="secondary-button" type="button" @click="store.addSearchedToArchive(anime)">加入仓库</button>
        </article>
      </div>
    </section>

    <form v-if="mode === 'manual'" class="panel add-panel manual-form" @submit.prevent="addManual">
      <div class="cover-upload">
        <AnimeCover :src="manual.coverData" :title="manual.titleCn || '番'" compact />
        <label class="text-button">选择封面<input class="visually-hidden" type="file" accept="image/*" @change="imageSelected" /></label>
      </div>
      <label class="field-label">中文名<input v-model="manual.titleCn" required placeholder="作品名称" /></label>
      <label class="field-label">原名<input v-model="manual.titleNative" placeholder="可选" /></label>
      <label class="field-label">看完日期<input v-model="manual.finishedAt" type="date" required /></label>
      <label class="field-label wide-field">感想<textarea v-model="manual.note" rows="3" placeholder="写点什么…"></textarea></label>
      <button class="primary-button" type="submit">保存</button>
    </form>

    <div v-if="store.archive.length" class="archive-grid">
      <article v-for="item in store.archive" :key="item.anime.id" class="archive-card panel">
        <AnimeCover :src="item.anime.coverData || item.anime.coverUrl" :title="item.anime.titleCn" />
        <div class="archive-body">
          <span class="finished-date">✓ {{ item.archive.finishedAt }} 看完</span>
          <h3>{{ item.anime.titleCn }}</h3>
          <p class="native-title">{{ item.anime.titleNative }}</p>
          <blockquote v-if="item.archive.note">“{{ item.archive.note }}”</blockquote>
          <p v-else class="empty-note">还没有写感想</p>
          <div class="archive-actions">
            <button type="button" class="text-button" @click="edit(item)">编辑记录</button>
            <button type="button" class="text-button" @click="store.restoreArchive(item.anime.id)">移回追更</button>
            <button type="button" class="text-button danger-text" @click="store.deleteArchive(item.anime.id)">删除</button>
          </div>
        </div>
      </article>
    </div>
    <div v-else class="empty-state panel"><span class="empty-icon">藏</span><h3>仓库里还没有作品</h3><p>看完一部动画后，把它和感想一起留在这里。</p></div>

    <div v-if="editing" class="modal-backdrop" @click.self="editing = null">
      <form class="modal-card" @submit.prevent="saveEdit">
        <span class="eyebrow">MEMORY</span><h3>编辑《{{ editing.anime.titleCn }}》</h3>
        <label class="field-label">看完日期<input v-model="editFinishedAt" type="date" required /></label>
        <label class="field-label">感想<textarea v-model="editNote" rows="6"></textarea></label>
        <div class="modal-actions"><button type="button" class="secondary-button" @click="editing = null">取消</button><button type="submit" class="primary-button">保存修改</button></div>
      </form>
    </div>
  </div>
</template>
