import { http } from '@/utils/request'

export const jdApi = {
  pickerOpen: (accountId) =>
    http.post('/api/jd/picker/open', { accountId }),
  pickerSearch: (accountId, keyword, page) =>
    http.post('/api/jd/picker/search', { accountId, keyword, page }),
  pickerGoPage: (accountId, page) =>
    http.post('/api/jd/picker/go_page', { accountId, page }),
  pickerClose: (accountId) =>
    http.post('/api/jd/picker/close', { accountId }),
}
