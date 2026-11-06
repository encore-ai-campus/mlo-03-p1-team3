<template>
  <main class="screen">
    <div v-if="!error" class="state" role="status">
      <BrandLogo :size="48" />
      <h1 class="message">카카오 로그인을 확인하는 중이에요</h1>
    </div>
    <div v-else class="state">
      <BrandLogo :size="48" />
      <h1 class="message">카카오 로그인을 마치지 못했어요</h1>
      <p class="form-error" role="alert">{{ error }}</p>
      <router-link to="/login" class="back-link hit-area">로그인 화면으로</router-link>
    </div>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandLogo from '@/components/BrandLogo.vue'
import { useUserStore } from '@/stores/user'

// 카카오가 로그인 뒤 돌려보내는 화면(Redirect URI). 주소의 code·state를 서버로 보낸다.
const route = useRoute()
const router = useRouter()
const user = useUserStore()
const error = ref('')

onMounted(async () => {
  const { code, state } = route.query
  if (route.query.error || !code || !state) {
    error.value = '카카오에서 로그인을 취소했거나 응답이 없어요.'
    return
  }
  try {
    const status = await user.kakaoLogin({ code: String(code), state: String(state) })
    router.replace(status === 'authenticated' ? { name: 'home' } : { name: 'kakao-signup' })
  } catch (loginError) {
    error.value = loginError.message
  }
})
</script>

<style scoped>
.screen {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--screen-padding);
  background: var(--color-surface);
}

.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
}

.message {
  margin: 0;
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
}

.back-link {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}
</style>
