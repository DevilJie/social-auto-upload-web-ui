import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settingsApi } from '@/api/v2'

export const useAppStore = defineStore('app', () => {
  // 是否是第一次进入账号管理页面
  const isFirstTimeAccountManagement = ref(true)

  // 自动填充标题设置
  const autoFillTitle = ref(true)

  const setAutoFillTitle = (value) => {
    autoFillTitle.value = value
    const settings = JSON.parse(localStorage.getItem('app_settings') || '{}')
    settings.autoFillTitle = value
    localStorage.setItem('app_settings', JSON.stringify(settings))
  }

  const loadAutoFillTitle = () => {
    const settings = JSON.parse(localStorage.getItem('app_settings') || '{}')
    autoFillTitle.value = settings.autoFillTitle !== undefined ? settings.autoFillTitle : true
  }

  // 自动保存草稿设置
  const autoSaveDraft = ref(true)
  const autoSaveInterval = ref(10) // 秒

  const setAutoSaveDraft = (value) => {
    autoSaveDraft.value = value
    const settings = JSON.parse(localStorage.getItem('app_settings') || '{}')
    settings.autoSaveDraft = value
    localStorage.setItem('app_settings', JSON.stringify(settings))
  }

  const setAutoSaveInterval = (value) => {
    autoSaveInterval.value = value
    const settings = JSON.parse(localStorage.getItem('app_settings') || '{}')
    settings.autoSaveInterval = value
    localStorage.setItem('app_settings', JSON.stringify(settings))
  }

  const loadAutoSaveSettings = () => {
    const settings = JSON.parse(localStorage.getItem('app_settings') || '{}')
    autoSaveDraft.value = settings.autoSaveDraft !== undefined ? settings.autoSaveDraft : true
    autoSaveInterval.value = settings.autoSaveInterval !== undefined ? settings.autoSaveInterval : 10
  }

  // 封面比例设置
  const portraitRatio = ref('9:16')
  const landscapeRatio = ref('16:9')

  const setPortraitRatio = (value) => {
    portraitRatio.value = value
    const settings = JSON.parse(localStorage.getItem('app_settings') || '{}')
    settings.portraitRatio = value
    localStorage.setItem('app_settings', JSON.stringify(settings))
  }

  const setLandscapeRatio = (value) => {
    landscapeRatio.value = value
    const settings = JSON.parse(localStorage.getItem('app_settings') || '{}')
    settings.landscapeRatio = value
    localStorage.setItem('app_settings', JSON.stringify(settings))
  }

  const loadCoverRatioSettings = () => {
    const settings = JSON.parse(localStorage.getItem('app_settings') || '{}')
    portraitRatio.value = settings.portraitRatio || '9:16'
    landscapeRatio.value = settings.landscapeRatio || '16:9'
  }
  
  // 是否是第一次进入素材管理页面
  const isFirstTimeMaterialManagement = ref(true)

  // 账号管理页面刷新状态
  const isAccountRefreshing = ref(false)

  // 素材列表数据
  const materials = ref([])
  
  // 设置账号管理页面已访问
  const setAccountManagementVisited = () => {
    isFirstTimeAccountManagement.value = false
  }
  
  // 设置素材管理页面已访问
  const setMaterialManagementVisited = () => {
    isFirstTimeMaterialManagement.value = false
  }
  
  // 重置所有访问状态（用于重新登录或刷新应用时）
  const resetVisitStatus = () => {
    isFirstTimeAccountManagement.value = true
    isFirstTimeMaterialManagement.value = true
  }

  // 更新素材列表
  const setMaterials = (materialList) => {
    materials.value = materialList
  }

  // 删除素材
  const removeMaterial = (materialId) => {
    const index = materials.value.findIndex(m => m.id === materialId)
    if (index > -1) {
      materials.value.splice(index, 1)
    }
  }
  
  // 设置账号管理页面刷新状态
  const setAccountRefreshing = (status) => {
    isAccountRefreshing.value = status
  }

  // ========== 渠道黑名单 ==========
  // 平台 key 数组,如 ['xiaohongshu', 'youtube']
  const disabledPlatforms = ref([])

  // 判断某平台 key 是否被拉黑
  const isPlatformDisabled = (key) => disabledPlatforms.value.includes(key)

  // 批量添加(单次 PUT)
  const addDisabledPlatforms = async (keys) => {
    const newKeys = keys.filter(k => !disabledPlatforms.value.includes(k))
    if (newKeys.length === 0) return
    const snapshot = [...disabledPlatforms.value]
    disabledPlatforms.value = [...disabledPlatforms.value, ...newKeys]
    try {
      await settingsApi.updateSettings({
        disabledPlatforms: disabledPlatforms.value
      })
    } catch (e) {
      disabledPlatforms.value = snapshot  // 回滚
      throw e
    }
  }

  // 移除单个
  const removeDisabledPlatform = async (key) => {
    const snapshot = [...disabledPlatforms.value]
    disabledPlatforms.value = disabledPlatforms.value.filter(k => k !== key)
    try {
      await settingsApi.updateSettings({
        disabledPlatforms: disabledPlatforms.value
      })
    } catch (e) {
      disabledPlatforms.value = snapshot
      throw e
    }
  }

  return {
    isFirstTimeAccountManagement,
    isFirstTimeMaterialManagement,
    isAccountRefreshing,
    materials,
    autoFillTitle,
    setAutoFillTitle,
    loadAutoFillTitle,
    autoSaveDraft,
    autoSaveInterval,
    setAutoSaveDraft,
    setAutoSaveInterval,
    loadAutoSaveSettings,
    portraitRatio,
    landscapeRatio,
    setPortraitRatio,
    setLandscapeRatio,
    loadCoverRatioSettings,
    setAccountManagementVisited,
    setMaterialManagementVisited,
    resetVisitStatus,
    setMaterials,
    removeMaterial,
    setAccountRefreshing,
    disabledPlatforms,
    isPlatformDisabled,
    addDisabledPlatforms,
    removeDisabledPlatform
  }
})