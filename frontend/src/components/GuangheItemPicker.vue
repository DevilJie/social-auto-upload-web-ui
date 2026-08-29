<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="handleVisibilityChange"
    :width="mode === 'product' ? '960px' : '760px'"
    top="5vh"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :before-close="handleClose"
    class="guanghe-picker-dialog"
  >
    <template #header>
      <div class="picker-header">
        <span class="header-accent"></span>
        <el-icon class="header-icon"><Goods /></el-icon>
        <h3>{{ mode === 'product' ? '关联商品' : '关联店铺' }}</h3>
        <span class="picker-tip">最多选择 6 个{{ mode === 'product' ? '商品' : '店铺' }}</span>
        <span class="picker-progress" :class="{ full: selectedItems.length >= MAX_SELECTED }">
          {{ selectedItems.length }} / {{ MAX_SELECTED }}
        </span>
      </div>
    </template>

    <div class="picker-toolbar">
      <!-- 商品模式: 筛选条件(平台优选内置,无 tab 切换) -->
      <template v-if="mode === 'product'">
        <div class="filter-row">
          <span class="filter-label">推荐</span>
          <button
            v-for="r in rules"
            :key="r"
            :class="['pill', { active: activeRule === r }]"
            @click="onRuleChange(r)"
          >{{ r }}</button>
        </div>
        <div class="filter-row">
          <span class="filter-label">品类</span>
          <button
            v-for="c in categories"
            :key="c"
            :class="['pill', { active: activeCategory === c }]"
            @click="onCategoryChange(c)"
          >{{ c }}</button>
        </div>
      </template>

      <!-- 搜索框 -->
      <div class="search-row">
        <el-input
          v-model="searchKeyword"
          :placeholder="mode === 'product' ? '输入商品关键词或商品ID' : '搜索店铺'"
          clearable
          @keyup.enter="onSearch"
        >
          <template #suffix>
            <el-icon class="cursor-pointer" @click="onSearch"><Search /></el-icon>
          </template>
        </el-input>
      </div>
    </div>

    <div class="picker-content" v-loading="loading" element-loading-text="加载中...">
      <div class="grid" :class="{ 'shop-grid': mode === 'shop' }">
        <div
          v-for="item in items"
          :key="item.id || item.title"
          :class="[
            'card',
            {
              selected: isSelected(item),
              disabled: item.disabled,
            },
          ]"
          @click="onCardClick(item)"
        >
          <div class="img-wrap">
            <img :src="item.image" :alt="item.title" loading="lazy" referrerpolicy="no-referrer" />
            <span v-if="item.disabled" class="disabled-mask">不可选</span>
            <span v-if="isSelected(item)" class="selected-badge">
              <el-icon :size="12"><Check /></el-icon>
            </span>
          </div>
          <div class="info">
            <div class="title" :title="item.title">{{ item.title }}</div>
            <div v-if="item.price" class="price">{{ item.price }}</div>
            <div v-if="item.shop_name" class="shop">
              <span class="shop-name">{{ item.shop_name }}</span>
              <span v-if="item.sold" class="sold">{{ item.sold }}</span>
            </div>
            <div v-if="item.buy_count" class="buy-count">{{ item.buy_count }}</div>
          </div>
        </div>
      </div>

      <div v-if="hasMore && items.length > 0" class="load-more" @click="onLoadMore">
        <span v-if="!loadingMore">加载更多</span>
        <span v-else>加载中...</span>
      </div>
      <div v-else-if="!hasMore && items.length > 0" class="no-more">已经到底啦</div>
      <div v-else-if="!loading && items.length === 0" class="empty">
        <el-icon class="empty-icon"><Goods /></el-icon>
        <span>暂无数据</span>
      </div>
    </div>

    <template #footer>
      <div class="picker-footer">
        <div class="selected-summary">
          <span class="selected-count">已选 <b>{{ selectedItems.length }}</b>/6</span>
          <div class="selected-chips">
            <el-tag
              v-for="(item, i) in selectedItems"
              :key="i + '_' + (item.id || item.title)"
              size="small"
              closable
              @close="removeSelected(item)"
            >{{ item.title }}</el-tag>
            <span v-if="selectedItems.length === 0" class="no-selected">尚未选择，点击卡片即可加入</span>
          </div>
        </div>
        <div class="footer-actions">
          <el-button @click="handleClose">取消</el-button>
          <el-button type="primary" :disabled="selectedItems.length === 0" @click="onConfirm">确认</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Check, Goods } from '@element-plus/icons-vue'
