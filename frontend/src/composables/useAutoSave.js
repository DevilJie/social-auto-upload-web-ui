import { ref, watch, onBeforeUnmount } from 'vue'
import { useAppStore } from '@/stores/app'

export function useAutoSave(saveFn) {
  const appStore = useAppStore()
  const autoSaveTimer = ref(null)
  const hasChanges = ref(false)

  function startAutoSaveTimer() {
    stopAutoSaveTimer()
    if (!appStore.autoSaveDraft) return
    autoSaveTimer.value = setInterval(() => {
      if (hasChanges.value) {
        saveFn()
        hasChanges.value = false
      }
    }, appStore.autoSaveInterval * 1000)
  }

  function stopAutoSaveTimer() {
    if (autoSaveTimer.value) {
      clearInterval(autoSaveTimer.value)
      autoSaveTimer.value = null
    }
  }

  watch(() => appStore.autoSaveDraft, (val) => {
    if (val) startAutoSaveTimer()
    else stopAutoSaveTimer()
  })

  watch(() => appStore.autoSaveInterval, () => {
    if (appStore.autoSaveDraft) startAutoSaveTimer()
  })

  onBeforeUnmount(() => {
    stopAutoSaveTimer()
  })

  return {
    hasChanges,
    startAutoSaveTimer,
    stopAutoSaveTimer,
  }
}
