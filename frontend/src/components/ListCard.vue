<template>
  <section class="card">
    <div class="head">
      <h2 class="title">{{ title }}</h2>
      <router-link :to="linkTo" class="more hit-area">{{ linkLabel }}</router-link>
    </div>
    <slot />
  </section>
</template>

<script setup>
defineProps({
  title: { type: String, required: true },
  linkLabel: { type: String, required: true },
  linkTo: { type: String, required: true },
})
</script>

<style scoped>
.card {
  box-sizing: border-box;
  padding: var(--space-4) var(--space-4) 0;
  border-radius: var(--radius-card);
  background: var(--color-surface);
  display: flex;
  flex-direction: column;
}

.head {
  height: var(--height-card-head);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: var(--font-bold);
}

.more {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  text-decoration: none;
}
</style>
