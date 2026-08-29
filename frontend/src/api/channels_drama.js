// 视频号剧集 picker API(后端 blueprint: backend/blueprints/channels_bp.py drama_picker)
// 服务端启动常驻无头浏览器 → 打开视频号发布页 → 打开剧集弹窗 → 暴露
// search/go_page/close 供前端实时调。
//
// 数据契约: 后端 open/search/go_page 统一返回 {items, page, total_pages, total, entry}。
//  items 字段: {key, title, cover, extinfo, sourceLeft, sourceRight, unusable}。
//
// 行为轨迹 trace: {keyword, page} —— 前端选完剧集后保存进 commonConfig.channelsDrama,
// 发布时 platform.py 按 trace 在弹窗里复现(走 search + go_page + 选 row)。

import { http } from '@/utils/request'

export const channelsDramaApi = {
  // linkType: 'drama'(视频号剧集) / 'mini_drama'(小程序短剧)
  open(accountId, linkType = 'drama') {
    return http.post('/api/channels/drama_picker/open', { accountId, linkType })
  },
  search(accountId, keyword) {
    return http.post('/api/channels/drama_picker/search', { accountId, keyword })
  },
  goPage(accountId, page) {
    return http.post('/api/channels/drama_picker/go_page', { accountId, page })
  },
  close(accountId) {
    return http.post('/api/channels/drama_picker/close', { accountId })
  },
}
