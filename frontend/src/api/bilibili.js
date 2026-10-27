import { http } from '@/utils/request'

// B 站创作者平台相关 API(后端 blueprint: backend/blueprints/bilibili_bp.py)
export const biliApi = {
  // 获取账号的合集列表(后端 CloakBrowser 打开上传页→上传视频→点请选择合集→解析 DOM)
  getCollections(accountId) {
    return http.get(`/api/bilibili/collections?account_id=${accountId}`)
  },
  // 获取参与话题列表(后端登录 context 直连 B站话题接口,按标题相关性推荐)
  getTopics(accountId, title = '') {
    return http.get(
      `/api/bilibili/topics?account_id=${accountId}&title=${encodeURIComponent(title || '')}`
    )
  },
}
