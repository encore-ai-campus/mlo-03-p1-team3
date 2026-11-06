import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { request } from '@/api/client'
import { useUserStore } from '@/stores/user'

// 원장 종류(entry_type) → 화면에 보이는 거래 이름
const ENTRY_TITLES = {
  deposit: '입금',
  withdrawal: '출금',
  transfer_out: '송금 보냄',
  transfer_in: '송금 받음',
  loan_disbursement: '대출금 입금',
  loan_repayment: '대출 상환',
  card_payment: '체크카드 결제',
}
const LEDGER_LIMIT = 50
const ACCOUNT_ALIAS = '포도 입출금 통장'

// 원장 한 줄을 화면이 쓰는 모양으로 바꾼다. 금액은 부호 없이, 방향은 IN/OUT으로 나눈다.
function toTransaction(entry, index) {
  return {
    entry_id: `${entry.transaction_id}-${entry.entry_type}-${index}`,
    title: ENTRY_TITLES[entry.entry_type] ?? '거래',
    entry_type: entry.entry_type,
    direction: entry.amount > 0 ? 'IN' : 'OUT',
    amount: Math.abs(entry.amount),
    balance_after: entry.balance_after,
    created_at: entry.created_at,
  }
}

// 갚지 않은 회차 합계 = 남은 빚. 진행 중인 대출(repaying)만 센다.
function remainingDebt(loans) {
  return loans
    .filter((loan) => loan.status === 'repaying')
    .flatMap((loan) => loan.installments)
    .filter((item) => item.status !== 'paid')
    .reduce((sum, item) => sum + item.amount, 0)
}

// 데이터 수집원: 계좌·거래내역. 백엔드는 한 사람당 계좌 1개다.
export const useBankingStore = defineStore('banking', () => {
  const user = useUserStore()

  const status = ref('idle')
  const errorMessage = ref('')
  const account = ref(null)
  const transactions = ref([])
  const totalDebt = ref(0)

  const accounts = computed(() => (account.value ? [account.value] : []))
  const totalBalance = computed(() => account.value?.balance ?? 0)
  const netAssets = computed(() => totalBalance.value - totalDebt.value)

  async function fetchAll() {
    const [me, ledger, loans] = await Promise.all([
      request('/accounts/me'),
      request(`/accounts/me/ledger?limit=${LEDGER_LIMIT}`),
      request('/loans/me'),
    ])
    account.value = {
      account_id: 'me',
      alias: ACCOUNT_ALIAS,
      account_no: me.account_number,
      balance: me.balance,
      is_primary: true,
    }
    transactions.value = ledger.items.map(toTransaction)
    totalDebt.value = remainingDebt(loans)
  }

  // 처음에만 '불러오는 중'을 보여 준다. 이미 받은 내용이 있으면 화면을 그대로 두고 뒤에서 새로 읽는다.
  // (탭을 옮길 때마다 빈 화면이 깜빡이지 않게 한다. 새로 읽기에 실패해도 보이던 내용은 둔다.)
  async function load() {
    const hadData = status.value === 'ready'
    if (!hadData) status.value = 'loading'
    errorMessage.value = ''
    try {
      await fetchAll()
      status.value = 'ready'
    } catch (error) {
      if (error.status === 401) user.clearSession()
      else if (hadData) return
      errorMessage.value = error.message
      status.value = 'error'
    }
  }

  // 결제·송금 뒤 잔액만 새로 읽는다. 실패해도 화면은 그대로 두고 false를 돌려준다.
  // (load처럼 오류 화면으로 바꾸면, 돈은 이미 빠졌는데 실패한 것처럼 보인다.)
  async function refresh() {
    try {
      await fetchAll()
      return true
    } catch (error) {
      if (error.status === 401) user.clearSession()
      return false
    }
  }

  // 로그아웃·로그인 만료 때 다른 사람이 볼 수 없도록 비운다.
  function reset() {
    status.value = 'idle'
    errorMessage.value = ''
    account.value = null
    transactions.value = []
    totalDebt.value = 0
  }

  // type: 'deposit' | 'withdraw'. 응답: { transaction_id, balance }
  function moveCash(type, amount) {
    const path = type === 'deposit' ? 'deposit' : 'withdrawal'
    return request(`/transactions/${path}`, { method: 'POST', body: { amount }, moneyMove: true })
  }

  return {
    status,
    errorMessage,
    accounts,
    transactions,
    totalBalance,
    totalDebt,
    netAssets,
    load,
    refresh,
    reset,
    moveCash,
  }
})
