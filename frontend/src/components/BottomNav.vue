<template>
  <nav class="nav" aria-label="하단 메뉴">
    <router-link :to="user.isLoggedIn ? '/' : '/guest'" class="tab">
      <svg v-bind="iconAttrs"><path d="M4 11l8-7 8 7v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" /></svg>
      홈
    </router-link>
    <router-link to="/accounts" class="tab">
      <svg v-bind="iconAttrs">
        <rect x="3" y="6" width="18" height="13" rx="2.5" />
        <path d="M3 10h18M16 14.5h2" />
      </svg>
      계좌
    </router-link>
    <router-link to="/card" class="tab">
      <svg v-bind="iconAttrs">
        <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
        <path d="M2.5 9.5h19M6.5 15h4" />
      </svg>
      카드
    </router-link>
    <router-link to="/loan" class="tab">
      <svg v-bind="iconAttrs">
        <circle cx="12" cy="12" r="8.5" />
        <path d="M9 15l6-6M9.5 9.5h.01M14.5 14.5h.01" />
      </svg>
      대출
    </router-link>
    <router-link to="/me" class="tab">
      <svg v-bind="iconAttrs">
        <circle cx="12" cy="8" r="4" />
        <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
      </svg>
      내 정보
    </router-link>
  </nav>
</template>

<script setup>
import { useUserStore } from '@/stores/user'

const user = useUserStore()

const iconAttrs = {
  width: 24,
  height: 24,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': 1.8,
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round',
  'aria-hidden': 'true',
}
</script>

<style scoped>
/* 메뉴 칸은 늘 64px로 두고, 아이폰 홈 막대 자리(안전 영역)는 그 아래에 따로 비워 둔다. */
.nav {
  flex: 0 0 auto;
  padding-bottom: env(safe-area-inset-bottom, 0px);
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  grid-template-rows: var(--height-tab);
  background: var(--color-surface);
  border-top: 1px solid var(--color-nav-border);
}

.tab {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  color: var(--color-text-sub);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-decoration: none;
}

.tab.router-link-exact-active {
  color: var(--color-brand-strong);
  font-weight: var(--font-semibold);
}
</style>
