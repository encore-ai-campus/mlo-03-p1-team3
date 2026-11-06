<template>
  <BackHeader to="/me" />
  <main class="main">
    <h1 class="title">약관 및 개인정보</h1>

    <section v-for="section in sections" :key="section.title" class="panel">
      <h2 class="section-title">{{ section.title }}</h2>
      <p class="body">{{ section.body }}</p>
    </section>
  </main>
</template>

<script setup>
import BackHeader from '@/components/BackHeader.vue'

const sections = [
  {
    title: '서비스 안내',
    body: '포도뱅크는 부트캠프 포트폴리오로 만든 가상 은행이에요. 실제 금융 서비스가 아니에요.',
  },
  {
    title: '가상의 돈',
    body: '계좌 잔액과 입금·출금 금액은 모두 가상의 금액이에요. 실제 돈으로 바꿀 수 없어요.',
  },
  {
    title: '저장하는 정보',
    body: '이름, 전화번호, 출생 연도, 성별, 혼인 상태, 직장 유무와 계좌·카드·거래·대출 기록을 저장해요. 비밀번호는 원문이 아니라 변환된 값으로 저장해요.',
  },
  {
    title: '통계로 쓰는 정보',
    body: '서비스 개선을 위해 거래 종류, 금액 구간, 가맹점 지역·업종 같은 통계를 남겨요. 이름·전화번호·계좌번호·정확한 금액은 통계에 넣지 않아요.',
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
  padding: var(--space-4);
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.section-title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.body {
  margin: 0;
  font-size: var(--text-sm);
  line-height: var(--leading-body);
  color: var(--color-text-sub);
}
</style>