import { guangheApi } from '@/api/taobaoGuanghe'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  accountId: { type: String, required: true },
  mode: { type: String, default: 'product' }, // 'product' | 'shop'
  initSelected: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const MAX_SELECTED = 6

// 筛选选项从面板 DOM 动态抓取(后端返回),不再硬编码
const rules = ref([])
const categories = ref([])

const sessionId = ref('')
const loading = ref(false)
const loadingMore = ref(false)
const items = ref([])
const hasMore = ref(false)
const selectedItems = ref([])

const activeRule = ref('')
const activeCategory = ref('')
const activeTab = ref('preferred') // 商品模式默认 preferred,店铺模式固定 'shop'
const searchKeyword = ref('')

// 跟踪当前已发起的请求类型(避免乱序返回覆盖最新数据)
const pendingOpId = ref(0)

// 应用后端返回的 filters,默认选第一个选项(通常是"全部")
function applyFilters(filters) {
  if (!filters) return
  if (Array.isArray(filters.rules) && filters.rules.length) {
    rules.value = filters.rules
    if (!activeRule.value || !rules.value.includes(activeRule.value)) {
      activeRule.value = rules.value[0]
    }
  }
  if (Array.isArray(filters.categories) && filters.categories.length) {
    categories.value = filters.categories
    if (!activeCategory.value || !categories.value.includes(activeCategory.value)) {
      activeCategory.value = categories.value[0]
    }
  }
}

watch(() => props.modelValue, async (visible) => {
  if (visible) {
    await openPanel()
  }
})

// 切换 mode(组件通常不会动态切换,但以防万一)
watch(() => props.mode, async (newMode, oldMode) => {
  if (!props.modelValue || newMode === oldMode || !sessionId.value) return
  loading.value = true
  try {
    const res = await guangheApi.pickerSwitchType(sessionId.value, newMode)
    items.value = res.data?.items || []
    hasMore.value = !!res.data?.has_more
    if (newMode === 'product') {
      applyFilters(res.data?.filters)
    } else {
      rules.value = []
      categories.value = []
    }
    activeRule.value = ''
    activeCategory.value = ''
    activeTab.value = newMode === 'shop' ? 'shop' : 'preferred'
    searchKeyword.value = ''
  } catch (e) {
    ElMessage.error('切换类型失败: ' + (e?.message || e))
  } finally {
    loading.value = false
  }
})

async function openPanel() {
  if (!props.accountId) {
    ElMessage.warning('请先选择账号')
    handleClose()
    return
  }
  // 初始已选(用于回显,不依赖后端跟踪)
  selectedItems.value = normalizeSelected(props.initSelected)
  // 重置筛选项(等后端返回)
  rules.value = []
  categories.value = []
  activeRule.value = ''
  activeCategory.value = ''
  activeTab.value = props.mode === 'shop' ? 'shop' : 'preferred'
  searchKeyword.value = ''
  loading.value = true
  try {
    const res = await guangheApi.pickerOpen(props.accountId, props.mode)
    sessionId.value = res.data?.session_id || ''
    items.value = res.data?.items || []
    hasMore.value = !!res.data?.has_more
    if (props.mode === 'product') {
      applyFilters(res.data?.filters)
    }
  } catch (e) {
    ElMessage.error('打开选择面板失败: ' + (e?.message || e))
    handleClose()
  } finally {
    loading.value = false
  }
}

async function onRuleChange(rule) {
  if (rule === activeRule.value || loading.value) return
  activeRule.value = rule
  await refreshList(async (sid) => guangheApi.pickerFilter(sid, { rule }))
}

async function onCategoryChange(category) {
  if (category === activeCategory.value || loading.value) return
  activeCategory.value = category
  await refreshList(async (sid) => guangheApi.pickerFilter(sid, { category }))
}

