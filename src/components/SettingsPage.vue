<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useAppStore } from "../stores/app";
import type { AppSettings, BackupKind } from "../types";
import { isTauri } from "../services/platform";

const store = useAppStore();
const form = ref<AppSettings>({ ...store.settings });
const autostart = ref(false);
const backupBusy = ref(false);
const message = ref("");
const fileInput = ref<HTMLInputElement | null>(null);

onMounted(async () => {
  form.value = { ...store.settings };
  if (isTauri()) {
    const plugin = await import("@tauri-apps/plugin-autostart");
    autostart.value = await plugin.isEnabled();
  }
});

async function saveSettings(): Promise<void> {
  await store.saveAppSettings({ ...form.value, autostartPrompted: true });
  if (isTauri()) {
    const plugin = await import("@tauri-apps/plugin-autostart");
    if (autostart.value) await plugin.enable();
    else await plugin.disable();
  }
  message.value = "设置已保存";
}

async function exportBackup(kind: BackupKind): Promise<void> {
  backupBusy.value = true;
  message.value = "";
  try {
    const saved = await store.backupService().exportToFile(kind);
    if (saved) message.value = kind === "following" ? "追更备份已导出" : "仓库备份已导出";
  } catch (reason) {
    message.value = reason instanceof Error ? reason.message : "导出失败";
  } finally {
    backupBusy.value = false;
  }
}

async function startImport(): Promise<void> {
  if (!isTauri()) {
    fileInput.value?.click();
    return;
  }
  const bytes = await store.backupService().chooseImportFile();
  if (bytes) await importBytes(bytes);
}

async function browserFileSelected(event: Event): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  await importBytes(new Uint8Array(await file.arrayBuffer()));
  (event.target as HTMLInputElement).value = "";
}

async function importBytes(bytes: Uint8Array): Promise<void> {
  backupBusy.value = true;
  message.value = "";
  try {
    const result = await store.backupService().import(bytes);
    await store.reloadCollections();
    message.value = `导入完成：新增 ${result.imported} 条，合并 ${result.merged} 条`;
  } catch (reason) {
    message.value = reason instanceof Error ? reason.message : "导入失败";
  } finally {
    backupBusy.value = false;
  }
}
</script>

<template>
  <div class="settings-layout">
    <section class="settings-section panel">
      <div class="settings-title"><span class="settings-icon">醒</span><div><h2>提醒与后台</h2><p>控制播出提醒的方式和频率。</p></div></div>
      <div class="settings-fields">
        <label class="setting-row"><span><strong>默认提前提醒</strong><small>单部作品可以单独覆盖</small></span><div class="suffix-input compact-input"><input v-model.number="form.reminderMinutes" type="number" min="0" max="1440" /><span>分钟</span></div></label>
        <label class="setting-row"><span><strong>Windows 系统通知</strong><small>在通知中心显示播出消息</small></span><input v-model="form.notificationsEnabled" type="checkbox" /></label>
        <label class="setting-row"><span><strong>桌面悬浮卡片</strong><small>带封面的置顶提醒窗口</small></span><input v-model="form.floatingWindowEnabled" type="checkbox" /></label>
        <label class="setting-row"><span><strong>开机时启动 AniDesk</strong><small>保证关机重启后仍能准时提醒</small></span><input v-model="autostart" type="checkbox" :disabled="!isTauri()" /></label>
        <label class="setting-row"><span><strong>日程同步周期</strong><small>程序启动时也会立即同步</small></span><select v-model.number="form.refreshHours"><option :value="3">每 3 小时</option><option :value="6">每 6 小时</option><option :value="12">每 12 小时</option><option :value="24">每天</option></select></label>
      </div>
      <button class="primary-button settings-save" type="button" @click="saveSettings">保存设置</button>
    </section>

    <section class="settings-section panel">
      <div class="settings-title"><span class="settings-icon">备</span><div><h2>本地备份与恢复</h2><p>追更和仓库分别保存，可单独恢复。</p></div></div>
      <div class="backup-grid">
        <article><strong>追更数据</strong><p>番剧、播出日程、提醒设置和播放地址。</p><button class="secondary-button" type="button" :disabled="backupBusy" @click="exportBackup('following')">导出追更备份</button></article>
        <article><strong>仓库数据</strong><p>看过的作品、封面、日期、感想和地址。</p><button class="secondary-button" type="button" :disabled="backupBusy" @click="exportBackup('archive')">导出仓库备份</button></article>
      </div>
      <div class="import-row"><div><strong>从 .anibackup 恢复</strong><small>导入前会自动保存当前数据快照；重复记录安全合并。</small></div><button class="primary-button" type="button" :disabled="backupBusy" @click="startImport">{{ backupBusy ? '处理中…' : '选择备份文件' }}</button></div>
      <input ref="fileInput" class="visually-hidden" type="file" accept=".anibackup" @change="browserFileSelected" />
    </section>

    <section class="settings-section panel cloud-panel">
      <div class="settings-title"><span class="settings-icon">云</span><div><h2>云端同步</h2><p>飞书云空间将在第二阶段提供。</p></div></div>
      <div class="coming-soon"><span>COMING SOON</span><p>接口已经预留，当前版本不会要求任何云端账号或权限。</p></div>
    </section>

    <div v-if="message" class="inline-message">{{ message }}</div>
  </div>
</template>
