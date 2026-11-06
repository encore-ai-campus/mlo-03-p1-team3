<template>
  <AppHeader />
  <main class="main">
    <div class="head">
      <div class="head-text">
        <h1 class="title">계좌</h1>
      </div>
    </div>

    <!-- 입출금 화면에서 돌아왔을 때 결과를 알린다. 상자는 늘 두고 글자만 바꿔야 화면 읽기 프로그램이 읽는다. -->
    <p class="notice-done" :class="{ 'visually-hidden': !doneMessage }" role="status">
      <svg v-if="doneMessage" class="notice-done-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M5 12.5l4.5 4.5L19 7.5" />
      </svg>
      {{ doneMessage }}
    </p>

    <BankingStatus
      v-if="banking.status !== 'ready'"
      :status="banking.status"
      :message="banking.errorMessage"
      @retry="load"
    />

    <template v-else>

      <section
        v-for="account in banking.accounts"
        :key="account.account_id"
        class="account"
        :class="{ 'account-primary': account.is_primary }"
        :aria-label="account.alias"
      >
        <div class="account-top">
          <span class="account-name">{{ account.alias }}</span>
          <span v-if="account.is_primary" class="badge">주계좌</span>
        </div>
        <div class="account-money">
          <span class="account-balance">{{ formatWon(account.balance) }}</span>
          <span class="account-no">{{ account.account_no }}</span>
        </div>
        <div class="account-actions">
          <router-link
            :to="{ name: 'cash', params: { id: account.account_id }, query: { type: 'deposit' } }"
            class="action"
            :aria-label="`${account.alias}에 입금`"
          >
            입금
          </router-link>
          <router-link
            :to="{ name: 'cash', params: { id: account.account_id }, query: { type: 'withdraw' } }"
            class="action"
            :aria-label="`${account.alias}에서 출금`"
          >
            출금
          </router-link>
          <router-link
            :to="{ path: '/transfer', query: { from: account.account_id } }"
            class="action"
            :class="{ 'action-primary': account.is_primary }"
            :aria-label="`${account.alias}에서 송금`"
          >
            송금
          </router-link>
        </div>
      </section>

      <section class="history">
        <div class="history-head">
          <h2 class="history-title">최근 거래내역</h2>
          <div class="filters" role="group" aria-label="거래 구분">
            <span class="filter-thumb" :data-filter="filter" aria-hidden="true"></span>
            <button
              v-for="option in FILTERS"
              :key="option.id"
              type="button"
              class="filter hit-area-y"
              :class="{ 'filter-on': filter === option.id }"
              :aria-pressed="filter === option.id"
              @click="filter = option.id"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
        <div>
          <div v-for="tx in rows" :key="tx.entry_id" class="row">
            <div class="row-left">
              <span class="row-title">{{ tx.title }}</span>
              <span class="row-sub">{{ rowSubtitle(tx) }}</span>
            </div>
            <div class="row-right">
              <span class="row-amount" :class="tx.direction === 'IN' ? 'amount-in' : 'amount-out'">
                {{ formatSignedWon(tx.direction === 'IN' ? tx.amount : -tx.amount) }}
              </span>
              <span class="row-sub">잔액 {{ formatWon(tx.balance_after) }}</span>
            </div>
          </div>
          <p v-if="!rows.length" class="empty">해당하는 거래가 없어요</p>
        </div>
      </section>
    </template>
  </main>
  <BottomNav />
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import BankingStatus from '@/components/BankingStatus.vue'
import BottomNav from '@/components/BottomNav.vue'
import { useBankingData } from '@/composables/useBankingData'
import { formatDateTime, formatSignedWon, formatWon } from '@/utils/format'

const FILTERS = [
  { id: 'all', label: '전체' },
  { id: 'IN', label: '입금' },
  { id: 'OUT', label: '출금' },
]

const { banking, load } = useBankingData()
const filter = ref('all')
const doneMessage = ref('')

