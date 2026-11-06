<template>
  <BackHeader to="/me" />

  <form class="form" novalidate @submit.prevent="handleSubmit">
    <div class="content">
      <div class="intro">
        <h1 class="title">비밀번호 변경</h1>
        <p class="desc">아직 서버와 연결되지 않아 실제 비밀번호는 바뀌지 않아요.</p>
      </div>

      <section class="card" aria-label="비밀번호 입력">
        <div v-for="field in fields" :key="field.key" class="form-field">
          <label class="form-label" :for="field.id">{{ field.label }}</label>
          <input
            :id="field.id"
            v-model="form[field.key]"
            class="form-input"
            type="password"
            :autocomplete="field.autocomplete"
            :enterkeyhint="field.enterKey"
            :placeholder="field.placeholder"
            :aria-invalid="Boolean(errors[field.key])"
            :aria-describedby="errors[field.key] ? `${field.id}-error` : undefined"
          />
          <p v-if="errors[field.key]" :id="`${field.id}-error`" class="form-error" role="alert">
            {{ errors[field.key] }}
          </p>
        </div>
      </section>

      <p v-if="checked" class="status" role="status">입력을 확인했어요. 실제 비밀번호는 그대로예요.</p>
    </div>

    <div class="cta-bar bar">
      <button type="submit" class="cta-button">비밀번호 변경</button>
    </div>
  </form>
</template>

<script setup>
import { nextTick, reactive, ref, watch } from 'vue'
import BackHeader from '@/components/BackHeader.vue'

const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/

const fields = [
  {
    key: 'current',
    id: 'password-current',
    label: '현재 비밀번호',
    autocomplete: 'current-password',
    enterKey: 'next',
    placeholder: '지금 쓰는 비밀번호',
  },
  {
    key: 'next',
    id: 'password-next',
    label: '새 비밀번호',
    autocomplete: 'new-password',
    enterKey: 'next',
    placeholder: '영문, 숫자 포함 8자 이상',
  },
  {
    key: 'confirm',
    id: 'password-confirm',
    label: '새 비밀번호 확인',
    autocomplete: 'new-password',
    enterKey: 'done',
    placeholder: '한 번 더 입력',
  },
]

const form = reactive({ current: '', next: '', confirm: '' })
const errors = ref({})
const checked = ref(false)

watch(form, (value) => {
  if (Object.values(value).some(Boolean)) checked.value = false
})

function validate() {
  const found = {}
  if (!form.current) found.current = '현재 비밀번호를 입력해 주세요.'
  if (!PASSWORD_PATTERN.test(form.next)) {
    found.next = '새 비밀번호는 영문, 숫자 포함 8자 이상이어야 해요.'
  } else if (form.next === form.current) {
    found.next = '지금 쓰는 비밀번호와 다르게 입력해 주세요.'
  }
  if (form.next !== form.confirm) found.confirm = '새 비밀번호가 서로 달라요.'
  return found
}

async function handleSubmit() {
  errors.value = validate()
  const firstInvalid = fields.find((field) => errors.value[field.key])
  if (firstInvalid) {
    await nextTick()
    document.getElementById(firstInvalid.id)?.focus()
    return
  }
  Object.assign(form, { current: '', next: '', confirm: '' })
  await nextTick()
  checked.value = true
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

.status {
  margin: 0;
  text-align: center;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-brand-strong);
}

.bar {
  border-top: 1px solid var(--color-nav-border);
}
</style>
