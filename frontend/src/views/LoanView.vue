<template>
  <AppHeader />
  <main class="main">
    <div class="head">
      <h1 class="title">대출</h1>
    </div>

    <BankingStatus v-if="viewStatus !== 'ready'" :status="viewStatus" :message="viewError" @retry="load" />

    <template v-else>
      <!-- 진행 중인 대출(심사 대기 또는 상환 중)은 1건만 있을 수 있다 -->
      <template v-if="active">
        <section class="card" aria-labelledby="active-title">
          <div class="loan-top">
            <h2 id="active-title" ref="activeTitle" class="card-title" tabindex="-1">
              <span class="visually-hidden">진행 중 대출, </span>{{ productName(active.product_code) }}
            </h2>
            <span class="badge" :class="`badge-${active.status}`">{{ STATUS_LABELS[active.status] }}</span>
          </div>

          <template v-if="active.status === 'pending'">
            <dl class="terms">
              <dt>신청 금액</dt>
              <dd>{{ formatWon(active.principal_amount) }}</dd>
              <dt>기간</dt>
              <dd>{{ active.term_months }}개월</dd>
              <dt>월 상환액</dt>
              <dd>{{ formatWon(active.monthly_installment) }}</dd>
            </dl>
          </template>

          <template v-else>
            <div class="remaining">
              <span class="remaining-label">남은 원금</span>
              <span class="remaining-amount">{{ formatWon(remaining) }}</span>
            </div>
            <div
              class="progress"
              role="progressbar"
              aria-label="상환한 회차"
              :aria-valuenow="paidCount"
              aria-valuemin="0"
              :aria-valuemax="active.installments.length"
              :aria-valuetext="`${active.installments.length}회 중 ${paidCount}회 냈어요`"
            >
              <span class="progress-fill" :style="{ width: `${paidRate}%` }"></span>
            </div>
            <p v-if="overdueCount" class="overdue" role="status">
              연체된 회차가 {{ overdueCount }}개 있어요. 통장에 {{ formatWon(overdueAmount) }} 이상 넣어 두면 다음 날 자동으로 빠져나가요.
            </p>
            <dl class="terms">
              <dt>대출 원금</dt>
              <dd>{{ formatWon(active.principal_amount) }}</dd>
              <dt>낸 회차</dt>
              <dd>{{ paidCount }} / {{ active.installments.length }}회</dd>
              <dt>다음 상환일</dt>
              <dd>{{ nextInstallment ? `${formatDate(nextInstallment.due_date)} · ${formatWon(nextInstallment.amount)}` : '-' }}</dd>
            </dl>
          </template>
        </section>

        <section v-if="active.installments.length" class="card" aria-labelledby="installments-title">
          <h2 id="installments-title" class="card-title">상환 일정</h2>
          <div>
            <div v-for="item in shownInstallments" :key="item.number" class="row">
              <div class="row-left">
                <span class="row-title">{{ item.number }}회차</span>
                <span class="row-sub">{{ formatDate(item.due_date) }}</span>
              </div>
              <div class="row-right">
                <span class="row-amount">{{ formatWon(item.amount) }}</span>
                <span class="row-sub" :class="`state-${item.status}`">{{ INSTALLMENT_LABELS[item.status] }}</span>
              </div>
            </div>
          </div>
          <button
            v-if="active.installments.length > INSTALLMENT_PREVIEW"
            type="button"
            class="more"
            :aria-expanded="showAll"
            @click="showAll = !showAll"
          >
            {{ showAll ? '접기' : `전체 ${active.installments.length}회차 보기` }}
          </button>
        </section>
      </template>

      <form v-else class="card" novalidate @submit.prevent="handleApply">
        <h2 class="card-title">새 대출 신청</h2>

        <fieldset class="group">
          <legend class="form-label">상품</legend>
          <div class="segments">
            <label v-for="product in loanStore.products" :key="product.code" class="segment">
              <input v-model="productCode" class="visually-hidden" type="radio" name="loan-product" :value="product.code" />
              <span class="segment-label">{{ SHORT_NAMES[product.code] ?? product.name }}</span>
            </label>
          </div>
          <p v-if="product" class="hint">
            {{ product.name }} · {{ formatWon(product.min_amount) }} ~ {{ formatWon(product.max_amount) }},
            {{ formatWon(product.amount_step) }} 단위
          </p>
        </fieldset>

        <div v-if="product" class="form-field">
          <label class="form-label" for="loan-amount">빌릴 금액</label>
          <AmountInput id="loan-amount" v-model="amount" :error="amountError" />
          <div class="quick">
            <button v-for="option in quickOptions" :key="option.label" type="button" class="quick-button" @click="option.apply">
              {{ option.label }}
            </button>
          </div>
        </div>

        <fieldset v-if="product" class="group">
          <legend class="form-label">기간</legend>
          <div class="segments segments-wrap">
            <label v-for="term in product.term_options" :key="term" class="segment">
              <input v-model="termMonths" class="visually-hidden" type="radio" name="loan-term" :value="term" />
              <span class="segment-label">{{ term }}개월</span>
            </label>
          </div>
        </fieldset>

        <dl class="terms">
          <dt>이자</dt>
          <dd>없음 (원금만 나눠 갚아요)</dd>
          <dt>월 상환액</dt>
          <dd>{{ monthly ? formatWon(monthly) : '-' }}</dd>
          <dt>받을 계좌</dt>
          <dd>{{ account.alias }}</dd>
          <dt>진행 중 대출</dt>
          <dd>1인 1건</dd>
        </dl>

        <p v-if="submitError" class="form-error" role="alert">{{ submitError }}</p>
        <button type="submit" class="cta-button" :disabled="!canApply || isLocked">{{ applyLabel }}</button>
      </form>

      <section v-if="pastLoans.length" class="card" aria-labelledby="past-title">
        <h2 id="past-title" class="card-title">지난 대출</h2>
        <div>
          <div v-for="loan in pastLoans" :key="loan.application_id" class="row">
            <div class="row-left">
              <span class="row-title">{{ productName(loan.product_code) }}</span>
              <span class="row-sub">{{ loan.term_months }}개월</span>
            </div>
            <div class="row-right">
              <span class="row-amount">{{ formatWon(loan.principal_amount) }}</span>
              <span class="row-sub">{{ STATUS_LABELS[loan.status] }}</span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </main>
  <BottomNav />
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AmountInput from '@/components/AmountInput.vue'
import AppHeader from '@/components/AppHeader.vue'
import BankingStatus from '@/components/BankingStatus.vue'
import BottomNav from '@/components/BottomNav.vue'
import { useSubmitGuard } from '@/composables/useSubmitGuard'
import { useBankingStore } from '@/stores/banking'
import { useLoanStore } from '@/stores/loan'
import { useUserStore } from '@/stores/user'
import { formatWon } from '@/utils/format'