async function onSearch() {
  if (loading.value) return
  await refreshList(async (sid) => guangheApi.pickerSearch(sid, searchKeyword.value))
}

async function onLoadMore() {
  if (loadingMore.value || loading.value) return
  loadingMore.value = true
  try {
    const res = await guangheApi.pickerLoadMore(sessionId.value)
    // load_more 返回的是当前页所有 items(含已加载的),直接替换
    items.value = res.data?.items || []
    hasMore.value = !!res.data?.has_more
  } catch (e) {
    ElMessage.error('加载更多失败: ' + (e?.message || e))
  } finally {
    loadingMore.value = false
  }
}

async function refreshList(fn) {
  if (!sessionId.value) return
  loading.value = true
  const opId = ++pendingOpId.value
  try {
    const res = await fn(sessionId.value)
    // 乱序保护:只接受最新一次操作的结果
    if (opId !== pendingOpId.value) return
    items.value = res.data?.items || []
    hasMore.value = !!res.data?.has_more
    // 消费 filters(仅商品模式后端会返回)
    if (props.mode === 'product' && res.data?.filters) {
      applyFilters(res.data.filters)
    }
  } catch (e) {
    if (opId === pendingOpId.value) {
      ElMessage.error('操作失败: ' + (e?.message || e))
    }
  } finally {
    if (opId === pendingOpId.value) {
      loading.value = false
    }
  }
}

// 兼容 props.initSelected 旧字符串数组格式 → 统一为 [{title, image, id, trace}]
function normalizeSelected(arr) {
  if (!Array.isArray(arr)) return []
  return arr
    .map(item => {
      if (typeof item === 'string') return { title: item, image: '', id: item, trace: undefined }
      return {
        title: item.title || '',
        image: item.image || '',
        id: item.id || item.title || '',
        trace: item.trace,
      }
    })
    .filter(it => it.title || it.id)
    .slice(0, MAX_SELECTED)
}

function isSelected(item) {
  return selectedItems.value.some(s =>
    (s.id && s.id === item.id) || s.title === item.title
  )
}

function onCardClick(item) {
  if (item.disabled) return
  if (isSelected(item)) {
    selectedItems.value = selectedItems.value.filter(s => !(
      (s.id && s.id === item.id) || s.title === item.title
    ))
  } else {
    if (selectedItems.value.length >= MAX_SELECTED) {
      ElMessage.warning(`最多选择 ${MAX_SELECTED} 个`)
      return
    }
    // 打包 trace 快照(选中那一刻的面板状态)
    const trace = {
      tab: props.mode === 'shop' ? 'shop' : activeTab.value,
      keyword: searchKeyword.value || '',
      rule: props.mode === 'shop' ? '' : (activeRule.value || ''),
      category: props.mode === 'shop' ? '' : (activeCategory.value || ''),
    }
    selectedItems.value = [...selectedItems.value, {
      title: item.title,
      image: item.image || '',
      id: item.id || item.title,
      trace,
    }]
  }
}

function removeSelected(item) {
  const key = typeof item === 'string' ? item : (item.id || item.title)
  selectedItems.value = selectedItems.value.filter(s =>
    (s.id !== key) && (s.title !== key)
  )
}

function onConfirm() {
  emit('confirm', [...selectedItems.value])
  emit('update:modelValue', false)
}

function handleVisibilityChange(visible) {
  if (!visible) handleClose()
  else emit('update:modelValue', true)
}

async function handleClose() {
  // 释放后端浏览器
  if (sessionId.value) {
    const sid = sessionId.value
    sessionId.value = ''
    try {
      await guangheApi.pickerClose(sid)
    } catch (e) {
      // 关闭失败不阻塞 UI
      console.warn('picker close error', e)
    }
  }
  emit('update:modelValue', false)
}
</script>

