<template>
  <header class="header">
    <router-link :to="to" class="back" aria-label="뒤로">
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M15 5l-7 7 7 7" />
      </svg>
    </router-link>
    <BrandLogo />
  </header>
</template>

<script setup>
import BrandLogo from '@/components/BrandLogo.vue'

defineProps({
  to: { type: String, required: true },
})
</script>

<style scoped>
.header {
  flex: 0 0 calc(var(--height-header) + env(safe-area-inset-top, 0px));
  box-sizing: border-box;
  padding-top: env(safe-area-inset-top, 0px);
  padding-right: var(--screen-padding);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.back {
  width: var(--height-control);
  height: var(--height-control);
  margin-left: var(--space-4);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text);
}
</style>
