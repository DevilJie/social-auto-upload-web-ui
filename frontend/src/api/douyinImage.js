import { http } from '@/utils/request'

// 抖音图文发布相关API
export const douyinImageApi = {
  // 获取用户的合集列表
  getMixList(accountId) {
    return http.get(`/api/douyin-image/mix-list?account_id=${accountId}`)
  },

  // 获取官方活动列表
  getActivityList(accountId) {
    return http.get(`/api/douyin-image/activity-list?account_id=${accountId}`)
  },

  // 搜索热点
  searchHotspot(accountId, keyword, count = 50) {
    return http.get(`/api/douyin-image/hotspot-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&count=${count}`)
  },

  // 搜索音乐
  searchMusic(accountId, keyword, cursor = 0, count = 20) {
    return http.get(`/api/douyin-image/music-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&cursor=${cursor}&count=${count}`)
  }
}
