import { http } from '@/utils/request'

// 图文发布相关API
export const imagePublishApi = {
  // 上传图片
  uploadImage(file, onProgress) {
    const formData = new FormData()
    formData.append('file', file)
    return http.upload('/api/image-publish/upload', formData, (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    })
  },

  // 发布图文
  publishImage(data) {
    return http.post('/api/image-publish/publish', data)
  },

  // 获取草稿列表
  getDrafts() {
    return http.get('/api/image-publish/drafts')
  },

  // 保存草稿
  saveDraft(data) {
    return http.post('/api/image-publish/drafts', data)
  },

  // 删除草稿
  deleteDraft(id) {
    return http.delete(`/api/image-publish/drafts/${id}`)
  },

  // 获取发布历史
  getHistory() {
    return http.get('/api/image-publish/history')
  }
}
