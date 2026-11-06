import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, request } from '@/api/client'
import { useBankingStore } from '@/stores/banking'
import { useCardStore } from '@/stores/cards'
import { useLoanStore } from '@/stores/loan'
import { useTransferStore } from '@/stores/transfer'

// 화면을 옮길 때 로그인이 아직 살아 있는지 서버에 다시 묻는 간격.
// 쿠키가 만료됐는데도 API를 부르지 않는 화면(마이 등)이 계속 열리지 않게 한다.
const RECHECK_MS = 60_000

// 데이터 수집원: 사용자 정보. 로그인 상태는 서버 쿠키가 들고 있고, 여기에는 화면에 쓸 값만 둔다.
export const useUserStore = defineStore('user', () => {
  const name = ref('')
  const role = ref('')
  const isRestored = ref(false)
  let checkedAt = 0
  const isLoggedIn = computed(() => Boolean(name.value))

  // 로그아웃·로그인 만료 때 이름뿐 아니라 잔액·거래내역·송금 결과도 모두 비운다.
  // 같은 기기에서 다른 사람이 로그인해도 앞사람 정보가 보이지 않게 한다.
  function clearSession() {
    name.value = ''
    role.value = ''
    useBankingStore().reset()
    useCardStore().reset()
    useLoanStore().reset()
    useTransferStore().reset()
  }

  async function loadMe() {
    const me = await request('/auth/me')
    if (me.role !== 'customer') {
      // 직원 계정은 고객 앱 기능을 쓸 수 없다(서버도 403). 바로 로그아웃한다.
      await request('/auth/logout', { method: 'POST' }).catch(() => {})
      clearSession()
      throw new ApiError(403, 'forbidden', '직원 계정은 고객 앱에서 쓸 수 없어요.')
    }
    name.value = me.name
    role.value = me.role
    checkedAt = Date.now()
  }

  async function login({ phoneNumber, password }) {
    await request('/auth/login', {
      method: 'POST',
      body: { phone_number: phoneNumber, password },
    })
    await loadMe()
  }

  // 일반 가입. 성공하면 서버가 바로 로그인 쿠키를 준다.
  async function signup(payload) {
    await request('/auth/signup', { method: 'POST', body: payload })
    await loadMe()
  }

  // 카카오 로그인 1단계: 서버가 state 쿠키를 주고 카카오 로그인 주소를 돌려준다.
  async function kakaoStart() {
    const { authorization_url: url } = await request('/auth/kakao/start', { method: 'POST' })
    return url
  }

  // 카카오 로그인 2단계: 카카오가 돌려준 code·state를 서버로 보낸다.
  // 우리 회원이면 'authenticated', 처음 온 사람이면 'registration_required'(카카오 가입 화면으로).
  async function kakaoLogin({ code, state }) {
    const { status } = await request('/auth/kakao/login', { method: 'POST', body: { code, state } })
    if (status === 'authenticated') await loadMe()
    return status
  }

  // 카카오 가입. 이름은 서버가 카카오 프로필에서 가져오므로 보내지 않는다.
  async function kakaoSignup(payload) {
    await request('/auth/kakao/signup', { method: 'POST', body: payload })
    await loadMe()
  }

  async function logout() {
    try {
      await request('/auth/logout', { method: 'POST' })
    } finally {
      clearSession()
    }
  }

  // 새로고침 후 쿠키가 살아 있으면 로그인 상태를 되살린다.
  // 로그인한 뒤에도 RECHECK_MS마다 한 번씩 다시 확인한다.
  async function restore() {
    if (isRestored.value) {
      if (!isLoggedIn.value || Date.now() - checkedAt < RECHECK_MS) return
      try {
        await loadMe()
      } catch (error) {
        // 연결이 잠깐 끊긴 것만으로 로그아웃시키지는 않는다.
        if (error.status === 401 || error.status === 403) clearSession()
      }
      return
    }
    isRestored.value = true
    try {
      await loadMe()
    } catch {
      clearSession()
    }
  }

  return {
    name, role, isLoggedIn, login, signup, kakaoStart, kakaoLogin, kakaoSignup, logout, restore, clearSession,
  }
})
