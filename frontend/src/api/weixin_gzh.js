import { http } from '@/utils/request'

// 微信公众号创作者平台相关 API(后端 blueprint: backend/blueprints/weixin_gzh_bp.py)
export const weixinGzhApi = {
  // 获取账号的合集列表(视频合集/贴图合集,由 collectionType 决定)
  // 后端: CloakBrowser 打开合集管理页→点对应 tab→解析表格 DOM
  //      找不到该类型 tab = 账号无此类型合集,返回空列表
  getCollections(accountId, collectionType = '视频合集') {
    return http.get(`/api/weixin_gzh/collections?account_id=${accountId}&collection_type=${encodeURIComponent(collectionType)}`)
  },
}
