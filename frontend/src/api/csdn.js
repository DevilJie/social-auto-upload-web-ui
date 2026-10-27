import { http } from '@/utils/request'

// CSDN 内容创作平台相关 API(后端 blueprint: backend/blueprints/csdn_bp.py)
export const csdnApi = {
  // 文章标签搜索(登录态浏览器抓标签抽屉联想下拉; keyword 为空返回推荐标签)
  searchTags(accountId, keyword) {
    return http.get(`/api/csdn/tag-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}`)
  },
}
