<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="handleVisibilityChange"
    :width="mode === 'product' ? '90%' : '70%'"
    top="5vh"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :before-close="handleClose"
    class="guanghe-picker-dialog"
  >
    <template #header>
      <div class="picker-header">
        <h3>{{ mode === 'product' ? '关联商品' : '关联店铺' }}</h3>
        <span class="picker-tip">最多选择 6 个{{ mode === 'product' ? '商品' : '店铺' }}</span>
      </div>
    </template>

    <div class="picker-toolbar">
      <!-- 商品模式: 筛选条件(平台优选内置,无 tab 切换) -->
      <template v-if="mode === 'product'">
        <div class="filter-row">
          <span class="filter-label">推荐规则:</span>
          <span
            v-for="r in rules"
            :key="r"
            :class="['filter-item', { active: activeRule === r }]"
            @click="onRuleChange(r)"
          >{{ r }}</span>
        </div>
        <div class="filter-row">
          <span class="filter-label">品类筛选:</span>
          <span
            v-for="c in categories"
            :key="c"
            :class="['filter-item', { active: activeCategory === c }]"
            @click="onCategoryChange(c)"
          >{{ c }}</span>
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
          <div class="check">
            <span class="checkbox-icon">
              <el-icon><Check /></el-icon>
            </span>
          </div>
        </div>
      </div>

      <div v-if="hasMore && items.length > 0" class="load-more" @click="onLoadMore">
        <span v-if="!loadingMore">加载更多</span>
        <span v-else>加载中...</span>
      </div>
      <div v-else-if="!hasMore && items.length > 0" class="no-more">没有更多了</div>
      <div v-else-if="!loading && items.length === 0" class="empty">暂无数据</div>
    </div>

    <template #footer>
      <div class="picker-footer">
        <div class="selected-summary">
          <span>已选 <b>{{ selectedItems.length }}</b>/6</span>
          <div class="selected-chips">
            <el-tag
              v-for="(item, i) in selectedItems"
              :key="i + '_' + (item.id || item.title)"
              size="small"
              closable
              @close="removeSelected(item)"
            >{{ item.title }}</el-tag>
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
import { Search, Check } from '@element-plus/icons-vue'
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
    max-height: 70vh;
    overflow-y: auto;
  }

  // loading 遮罩:用主题感知的 CSS 变量,亮/暗都协调
  :deep(.el-loading-mask) {
    background-color: var(--guanghe-loading-mask-bg, rgba(255, 247, 240, 0.92));
    backdrop-filter: blur(2px);
  }
  :deep(.el-loading-spinner) {
    .circular {
      width: 36px;
      height: 36px;
    }
    .path {
      stroke: #ff5000;
      stroke-width: 4;
    }
    .el-loading-text {
      color: #ff5000;
      font-size: 13px;
      margin: 8px 0 0;
    }
  }
}

.picker-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  h3 {
    margin: 0;
    font-size: 18px;
  }
  .picker-tip {
    font-size: 12px;
    color: #999;
  }
}

.picker-toolbar {
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;

  .filter-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 12px;
    margin-bottom: 6px;
    font-size: 13px;

    .filter-label {
      color: #999;
      margin-right: 4px;
    }

    .filter-item {
      cursor: pointer;
      padding: 2px 10px;
      border-radius: 4px;
      color: #555;
      transition: all 0.15s;
      &:hover { color: #ff5000; }
      &.active {
        color: #fff;
        background: #ff5000;
      }
    }
  }

  .search-row {
    margin-top: 8px;
    :deep(.el-input) {
      max-width: 320px;
    }
  }
}

.picker-content {
  padding: 16px 0;
  min-height: 300px;

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 12px;

    &.shop-grid {
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    }
  }

  .card {
    position: relative;
    border: 1px solid var(--guanghe-card-border);
    border-radius: 6px;
    background: var(--guanghe-card-bg);
    overflow: hidden;
    cursor: pointer;
    transition: all 0.15s;
    display: flex;
    flex-direction: column;

    &:hover {
      border-color: #ff5000;
      box-shadow: 0 2px 8px rgba(255, 80, 0, 0.12);
    }

    &.selected {
      border-color: #ff5000;
      box-shadow: 0 0 0 2px rgba(255, 80, 0, 0.3);
      .check .checkbox-icon {
        background: #ff5000;
        color: #fff;
        opacity: 1;
      }
    }

    &.disabled {
      cursor: not-allowed;
      opacity: 0.5;
      &:hover { border-color: var(--guanghe-card-border); box-shadow: none; }
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
      }
      .disabled-mask {
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0,0,0,0.4);
        color: #fff;
        font-size: 13px;
      }
    }

    .info {
      padding: 8px;
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 4px;

      .title {
        font-size: 12px;
        color: var(--guanghe-card-title);
        line-height: 1.4;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        min-height: 34px;
      }
      .price {
        color: #ff5000;
        font-size: 14px;
        font-weight: 600;
      }
      .shop {
        display: flex;
        justify-content: space-between;
        font-size: 11px;
        color: var(--guanghe-card-meta);
      }
      .buy-count {
        font-size: 11px;
        color: var(--guanghe-card-meta);
      }
    }

    .check {
      position: absolute;
      top: 6px;
      right: 6px;
      .checkbox-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
        border-radius: 50%;
        background: rgba(255,255,255,0.9);
        color: transparent;
        border: 1px solid #ddd;
        opacity: 0.8;
        font-size: 12px;
      }
    }
  }

  .load-more {
    margin: 20px auto;
    text-align: center;
    padding: 8px 24px;
    background: #f5f5f5;
    border-radius: 4px;
    color: #666;
    cursor: pointer;
    width: fit-content;
    font-size: 13px;
    &:hover { background: #eaeaea; }
  }

  .no-more, .empty {
    text-align: center;
    color: #aaa;
    font-size: 13px;
    padding: 30px 0;
  }
}

.picker-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;

  .selected-summary {
    flex: 1;
    min-width: 0;
    b { color: #ff5000; }
    .selected-chips {
      margin-top: 6px;
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
  }

  .footer-actions {
    display: flex;
    gap: 8px;
  }
}
</style>

<!-- 非 scoped:scoped 块无法选 html 父级,用独立块做主题感知 -->
<style lang="scss">
// loading 遮罩 + 卡片主题变量(亮/暗)
html:not(.dark) .guanghe-picker-dialog {
  --guanghe-loading-mask-bg: rgba(255, 247, 240, 0.92);  // 极淡橙色
  --guanghe-card-bg: #ffffff;
  --guanghe-card-border: #eeeeee;
  --guanghe-card-title: #333333;
  --guanghe-card-meta: #999999;
  --guanghe-card-img-placeholder: #f5f5f5;
}
html.dark .guanghe-picker-dialog {
  --guanghe-loading-mask-bg: rgba(30, 25, 22, 0.88);  // 暗色暖调
  --guanghe-card-bg: #2a2a2c;
  --guanghe-card-border: #3a3a3c;
  --guanghe-card-title: #e5e5e7;
  --guanghe-card-meta: #8a8a8e;
  --guanghe-card-img-placeholder: #1f1f21;
}
</style>
