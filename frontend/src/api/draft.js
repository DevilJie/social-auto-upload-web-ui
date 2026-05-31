import { http } from '@/utils/request'

export const draftApi = {
  getDrafts(type) {
    const params = type ? `?type=${type}` : ''
    return http.get(`/api/v2/drafts${params}`)
  },
  createDraft(data) {
    return http.post('/api/v2/drafts', data)
  },
  getDraft(id) {
    return http.get(`/api/v2/drafts/${id}`)
  },
  updateDraft(id, data) {
    return http.put(`/api/v2/drafts/${id}`, data)
  },
  deleteDraft(id) {
    return http.delete(`/api/v2/drafts/${id}`)
  },
}
