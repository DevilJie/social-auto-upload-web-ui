import { request } from '@/utils/request'

export const jdApi = {
  pickerOpen: (accountId) =>
    request.post('/api/jd/picker/open', { accountId }),
  pickerSearch: (accountId, keyword, page) =>
    request.post('/api/jd/picker/search', { accountId, keyword, page }),
  pickerGoPage: (accountId, page) =>
    request.post('/api/jd/picker/go_page', { accountId, page }),
  pickerClose: (accountId) =>
    request.post('/api/jd/picker/close', { accountId }),
}
