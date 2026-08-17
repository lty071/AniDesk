<script setup lang="ts">
withDefaults(
  defineProps<{
    src?: string;
    title: string;
    compact?: boolean;
  }>(),
  { src: "", compact: false },
);
</script>

<template>
  <div :class="['anime-cover', { compact }]">
    <img v-if="src" :src="src" :alt="`${title}封面`" loading="lazy" />
    <div v-else class="cover-placeholder">
      <span>{{ title.slice(0, 1) }}</span>
      <small>NO COVER</small>
    </div>
  </div>
</template>
