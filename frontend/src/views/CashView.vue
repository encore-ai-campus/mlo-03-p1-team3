<template>
  <BackHeader to="/accounts" />

  <BankingStatus
    v-if="banking.status !== 'ready'"
    :status="banking.status"
    :message="banking.errorMessage"
    @retry="load"
  />

  <main v-else-if="!account" class="missing">
    <h1 class="title">계좌를 찾을 수 없어요</h1>
    <router-link to="/accounts" class="missing-link hit-area-y">계좌 목록으로 돌아가기</router-link>
  </main>

  <form v-else class="form" role="main" novalidate @submit.prevent="handleSubmit">
    <div class="content">
      <div class="intro">
        <h1 class="title">{{ copy.title }}</h1>
        <p class="desc">{{ account.alias }} {{ account.account_no }}</p>
      </div>

      <section class="card">
        <div class="form-field">
          <label class="form-label" for="cash-amount">{{ copy.label }}</label>
          <AmountInput id="cash-amount" v-model="amount" :error="amountError" />
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
          <dt>현재 잔액</dt>
          <dd>{{ formatWon(account.balance) }}</dd>
          <dt class="total">{{ copy.after }}</dt>
          <dd class="total total-value">{{ amountError ? '-' : formatWon(balanceAfter) }}</dd>
        </dl>
      </section>
    </div>

    <div class="cta-bar bar">
      <p v-if="submitError" class="form-error submit-error" role="alert">{{ submitError }}</p>
      <button type="submit" class="cta-button" :disabled="!canSubmit || isLocked">
        {{ ctaLabel }}
      </button>
    </div>
  </form>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AmountInput from '@/components/AmountInput.vue'
import BackHeader from '@/components/BackHeader.vue'
import BankingStatus from '@/components/BankingStatus.vue'
import { useBankingData } from '@/composables/useBankingData'
import { useSubmitGuard } from '@/composables/useSubmitGuard'
import { useUserStore } from '@/stores/user'
import { formatWon } from '@/utils/format'

// 서버 규칙과 같다(입금·출금 모두 1회 1원 ~ 1,000만 원).
const MAX_AMOUNT = 10_000_000
const COPY = {
  deposit: {
    title: '입금하기',
    label: '입금할 금액',
    after: '입금 후 잔액',
    verb: '입금',
  },
  withdraw: {
    title: '출금하기',
    label: '출금할 금액',
    after: '출금 후 잔액',
    verb: '출금',
  },
}

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const { banking, load } = useBankingData()

const amount = ref(0)
const submitError = ref('')
const { isSending, isCooling, isLocked, run } = useSubmitGuard()

const type = computed(() => (route.query.type === 'withdraw' ? 'withdraw' : 'deposit'))
const isDeposit = computed(() => type.value === 'deposit')
const copy = computed(() => COPY[type.value])
const account = computed(() =>
  // 한 사람당 계좌 1개라서 주소의 id와 상관없이 내 계좌를 쓴다.
  banking.accounts[0],
)

const balanceAfter = computed(
  () => account.value.balance + (isDeposit.value ? amount.value : -amount.value),
)
const amountError = computed(() => {
  if (amount.value > MAX_AMOUNT) {
    return `1회 최대 ${formatWon(MAX_AMOUNT)}까지 ${copy.value.verb}할 수 있어요.`
  }
  if (!isDeposit.value && amount.value > account.value.balance) {
    return `잔액이 부족해요. 최대 ${formatWon(account.value.balance)}까지 출금할 수 있어요.`
  }
  return ''
})

const canSubmit = computed(() => amount.value > 0 && !amountError.value)
const ctaLabel = computed(() => {
  if (isSending.value) return `${copy.value.verb}하는 중이에요`
  if (isCooling.value) return '잠시 후 다시 누를 수 있어요'
  if (!amount.value) return '금액을 입력해 주세요'
  return amountError.value ? '금액을 확인해 주세요' : `${formatWon(amount.value)} ${copy.value.verb}하기`
})

function addAmount(value) {
  amount.value = Math.min(amount.value + value, MAX_AMOUNT)
}

const quickOptions = computed(() => [
  { label: '+1만', apply: () => addAmount(10_000) },
  { label: '+5만', apply: () => addAmount(50_000) },
  { label: '+10만', apply: () => addAmount(100_000) },
  isDeposit.value
    ? { label: '최대', apply: () => (amount.value = MAX_AMOUNT) }
    : { label: '전액', apply: () => (amount.value = Math.min(account.value.balance, MAX_AMOUNT)) },
  { label: '지우기', apply: () => (amount.value = 0) },
])

watch(amount, () => {
  submitError.value = ''
})

async function handleSubmit() {
  if (!canSubmit.value || isLocked.value) return
  submitError.value = ''
  try {
    const done = await run(() => banking.moveCash(type.value, amount.value))
    if (done) {
      const notice = `${formatWon(amount.value)} ${copy.value.verb}했어요.`
      router.replace({ name: 'accounts', state: { notice } })
    }
  } catch (error) {
    if (error.status === 401) {
      user.clearSession()
      router.replace({ name: 'login' })
      return
    }
    submitError.value = error.message
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

.desc {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-sub);
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
  gap: var(--space-4) 0;
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}

.summary dt {
  color: var(--color-text-sub);
}

.summary dd {
  margin: 0;
  padding-left: var(--space-4);
  text-align: right;
  font-weight: var(--font-semibold);
}

.summary .total {
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-nav-border);
}

.summary .total-value {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.bar {
  border-top: 1px solid var(--color-nav-border);
}

.submit-error {
  margin-bottom: var(--space-4);
}

.missing {
  flex: 1 1 auto;
  padding: var(--space-4) var(--screen-padding);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.missing-link {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}
</style>