const STATUS_LABELS = { pending: '심사 대기', repaying: '상환 중', rejected: '반려', repaid: '상환 완료' }
const INSTALLMENT_LABELS = { scheduled: '예정', paid: '냈어요', overdue: '연체' }
const SHORT_NAMES = { car: '자동차', jeonse: '전세', home: '주택' }
const ACTIVE = ['pending', 'repaying']
const INSTALLMENT_PREVIEW = 6

const router = useRouter()
const user = useUserStore()
const banking = useBankingStore()
const loanStore = useLoanStore()

const productCode = ref(null)
const amount = ref(0)
const termMonths = ref(null)
const { isSending: isApplying, isCooling, isLocked, run } = useSubmitGuard()
const submitError = ref('')
const showAll = ref(false)
const activeTitle = ref(null)

const viewStatus = computed(() => {
  if (banking.status === 'error' || loanStore.status === 'error') return 'error'
  return banking.accounts.length && loanStore.status === 'ready' ? 'ready' : 'loading'
})
const viewError = computed(() => banking.errorMessage || loanStore.errorMessage)
const account = computed(() => banking.accounts[0])

const active = computed(() => loanStore.loans.find((loan) => ACTIVE.includes(loan.status)))
const pastLoans = computed(() => loanStore.loans.filter((loan) => !ACTIVE.includes(loan.status)))

const paidCount = computed(() => active.value?.installments.filter((i) => i.status === 'paid').length ?? 0)
const paidRate = computed(() => {
  const total = active.value?.installments.length ?? 0
  return total ? Math.floor((paidCount.value / total) * 100) : 0
})
const unpaid = computed(() => active.value?.installments.filter((i) => i.status !== 'paid') ?? [])
const remaining = computed(() => unpaid.value.reduce((sum, i) => sum + i.amount, 0))
const overdue = computed(() => unpaid.value.filter((i) => i.status === 'overdue'))
const overdueCount = computed(() => overdue.value.length)
const overdueAmount = computed(() => overdue.value.reduce((sum, i) => sum + i.amount, 0))
const nextInstallment = computed(() => unpaid.value.find((i) => i.status === 'scheduled'))
const shownInstallments = computed(() =>
  showAll.value ? active.value.installments : active.value.installments.slice(0, INSTALLMENT_PREVIEW),
)

function productName(code) {
  return loanStore.products.find((p) => p.code === code)?.name ?? code
}

function formatDate(value) {
  const [year, month, day] = value.split('-')
  return `${year}.${month}.${day}`
}

// 신청 화면
const product = computed(() => loanStore.products.find((p) => p.code === productCode.value))
const monthly = computed(() => (amount.value && termMonths.value ? Math.floor(amount.value / termMonths.value) : 0))

watch(
  () => loanStore.products,
  (list) => {
    if (!productCode.value && list.length) productCode.value = list[0].code
  },
  { immediate: true },
)
watch(product, (value) => {
  amount.value = 0
  termMonths.value = value?.term_options[0] ?? null
})
watch([productCode, amount, termMonths], () => {
  submitError.value = ''
})

