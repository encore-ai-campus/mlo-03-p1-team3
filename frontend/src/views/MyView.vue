<template>
  <AppHeader />
  <main class="main">
    <h1 class="title">내 정보</h1>

    <section class="panel profile" aria-label="프로필">
      <span class="avatar" aria-hidden="true">{{ user.name.charAt(0) }}</span>
      <div class="profile-text">
        <span class="name">{{ user.name }}</span>
        <span class="email">포도뱅크 고객</span>
      </div>
    </section>

    <section v-for="group in groups" :key="group.title" class="panel menu">
      <h2 class="group-title">{{ group.title }}</h2>
      <MenuRow v-for="item in group.items" :key="item.label" v-bind="item" />
    </section>

    <section class="panel menu" aria-label="계정">
      <button type="button" class="logout" :disabled="isLoggingOut" @click="handleLogout">
        <span class="logout-tile" aria-hidden="true">
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
            <path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4M10 16l-4-4 4-4M6 12h9" />
          </svg>
        </span>
        {{ isLoggingOut ? '로그아웃하는 중이에요' : '로그아웃' }}
      </button>
    </section>
  </main>
  <BottomNav />
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { version } from '../../package.json'
import AppHeader from '@/components/AppHeader.vue'
import BottomNav from '@/components/BottomNav.vue'
import MenuRow from '@/components/MenuRow.vue'
import { useUserStore } from '@/stores/user'

const ICONS = {
  bell: 'M6 16v-5a6 6 0 1 1 12 0v5l1.5 2h-15zM10 20.5h4',
  help: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM9.5 9.5a2.5 2.5 0 1 1 3.8 2.1c-.8.5-1.3 1-1.3 1.9M12 16.5h.01',
  document: 'M7 3.5h7l4 4V20a.5.5 0 0 1-.5.5h-10.5a.5.5 0 0 1-.5-.5V4a.5.5 0 0 1 .5-.5zM14 3.5V8h4M9 12.5h6M9 16h6',
  info: 'M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 11v5M12 8h.01',
}

const router = useRouter()
const user = useUserStore()

const isLoggingOut = ref(false)

const groups = [
  {
    title: '설정',
    items: [
      { icon: ICONS.bell, label: '알림 설정', to: '/me/notifications' },
    ],
  },
  {
    title: '고객 지원',
    items: [
      { icon: ICONS.help, label: '자주 묻는 질문', to: '/me/faq' },
      { icon: ICONS.document, label: '약관 및 개인정보', to: '/me/terms' },
      { icon: ICONS.info, label: '앱 버전', value: version },
    ],
  },
]

async function handleLogout() {
  isLoggingOut.value = true
  try {
    await user.logout()
  } catch {
    // 서버에 닿지 않아도 이 기기의 로그인 상태는 이미 지워졌다.
  }
  router.push({ name: 'guest' })
}
</script>

<style scoped>
.main {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  box-sizing: border-box;
  padding: 0 var(--screen-padding) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--card-gap);
}

.title {
  margin: 0;
  padding: var(--space-4) 0;
  font-size: var(--text-title);
  line-height: var(--leading-title);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-title);
}

.panel {
  flex: 0 0 auto;
  box-sizing: border-box;
  border-radius: var(--radius-card);
  background: var(--color-surface);
}

.profile {
  padding: var(--space-4);
  display: grid;
  grid-template-columns: var(--size-avatar) minmax(0, 1fr);
  align-items: center;
  gap: var(--space-4);
}

.avatar {
  width: var(--size-avatar);
  height: var(--size-avatar);
  border-radius: 50%;
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
}

.profile-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.name {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.email {
  font-size: var(--text-sm);
  color: var(--color-text-sub);
  overflow-wrap: anywhere;
}

.menu {
  padding: var(--space-4) var(--space-4) 0;
  display: flex;
  flex-direction: column;
}

.group-title {
  height: var(--height-card-head);
  margin: 0;
  display: flex;
  align-items: center;
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.menu:last-child {
  padding: 0 var(--space-4);
}

.logout {
  width: 100%;
  min-height: var(--height-summary-row);
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-error);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  font-family: inherit;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
}

.logout-tile {
  flex: 0 0 var(--size-tile);
  height: var(--size-tile);
  border-radius: var(--radius-tile);
  background: var(--color-divider);
  display: flex;
  align-items: center;
  justify-content: center;
}

.logout:disabled {
  color: var(--color-text-sub);
  cursor: not-allowed;
}
</style>
