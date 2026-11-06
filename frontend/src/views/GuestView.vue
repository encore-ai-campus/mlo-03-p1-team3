<template>
  <AppHeader />
  <main class="main">
    <h1 class="visually-hidden">포도뱅크 시작하기</h1>

    <BalanceCard
      aria-label="내 계좌"
      :primary="{ to: '/signup', label: '회원가입' }"
      :secondary="{ to: '/login', label: '로그인' }"
    >
      <span class="locked">
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
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path d="M8 11V8a4 4 0 0 1 8 0v3" />
        </svg>
        로그인 후 확인
      </span>
    </BalanceCard>

    <SummaryCard :items="summary" />

    <section class="panel panel-padded">
      <div class="card-head">
        <h2 class="card-title">최근 거래</h2>
      </div>
      <div class="empty">
        <svg
          class="empty-icon"
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <rect x="5" y="11" width="14" height="10" rx="2" />
          <path d="M8 11V8a4 4 0 0 1 8 0v3" />
        </svg>
        <span class="empty-title">로그인하면 거래 내역이 보여요</span>
        <span class="empty-note">계좌, 대출 정보도 함께 확인할 수 있어요</span>
      </div>
    </section>

    <section class="panel panel-list">
      <div class="card-head">
        <h2 class="card-title">포도뱅크에서 할 수 있어요</h2>
      </div>
      <router-link
        v-for="feature in features"
        :key="feature.title"
        :to="feature.to"
        class="feature"
      >
        <span class="feature-mark" aria-hidden="true">{{ feature.mark }}</span>
        <span class="feature-text">
          <span class="feature-title">{{ feature.title }}</span>
          <span class="feature-desc">{{ feature.desc }}</span>
        </span>
        <svg
          class="feature-chevron"
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
      </router-link>
    </section>
  </main>
  <BottomNav />
</template>

<script setup>
import AppHeader from '@/components/AppHeader.vue'
import BalanceCard from '@/components/BalanceCard.vue'
import BottomNav from '@/components/BottomNav.vue'
import SummaryCard from '@/components/SummaryCard.vue'

const summary = [
  { label: '총 자산', value: '— 원', tone: 'tone-empty' },
  { label: '총 부채', value: '— 원', tone: 'tone-empty' },
  { label: '순자산', value: '— 원', tone: 'tone-empty' },
]

const features = [
  { mark: '계', title: '통장과 카드', desc: '가입하면 통장과 체크카드가 바로 나와요', to: '/signup' },
  { mark: '송', title: '수수료 없는 송금', desc: '포도뱅크끼리 바로 보내요', to: '/login' },
  { mark: '대', title: '무이자 대출', desc: '원금만 매달 나눠 갚아요', to: '/login' },
]
</script>

<style scoped>
.main {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  box-sizing: border-box;
  padding: var(--space-4) var(--screen-padding) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--card-gap);
}

.locked {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  font-size: var(--text-title);
  line-height: var(--leading-title);
  font-weight: var(--font-bold);
}

.panel {
  box-sizing: border-box;
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
}

.panel-padded {
  padding: var(--space-4);
  gap: var(--space-4);
}

.panel-list {
  padding: var(--space-4) var(--space-4) 0;
}

.card-head {
  height: var(--height-card-head);
  display: flex;
  align-items: center;
}

.card-title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.empty {
  box-sizing: border-box;
  padding: var(--space-8) var(--space-4);
  border: 1px dashed var(--color-dot-empty);
  border-radius: var(--radius-card);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
}

.empty-icon {
  color: var(--color-brand-light);
}

.empty-title {
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
}

.empty-note {
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

.feature {
  height: var(--height-row);
  display: grid;
  grid-template-columns: var(--size-tile) minmax(0, 1fr) var(--width-chevron);
  align-items: center;
  gap: var(--space-4);
  border-top: 1px solid var(--color-divider);
  color: var(--color-text);
  text-decoration: none;
}

.feature-mark {
  width: var(--size-tile);
  height: var(--size-tile);
  border-radius: var(--radius-tile);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
}

.feature-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.feature-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.feature-desc {
  font-size: var(--text-xs);
  color: var(--color-text-sub);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.feature-chevron {
  color: var(--color-input-border);
}
</style>
