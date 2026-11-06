<template>
  <BackHeader :to="kakao ? '/login' : '/guest'" />

  <form class="form" role="main" novalidate @submit.prevent="handleSubmit">
    <div class="content">
      <div class="intro">
        <p class="eyebrow">{{ kakao ? '카카오 인증 완료' : '포도뱅크 시작하기' }}</p>
        <h1 class="title">{{ kakao ? '로그인에 쓸 정보를 정해 주세요' : '첫 통장을 만들어 보세요' }}</h1>
      </div>

      <section class="card" aria-label="로그인 정보">
        <div v-for="field in visibleFields" :key="field.key" class="form-field">
          <label class="form-label" :for="field.id">{{ field.label }}</label>
          <input
            :id="field.id"
            v-model="form[field.key]"
            class="form-input"
            :type="field.type"
            :inputmode="field.inputmode"
            :autocomplete="field.autocomplete"
            :enterkeyhint="field.enterKey"
            :placeholder="field.placeholder"
            :aria-invalid="Boolean(errors[field.key])"
            :aria-describedby="errors[field.key] ? `${field.id}-error` : field.help ? `${field.id}-help` : undefined"
          />
          <p v-if="errors[field.key]" :id="`${field.id}-error`" class="form-error">
            {{ errors[field.key] }}
          </p>
          <p v-else-if="field.help" :id="`${field.id}-help`" class="help">{{ field.help }}</p>
        </div>
      </section>

      <section class="card" aria-label="기본 정보">
        <div class="form-field">
          <label class="form-label" for="signup-birth-year">출생 연도</label>
          <input
            id="signup-birth-year"
            v-model="form.birthYear"
            class="form-input"
            type="text"
            inputmode="numeric"
            maxlength="4"
            autocomplete="bday-year"
            enterkeyhint="next"
            placeholder="1998"
            :aria-invalid="Boolean(errors.birthYear)"
            :aria-describedby="errors.birthYear ? 'signup-birth-year-error' : undefined"
          />
          <p v-if="errors.birthYear" id="signup-birth-year-error" class="form-error">
            {{ errors.birthYear }}
          </p>
        </div>

        <fieldset
          v-for="group in choiceGroups"
          :id="`signup-${group.key}`"
          :key="group.key"
          class="choice-field"
          tabindex="-1"
          :aria-describedby="errors[group.key] ? `signup-${group.key}-error` : undefined"
        >
          <legend class="form-label">{{ group.label }}</legend>
          <div class="choice-row">
            <label v-for="option in group.options" :key="String(option.value)" class="choice">
              <input
                v-model="form[group.key]"
                class="choice-input"
                type="radio"
                :name="group.key"
                :value="option.value"
              />
              <span class="choice-label">{{ option.label }}</span>
            </label>
          </div>
          <p v-if="errors[group.key]" :id="`signup-${group.key}-error`" class="form-error">
            {{ errors[group.key] }}
          </p>
        </fieldset>

        <label class="agree">
          <span class="agree-box-wrap">
            <input
              id="signup-agree"
              v-model="form.agreed"
              class="agree-box"
              type="checkbox"
              :aria-invalid="Boolean(errors.agreed)"
              :aria-describedby="errors.agreed ? 'signup-agree-error' : undefined"
            />
          </span>
          <span class="agree-label">서비스 이용약관과 개인정보 처리방침에 동의해요.</span>
        </label>
        <p v-if="errors.agreed" id="signup-agree-error" class="form-error">
          {{ errors.agreed }}
        </p>
      </section>

      <p v-if="formError" class="form-error submit-error" role="alert">{{ formError }}</p>

      <p class="login">
        이미 계정이 있나요? <router-link to="/login" class="login-link hit-area">로그인</router-link>
      </p>
    </div>

    <div class="cta-bar">
      <button type="submit" class="cta-button" :disabled="submitting">
        {{ submitting ? '가입하는 중' : '가입하기' }}
      </button>
    </div>
  </form>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import BackHeader from '@/components/BackHeader.vue'
import { useUserStore } from '@/stores/user'

