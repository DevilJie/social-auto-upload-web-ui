import { http } from '@/utils/request'

// 支付宝内容创作平台相关 API(后端 blueprint: backend/blueprints/alipay_bp.py)
export const alipayApi = {
  // 搜索合集(后端通过 CloakBrowser 拦截 queryCompilationsByPublicId.json)
  searchCompilation(accountId, keyword) {
    return http.get(`/api/alipay/compilation-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}`)
  },
}
