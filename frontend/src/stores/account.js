import { defineStore } from 'pinia'
import { ref } from 'vue'
import { platformIdToName } from '@/config/platforms'
import { accountApi } from '@/api/account'

export const useAccountStore = defineStore('account', () => {
  // 存储所有账号信息
  const accounts = ref([])
  
  // 设置账号列表
  const setAccounts = (accountsData) => {
    // 后端 SELECT * 列顺序:id/type/filePath/userName/status/avatar/fans/likes/follows/stats,
    // 然后 row.append(tags) → tags 为最后一列。stats 是 JSON 字符串,需要解析。
    accounts.value = accountsData.map(item => {
      let stats = []
      const rawStats = item[9]
      if (typeof rawStats === 'string' && rawStats) {
        try { stats = JSON.parse(rawStats) } catch { stats = [] }
      } else if (Array.isArray(rawStats)) {
        stats = rawStats
      }
      return {
        id: item[0],
        type: item[1],
        filePath: item[2],
        name: item[3],
        status: item[4] === -1 ? '验证中' : (item[4] === 1 ? '正常' : '异常'),
        platform: platformIdToName[item[1]] || '未知',
        avatar: item[5] || '',
        fans: item[6] || 0,
        likes: item[7] || 0,
        follows: item[8] || 0,
        stats,
        tags: item[10] || item[item.length - 1] || []
      }
    })
  }
  
  // 添加账号
  const addAccount = (account) => {
    accounts.value.push(account)
  }
  
  // 更新账号
  const updateAccount = (id, updatedAccount) => {
    const index = accounts.value.findIndex(acc => acc.id === id)
    if (index !== -1) {
      accounts.value[index] = { ...accounts.value[index], ...updatedAccount }
    }
  }
  
  // 删除账号
  const deleteAccount = (id) => {
    accounts.value = accounts.value.filter(acc => acc.id !== id)
  }
  
  // 根据平台获取账号
  const getAccountsByPlatform = (platform) => {
    return accounts.value.filter(acc => acc.platform === platform)
  }

  const allTags = ref([])

  const loadTags = async () => {
    try {
      const res = await accountApi.getTags()
      if (res.code === 200 && res.data) {
        allTags.value = res.data
      }
    } catch (e) {
      console.error('加载标签失败:', e)
    }
  }
  
  return {
    accounts,
    setAccounts,
    addAccount,
    updateAccount,
    deleteAccount,
    getAccountsByPlatform,
    allTags,
    loadTags
  }
})