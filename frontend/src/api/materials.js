import { http } from '@/utils/request'

export const materialsApi = {
  /** 上传文件 */
  upload(formData, onProgress) {
    return http.upload('/api/materials/upload', formData, onProgress)
  },

  /** 获取素材列表，type: 'all' | 'video' | 'image' */
  list(type = 'all') {
    return http.get('/api/materials/list', { type })
  },

  /** 删除素材 */
  delete(id) {
    return http.delete(`/api/materials/${id}`)
  },
}
