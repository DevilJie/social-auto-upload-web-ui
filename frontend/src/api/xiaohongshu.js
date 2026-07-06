import { http } from '@/utils/request'

// 小红书创作者平台相关 API(后端 blueprint: backend/blueprints/xiaohongshu_bp.py)
// 合集列表 / POI 搜索都通过 CloakBrowser 打开发布页拦截平台接口(带签名)
export const xhsApi = {
  // 获取账号的合集列表(后端监听 collection/pc/list_v2 响应)
  getCollections(accountId) {
    return http.get(`/api/xiaohongshu/collections?account_id=${accountId}`)
  },
  // 搜索拍摄地点 POI(后端 fetch poi/creator/search)
  searchPoi(accountId, keyword) {
    return http.get(`/api/xiaohongshu/search-poi?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}`)
  },
}
