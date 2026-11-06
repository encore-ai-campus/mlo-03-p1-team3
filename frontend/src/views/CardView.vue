<template>
  <AppHeader />

  <BankingStatus
    v-if="status !== 'ready'"
    class="status"
    :status="status"
    :message="errorMessage"
    @retry="load"
  />

  <form v-else class="form" role="main" novalidate @submit.prevent="handleSubmit">
    <div class="content">
      <h1 class="title">카드</h1>

      <section class="plastic" aria-label="내 체크카드">
        <div class="plastic-top">
          <span class="plastic-name">포도 체크카드</span>
          <span class="plastic-chip" aria-hidden="true"></span>
        </div>
        <span class="plastic-number">
          <span aria-hidden="true">•••• •••• •••• </span>
          <span class="visually-hidden">카드번호 끝자리</span>{{ cards.cardLast4 }}
        </span>
        <div class="plastic-bottom">
          <span>{{ account.alias }}</span>
          <span class="plastic-balance">잔액 {{ formatWon(account.balance) }}</span>
        </div>
      </section>

      <section class="card" aria-labelledby="merchant-title">
        <div class="card-head">
          <h2 id="merchant-title" class="card-title">어디서 결제할까요?</h2>
          <span class="count">{{ visibleMerchants.length }}곳</span>
        </div>
        <div class="chips" role="group" aria-label="업종">
          <button
            v-for="option in categories"
            :key="option"
            type="button"
            class="chip hit-area-y"
            :class="{ 'chip-on': category === option }"
            :aria-pressed="category === option"
            @click="category = option"
          >
            {{ option }}
          </button>
        </div>
        <fieldset class="merchants">
          <legend class="visually-hidden">가맹점</legend>
          <label v-for="merchant in visibleMerchants" :key="merchant.id" class="merchant">
            <input
              v-model="merchantId"
              class="merchant-input"
              type="radio"
              name="merchant"
              :value="merchant.id"
              :aria-label="`${merchant.name}, ${merchant.region} ${merchant.category}`"
            />
            <span class="merchant-tile" aria-hidden="true">{{ merchant.category.charAt(0) }}</span>
            <span class="merchant-text">
              <span class="merchant-name">{{ merchant.name }}</span>
              <span class="merchant-sub">{{ merchant.region }} · {{ merchant.category }}</span>
            </span>
            <span class="merchant-check" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>
            </span>
          </label>
        </fieldset>
      </section>

      <section class="card" aria-label="결제 금액">
        <div class="form-field">
          <label class="form-label" for="card-amount">결제할 금액</label>
          <AmountInput id="card-amount" v-model="amount" :error="amountError" />
          <div class="quick">
            <button
              v-for="option in quickOptions"
              :key="option.label"
              type="button"
              class="quick-button"
              @click="option.apply"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
        <dl class="summary">
          <dt>결제 후 잔액</dt>
          <dd>{{ amountError ? '-' : formatWon(account.balance - amount) }}</dd>
        </dl>
      </section>

      <ListCard v-if="recentPayments.length" title="최근 카드 결제" link-label="거래내역" link-to="/accounts">
        <div v-for="tx in recentPayments" :key="tx.entry_id" class="tx-row">
          <span class="tx-text">
            <span class="tx-title">{{ tx.title }}</span>
            <span class="tx-when">{{ formatDateTime(tx.created_at) }}</span>
          </span>
          <span class="tx-amount">{{ formatSignedWon(-tx.amount) }}</span>
        </div>
      </ListCard>
    </div>

    <div class="cta-bar above-nav bar">
      <p v-if="submitError" class="form-error submit-error" role="alert">{{ submitError }}</p>
      <!-- 늘 그려 두고 글자만 바꿔야 화면 읽기 프로그램이 결제 완료를 놓치지 않는다 -->
      <p class="notice-done done-message" :class="{ 'visually-hidden': !doneMessage }" role="status">
        <svg v-if="doneMessage" class="notice-done-icon" width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
        {{ doneMessage }}
      </p>
      <button type="submit" class="cta-button" :disabled="!canPay || isLocked">{{ ctaLabel }}</button>
    </div>
  </form>
  <BottomNav />
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AmountInput from '@/components/AmountInput.vue'
import AppHeader from '@/components/AppHeader.vue'
import BankingStatus from '@/components/BankingStatus.vue'
import BottomNav from '@/components/BottomNav.vue'
import ListCard from '@/components/ListCard.vue'
import { useSubmitGuard } from '@/composables/useSubmitGuard'
import { useBankingStore } from '@/stores/banking'
import { useCardStore } from '@/stores/cards'
import { useUserStore } from '@/stores/user'
import { formatDateTime, formatSignedWon, formatWon } from '@/utils/format'

