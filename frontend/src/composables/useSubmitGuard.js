import { computed, onBeforeUnmount, ref } from 'vue'

// 서버에 중복 요청 방지 키가 아직 없어서, 돈이 움직이는 버튼은 화면에서 시간으로 막는다.
// - 요청하는 동안에는 다시 누를 수 없다.
// - 처리된 뒤에도 잠깐 더 막아, 두 번 누른 것이 두 번 처리되지 않게 한다.
// - 응답을 못 받았으면(연결 끊김·시간 초과·서버 오류) 처리됐을 수 있으니 더 오래 막는다.
// - 서버가 처리하지 않았다고 답한 오류(400번대)는 바로 다시 누를 수 있다.
const DONE_COOLDOWN_MS = 3_000
const UNSURE_COOLDOWN_MS = 10_000

export function useSubmitGuard() {
  const isSending = ref(false)
  const isCooling = ref(false)
  const isLocked = computed(() => isSending.value || isCooling.value)
  let timer = null

  function coolDown(ms) {
    clearTimeout(timer)
    isCooling.value = true
    timer = setTimeout(() => {
      isCooling.value = false
    }, ms)
  }

  // 막혀 있으면 아무것도 하지 않고 undefined를 돌려준다. 오류는 그대로 던진다.
  async function run(task) {
    if (isLocked.value) return undefined
    isSending.value = true
    let cooldown = DONE_COOLDOWN_MS
    try {
      return await task()
    } catch (error) {
      const unsure = !error.status || error.status >= 500
      cooldown = unsure ? UNSURE_COOLDOWN_MS : 0
      throw error
    } finally {
      isSending.value = false
      if (cooldown) coolDown(cooldown)
    }
  }

  onBeforeUnmount(() => clearTimeout(timer))

  return { isSending, isCooling, isLocked, run }
}