// kakao: 카카오 인증 뒤 가입. 이름은 카카오 프로필에서 가져오므로 입력칸이 없다.
const props = defineProps({ kakao: { type: Boolean, default: false } })

const PHONE_PATTERN = /^01\d{8,9}$/
const PASSWORD_PATTERN = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/
const THIS_YEAR = new Date().getFullYear()

const textFields = [
  { key: 'name', id: 'signup-name', label: '이름', type: 'text', autocomplete: 'name',
    enterKey: 'next', placeholder: '홍길동' },
  { key: 'phone', id: 'signup-phone', label: '전화번호', type: 'tel', inputmode: 'numeric',
    autocomplete: 'tel', enterKey: 'next', placeholder: '01012345678' },
  { key: 'password', id: 'signup-password', label: '비밀번호', type: 'password',
    autocomplete: 'new-password', enterKey: 'next', placeholder: '영문, 숫자 포함 8자 이상' },
  { key: 'passwordConfirm', id: 'signup-password-confirm', label: '비밀번호 확인', type: 'password',
    autocomplete: 'new-password', enterKey: 'next', placeholder: '한 번 더 입력' },
]

const choiceGroups = [
  { key: 'gender', label: '성별', options: [{ value: 'female', label: '여성' }, { value: 'male', label: '남성' }] },
  { key: 'maritalStatus', label: '혼인 상태',
    options: [{ value: 'single', label: '미혼' }, { value: 'married', label: '기혼' }] },
  { key: 'isEmployed', label: '직장', options: [{ value: true, label: '있어요' }, { value: false, label: '없어요' }] },
]

// 화면 순서대로. 첫 번째로 틀린 칸에 포커스를 준다.
const FIELD_ORDER = ['name', 'phone', 'password', 'passwordConfirm', 'birthYear', 'gender', 'maritalStatus',
  'isEmployed', 'agreed']
const FIELD_IDS = {
  name: 'signup-name', phone: 'signup-phone', password: 'signup-password',
  passwordConfirm: 'signup-password-confirm', birthYear: 'signup-birth-year', gender: 'signup-gender',
  maritalStatus: 'signup-maritalStatus', isEmployed: 'signup-isEmployed', agreed: 'signup-agree',
}
// 서버 오류의 칸 이름 → 화면 칸 이름
const SERVER_FIELDS = {
  name: 'name', phone_number: 'phone', password: 'password', birth_year: 'birthYear', gender: 'gender',
  marital_status: 'maritalStatus', is_employed: 'isEmployed',
}

const router = useRouter()
const user = useUserStore()
const visibleFields = computed(() => textFields.filter((field) => !(props.kakao && field.key === 'name')))

const form = reactive({
  name: '',
  phone: '',
  password: '',
  passwordConfirm: '',
  birthYear: '',
  gender: null,
  maritalStatus: null,
  isEmployed: null,
  agreed: false,
})
const errors = reactive({})
const formError = ref('')
const submitting = ref(false)

// 칸을 고치면 그 칸의 오류를 바로 지운다. 비밀번호를 고치면 확인 칸 오류도 다시 본다.
for (const key of FIELD_ORDER) {
  watch(
    () => form[key],
    () => {
      delete errors[key]
      if (key === 'password') delete errors.passwordConfirm
      formError.value = ''
    },
  )
}

const phoneDigits = () => form.phone.replace(/\D/g, '')

function validate() {
  const next = {}
  const year = Number(form.birthYear)
  if (!props.kakao) {
    if (!form.name.trim()) next.name = '이름을 입력해 주세요.'
    else if (form.name.trim().length > 50) next.name = '이름은 50자까지 쓸 수 있어요.'
  }
  if (!PHONE_PATTERN.test(phoneDigits())) next.phone = '010으로 시작하는 휴대폰 번호를 숫자로 입력해 주세요.'
  if (!PASSWORD_PATTERN.test(form.password)) {
    next.password = '비밀번호는 영문, 숫자 포함 8자 이상이어야 해요.'
  }
  if (form.password !== form.passwordConfirm) next.passwordConfirm = '비밀번호가 서로 달라요.'
  if (!/^\d{4}$/.test(form.birthYear) || year < 1900 || year > THIS_YEAR) {
    next.birthYear = `1900년부터 ${THIS_YEAR}년 사이로 입력해 주세요.`
  }
  if (form.gender === null) next.gender = '성별을 골라 주세요.'
  if (form.maritalStatus === null) next.maritalStatus = '혼인 상태를 골라 주세요.'
  if (form.isEmployed === null) next.isEmployed = '직장이 있는지 골라 주세요.'
  if (!form.agreed) next.agreed = '약관에 동의해 주세요.'
  return next
}

