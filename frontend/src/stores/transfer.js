import { ref } from 'vue'
import { defineStore } from 'pinia'
import { request } from '@/api/client'

export const useTransferStore = defineStore('transfer', () => {
  const result = ref(null)

  // 전화번호 또는 계좌번호로 받는 사람을 찾는다. 응답은 이름뿐이다(계좌번호는 내려주지 않음).
  function lookup(query) {
    return request('/transfers/recipient-lookup', { method: 'POST', body: { query } })
  }

  // recipient는 조회할 때 쓴 값 그대로. 응답: { transaction_id, balance }
  function send({ recipient, amount }) {
    return request('/transfers', { method: 'POST', body: { recipient, amount }, moneyMove: true })
  }

  function setResult(value) {
    result.value = value
  }

  function reset() {
    result.value = null
  }

  return { result, lookup, send, setResult, reset }
})
