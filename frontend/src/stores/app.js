import { defineStore } from 'pinia'
import { ref } from 'vue'

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

  // 添加新素材
  const addMaterial = (material) => {
    materials.value.push(material)
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

  return {
    isFirstTimeAccountManagement,
    isFirstTimeMaterialManagement,
    isAccountRefreshing,
    materials,
    autoFillTitle,
    setAutoFillTitle,
    loadAutoFillTitle,
    setAccountManagementVisited,
    setMaterialManagementVisited,
    resetVisitStatus,
    setMaterials,
    addMaterial,
    removeMaterial,
    setAccountRefreshing
  }
})