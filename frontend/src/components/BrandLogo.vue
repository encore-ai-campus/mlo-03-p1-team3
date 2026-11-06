<template>
  <svg :width="size" :height="size" viewBox="0 0 32 32" aria-hidden="true">
    <rect class="tile" width="32" height="32" rx="9" />
    <circle class="grape" cx="12" cy="15" r="3.8" />
    <circle class="grape" cx="20" cy="15" r="3.8" />
    <circle class="grape" cx="16" cy="21.5" r="3.8" />
    <path class="stem" d="M16 11V7.5M16 8.5c2-1.6 4-1.6 5.5 0" />
  </svg>
</template>

<script setup>
defineProps({
  size: { type: Number, default: 32 },
})
</script>

<style scoped>
.tile {
  fill: var(--color-brand);
}

.grape {
  fill: var(--color-surface);
}

.stem {
  fill: none;
  stroke: var(--color-surface);
  stroke-width: 1.8;
  stroke-linecap: round;
}
</style>