async function showErrors(next) {
  FIELD_ORDER.forEach((key) => delete errors[key])
  Object.assign(errors, next)
  await nextTick()
  const firstKey = FIELD_ORDER.find((key) => next[key])
  if (firstKey) document.getElementById(FIELD_IDS[firstKey])?.focus()
}

async function handleSubmit() {
  formError.value = ''
  const invalid = validate()
  if (Object.keys(invalid).length) {
    await showErrors(invalid)
    return
  }
  await showErrors({})

  submitting.value = true
  try {
    const payload = {
      phone_number: phoneDigits(),
      password: form.password,
      birth_year: Number(form.birthYear),
      gender: form.gender,
      marital_status: form.maritalStatus,
      is_employed: form.isEmployed,
    }
    if (props.kakao) await user.kakaoSignup(payload)
    else await user.signup({ name: form.name.trim(), ...payload })
    router.push({ name: 'home' })
  } catch (signupError) {
    if (signupError instanceof ApiError && signupError.code === 'signup_session_expired') {
      formError.value = '가입 시간(5분)이 지났어요. 카카오로 다시 시작해 주세요.'
    } else if (signupError instanceof ApiError && signupError.code === 'phone_already_registered') {
      await showErrors({ phone: '이미 가입된 전화번호예요. 로그인해 주세요.' })
    } else if (signupError instanceof ApiError && signupError.fields) {
      const next = {}
      for (const name of Object.keys(signupError.fields)) {
        if (SERVER_FIELDS[name]) next[SERVER_FIELDS[name]] = '입력한 값을 확인해 주세요.'
      }
      await showErrors(next)
      if (!Object.keys(next).length) formError.value = signupError.message
    } else {
      formError.value = signupError.message
    }
  } finally {
    submitting.value = false
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


.card {
  box-sizing: border-box;
  padding: var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.choice-field {
  margin: 0;
  padding: 0;
  border: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.choice-field legend {
  padding: 0;
  margin-bottom: var(--space-4);
}

.choice-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.choice {
  position: relative;
  display: block;
}

.choice-input {
  position: absolute;
  opacity: 0;
  inset: 0;
  margin: 0;
  cursor: pointer;
}

.choice-label {
  height: var(--height-control);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--color-input-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: var(--text-md);
  font-weight: var(--font-medium);
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out);
}

.choice-input:checked + .choice-label {
  border-color: var(--color-brand);
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
  font-weight: var(--font-semibold);
}

.choice-input:focus-visible + .choice-label {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

.choice-field[aria-describedby] .choice-label {
  border-color: var(--color-error);
}

.help {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

.agree {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-divider);
  cursor: pointer;
}

/* 체크박스를 글자 첫 줄 높이 안에서 가운데에 둔다(줄 높이는 글자 크기 기준). */
.agree-box-wrap {
  flex: 0 0 auto;
  height: calc(var(--text-sm) * var(--leading-body));
  display: flex;
  align-items: center;
}

.agree-box {
  width: var(--size-checkbox);
  height: var(--size-checkbox);
  margin: 0;
  accent-color: var(--color-brand);
}

.agree-label {
  font-size: var(--text-sm);
  line-height: var(--leading-body);
  color: var(--color-label);
}

.submit-error {
  text-align: center;
}

.login {
  margin: 0;
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-sub);
}

.login-link {
  font-weight: var(--font-semibold);
}

.cta-bar {
  border-top: 1px solid var(--color-nav-border);
}
</style>
