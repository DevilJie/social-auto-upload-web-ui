import { http } from '@/utils/request'

export const materialsApi = {
  /** 上传文件 */
  upload(formData, onProgress) {
    return http.upload('/api/materials/upload', formData, onProgress)
  },

  /**
   * 分页获取素材列表
   * @param {Object} params
   * @param {'all'|'video'|'image'} [params.type]
   * @param {string} [params.keyword]
   * @param {number} [params.page=1]
   * @param {number} [params.page_size=24]
   */
  list(params = {}) {
    return http.get('/api/materials/list', params)
  },

  /** 删除素材 */
  delete(id) {
    return http.delete(`/api/materials/${id}`)
  },
}
