import { http } from '@/utils/request'

// 任务管理
export const taskApi = {
  getTasks(params) {
    return http.get('/api/v2/tasks', params)
  },
  getTask(taskId) {
    return http.get(`/api/v2/tasks/${taskId}`)
  },
  createTask(data) {
    return http.post('/api/v2/tasks', data)
  },
  cancelTask(taskId) {
    return http.post(`/api/v2/tasks/${taskId}/cancel`)
  },
  retryTask(taskId) {
    return http.post(`/api/v2/tasks/${taskId}/retry`)
  },
  getQueueStatus() {
    return http.get('/api/v2/queue/status')
  },
}

// 发布历史
export const historyApi = {
  getHistory(params) {
    // params: { type?: 'video'|'image', status?, timeRange?, startDate?, endDate?, page, pageSize }
    // 返回: data.items = [{id, type, title, ..., items: [{id, account_name, platform, status, ...}]}, ...]
    return http.get('/api/v2/history', params)
  },
}

// 统计数据
export const statsApi = {
  getStats() {
    return http.get('/api/v2/stats')
  },
}

// 系统设置
export const settingsApi = {
  getSettings() {
    return http.get('/api/v2/settings')
  },
  updateSettings(data) {
    return http.put('/api/v2/settings', data)
  },
}
