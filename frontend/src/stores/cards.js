import { ref } from 'vue'
import { defineStore } from 'pinia'
import { request } from '@/api/client'
import { useUserStore } from '@/stores/user'

// 데이터 수집원: 체크카드·가맹점. 가입할 때 카드 1장이 자동으로 나온다.
export const useCardStore = defineStore('cards', () => {
  const status = ref('idle')
  const errorMessage = ref('')
  const cardLast4 = ref('')
  const merchants = ref([])

  // 처음에만 '불러오는 중'. 이미 받은 내용이 있으면 화면을 그대로 두고 뒤에서 새로 읽는다.
  async function load() {
    const hadData = status.value === 'ready'
    if (!hadData) status.value = 'loading'
    errorMessage.value = ''
    try {
      const [card, list] = await Promise.all([request('/cards/me'), request('/merchants')])
      cardLast4.value = card.card_last4
      merchants.value = list
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
    cardLast4.value = ''
    merchants.value = []
  }

  // 응답: { transaction_id, balance }. 결제하면 연결 계좌에서 바로 빠진다.
  function pay(merchantId, amount) {
    return request('/cards/payments', { method: 'POST', body: { merchant_id: merchantId, amount }, moneyMove: true })
  }

  return { status, errorMessage, cardLast4, merchants, load, pay, reset }
})
