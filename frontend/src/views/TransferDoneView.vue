<template>
  <main v-if="transfer.result" class="screen">
    <router-link to="/" class="brand">
      <BrandLogo />
      <span class="brand-name">포도뱅크</span>
    </router-link>

    <section class="card">
      <span class="success" aria-hidden="true">
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      </span>

      <div class="headline">
        <!-- 화면에는 두 줄로 보이고, 제목(h1)으로는 '누구에게 얼마 보냈어요'를 한 번에 읽는다. -->
        <p class="to" aria-hidden="true">{{ transfer.result.recipientName }}님에게 보냈어요</p>
        <h1 class="amount">
          <span class="visually-hidden">{{ transfer.result.recipientName }}님에게 </span>
          {{ formatWon(transfer.result.amount) }}
          <span class="visually-hidden"> 보냈어요</span>
        </h1>
      </div>

      <dl class="details">
        <dt>출금 계좌</dt>
        <dd>{{ transfer.result.fromAlias }}</dd>
        <dt>일시</dt>
        <dd>{{ formatFullDateTime(transfer.result.requestedAt) }}</dd>
        <dt class="total">남은 잔액</dt>
        <dd class="total total-value">{{ formatWon(transfer.result.balanceAfter) }}</dd>
      </dl>

      <div class="actions">
        <router-link to="/accounts" class="action action-soft">거래내역 보기</router-link>
        <router-link to="/" class="action action-strong">홈으로</router-link>
      </div>
    </section>
  </main>
</template>

<script setup>
import BrandLogo from '@/components/BrandLogo.vue'
import { useTransferStore } from '@/stores/transfer'
import { formatFullDateTime, formatWon } from '@/utils/format'

const transfer = useTransferStore()
</script>

<style scoped>
.screen {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  box-sizing: border-box;
  padding: calc(var(--space-8) + env(safe-area-inset-top, 0px)) var(--screen-padding)
    calc(var(--space-8) + env(safe-area-inset-bottom, 0px));
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: safe center;
  gap: var(--space-8);
}

.brand {
  flex: 0 0 auto;
  height: var(--height-control);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  color: var(--color-text);
  text-decoration: none;
}

.brand-name {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-brand);
}

.card {
  flex: 0 0 auto;
  width: 100%;
  box-sizing: border-box;
  padding: var(--space-8) var(--space-4) var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-8);
  /* 금액 글자 크기를 카드 폭에 맞추려고 카드를 크기 기준으로 삼는다 */
  container-type: inline-size;
}

.success {
  width: var(--size-success);
  height: var(--size-success);
  border-radius: 50%;
  background: var(--color-brand);
  color: var(--color-on-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: pop-in var(--duration-slow) var(--ease-out) var(--duration-fast) backwards;
}

@media (prefers-reduced-motion: reduce) {
  .success {
    animation-name: fade-in;
  }
}

.headline {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  text-align: center;
}

.to {
  margin: 0;
  font-size: var(--text-md);
  color: var(--color-text-sub);
}

.amount {
  margin: 0;
  /* 최대 금액 '10,000,000원'도 한 줄에 들어가게, 좁은 카드(320px 화면)에서는 글자를 줄인다 */
  font-size: min(var(--text-done), 15cqi);
  line-height: var(--leading-hero);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-done);
  font-variant-numeric: tabular-nums;
}

.details {
  width: 100%;
  box-sizing: border-box;
  margin: 0;
  padding: var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-bg);
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--space-4) 0;
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}

.details dt {
  color: var(--color-text-sub);
}

.details dd {
  margin: 0;
  padding-left: var(--space-4);
  text-align: right;
  font-weight: var(--font-semibold);
}

.details .total {
  padding-top: var(--space-4);
  border-top: 1px solid var(--color-dot-empty);
}

.details .total-value {
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.actions {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-4);
}

.action {
  height: var(--height-control);
  border-radius: var(--radius-card);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-md);
  font-weight: var(--font-semibold);
  text-decoration: none;
}

.action-soft {
  background: var(--color-brand-soft);
  color: var(--color-brand-strong);
}

.action-strong {
  background: var(--color-brand);
  color: var(--color-on-brand);
}
</style>
