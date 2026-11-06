<template>
  <BackHeader to="/me" />
  <main class="main">
    <h1 class="title">자주 묻는 질문</h1>

    <section class="panel" aria-label="질문 목록">
      <details v-for="item in questions" :key="item.question" class="item">
        <summary class="question">
          {{ item.question }}
          <svg
            class="chevron"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <path d="M9 5l7 7-7 7" />
          </svg>
        </summary>
        <p class="answer">{{ item.answer }}</p>
      </details>
    </section>
  </main>
</template>

<script setup>
import BackHeader from '@/components/BackHeader.vue'

const questions = [
  {
    question: '송금 수수료가 있나요?',
    answer: '포도뱅크 고객끼리 보낼 때 수수료는 0원이에요. 받는 분의 전화번호나 계좌번호로 보낼 수 있어요.',
  },
  {
    question: '한 번에 얼마까지 보낼 수 있나요?',
    answer: '1회 최대 10,000,000원, 하루(한국 시간 0시 기준) 합계 100,000,000원까지 보낼 수 있어요. 잔액보다 많이 보낼 수는 없어요.',
  },
  {
    question: '입금과 출금은 얼마까지 되나요?',
    answer: '입금과 출금 모두 1회 1원부터 10,000,000원까지 할 수 있어요.',
  },
  {
    question: '계좌는 몇 개까지 만들 수 있나요?',
    answer: '한 사람당 입출금 통장 1개를 써요. 가입하면 통장과 체크카드 1장이 바로 만들어져요.',
  },
  {
    question: '체크카드는 어떻게 쓰나요?',
    answer: '카드 탭에서 가맹점을 고르고 금액을 넣으면 통장에서 바로 빠져나가요. 1회 최대 10,000,000원이에요.',
  },
  {
    question: '대출은 얼마까지 받을 수 있나요?',
    answer: '자동차는 5,000만 원, 전세는 2억 원, 주택은 6억 원까지 100만 원 단위로 신청할 수 있어요. 이자는 없고 원금을 개월 수로 나눠 매달 갚아요. 진행 중인 대출은 1인 1건이에요.',
  },
  {
    question: '대출을 신청했는데 잔액이 그대로예요.',
    answer: '신청하면 먼저 직원 심사를 기다려요. 승인되면 대출금이 통장에 바로 들어와요.',
  },
  {
    question: '대출 상환일에 잔액이 모자라면요?',
    answer: '그 회차는 연체가 돼요. 연체 이자는 없고, 통장에 돈을 넣어 두면 다음 날 자동으로 빠져나가요.',
  },
  {
    question: '자꾸 다시 로그인하라고 나와요.',
    answer: '안전을 위해 로그인은 60분 동안 유지돼요. 비밀번호를 5번 틀리면 5분 동안 로그인이 막혀요.',
  },
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

.title {
  margin: 0;
  padding: var(--space-4) 0;
  font-size: var(--text-title);
  line-height: var(--leading-title);
  font-weight: var(--font-bold);
  letter-spacing: var(--tracking-title);
}

.panel {
  flex: 0 0 auto;
  padding: 0 var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-surface);
}

.item + .item {
  border-top: 1px solid var(--color-divider);
}

.question {
  min-height: var(--height-summary-row);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  list-style: none;
  cursor: pointer;
  user-select: none;
  -webkit-user-select: none;
  touch-action: manipulation;
}

.question::-webkit-details-marker {
  display: none;
}

.chevron {
  flex: 0 0 var(--width-chevron);
  color: var(--color-input-border);
  transform: rotate(90deg);
  transition: transform var(--duration-fast);
}

.item[open] .chevron {
  transform: rotate(-90deg);
}

.answer {
  margin: 0;
  padding-bottom: var(--space-4);
  font-size: var(--text-sm);
  line-height: var(--leading-body);
  color: var(--color-text-sub);
  transition:
    opacity var(--duration-base) var(--ease-out),
    transform var(--duration-base) var(--ease-out);
}

@starting-style {
  .answer {
    opacity: 0;
    transform: translateY(calc(var(--space-4) * -1));
  }
}

@media (prefers-reduced-motion: reduce) {
  .chevron {
    transition: none;
  }

  .answer {
    transition: opacity var(--duration-base) var(--ease-out);
  }
}
</style>
