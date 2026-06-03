import { http } from '@/utils/request'

// 快手图文发布相关 API
export const kuaishouImageApi = {
  // 搜索音乐
  searchMusic(accountId, keyword, cursor = 0, count = 20) {
    return http.get(`/api/kuaishou-image/music-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&cursor=${cursor}&count=${count}`)
  },
}
