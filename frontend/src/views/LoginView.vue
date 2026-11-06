<template>
  <div class="screen" role="main">
    <header class="header">
      <router-link to="/guest" class="close" aria-label="닫기">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </router-link>
    </header>

    <form class="form" novalidate @submit.prevent="handleSubmit">
      <div class="content">
        <div class="intro">
          <BrandLogo :size="48" />
          <div class="intro-text">
            <p class="eyebrow">다시 만나 반가워요</p>
            <h1 class="title">전화번호로 로그인해 주세요</h1>
          </div>
        </div>

        <div class="fields">
          <div class="form-field">
            <label class="form-label" for="login-phone">전화번호</label>
            <input
              id="login-phone"
              v-model="phone"
              class="form-input"
              type="tel"
              inputmode="numeric"
              :aria-invalid="Boolean(error)"
              :aria-describedby="error ? 'login-error' : undefined"
              autocomplete="tel"
              enterkeyhint="next"
              placeholder="01012345678"
            />
          </div>
          <div class="form-field">
            <label class="form-label" for="login-password">비밀번호</label>
            <input
              id="login-password"
              v-model="password"
              class="form-input"
              type="password"
              :aria-invalid="Boolean(error)"
              :aria-describedby="error ? 'login-error' : undefined"
              autocomplete="current-password"
              enterkeyhint="go"
              placeholder="비밀번호 입력"
            />
          </div>
          <p v-if="error" id="login-error" class="form-error" role="alert">{{ error }}</p>
        </div>

        <div class="divider" aria-hidden="true"><span>또는</span></div>

        <button type="button" class="kakao-button" :disabled="kakaoLoading" @click="handleKakao">
          <svg class="kakao-icon" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
            <path
              fill="currentColor"
              d="M12 3C6.48 3 2 6.58 2 11c0 2.84 1.86 5.33 4.66 6.75l-.95 3.5c-.08.3.26.54.52.37l4.17-2.77c.53.07 1.06.1 1.6.1 5.52 0 10-3.58 10-8S17.52 3 12 3z"
            />
          </svg>
          {{ kakaoLoading ? '카카오로 이동하는 중' : '카카오로 시작하기' }}
        </button>
        <p v-if="kakaoError" class="form-error kakao-error" role="alert">{{ kakaoError }}</p>

        <p class="signup">
          아직 계정이 없나요? <router-link to="/signup" class="signup-link hit-area">회원가입</router-link>
        </p>
      </div>

      <div class="cta-bar">
        <button type="submit" class="cta-button" :disabled="submitting">
          {{ submitting ? '로그인하는 중' : '로그인' }}
        </button>
      </div>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BrandLogo from '@/components/BrandLogo.vue'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const user = useUserStore()

const phone = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)
const kakaoLoading = ref(false)
const kakaoError = ref('')

async function handleKakao() {
  kakaoError.value = ''
  kakaoLoading.value = true
  try {
    window.location.assign(await user.kakaoStart())
  } catch (startError) {
    kakaoError.value = startError.message
    kakaoLoading.value = false
  }
}

async function handleSubmit() {
  error.value = ''
  const phoneNumber = phone.value.replace(/\D/g, '')
  if (!phoneNumber || !password.value) {
    error.value = '전화번호와 비밀번호를 입력해 주세요.'
    return
  }

  submitting.value = true
  try {
    await user.login({ phoneNumber, password: password.value })
    router.push({ name: 'home' })
  } catch (loginError) {
    error.value = loginError.message
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.screen {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
}

.header {
  flex: 0 0 calc(var(--height-header) + env(safe-area-inset-top, 0px));
  box-sizing: border-box;
  padding-top: env(safe-area-inset-top, 0px);
  display: flex;
  align-items: center;
}

.close {
  width: var(--height-control);
  height: var(--height-control);
  margin-left: var(--space-4);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text);
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
  padding: var(--space-8) var(--screen-padding);
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
}

.intro {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-8);
  text-align: center;
}

.intro-text {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.eyebrow {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-brand-strong);
}

.title {
  margin: 0;
  font-size: var(--text-title);
  line-height: var(--leading-title);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-title);
}

.fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.divider {
  display: flex;
  align-items: center;
  gap: var(--space-4);
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

.divider::before,
.divider::after {
  content: '';
  flex: 1 1 auto;
  border-top: 1px solid var(--color-divider);
}

.kakao-button {
  width: 100%;
  height: var(--height-control);
  border: 0;
  border-radius: var(--radius-card);
  background: var(--color-kakao);
  color: var(--color-on-kakao);
  font-family: inherit;
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  cursor: pointer;
}

.kakao-button:disabled {
  cursor: progress;
}

.kakao-error {
  text-align: center;
}

.signup {
  margin: 0;
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-sub);
}

.signup-link {
  font-weight: var(--font-semibold);
}
</style>
