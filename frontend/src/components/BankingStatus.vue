<template>
  <div v-if="status === 'error'" class="state" role="alert">
    <p class="text">{{ message }}</p>
    <button type="button" class="retry" @click="$emit('retry')">다시 시도</button>
  </div>
  <div v-else class="skeleton" role="status">
    <span class="visually-hidden">정보를 불러오고 있어요</span>
    <span class="bone bone-hero"></span>
    <span class="bone"></span>
    <span class="bone"></span>
  </div>
</template>

<script setup>
defineProps({
  status: { type: String, required: true },
  message: { type: String, default: '' },
})

defineEmits(['retry'])
</script>

<style scoped>
.state {
  margin: 0;
  padding: var(--space-8) 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
}

.text {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-sub);
}

.retry {
  height: var(--height-control);
  padding: 0 var(--space-8);
  border: 0;
  border-radius: var(--radius-card);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  font-family: inherit;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
}

/* 금방 끝나는 로딩에서 번쩍이지 않도록 조금 기다렸다가 나타난다. */
.skeleton {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--card-gap);
  animation: fade-in var(--duration-base) var(--ease-out) var(--duration-base) backwards;
}

/* main 밖에 놓이는 송금·입출금 화면에서는 좌우 여백을 직접 둔다. */
.app-frame > .skeleton {
  padding: var(--space-4) var(--screen-padding) 0;
}

.bone {
  height: var(--height-row);
  border-radius: var(--radius-card);
  background: var(--color-nav-border);
  animation: bone-pulse var(--duration-pulse) ease-in-out infinite alternate;
}

.bone-hero {
  height: var(--height-skeleton-hero);
}

@keyframes bone-pulse {
  to {
    opacity: var(--opacity-disabled);
  }
}

@media (prefers-reduced-motion: reduce) {
  .skeleton {
    animation-delay: 0ms;
  }

  .bone {
    animation: none;
  }
}
</style>
