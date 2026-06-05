import { http } from '@/utils/request'

export function listFeedback({ tab, page = 1, pageSize = 20 }) {
  return http.get('/api/feedback/list', {
    params: { tab, page, page_size: pageSize }
  })
}

export function submitFeedback(formData) {
  return http.upload('/api/feedback/submit', formData)
}

export function voteFeedback({ id, email }) {
  return http.post('/api/feedback/vote', { id, email })
}
