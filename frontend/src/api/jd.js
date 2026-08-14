import { http } from '@/utils/request'

// 京东「关联商品」picker API
// 后端 blueprint: backend/blueprints/jd_bp.py
// 响应格式 {code:200, data:{products, total, sessionId?}} 已被 utils/request.js
// 拦截器整体放行 —— 调用方拿到的是整个 {code,data} 对象,需用 res.data?.xxx 取值。
// 错误走拦截器 reject,调用方 try/catch 即可。
export const jdApi = {
  pickerOpen: (accountId) =>
    http.post('/api/jd/picker/open', { accountId }),
  pickerSearch: (accountId, keyword) =>
    http.post('/api/jd/picker/search', { accountId, keyword }),
  pickerGoPage: (accountId, page) =>
    http.post('/api/jd/picker/go_page', { accountId, page }),
  pickerClose: (accountId) =>
    http.post('/api/jd/picker/close', { accountId }),
  novelSearch: (accountId, keyword) =>
    http.post('/api/jd/novel/search', { accountId, keyword }),
}