// 서버 규칙과 같다(최소·최대 금액, 100만 원 단위). 서버도 다시 확인한다.
const amountError = computed(() => {
  if (!product.value || !amount.value) return ''
  const { min_amount: min, max_amount: max, amount_step: step } = product.value
  if (amount.value < min || amount.value > max) return `${formatWon(min)} ~ ${formatWon(max)} 사이로 신청해 주세요.`
  if (amount.value % step) return `${formatWon(step)} 단위로 신청해 주세요.`
  return ''
})

function addAmount(value) {
  amount.value = Math.min(amount.value + value, product.value.max_amount)
}

const quickOptions = computed(() => [
  { label: '+100만', apply: () => addAmount(1_000_000) },
  { label: '+1,000만', apply: () => addAmount(10_000_000) },
  { label: '최대', apply: () => (amount.value = product.value.max_amount) },
  { label: '지우기', apply: () => (amount.value = 0) },
])

const canApply = computed(() => Boolean(product.value && termMonths.value && amount.value && !amountError.value))
const applyLabel = computed(() => {
  if (isApplying.value) return '신청하는 중이에요'
  if (isCooling.value) return '잠시 후 다시 누를 수 있어요'
  return canApply.value ? `${formatWon(amount.value)} 신청하기` : '금액과 기간을 골라 주세요'
})

async function load() {
  await Promise.all([banking.load(), loanStore.load()])
  if (!user.isLoggedIn) router.replace({ name: 'guest' })
}

onMounted(load)

async function handleApply() {
  if (!canApply.value || isLocked.value) return
  submitError.value = ''
  try {
    const done = await run(() =>
      loanStore.apply({ productCode: productCode.value, amount: amount.value, termMonths: termMonths.value }),
    )
    if (!done) return
    await loanStore.load()
    // 신청 폼이 사라지고 '진행 중 대출' 카드가 나타난다. 그 제목으로 포커스를 옮겨 결과를 알린다.
    await nextTick()
    activeTitle.value?.focus()
  } catch (error) {
    if (error.status === 401) {
      user.clearSession()
      router.replace({ name: 'login' })
      return
    }
    submitError.value = error.message
    if (error.code === 'active_loan_exists') loanStore.load()
  }
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
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4) 0;
}

.title {
  margin: 0;
  font-size: var(--text-title);
  line-height: var(--leading-title);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-title);
}



.card {
  box-sizing: border-box;
  padding: var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.card-title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.group {
  min-width: 0;
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.group legend {
  margin-bottom: var(--space-4);
  padding: 0;
}

.segments {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  gap: var(--space-4);
}

.segment {
  position: relative;
  cursor: pointer;
}

.segment-label {
  height: var(--height-control);
  border-radius: var(--radius-card);
  background: var(--color-divider);
  color: var(--color-label);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

/* 고른 상태는 앱 전체에서 같은 모양: 연보라 바탕 + 보라 테두리·글자 (회원가입 선택지와 같음) */
.segment input:checked + .segment-label {
  background: var(--color-brand-soft);
  box-shadow: inset 0 0 0 1px var(--color-brand);
  color: var(--color-brand-strong);
}

.segment input:focus-visible + .segment-label {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

.terms {
  margin: 0;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-4) 0;
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}

.terms dt {
  color: var(--color-text-sub);
}

.terms dd {
  margin: 0;
  text-align: right;
  font-weight: var(--font-semibold);
}

.remaining {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.remaining-label {
  font-size: var(--text-sm);
  color: var(--color-text-sub);
}

.remaining-amount {
  font-size: var(--text-hero);
  line-height: var(--leading-hero);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-hero);
  color: var(--color-debt);
  font-variant-numeric: tabular-nums;
}

.progress {
  height: var(--height-progress);
  overflow: hidden;
  border-radius: var(--radius-tile);
  background: var(--color-divider);
}

.progress-fill {
  display: block;
  height: 100%;
  border-radius: var(--radius-tile);
  background: var(--color-brand);
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


.loan-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
}

.badge {
  flex: 0 0 auto;
  /* 위아래 여백 대신 줄 높이로 알약 높이를 만든다(16의 배수 규칙). */
  padding: 0 var(--space-4);
  line-height: var(--leading-body);
  border-radius: var(--radius-card);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.badge-pending {
  background: var(--color-divider);
  color: var(--color-label);
}


.overdue {
  margin: 0;
  padding: var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-bg);
  color: var(--color-debt);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  line-height: var(--leading-body);
}

.state-paid {
  color: var(--color-brand-strong);
}

.state-overdue {
  color: var(--color-debt);
  font-weight: var(--font-semibold);
}

.more {
  height: var(--height-control);
  border: 0;
  border-radius: var(--radius-card);
  background: var(--color-divider);
  color: var(--color-label);
  font-family: inherit;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
}

.segments-wrap {
  grid-auto-flow: row;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.hint {
  margin: var(--space-4) 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

.quick {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-4);
}

/* 좁은 휴대폰에서는 4칸이면 '+1,000만'이 두 줄로 깨진다. 2칸씩 두 줄로 놓는다. */
@media (max-width: 359px) {
  .quick {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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
</style>
