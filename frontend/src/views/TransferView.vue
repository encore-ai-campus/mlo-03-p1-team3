<template>
  <BackHeader to="/" />

  <BankingStatus
    v-if="banking.status !== 'ready'"
    :status="banking.status"
    :message="banking.errorMessage"
    @retry="load"
  />

  <form v-else class="form" role="main" novalidate @submit.prevent="handleSubmit">
    <div class="content">
      <div class="intro">
        <h1 class="title">송금</h1>
      </div>

      <section class="card">
        <div class="form-field">
          <span class="form-label">출금 계좌</span>
          <p class="from-account">
            <span>{{ fromAccount.alias }}</span>
            <span class="from-balance">{{ formatWon(fromBalance) }}</span>
          </p>
        </div>

        <div class="form-field">
          <label class="form-label" for="transfer-to">받는 분 전화번호 또는 계좌번호</label>
          <input
            id="transfer-to"
            :value="query"
            class="form-input number"
            type="text"
            inputmode="numeric"
            autocomplete="off"
            enterkeyhint="next"
            placeholder="예: 01012345678"
            :aria-invalid="Boolean(accountError)"
            aria-describedby="transfer-to-status"
            @input="handleQueryInput"
          />
          <!-- 늘 그려 두고 안의 글자만 바꿔야 화면 읽기 프로그램이 받는 분 이름을 놓치지 않는다 -->
          <p id="transfer-to-status" class="lookup-status" aria-live="polite">
            <span v-if="recipient" class="found">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path d="M5 12.5l4.5 4.5L19 7.5" />
              </svg>
              {{ recipient.label }}
            </span>
            <span v-else-if="accountError" class="form-error">{{ accountError }}</span>
            <span v-else-if="isLookingUp" class="help">받는 분을 찾고 있어요</span>
          </p>
        </div>

        <div class="form-field amount-field">
          <label class="form-label" for="transfer-amount">보낼 금액</label>
          <AmountInput id="transfer-amount" v-model="amount" :error="amountError" />
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

      </section>

      <section class="card" aria-label="송금 확인">
        <h2 class="confirm-title">이렇게 보낼게요</h2>
        <div class="confirm-to">
          <span class="avatar" aria-hidden="true">{{ recipient?.name.charAt(0) ?? '?' }}</span>
          <div class="confirm-text">
            <span class="confirm-name">
              {{ recipient ? `${recipient.name}님에게` : '받는 분을 입력해 주세요' }}
            </span>
            <span v-if="recipient" class="confirm-no">포도뱅크 고객</span>
          </div>
        </div>
        <dl class="confirm-list">
          <dt>보낼 금액</dt>
          <dd class="strong">{{ formatWon(amount) }}</dd>
          <dt>수수료</dt>
          <dd>0원</dd>
          <dt class="total">송금 후 잔액</dt>
          <dd class="total total-value" :class="{ 'total-error': isOverBalance }">
            {{ isOverBalance ? '잔액 부족' : formatWon(fromBalance - amount) }}
          </dd>
        </dl>
      </section>
    </div>

    <div class="cta-bar bar">
      <p v-if="submitError" class="form-error submit-error" role="alert">{{ submitError }}</p>
      <button type="submit" class="cta-button" :disabled="!canSend || isLocked">{{ ctaLabel }}</button>
    </div>
  </form>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AmountInput from '@/components/AmountInput.vue'
import BackHeader from '@/components/BackHeader.vue'
import BankingStatus from '@/components/BankingStatus.vue'
import { useBankingData } from '@/composables/useBankingData'
import { useSubmitGuard } from '@/composables/useSubmitGuard'
import { useTransferStore } from '@/stores/transfer'
import { useUserStore } from '@/stores/user'
import { formatWon } from '@/utils/format'

// 서버 규칙과 같다. 하루 합계(1억 원)는 서버가 확인하고 오류 문구를 돌려준다.
const MAX_TRANSFER = 10_000_000
const PHONE_PATTERN = /^01\d{8,9}$/
const ACCOUNT_PATTERN = /^\d{3}-\d{4}-\d{4}$/
// 입력이 멈추고 이만큼 지나면 받는 분을 찾는다. 11자리 번호를 치는 중 10자리에서 잘못 찾지 않게 한다.
const LOOKUP_DELAY_MS = 400

const router = useRouter()
const user = useUserStore()
const transfer = useTransferStore()
const { banking, load } = useBankingData()

const query = ref('')
const amount = ref(0)
const lookedUp = ref(null)
const lookupFailure = ref(null)
const isLookingUp = ref(false)
const submitError = ref('')
const { isSending, isCooling, isLocked, run } = useSubmitGuard()
let lookupTimer = null

// 한 사람당 계좌 1개라서 출금 계좌는 고르지 않는다.
const fromAccount = computed(() => banking.accounts[0])
const fromBalance = computed(() => fromAccount.value?.balance ?? 0)

const isComplete = computed(() => PHONE_PATTERN.test(query.value) || ACCOUNT_PATTERN.test(query.value))
const isOwnAccount = computed(() => query.value === fromAccount.value?.account_no)

const recipient = computed(() => {
  if (lookedUp.value?.query !== query.value) return null
  return { ...lookedUp.value, label: `${lookedUp.value.name}님에게 보내요` }
})

