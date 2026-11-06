<template>
  <div class="box" :class="{ 'box-error': error }">
    <input
      :id="id"
      class="input"
      type="text"
      inputmode="numeric"
      autocomplete="off"
      enterkeyhint="done"
      placeholder="0"
      :value="modelValue ? formatNumber(modelValue) : ''"
      :aria-invalid="Boolean(error)"
      :aria-describedby="error ? `${id}-error` : undefined"
      @input="handleInput"
    />
    <span class="unit">원</span>
  </div>
  <p v-if="error" :id="`${id}-error`" class="form-error" role="alert">{{ error }}</p>
</template>

<script setup>
import { formatNumber } from '@/utils/format'

defineProps({
  id: { type: String, required: true },
  modelValue: { type: Number, required: true },
  error: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue'])

function handleInput(event) {
  const value = Number(event.target.value.replace(/\D/g, '').slice(0, 10))
  emit('update:modelValue', value)
  event.target.value = value ? formatNumber(value) : ''
}
</script>

<style scoped>
.box {
  height: var(--height-amount);
  box-sizing: border-box;
  padding: 0 var(--space-4);
  border: 1px solid var(--color-input-border);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  /* 숫자와 '원'은 한 단어처럼 붙인다. 글자 간격이라 16배수 대신 글자 크기 기준으로 둔다. */
  gap: 0.25em;
}

.box:focus-within {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

.box-error {
  border-color: var(--color-error);
}

.input {
  flex: 1 1 auto;
  min-width: 0;
  height: calc(var(--height-amount) - 2px);
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--color-text);
  font-family: inherit;
  font-size: var(--text-title);
  font-weight: var(--font-bold);
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.input::placeholder {
  color: var(--color-text-sub);
  opacity: 1;
}

.unit {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-weak);
}
</style>
