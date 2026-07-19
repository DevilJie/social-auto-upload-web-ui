import { http } from '@/utils/request'

// VIVO 内容创作平台相关 API(后端 blueprint: backend/blueprints/vivo_bp.py)
export const vivoApi = {
  // 位置搜索(后端通过 CloakBrowser 打开 vivo 发布页,输入关键词解析下拉 DOM)
  searchPosition(accountId, keyword) {
    return http.get(`/api/vivo/search-position?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}`)
  },
}
