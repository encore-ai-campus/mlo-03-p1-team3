import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useBankingStore } from '@/stores/banking'
import { useUserStore } from '@/stores/user'

export function useBankingData() {
  const router = useRouter()
  const user = useUserStore()
  const banking = useBankingStore()

  async function load() {
    await banking.load()
    if (!user.isLoggedIn) router.replace({ name: 'guest' })
  }

  onMounted(load)

  return { banking, load }
}