// 서버 규칙과 같다(1회 1원 ~ 1,000만 원).
const MAX_PAYMENT = 10_000_000
const ALL = '전체'

const router = useRouter()
const user = useUserStore()
const banking = useBankingStore()
const cards = useCardStore()

const category = ref(ALL)
const merchantId = ref(null)
const amount = ref(0)
const submitError = ref('')
const doneMessage = ref('')
const { isSending: isPaying, isCooling, isLocked, run } = useSubmitGuard()

// 카드와 계좌를 둘 다 불러와야 화면을 그린다. 결제 뒤 잔액을 다시 읽는 동안에는 화면을 그대로 둔다.
const status = computed(() => {
  if (banking.status === 'error' || cards.status === 'error') return 'error'
  return banking.accounts.length && cards.status === 'ready' ? 'ready' : 'loading'
})
const errorMessage = computed(() => banking.errorMessage || cards.errorMessage)
const account = computed(() => banking.accounts[0])

const categories = computed(() => [ALL, ...new Set(cards.merchants.map((m) => m.category))])
const visibleMerchants = computed(() =>
  cards.merchants.filter((m) => category.value === ALL || m.category === category.value),
)
const merchant = computed(() => cards.merchants.find((m) => m.id === merchantId.value))
const recentPayments = computed(() =>
  banking.transactions.filter((tx) => tx.entry_type === 'card_payment').slice(0, 3),
)

const amountError = computed(() => {
  if (amount.value > MAX_PAYMENT) return `1회 최대 ${formatWon(MAX_PAYMENT)}까지 결제할 수 있어요.`
  if (amount.value > account.value.balance) {
    return `잔액이 부족해요. 최대 ${formatWon(account.value.balance)}까지 결제할 수 있어요.`
  }
  return ''
})
const canPay = computed(() => Boolean(merchant.value) && amount.value > 0 && !amountError.value)
const ctaLabel = computed(() => {
  if (isPaying.value) return '결제하는 중이에요'
  if (isCooling.value && amount.value) return '잠시 후 다시 누를 수 있어요'
  if (!merchant.value) return '가맹점을 골라 주세요'
  if (!amount.value) return '금액을 입력해 주세요'
  return canPay.value ? `${formatWon(amount.value)} 결제하기` : '금액을 확인해 주세요'
})

function addAmount(value) {
  amount.value = Math.min(amount.value + value, MAX_PAYMENT)
}

const quickOptions = [
  { label: '+5천', apply: () => addAmount(5_000) },
  { label: '+1만', apply: () => addAmount(10_000) },
  { label: '+5만', apply: () => addAmount(50_000) },
  { label: '+10만', apply: () => addAmount(100_000) },
  { label: '지우기', apply: () => (amount.value = 0) },
]

watch([merchantId, amount], ([, value]) => {
  submitError.value = ''
  if (value) doneMessage.value = ''
})

async function load() {
  await Promise.all([banking.load(), cards.load()])
  if (!user.isLoggedIn) router.replace({ name: 'guest' })
}

onMounted(load)

async function handleSubmit() {
  if (!canPay.value || isLocked.value) return
  submitError.value = ''
  doneMessage.value = ''
  const paid = { name: merchant.value.name, amount: amount.value }
  try {
    const done = await run(() => cards.pay(merchantId.value, paid.amount))
    if (!done) return
  } catch (error) {
    if (error.status === 401) {
      user.clearSession()
      router.replace({ name: 'login' })
      return
    }
    submitError.value = error.message
    if (error.code === 'insufficient_funds') banking.refresh()
    return
  }
  amount.value = 0
  doneMessage.value = `${paid.name}에서 ${formatWon(paid.amount)} 결제했어요.`
  // 결제는 이미 끝났다. 잔액을 못 읽어 와도 결제 실패로 보이지 않게 화면을 그대로 둔다.
  const refreshed = await banking.refresh()
  if (!refreshed) doneMessage.value += ' 잔액은 잠시 후 다시 확인해 주세요.'
}
</script>