// CashView가 router.replace의 state로 넘긴 안내. 새로고침·뒤로 가기로 다시 보이지 않게 읽고 지운다.
onMounted(() => {
  const notice = window.history.state?.notice
  if (!notice) return
  window.history.replaceState({ ...window.history.state, notice: null }, '')
  // 상자가 그려진 뒤에 글자를 넣어야 바뀐 내용으로 읽힌다.
  setTimeout(() => {
    doneMessage.value = notice
  }, 100)
})

const rows = computed(() =>
  banking.transactions.filter((tx) => filter.value === 'all' || tx.direction === filter.value),
)

function rowSubtitle(tx) {
  return formatDateTime(tx.created_at)
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

.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-4) 0;
}

.head-text {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.title {
  margin: 0;
  font-size: var(--text-title);
  line-height: var(--leading-title);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-title);
}



.account {
  box-sizing: border-box;
  padding: var(--space-4);
  border: 1px solid transparent;
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.account-primary {
  border-color: var(--color-brand);
}

.account-top {
  height: var(--height-card-head);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.account-name {
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
}

.badge {
  /* 위아래 여백 대신 줄 높이로 알약 높이를 만든다(16의 배수 규칙). */
  padding: 0 var(--space-4);
  line-height: var(--leading-body);
  border-radius: var(--radius-card);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.account-balance {
  font-size: var(--text-hero);
  line-height: var(--leading-hero);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-hero);
  font-variant-numeric: tabular-nums;
}

.account-money {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.account-actions {
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-divider);
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-4);
}

.account-no {
  font-size: var(--text-sm);
  color: var(--color-text-sub);
  font-variant-numeric: tabular-nums;
}

.action {
  height: var(--height-control);
  border-radius: var(--radius-card);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  text-decoration: none;
}

.action-primary {
  background: var(--color-brand);
  color: var(--color-on-brand);
}

.history {
  box-sizing: border-box;
  padding: var(--space-4) var(--space-4) 0;
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.history-head {
  min-height: var(--height-card-head);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.history-title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.filters {
  flex: 0 0 auto;
  position: relative;
  height: var(--height-pill);
  border-radius: var(--radius-card);
  background: var(--color-divider);
  display: grid;
  grid-template-columns: repeat(3, var(--width-filter));
}

.filter-thumb {
  position: absolute;
  inset: 0 auto 0 0;
  width: var(--width-filter);
  border-radius: var(--radius-card);
  /* 고른 상태는 앱 전체에서 같은 모양: 연보라 바탕 + 보라 테두리·글자 */
  background: var(--color-brand-soft);
  box-shadow: inset 0 0 0 1px var(--color-brand);
  transition: transform var(--duration-base) var(--ease-out);
}

.filter-thumb[data-filter='IN'] {
  transform: translateX(100%);
}

.filter-thumb[data-filter='OUT'] {
  transform: translateX(200%);
}

.filter {
  height: var(--height-pill);
  border: 0;
  border-radius: var(--radius-card);
  background: transparent;
  color: var(--color-text-sub);
  font-family: inherit;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition:
    color var(--duration-base) var(--ease-out),
    opacity var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.filter-on {
  color: var(--color-brand-strong);
}

.row {
  height: var(--height-row);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-4);
  border-top: 1px solid var(--color-divider);
}

.row-left {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.row-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  font-variant-numeric: tabular-nums;
}

.row-sub {
  font-size: var(--text-xs);
  color: var(--color-text-sub);
  font-variant-numeric: tabular-nums;
}

.row-amount {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.amount-in {
  color: var(--color-amount-in);
}

.amount-out {
  color: var(--color-amount-out);
}

.empty {
  margin: 0;
  padding: var(--space-8) 0;
  border-top: 1px solid var(--color-divider);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-sub);
}

@media (prefers-reduced-motion: reduce) {
  .filter,
  .filter-thumb {
    transition: none;
  }
}
</style>
