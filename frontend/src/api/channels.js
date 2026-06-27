import { http } from '@/utils/request'

// 视频号创作者平台相关 API(后端 blueprint: backend/blueprints/channels_bp.py)
export const channelsApi = {
  // 获取账号的合集列表(后端 CloakBrowser 打开发布页→点选择合集→解析 DOM)
  getCollections(accountId) {
    return http.get(`/api/channels/collections?account_id=${accountId}`)
  },
}
