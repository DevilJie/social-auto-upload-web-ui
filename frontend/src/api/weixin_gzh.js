import { http } from '@/utils/request'

// 微信公众号创作者平台相关 API(后端 blueprint: backend/blueprints/weixin_gzh_bp.py)
export const weixinGzhApi = {
  // 获取账号的视频合集列表(后端 CloakBrowser 打开合集管理页→点视频合集 tab→解析表格 DOM)
  getCollections(accountId) {
    return http.get(`/api/weixin_gzh/collections?account_id=${accountId}`)
  },
}