<style scoped lang="scss">
.guanghe-picker-dialog {
  :deep(.el-dialog__body) {
    padding: 0 20px;
    // 不限制高度：内容区(.picker-content)固定高度内自己滚动,
    // 这样不管商品有多少,toolbar 始终贴顶、footer 始终贴底,弹窗总高度稳定
  }

  // 商品区显式白/暗背景，避免和 EP 默认 --el-mask-color (rgba 半透明) 叠出来偏灰
  // loading 遮罩 spinner 颜色由下方非 scoped 块统一接管（带 !important）
  .picker-content {
    background: var(--guanghe-card-bg);
    border-radius: 0 0 8px 8px;
  }
}

.picker-header {
  display: flex;
  align-items: center;
  gap: 10px;

  .header-accent {
    width: 4px;
    height: 16px;
    border-radius: 2px;
    background: #ff5000;
    flex-shrink: 0;
  }
  .header-icon {
    color: #ff5000;
    font-size: 18px;
    flex-shrink: 0;
  }
  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
    color: var(--guanghe-card-title, #333);
    letter-spacing: -0.01em;
  }
  .picker-tip {
    font-size: 12px;
    color: var(--guanghe-card-meta, #999);
    flex: 1;
    min-width: 0;
  }
  .picker-progress {
    font-size: 12px;
    padding: 3px 10px;
    border-radius: 10px;
    border: 1px solid var(--guanghe-pill-border, #ffd9c2);
    color: #ff5000;
    background: rgba(255, 80, 0, 0.06);
    font-variant-numeric: tabular-nums;
    flex-shrink: 0;

    &.full {
      color: #fff;
      background: #ff5000;
      border-color: #ff5000;
    }
  }
}

.picker-toolbar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 0 16px;
  border-bottom: 1px solid var(--guanghe-toolbar-border, #f0f0f0);

  .filter-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-size: 13px;

    .filter-label {
      color: var(--guanghe-card-meta, #999);
      flex-shrink: 0;
      min-width: 32px;
    }

    .pill {
      border: 1px solid var(--guanghe-pill-border, #e8e8e8);
      background: var(--guanghe-pill-bg, #fafafa);
      color: var(--guanghe-card-title, #555);
      padding: 4px 12px;
      border-radius: 14px;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s;

      &:hover {
        border-color: #ff5000;
        color: #ff5000;
      }
      &.active {
        background: #ff5000;
        border-color: #ff5000;
        color: #fff;
      }
    }
  }

  .search-row {
    :deep(.el-input) {
      max-width: 340px;
      width: 100%;
    }
    :deep(.el-input__wrapper) {
      border-radius: 14px;
      padding-left: 12px;
    }
  }
}

.picker-content {
  padding: 16px 0;
  // 商品区固定高度,内部出滚动条 — 商品再多也不撑大弹窗整体高度,
  // toolbar 始终贴顶、footer 始终贴底;视窗高度自适应
  height: 52vh;
  min-height: 360px;
  max-height: 560px;
  overflow-y: auto;
  overscroll-behavior: contain;

  // 浅色滚动条:在商品区背景上更自然
  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.12);
    border-radius: 3px;
  }
  &::-webkit-scrollbar-thumb:hover { background: rgba(0, 0, 0, 0.2); }
  &::-webkit-scrollbar-track { background: transparent; }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
    gap: 12px;

    &.shop-grid {
      grid-template-columns: repeat(auto-fill, minmax(196px, 1fr));
    }
  }

  .card {
    position: relative;
    border: 1px solid var(--guanghe-card-border);
    border-radius: 10px;
    background: var(--guanghe-card-bg);
    overflow: hidden;
    cursor: pointer;
    transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
    display: flex;
    flex-direction: column;

    &:hover {
      border-color: #ff5000;
      transform: translateY(-2px);
      box-shadow: 0 4px 14px rgba(255, 80, 0, 0.10);
    }

    &.selected {
      border-color: #ff5000;
      box-shadow: 0 0 0 2px rgba(255, 80, 0, 0.25);
    }

    &.disabled {
      cursor: not-allowed;
      opacity: 0.55;
      &:hover { border-color: var(--guanghe-card-border); transform: none; box-shadow: none; }
    }

    .img-wrap {
      position: relative;
      width: 100%;
      aspect-ratio: 1;
      background: var(--guanghe-card-img-placeholder);

      img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }

      .disabled-mask {
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 0, 0, 0.4);
        color: #fff;
        font-size: 13px;
        border-radius: 10px;
      }

      .selected-badge {
        position: absolute;
        top: 8px;
        right: 8px;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background: #ff5000;
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
      }
    }

    .info {
      padding: 10px;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 4px;

      .title {
        font-size: 12px;
        color: var(--guanghe-card-title);
        line-height: 1.45;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        min-height: 35px;
      }

      .price {
        color: #ff5000;
        font-size: 14px;
        font-weight: 600;
      }

      .shop {
        display: flex;
        justify-content: space-between;
        gap: 6px;
        font-size: 11px;
        color: var(--guanghe-card-meta);

        .shop-name {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sold { flex-shrink: 0; }
      }

      .buy-count {
        font-size: 11px;
        color: var(--guanghe-card-meta);
      }
    }
  }

  .load-more {
    margin: 20px auto;
    text-align: center;
    padding: 8px 28px;
    background: var(--guanghe-pill-bg, #f5f5f5);
    border: 1px solid var(--guanghe-pill-border, #e8e8e8);
    border-radius: 16px;
    color: var(--guanghe-card-title, #666);
    cursor: pointer;
    width: fit-content;
    font-size: 13px;

    &:hover {
      border-color: #ff5000;
      color: #ff5000;
    }
  }

  .no-more {
    text-align: center;
    color: var(--guanghe-card-meta, #aaa);
    font-size: 12px;
    padding: 18px 0 4px;
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    color: var(--guanghe-card-meta, #aaa);
    font-size: 13px;
    padding: 48px 0;

    .empty-icon {
      font-size: 42px;
      opacity: 0.6;
    }
  }
}

.picker-footer {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;

  .selected-summary {
    flex: 1;
    min-width: 0;

    .selected-count {
      font-size: 13px;
      color: var(--guanghe-card-title, #333);
      b { color: #ff5000; }
    }

    .no-selected {
      font-size: 12px;
      color: var(--guanghe-card-meta, #999);
    }

    .selected-chips {
      margin-top: 6px;
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      max-height: 64px;
      overflow-y: auto;
    }
  }

  .footer-actions {
    display: flex;
    gap: 8px;
    flex-shrink: 0;
  }
}
</style>

<!-- 非 scoped:scoped 块无法选 html 父级,用独立块做主题感知 -->
<style lang="scss">
// loading 遮罩 + 卡片主题变量(亮/暗)
html:not(.dark) .guanghe-picker-dialog {
  // 同时覆盖 EP 自己的遮罩变量（v-loading 直接用它）
  --el-mask-color: #ffffff !important;
  --guanghe-card-bg: #ffffff;
  --guanghe-card-border: #eeeeee;
  --guanghe-card-title: #333333;
  --guanghe-card-meta: #999999;
  --guanghe-card-img-placeholder: #f5f5f5;
  --guanghe-toolbar-border: #f0f0f0;
  --guanghe-pill-border: #e8e8e8;
  --guanghe-pill-bg: #fafafa;
}
html.dark .guanghe-picker-dialog {
  --el-mask-color: #2a2a2c !important;
  --guanghe-card-bg: #2a2a2c;
  --guanghe-card-border: #3a3a3c;
  --guanghe-card-title: #e5e5e7;
  --guanghe-card-meta: #8a8a8e;
  --guanghe-card-img-placeholder: #1f1f21;
  --guanghe-toolbar-border: #333;
  --guanghe-pill-border: #3a3a3c;
  --guanghe-pill-bg: #262628;
}

// 兜底：!important 强制盖掉 EP 的默认 rgba 遮罩，杜绝「灰色蒙层」
.guanghe-picker-dialog .el-loading-mask {
  background-color: var(--guanghe-card-bg) !important;
  border-radius: 0 0 8px 8px !important;
}
.guanghe-picker-dialog .el-loading-spinner {
  .circular { width: 36px; height: 36px; }
  .path { stroke: #ff5000; stroke-width: 4; }
  .el-loading-text { color: #ff5000; font-size: 13px; margin: 8px 0 0; }
}
</style>
