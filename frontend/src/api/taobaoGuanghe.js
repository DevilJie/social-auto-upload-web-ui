import { http } from '@/utils/request'

// 淘宝光合「关联商品/店铺」选择面板 API
// 后端 blueprint: backend/blueprints/taobao_guanghe_bp.py
// 一个 session_id 对应一个常驻无头浏览器,前端弹窗生命周期内复用
export const guangheApi = {
  // 打开弹窗 → 启动浏览器并初始化到选择面板
  // body: { account_id, type: 'product' | 'shop' }
  // 返回: { session_id, items, has_more, type }
  pickerOpen(accountId, type) {
    return http.post('/api/taobao_guanghe/picker/open', { account_id: accountId, type })
  },

  // 切换商品↔店铺
  pickerSwitchType(sessionId, type) {
    return http.post('/api/taobao_guanghe/picker/switch_type', { session_id: sessionId, type })
  },

  // 切换「已购商品/平台优选」(仅商品模式)
  // tab: 'bought' | 'preferred'
  pickerTab(sessionId, tab) {
    return http.post('/api/taobao_guanghe/picker/tab', { session_id: sessionId, tab })
  },

  // 切换筛选(仅商品模式平台优选 tab)
  // body: { rule?, category? }
  pickerFilter(sessionId, { rule, category } = {}) {
    return http.post('/api/taobao_guanghe/picker/filter', { session_id: sessionId, rule, category })
  },

  // 搜索
  pickerSearch(sessionId, keyword) {
    return http.post('/api/taobao_guanghe/picker/search', { session_id: sessionId, keyword })
  },

  // 加载更多
  pickerLoadMore(sessionId) {
    return http.post('/api/taobao_guanghe/picker/load_more', { session_id: sessionId })
  },

  // 关闭(释放浏览器)
  pickerClose(sessionId) {
    return http.post('/api/taobao_guanghe/picker/close', { session_id: sessionId })
  },
}
