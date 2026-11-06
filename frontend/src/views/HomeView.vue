<template>
  <AppHeader />
  <main class="main">
    <h1 class="visually-hidden">{{ user.name }}님의 홈</h1>

    <BankingStatus
      v-if="banking.status !== 'ready'"
      :status="banking.status"
      :message="banking.errorMessage"
      @retry="load"
    />

    <template v-else>
    <BalanceCard
      aria-label="총 잔액"
      :primary="{ to: '/accounts', label: '계좌 보기' }"
      :secondary="{ to: '/transfer', label: '송금하기' }"
    >
      <span class="hero-amount">
        <span class="hero-number">{{ formatNumber(banking.totalBalance) }}</span>
        <span class="hero-unit">원</span>
      </span>
    </BalanceCard>

    <SummaryCard :items="summary" />

    <ListCard title="내 계좌" link-label="전체 보기" link-to="/accounts">
      <div v-for="account in banking.accounts" :key="account.account_id" class="account-row">
        <span class="account-icon">
          <svg
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
            <rect x="3" y="6" width="18" height="13" rx="2.5" />
            <path d="M3 10h18M16 14.5h2" />
          </svg>
        </span>
        <div class="account-info">
          <span class="account-name">{{ account.alias }}</span>
          <span class="account-no">{{ account.account_no }}</span>
        </div>
        <span class="row-amount">{{ formatWon(account.balance) }}</span>
      </div>
    </ListCard>

    <ListCard title="최근 거래" link-label="거래내역" link-to="/accounts">
      <div v-for="tx in recent" :key="tx.entry_id" class="tx-row">
        <span class="tx-text">
          <span class="tx-title">{{ tx.title }}</span>
          <span class="tx-when">{{ formatDateTime(tx.created_at) }}</span>
        </span>
        <span class="row-amount" :class="tx.direction === 'IN' ? 'amount-in' : 'amount-out'">
          {{ formatSignedWon(tx.direction === 'IN' ? tx.amount : -tx.amount) }}
        </span>
      </div>
      <p v-if="!banking.transactions.length" class="tx-empty">아직 거래 내역이 없어요</p>
    </ListCard>
    </template>
  </main>
  <BottomNav />
</template>

<script setup>
import { computed } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import BalanceCard from '@/components/BalanceCard.vue'
import BankingStatus from '@/components/BankingStatus.vue'
import BottomNav from '@/components/BottomNav.vue'
import ListCard from '@/components/ListCard.vue'
import SummaryCard from '@/components/SummaryCard.vue'
import { useBankingData } from '@/composables/useBankingData'
import { useUserStore } from '@/stores/user'
import { formatDateTime, formatNumber, formatSignedWon, formatWon } from '@/utils/format'

const user = useUserStore()
const { banking, load } = useBankingData()

// 홈에는 최근 5건만 보여 주고, 나머지는 계좌 화면 거래내역에서 본다.
const recent = computed(() => banking.transactions.slice(0, 5))

const summary = computed(() => [
  { label: '총 자산', value: formatWon(banking.totalBalance) },
  // 주황(부채색)은 갚을 돈이 있을 때만. 빚이 없으면 회색으로 둔다.
  { label: '총 부채', value: formatWon(banking.totalDebt), tone: banking.totalDebt > 0 ? 'tone-debt' : 'tone-empty' },
  { label: '순자산', value: formatWon(banking.netAssets), tone: banking.netAssets < 0 ? 'tone-debt' : 'tone-net' },
])
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

.tx-empty {
  margin: 0;
  padding: var(--space-8) 0;
  border-top: 1px solid var(--color-divider);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-sub);
}

.hero-amount {
  display: flex;
  align-items: baseline;
  /* 숫자와 '원'은 한 단어처럼 붙인다(글자 간격 예외) */
  gap: 0.25em;
  font-variant-numeric: tabular-nums;
}

.hero-number {
  font-size: var(--text-hero);
  line-height: var(--leading-hero);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-hero);
}

.hero-unit {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.account-row,
.tx-row {
  height: var(--height-row);
  display: grid;
  align-items: center;
  gap: var(--space-4);
  border-top: 1px solid var(--color-divider);
}

.account-row {
  grid-template-columns: var(--size-tile) minmax(0, 1fr) auto;
}

/* 계좌 화면 거래내역처럼 왼쪽에 제목/날짜 두 줄, 오른쪽에 금액. 좁은 화면에서도 제목 자리가 남는다. */
.tx-row {
  grid-template-columns: minmax(0, 1fr) auto;
}

.tx-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.account-icon {
  width: var(--size-tile);
  height: var(--size-tile);
  border-radius: var(--radius-tile);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  display: flex;
  align-items: center;
  justify-content: center;
}

.account-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.account-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.account-no,
.tx-when {
  font-size: var(--text-xs);
  color: var(--color-text-sub);
  font-variant-numeric: tabular-nums;
}

.tx-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-amount {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.amount-in {
  color: var(--color-amount-in);
}

.amount-out {
  color: var(--color-amount-out);
}
</style>
