import { http } from '@/utils/request'

// 今日头条内容创作平台相关 API(后端 blueprint: backend/blueprints/toutiao_bp.py)
export const toutiaoApi = {
  // 搜索合集(后端通过 CloakBrowser 拦截 pSeries/simpleGetAlbumInfoByMediaId)
  searchCompilation(accountId, keyword) {
    return http.get(`/api/toutiao/compilation-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}`)
  },
}
