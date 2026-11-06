<template>
  <section class="card" aria-label="자산과 부채 요약">
    <div v-for="item in items" :key="item.label" class="row">
      <span class="label">{{ item.label }}</span>
      <span class="value" :class="item.tone">{{ item.value }}</span>
    </div>
  </section>
</template>

<script setup>
defineProps({
  items: { type: Array, required: true },
})
</script>

<style scoped>
.card {
  box-sizing: border-box;
  padding: 0 var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
}

.row {
  height: var(--height-summary-row);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.row + .row {
  border-top: 1px solid var(--color-divider);
}

.label {
  font-size: var(--text-sm);
  color: var(--color-text-sub);
}

.value {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  font-variant-numeric: tabular-nums;
}

.tone-debt {
  color: var(--color-debt);
}

.tone-net {
  color: var(--color-brand-strong);
}

.tone-empty {
  color: var(--color-text-sub);
}
</style>
