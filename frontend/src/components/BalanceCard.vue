<template>
  <section class="card" :aria-label="ariaLabel">
    <div class="body">
      <span class="label">내 계좌 총 잔액</span>
      <slot />
      <span v-if="note" class="note">{{ note }}</span>
    </div>
    <div class="actions">
      <router-link :to="primary.to" class="action action-strong">{{ primary.label }}</router-link>
      <router-link :to="secondary.to" class="action action-plain">{{ secondary.label }}</router-link>
    </div>
  </section>
</template>

<script setup>
defineProps({
  ariaLabel: { type: String, required: true },
  note: { type: String, default: '' },
  primary: { type: Object, required: true },
  secondary: { type: Object, required: true },
})
</script>

<style scoped>
.card {
  box-sizing: border-box;
  padding: var(--space-8) var(--space-4) var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-brand);
  color: var(--color-on-brand);
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  /* 포커스 색이 배경과 같은 보라라서 보이지 않는다. 카드 안에서는 흰 테두리로 바꾼다. */
  --color-focus: var(--color-on-brand);
}

.body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.label {
  font-size: var(--text-sm);
  color: var(--color-on-brand-muted);
}

.note {
  font-size: var(--text-xs);
  color: var(--color-on-brand-muted);
}

.actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.action {
  height: var(--height-control);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-card);
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  text-decoration: none;
}

.action-strong {
  background: var(--color-brand-strong);
  color: var(--color-on-brand);
}

.action-plain {
  background: var(--color-surface);
  color: var(--color-brand-strong);
}
</style>
