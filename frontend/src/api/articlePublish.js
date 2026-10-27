import { http } from '@/utils/request'
import { materialsApi } from '@/api/materials'

/**
 * 文章发布 API — 一键分发文章(标题 + 富文本正文)到多平台。
 * 首个平台: 微信公众号(后端 filetransfer 自动转存正文图片)。
 */
export const articlePublishApi = {
  uploadImage(file, onProgress) {
    const formData = new FormData()
    formData.append('file', file)
    return materialsApi.upload(formData, (percent) => {
      if (onProgress) onProgress(percent)
    })
  },
  /** 发布文章到单账号(前端多账号循环调用,共用 batchId) */
  publish(data) { return http.post('/api/article-publish/publish', data) },
  /** 草稿管理(type='article') */
  getDrafts() { return http.get('/api/v2/drafts', { params: { type: 'article' } }) },
  /** 新建草稿 */
  saveDraft(data) { return http.post('/api/v2/drafts', { type: 'article', ...data }) },
  /** 更新已有草稿(PUT /drafts/<id>;POST 会忽略 id 永远新建) */
  updateDraft(id, draftData) { return http.put(`/api/v2/drafts/${id}`, { draft_data: draftData }) },
  getDraft(id) { return http.get(`/api/v2/drafts/${id}`) },
  deleteDraft(id) { return http.delete(`/api/v2/drafts/${id}`) },
  /** 草稿批量发布: 每篇逐账号推送到公众号草稿箱 */
  batchPublishArticleDrafts(draftIds) {
    return http.post('/api/article-publish/drafts/batch-publish', { draft_ids: draftIds })
  },
}
