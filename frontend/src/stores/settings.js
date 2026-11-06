import { reactive, watch } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'grape-bank.notifications'
const DEFAULT_NOTIFICATIONS = { transaction: true, loan: true, marketing: false }

function readNotifications() {
  try {
    return { ...DEFAULT_NOTIFICATIONS, ...JSON.parse(localStorage.getItem(STORAGE_KEY)) }
  } catch {
    return { ...DEFAULT_NOTIFICATIONS }
  }
}

// 알림 API가 없어서 이 기기에만 저장한다.
export const useSettingsStore = defineStore('settings', () => {
  const notifications = reactive(readNotifications())

  watch(notifications, (value) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    } catch {
      // 저장소를 쓸 수 없으면 이번 사용 중에만 유지한다.
    }
  })

  return { notifications }
})
