<template>
  <component
    :is="to ? 'router-link' : 'div'"
    :to="to"
    class="row"
  >
    <span class="tile" aria-hidden="true">
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.8"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path :d="icon" />
      </svg>
    </span>
    <span class="label">{{ label }}</span>
    <span v-if="value" class="value">{{ value }}</span>
    <svg
      v-if="to"
      class="chevron"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M9 5l7 7-7 7" />
    </svg>
  </component>
</template>

<script setup>
defineProps({
  icon: { type: String, required: true },
  label: { type: String, required: true },
  value: { type: String, default: '' },
  to: { type: String, default: undefined },
})
</script>

<style scoped>
.row {
  min-height: var(--height-summary-row);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  border-top: 1px solid var(--color-divider);
  color: var(--color-text);
  text-decoration: none;
}

.tile {
  flex: 0 0 var(--size-tile);
  height: var(--size-tile);
  border-radius: var(--radius-tile);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  display: flex;
  align-items: center;
  justify-content: center;
}

.label {
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.value {
  flex: 0 0 auto;
  font-size: var(--text-sm);
  color: var(--color-text-sub);
  font-variant-numeric: tabular-nums;
}

.chevron {
  flex: 0 0 var(--width-chevron);
  margin-left: calc(var(--space-4) * -1);
  color: var(--color-input-border);
}
</style>
