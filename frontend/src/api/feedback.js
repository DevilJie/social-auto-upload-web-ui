import { http } from '@/utils/request'

export function listFeedback({ status, includeAll = false, page = 1, pageSize = 20 }) {
  const params = { page, page_size: pageSize }
  if (status !== undefined && status !== null) {
    params.status = status
  } else if (includeAll) {
    params.include_all = 'true'
  }
  return http.get('/api/feedback/list', params)
}

export function submitFeedback(formData) {
  return http.upload('/api/feedback/submit', formData)
}

export function voteFeedback({ id }) {
  return http.post('/api/feedback/vote', { id })
}
