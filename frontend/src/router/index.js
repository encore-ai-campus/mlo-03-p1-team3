import { nextTick } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import { useTransferStore } from '@/stores/transfer'
import { useUserStore } from '@/stores/user'
import AccountsView from '@/views/AccountsView.vue'
import CardView from '@/views/CardView.vue'
import CashView from '@/views/CashView.vue'
import GuestView from '@/views/GuestView.vue'
import HomeView from '@/views/HomeView.vue'
import KakaoCallbackView from '@/views/KakaoCallbackView.vue'
import LoanView from '@/views/LoanView.vue'
import LoginView from '@/views/LoginView.vue'
import MyFaqView from '@/views/MyFaqView.vue'
import MyNotificationsView from '@/views/MyNotificationsView.vue'
import MyTermsView from '@/views/MyTermsView.vue'
import MyView from '@/views/MyView.vue'
import SignupView from '@/views/SignupView.vue'
import TransferDoneView from '@/views/TransferDoneView.vue'
import TransferView from '@/views/TransferView.vue'

const routes = [
  { path: '/guest', name: 'guest', component: GuestView, meta: { title: '시작하기', guestOnly: true } },
  { path: '/login', name: 'login', component: LoginView, meta: { title: '로그인', guestOnly: true } },
  { path: '/signup', name: 'signup', component: SignupView, meta: { title: '회원가입', guestOnly: true } },
  {
    path: '/signup/kakao',
    name: 'kakao-signup',
    component: SignupView,
    props: { kakao: true },
    meta: { title: '카카오로 가입', guestOnly: true },
  },
  {
    path: '/auth/kakao/callback',
    name: 'kakao-callback',
    component: KakaoCallbackView,
    meta: { title: '카카오 로그인 확인', guestOnly: true },
  },
  { path: '/', name: 'home', component: HomeView, meta: { title: '홈', requiresAuth: true } },
  { path: '/accounts', name: 'accounts', component: AccountsView, meta: { title: '계좌', requiresAuth: true } },
  { path: '/accounts/:id/cash', name: 'cash', component: CashView, meta: { title: '입출금', requiresAuth: true } },
  { path: '/transfer', name: 'transfer', component: TransferView, meta: { title: '송금', requiresAuth: true } },
  {
    path: '/transfer/done',
    name: 'transfer-done',
    component: TransferDoneView,
    meta: { title: '송금 완료', requiresAuth: true },
    beforeEnter: () => (useTransferStore().result ? true : { name: 'transfer' }),
  },
  { path: '/card', name: 'card', component: CardView, meta: { title: '카드', requiresAuth: true } },
  { path: '/loan', name: 'loan', component: LoanView, meta: { title: '대출', requiresAuth: true } },
  { path: '/me', name: 'my', component: MyView, meta: { title: '내 정보', requiresAuth: true } },
  {
    path: '/me/notifications',
    name: 'my-notifications',
    component: MyNotificationsView,
    meta: { title: '알림 설정', requiresAuth: true },
  },
  { path: '/me/faq', name: 'my-faq', component: MyFaqView, meta: { title: '자주 묻는 질문', requiresAuth: true } },
  { path: '/me/terms', name: 'my-terms', component: MyTermsView, meta: { title: '약관 및 개인정보', requiresAuth: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const user = useUserStore()
  await user.restore()

  if (to.meta.requiresAuth && !user.isLoggedIn) {
    return to.name === 'home' ? { name: 'guest' } : { name: 'login' }
  }
  if (to.meta.guestOnly && user.isLoggedIn) {
    return { name: 'home' }
  }
})

const APP_NAME = '포도뱅크'

// 화면이 바뀐 것을 화면 읽기 프로그램도 알 수 있게, 탭 제목을 바꾸고 새 화면의 제목(h1)으로 포커스를 옮긴다.
// 처음 열 때는 옮기지 않는다(브라우저가 알아서 페이지 처음부터 읽는다).
router.afterEach(async (to, from, failure) => {
  if (failure) return
  document.title = to.meta.title ? `${to.meta.title} - ${APP_NAME}` : APP_NAME
  if (from.matched.length === 0) return

  const startFocus = document.activeElement
  await nextTick()
  const target = await findHeading()
  // 기다리는 사이 사용자가 다른 곳을 눌렀으면 포커스를 빼앗지 않는다.
  const active = document.activeElement
  if (!target || (active && active !== document.body && active !== startFocus)) return
  if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1')
  target.focus({ preventScroll: true })
})

// 송금·카드처럼 정보를 불러온 뒤에 제목이 그려지는 화면이 있어서, 제목이 나타날 때까지 잠깐 기다린다.
const HEADING_WAIT_MS = 3_000

function findHeading() {
  const find = () => document.querySelector('#app h1')
  const found = find()
  if (found) return Promise.resolve(found)

  return new Promise((resolve) => {
    const observer = new MutationObserver(() => {
      const heading = find()
      if (!heading) return
      observer.disconnect()
      clearTimeout(timer)
      resolve(heading)
    })
    const timer = setTimeout(() => {
      observer.disconnect()
      resolve(null)
    }, HEADING_WAIT_MS)
    observer.observe(document.querySelector('#app'), { childList: true, subtree: true })
  })
}

export default router
