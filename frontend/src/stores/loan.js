import { ref } from 'vue'
import { defineStore } from 'pinia'
import { request } from '@/api/client'
import { useUserStore } from '@/stores/user'

// 데이터 수집원: 대출. 신청하면 심사 대기(pending)가 되고, 직원이 승인하면 대출금이 통장에 들어온다.
export const useLoanStore = defineStore('loan', () => {
  const status = ref('idle')
  const errorMessage = ref('')
  const products = ref([])
  const loans = ref([])

  // 처음에만 '불러오는 중'. 이미 받은 내용이 있으면 화면을 그대로 두고 뒤에서 새로 읽는다.
  async function load() {
    const hadData = status.value === 'ready'
    if (!hadData) status.value = 'loading'
    errorMessage.value = ''
    try {
      const [productList, myLoans] = await Promise.all([request('/loans/products'), request('/loans/me')])
      products.value = productList
      loans.value = myLoans
      status.value = 'ready'
    } catch (error) {
      if (error.status === 401) useUserStore().clearSession()
      else if (hadData) return
      errorMessage.value = error.message
      status.value = 'error'
    }
  }

  // 로그아웃·로그인 만료 때 비운다.
  function reset() {
    status.value = 'idle'
    errorMessage.value = ''
    products.value = []
    loans.value = []
  }

  // 응답: { application_id, status: 'pending', monthly_installment }
  function apply({ productCode, amount, termMonths }) {
    return request('/loans/applications', {
      method: 'POST',
      body: { product_code: productCode, amount, term_months: termMonths },
      moneyMove: true,
    })
  }

  return { status, errorMessage, products, loans, load, apply, reset }
})
