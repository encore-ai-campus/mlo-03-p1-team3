<template>
  <header class="header">
    <div class="brand">
      <BrandLogo />
      <span class="brand-name">포도뱅크</span>
    </div>
    <router-link v-if="!user.isLoggedIn" to="/login" class="login hit-area">로그인</router-link>
  </header>
</template>

<script setup>
import BrandLogo from '@/components/BrandLogo.vue'
import { useUserStore } from '@/stores/user'

const user = useUserStore()
</script>

<style scoped>
.header {
  flex: 0 0 calc(var(--height-header) + env(safe-area-inset-top, 0px));
  box-sizing: border-box;
  padding-top: env(safe-area-inset-top, 0px);
  padding-left: var(--screen-padding);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.brand-name {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-brand);
}

.login {
  height: var(--height-pill);
  margin-right: var(--screen-padding);
  padding: 0 var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  display: flex;
  align-items: center;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  text-decoration: none;
}
</style>
