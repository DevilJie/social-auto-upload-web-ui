import { http } from '@/utils/request'

// 微博创作者平台相关 API(后端 blueprint: backend/blueprints/weibo_bp.py)
export const weiboApi = {
  // 获取账号的视频合集列表(后端 CloakBrowser 打开上传页→上传测试视频→切换合集开关→解析 DOM)
  getCollections(accountId) {
    return http.get(`/api/weibo/collections?account_id=${accountId}`)
  },
}
