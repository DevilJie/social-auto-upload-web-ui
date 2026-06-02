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
  },

  // 搜索位置
  searchPoi(accountId, keyword, count = 12) {
    return http.get(`/api/douyin-image/search-poi?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&count=${count}`)
  },

  // 搜索小程序（通过链接中的token）
  searchMiniapp(accountId, link) {
    return http.get(`/api/douyin-image/search-miniapp?account_id=${accountId}&link=${encodeURIComponent(link)}`)
  },

  // 搜索游戏
  searchGame(accountId, keyword, count = 20) {
    return http.get(`/api/douyin-image/search-game?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&count=${count}`)
  },

  // 搜索标记万物商品
  searchMarkSpu(accountId, keyword, pageSize = 10) {
    return http.get(`/api/douyin-image/search-mark-spu?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&page_size=${pageSize}`)
  },

  // 搜索影视演绎
  searchMedium(accountId, keyword, count = 12, offset = 0) {
    return http.get(`/api/douyin-image/search-medium?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&count=${count}&offset=${offset}`)
  }
}
