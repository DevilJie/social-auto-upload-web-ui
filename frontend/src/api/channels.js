import { http } from '@/utils/request'

// 视频号创作者平台相关 API(后端 blueprint: backend/blueprints/channels_bp.py)
export const channelsApi = {
  // 获取账号的合集列表(后端 CloakBrowser 打开发布页→点选择合集→解析 DOM)
  getCollections(accountId) {
    return http.get(`/api/channels/collections?account_id=${accountId}`)
  },
  // 搜索账号附近的位置(后端 CloakBrowser 打开发布页→点位置卡→输入关键字→解析下拉 DOM)
  // 与合集不同:位置必须传 keyword,后端用关键字真实搜索附近位置
  getLocations(accountId, keyword) {
    return http.get(`/api/channels/locations?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}`)
  },
  // 搜索可参与的活动(后端 CloakBrowser 打开发布页→点活动卡→输入关键字→解析下拉 DOM)
  // 与位置同模式:必传 keyword,后端真实搜索;index 0 是「不参与活动」会被跳过
  searchActivities(accountId, keyword) {
    return http.get(`/api/channels/activities?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}`)
  },
}
