<template>
  <BackHeader to="/me" />
  <main class="main">
    <div class="intro">
      <h1 class="title">알림 설정</h1>
      <p class="desc">받고 싶은 알림을 골라 주세요</p>
    </div>

    <section class="panel" aria-label="알림 종류">
      <label v-for="option in options" :key="option.key" class="option">
        <span class="option-text">
          <span class="option-title">{{ option.title }}</span>
          <span class="option-desc">{{ option.desc }}</span>
        </span>
        <input v-model="settings.notifications[option.key]" class="input" type="checkbox" role="switch" />
        <span class="switch" aria-hidden="true"></span>
      </label>
    </section>

    <p class="notice">이 기기에만 저장돼요. 실제 알림 발송은 아직 연결되지 않았어요.</p>
  </main>
</template>

<script setup>
import BackHeader from '@/components/BackHeader.vue'
import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore()

const options = [
  { key: 'transaction', title: '입출금 알림', desc: '돈이 들어오거나 나갈 때 알려 드려요' },
  { key: 'loan', title: '대출 알림', desc: '대출 신청과 상환 내용을 알려 드려요' },
  { key: 'marketing', title: '혜택·마케팅 알림', desc: '새 소식과 혜택을 알려 드려요' },
]
</script>

<style scoped>
.main {
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

.panel {
  flex: 0 0 auto;
  padding: 0 var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}

.option {
  position: relative;
  min-height: var(--height-row);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  cursor: pointer;
}

.option + .option {
  border-top: 1px solid var(--color-divider);
}

.option-text {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.option-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.option-desc {
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

/* 입력은 행 전체를 덮어 44px 터치 영역과 키보드 포커스를 그대로 쓴다. */
.input {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  margin: 0;
  opacity: 0;
  cursor: pointer;
}

.switch {
  flex: 0 0 var(--width-switch);
  height: var(--height-switch);
  border-radius: var(--height-switch);
  background: var(--color-input-border);
  display: flex;
  align-items: center;
  padding: 0 var(--offset-switch-knob);
  box-sizing: border-box;
  transition: background var(--duration-fast);
}

.switch::after {
  content: '';
  width: var(--size-switch-knob);
  height: var(--size-switch-knob);
  border-radius: 50%;
  background: var(--color-surface);
  transition: transform var(--duration-fast);
}

.input:checked + .switch {
  background: var(--color-brand);
}

.input:checked + .switch::after {
  transform: translateX(calc(var(--width-switch) - var(--size-switch-knob) - var(--offset-switch-knob) * 2));
}

.input:focus-visible + .switch {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

.notice {
  margin: 0;
  text-align: center;
  font-size: var(--text-xs);
  color: var(--color-text-sub);
}

@media (prefers-reduced-motion: reduce) {
  .switch,
  .switch::after {
    transition: none;
  }
}
</style>
