<template>
  <BackHeader to="/accounts" />

  <form class="form" novalidate @submit.prevent="handleSubmit">
    <div class="content">
      <div class="intro">
        <h1 class="title">새 계좌 개설</h1>
        <p class="desc">계좌는 최대 3개까지 만들 수 있어요</p>
      </div>

      <section class="card">
        <div class="form-field">
          <label class="form-label" for="account-alias">계좌 이름</label>
          <input
            id="account-alias"
            v-model="alias"
            class="form-input"
            type="text"
            enterkeyhint="done"
            maxlength="20"
            placeholder="여행 통장"
            :aria-invalid="Boolean(errorMessage)"
            :aria-describedby="errorMessage ? 'account-alias-error' : undefined"
          />
          <p v-if="errorMessage" id="account-alias-error" class="form-error" role="alert">
            {{ errorMessage }}
          </p>
        </div>

        <dl class="terms">
          <dt>시작 잔액</dt>
          <dd>0원</dd>
          <dt>계좌번호</dt>
          <dd>만들 때 자동으로 정해져요</dd>
        </dl>
      </section>
    </div>

    <div class="cta-bar bar">
      <button type="submit" class="cta-button" :disabled="!alias.trim() || isSending">
        {{ isSending ? '만드는 중이에요' : '계좌 만들기' }}
      </button>
    </div>
  </form>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import BackHeader from '@/components/BackHeader.vue'
import { useBankingStore } from '@/stores/banking'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const user = useUserStore()
const banking = useBankingStore()

const alias = ref('')
const isSending = ref(false)
const errorMessage = ref('')

watch(alias, () => {
  errorMessage.value = ''
})

async function handleSubmit() {
  if (!alias.value.trim() || isSending.value) return
  isSending.value = true
  errorMessage.value = ''
  try {
    const account = await banking.openAccount(alias.value)
    banking.setNotice(`${account.alias}을 만들었어요.`)
    router.replace({ name: 'accounts' })
  } catch (error) {
    if (error.status === 401) {
      user.clearSession()
      router.replace({ name: 'login' })
      return
    }
    errorMessage.value = error.message
  } finally {
    isSending.value = false
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

.terms {
  margin: 0;
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-divider);
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-4) 0;
  font-size: var(--text-sm);
}

.terms dt {
  color: var(--color-text-sub);
}

.terms dd {
  margin: 0;
  padding-left: var(--space-4);
  text-align: right;
  font-weight: var(--font-semibold);
}

.bar {
  border-top: 1px solid var(--color-nav-border);
}
</style>