watch(query, (value) => {
  lookedUp.value = null
  lookupFailure.value = null
  submitError.value = ''
  clearTimeout(lookupTimer)
  isLookingUp.value = false
  if (!isComplete.value || isOwnAccount.value) return

  isLookingUp.value = true
  lookupTimer = setTimeout(() => lookupRecipient(value), LOOKUP_DELAY_MS)
})

onBeforeUnmount(() => clearTimeout(lookupTimer))

async function lookupRecipient(value) {
  if (query.value !== value) return
  try {
    const { name } = await transfer.lookup(value)
    if (query.value === value) lookedUp.value = { name, query: value }
  } catch (error) {
    if (error.status === 401) return endSession()
    if (query.value === value) lookupFailure.value = { query: value, message: error.message }
  } finally {
    if (query.value === value) isLookingUp.value = false
  }
}

watch(amount, () => {
  submitError.value = ''
})

const accountError = computed(() => {
  if (!isComplete.value || recipient.value) return ''
  if (isOwnAccount.value) return '내 계좌로는 보낼 수 없어요.'
  return lookupFailure.value?.query === query.value ? lookupFailure.value.message : ''
})

const isOverBalance = computed(() => amount.value > fromBalance.value)
const amountError = computed(() => {
  if (isOverBalance.value) {
    return `잔액이 부족해요. 최대 ${formatWon(Math.min(fromBalance.value, MAX_TRANSFER))}까지 보낼 수 있어요.`
  }
  if (amount.value > MAX_TRANSFER) return `1회 최대 ${formatWon(MAX_TRANSFER)}까지 보낼 수 있어요.`
  return ''
})

const canSend = computed(() => Boolean(recipient.value) && amount.value > 0 && !amountError.value)
const ctaLabel = computed(() => {
  if (isSending.value) return '보내는 중이에요'
  if (isCooling.value) return '잠시 후 다시 누를 수 있어요'
  if (!recipient.value) return '받는 분을 확인해 주세요'
  return canSend.value ? `${formatWon(amount.value)} 보내기` : '금액을 확인해 주세요'
})

function addAmount(value) {
  amount.value = Math.min(amount.value + value, MAX_TRANSFER)
}

const quickOptions = [
  { label: '+1만', apply: () => addAmount(10_000) },
  { label: '+5만', apply: () => addAmount(50_000) },
  { label: '+10만', apply: () => addAmount(100_000) },
  { label: '전액', apply: () => (amount.value = Math.min(fromBalance.value, MAX_TRANSFER)) },
  { label: '지우기', apply: () => (amount.value = 0) },
]

// 01로 시작하면 전화번호(숫자만), 아니면 계좌번호(100-1234-5678 모양)로 맞춘다.
function handleQueryInput(event) {
  const digits = event.target.value.replace(/\D/g, '').slice(0, 11)
  query.value = digits.startsWith('01')
    ? digits
    : [digits.slice(0, 3), digits.slice(3, 7), digits.slice(7)].filter(Boolean).join('-')
  event.target.value = query.value
}

function endSession() {
  user.clearSession()
  router.replace({ name: 'login' })
}

async function handleSubmit() {
  if (!canSend.value || isLocked.value) return
  submitError.value = ''
  try {
    const done = await run(() => transfer.send({ recipient: query.value, amount: amount.value }))
    if (!done) return
    const { balance } = done
    transfer.setResult({
      recipientName: recipient.value.name,
      fromAlias: fromAccount.value.alias,
      amount: amount.value,
      balanceAfter: balance,
      requestedAt: Date.now(),
    })
    router.replace({ name: 'transfer-done' })
  } catch (error) {
    if (error.status === 401) return endSession()
    submitError.value = error.message
    // 잔액이 바뀌었을 수 있으니(다른 기기 등) 계좌를 다시 읽는다.
    if (error.code === 'insufficient_funds') banking.refresh()
  }
}
</script>

<style scoped>
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

.intro {
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

.number {
  font-variant-numeric: tabular-nums;
}

.lookup-status {
  margin: 0;
}

/* 비어 있을 때는 자리만 차지하지 않게 숨긴다. 화면 읽기 프로그램이 지켜보도록 요소는 남겨 둔다. */
.lookup-status:empty {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
}

.found {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-4);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-brand-strong);
}

.amount-field {
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-divider);
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

.from-account {
  height: var(--height-control);
  box-sizing: border-box;
  margin: 0;
  padding: 0 var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-bg);
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
}

.from-balance {
  color: var(--color-text-sub);
  font-weight: var(--font-medium);
  font-variant-numeric: tabular-nums;
}

.help {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

.confirm-title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.confirm-to {
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

.confirm-text {
  display: flex;
  flex-direction: column;
}

.confirm-name {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.confirm-no {
  font-size: var(--text-xs);
  color: var(--color-text-sub);
  font-variant-numeric: tabular-nums;
}

.confirm-list {
  margin: 0;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-4) 0;
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}

.confirm-list dt {
  color: var(--color-text-sub);
}

.confirm-list dd {
  margin: 0;
  text-align: right;
  font-weight: var(--font-semibold);
}

.confirm-list .strong {
  font-weight: var(--font-bold);
}

.confirm-list .total {
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-nav-border);
}

.confirm-list .total-value {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.confirm-list .total-error {
  color: var(--color-error);
}

.bar {
  border-top: 1px solid var(--color-nav-border);
}

.submit-error {
  margin-bottom: var(--space-4);
}
</style>