<style scoped>
.done-message {
  margin-bottom: var(--space-4);
}

.status {
  flex: 1 1 auto;
}

.form {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  box-sizing: border-box;
  padding: 0 var(--screen-padding) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--card-gap);
}

/* 계좌·대출·내 정보 화면 제목과 같은 위아래 여백 */
.title {
  margin: 0;
  padding: var(--space-4) 0;
  font-size: var(--text-title);
  line-height: var(--leading-title);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-title);
}


/* 카드 실물 모양. 홈 잔액 카드와 같은 브랜드 색을 쓴다. */
.plastic {
  flex: 0 0 var(--height-card-plastic);
  box-sizing: border-box;
  padding: var(--space-8) var(--space-8) var(--space-4);
  border-radius: var(--radius-card);
  background: linear-gradient(135deg, var(--color-brand) 0%, var(--color-brand-deep) 100%);
  color: var(--color-on-brand);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.plastic-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plastic-name {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-brand);
}

.plastic-chip {
  width: var(--height-control);
  height: var(--height-pill);
  border-radius: var(--radius-tile);
  background: var(--color-brand-light);
}

.plastic-number {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  font-variant-numeric: tabular-nums;
}

.plastic-bottom {
  display: flex;
  justify-content: space-between;
  gap: var(--space-4);
  font-size: var(--text-sm);
  color: var(--color-on-brand-muted);
}

.plastic-balance {
  font-variant-numeric: tabular-nums;
}


.card {
  flex: 0 0 auto;
  box-sizing: border-box;
  padding: var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.card-title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.count {
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
}

.chip {
  height: var(--height-pill);
  padding: 0 var(--space-4);
  border: 0;
  border-radius: var(--radius-card);
  background: var(--color-divider);
  color: var(--color-text-sub);
  font-family: inherit;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  cursor: pointer;
}

/* 고른 상태는 앱 전체에서 같은 모양: 연보라 바탕 + 보라 테두리·글자 */
.chip-on {
  background: var(--color-brand-soft);
  box-shadow: inset 0 0 0 1px var(--color-brand);
  color: var(--color-brand-strong);
}

.merchants {
  margin: 0;
  padding: 0;
  border: 0;
  max-height: calc(var(--height-row) * 4);
  overflow-y: auto;
  overscroll-behavior: contain;
}

.merchant {
  position: relative;
  height: var(--height-row);
  display: grid;
  grid-template-columns: var(--size-tile) minmax(0, 1fr) var(--width-chevron);
  align-items: center;
  gap: var(--space-4);
  border-top: 1px solid var(--color-divider);
  cursor: pointer;
}

.merchant-input {
  position: absolute;
  inset: 0;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.merchant-tile {
  width: var(--size-tile);
  height: var(--size-tile);
  border-radius: var(--radius-tile);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
}

.merchant-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.merchant-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.merchant-sub {
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

.merchant-check {
  color: var(--color-brand-strong);
  opacity: 0;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.merchant-input:checked ~ .merchant-check {
  opacity: 1;
}

.merchant-input:checked ~ .merchant-text .merchant-name {
  color: var(--color-brand-strong);
}

.merchant-input:focus-visible ~ .merchant-tile {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

.quick {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--space-4);
}

/* 좁은 휴대폰에서는 5칸이면 버튼이 44px보다 좁아진다. 3칸씩 두 줄로 놓는다. */
@media (max-width: 359px) {
  .quick {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.quick-button {
  height: var(--height-control);
  padding: 0;
  border: 0;
  border-radius: var(--radius-card);
  background: var(--color-divider);
  color: var(--color-label);
  font-family: inherit;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
}

.summary {
  margin: 0;
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-divider);
  display: grid;
  grid-template-columns: auto 1fr;
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}

.summary dt {
  color: var(--color-text-sub);
}

.summary dd {
  margin: 0;
  text-align: right;
  font-weight: var(--font-bold);
}

.tx-row {
  height: var(--height-row);
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-4);
  border-top: 1px solid var(--color-divider);
}

.tx-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

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

.tx-amount {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
  text-align: right;
  color: var(--color-amount-out);
  font-variant-numeric: tabular-nums;
}

.bar {
  border-top: 1px solid var(--color-nav-border);
}

.submit-error {
  margin-bottom: var(--space-4);
}
</style>
