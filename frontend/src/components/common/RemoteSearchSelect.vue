<template>
  <div class="remote-search-select">
    <el-select
      v-model="selectedValue"
      :placeholder="placeholder"
      clearable
      filterable
      no-data-text=" "
      :popper-class="popperClass"
      @change="handleChange"
      @visible-change="handleVisibleChange"
      style="width: 100%"
    >
      <!-- ===== 顶部区:搜索框(仅非 autoLoad)+ loading(始终可用) ===== -->
      <template #header>
        <!-- 搜索框:autoLoad 模式隐藏(全量加载无需搜索) -->
        <div v-if="!isAutoLoad" class="rss-header">
          <div class="rss-search" :class="{ 'is-focused': searchFocused }">
            <el-icon class="rss-search-icon"><Search /></el-icon>
            <el-input
              v-model="searchKeyword"
              class="rss-search-input"
              :placeholder="searchPlaceholder"
              @keyup.enter="handleSearch"
              @focus="searchFocused = true"
              @blur="searchFocused = false"
            />
            <el-icon
              v-if="searchKeyword"
              class="rss-search-clear"
              @mousedown.prevent="handleClear"
            ><CircleClose /></el-icon>
          </div>
          <div class="rss-hint">
            <el-icon><Promotion /></el-icon>
            <span>按 Enter 搜索</span>
          </div>
        </div>
        <!-- loading:三个脉冲点(autoLoad / 手动搜索 都显示) -->
        <div v-if="loading" class="rss-loading" :class="{ 'rss-loading--standalone': isAutoLoad }">
          <span class="rss-dot" />
          <span class="rss-dot" />
          <span class="rss-dot" />
          <span class="rss-loading-text">正在加载...</span>
        </div>
      </template>

      <!-- ===== 列表区 ===== -->
      <el-option
        v-for="item in list"
        :key="getKey(item)"
        :label="getLabel(item)"
        :value="getLabel(item)"
      >
        <div class="rss-option" :class="{ 'is-selected': isSelected(item) }">
          <!-- 选中态:左侧紫蓝渐变条 -->
          <span class="rss-option-bar" />
          <!-- 封面图(可选) -->
          <div v-if="hasCover" class="rss-option-cover">
            <img
              v-if="getCover(item)"
              :src="getCover(item)"
              @error="onCoverError"
            />
            <div v-else class="rss-cover-placeholder">
              <el-icon><Picture /></el-icon>
            </div>
          </div>
          <!-- 主信息 -->
          <div class="rss-option-info">
            <div class="rss-option-label">{{ getLabel(item) }}</div>
            <div v-if="getDesc(item)" class="rss-option-desc">{{ getDesc(item) }}</div>
          </div>
          <!-- 选中勾 -->
          <el-icon v-if="isSelected(item)" class="rss-option-check"><Check /></el-icon>
        </div>
      </el-option>

      <!-- ===== 空态 ===== -->
      <template #empty>
        <div class="rss-empty">
          <el-icon class="rss-empty-icon"><MagicStick /></el-icon>
          <span>{{ searched && !loading ? `没有匹配「${searchKeyword || ''}」的结果` : '输入关键词,按回车开始搜索' }}</span>
        </div>
      </template>
    </el-select>

    <!-- ===== loading:三个脉冲点(通过 popper-class 注入到下拉面板) ===== -->
  </div>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { Search, CircleClose, Promotion, Picture, Check, MagicStick } from '@element-plus/icons-vue'

const props = defineProps({
  // v-model 绑定的名称字符串(原契约)
  modelValue: {
    type: String,
    default: ''
  },
  // 回显用的完整对象(原契约)
  data: {
    type: Object,
    default: null
  },
  /**
   * 数据源函数。调用方在此内联调 api + 取 list。
   * 签名:(keyword?: string) => Promise<{ list: any[], total?: number }>
   * 组件内部零硬编码 api。
   */
  fetcher: {
    type: Function,
    required: true
  },
  /**
   * 字段映射。label/desc/cover 既可是字段名字符串,也可是 (item)=>string 函数。
   * 覆盖 name/mix_name/title、note_num 派生、嵌套封面图等所有差异。
   */
  fieldMap: {
    type: Object,
    default: () => ({ label: 'name' })
  },
  /**
   * frontend(默认):空关键词也调 fetcher 展示全量
   * backend:空关键词不调(对应 location/compilation)
   */
  searchMode: {
    type: String,
    default: 'frontend'
  },
  /**
   * autoLoad=true 时:下拉打开即调 fetcher 加载全量,隐藏搜索框。
   * 适用于「后端一次返回全量」的场景(合集/mix)。默认跟随 searchMode:
   * frontend → true(打开即加载),backend → false(需手动搜索)。
   */
  autoLoad: {
    type: Boolean,
    default: null
  },
  /**
   * 空关键词行为(仅 searchMode=frontend 时生效):
   * load-all(默认) / clear / block
   */
  emptyBehavior: {
    type: String,
    default: 'load-all'
  },
  placeholder: {
    type: String,
    default: '请选择'
  },
  searchPlaceholder: {
    type: String,
    default: '输入关键词搜索'
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const list = ref([])
const selectedValue = ref(props.modelValue)
const searchKeyword = ref('')
const searchFocused = ref(false)
const searched = ref(false)   // 是否已发起过搜索(用于空态文案区分)

// autoLoad:未显式传时,frontend 模式默认 true(打开即加载),backend 默认 false
const isAutoLoad = computed(() =>
  props.autoLoad === null ? props.searchMode === 'frontend' : props.autoLoad
)

// 每个实例独立的 popper class,避免多实例共用同一 loading 遮罩
const popperClass = computed(() => `rss-popper rss-popper-${instanceId}`)
const instanceId = Math.random().toString(36).slice(2, 9)

// ─────────── 字段取值工具 ───────────
function resolveField(item, mapping) {
  if (mapping == null) return ''
  if (typeof mapping === 'function') {
    try { return mapping(item) || '' } catch { return '' }
  }
  // 字符串:支持点路径嵌套,如 'cover_url.url_list.0'
  return String(mapping).split('.').reduce((acc, key) => {
    if (acc == null) return ''
    // 数组下标
    if (/^\d+$/.test(key) && Array.isArray(acc)) return acc[Number(key)]
    return acc[key]
  }, item) ?? ''
}

function getKey(item) {
  return resolveField(item, props.fieldMap.key) || resolveField(item, props.fieldMap.label)
}
function getLabel(item) {
  return resolveField(item, props.fieldMap.label) || ''
}
function getDesc(item) {
  return resolveField(item, props.fieldMap.desc)
}
function getCover(item) {
  return resolveField(item, props.fieldMap.cover)
}
const hasCover = computed(() => props.fieldMap.cover != null)
function isSelected(item) {
  return getLabel(item) === selectedValue.value && selectedValue.value !== ''
}

function onCoverError(e) {
  e.target.style.display = 'none'
}

// ─────────── 搜索逻辑 ───────────
async function handleSearch() {
  const kw = searchKeyword.value?.trim()

  // 空关键词行为分流
  if (!kw) {
    if (props.searchMode === 'backend') {
      // 后端搜索模式:空关键词不请求
      return
    }
    if (props.emptyBehavior === 'block') return
    if (props.emptyBehavior === 'clear') {
      list.value = []
      searched.value = true
      return
    }
    // load-all:继续走请求
  }

  loading.value = true
  try {
    const result = await props.fetcher(kw)
    list.value = result?.list || []
    searched.value = true
  } catch (e) {
    console.error('[RemoteSearchSelect] 搜索失败:', e)
    list.value = []
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  list.value = []
  searched.value = false
}

function handleChange(val) {
  emit('update:modelValue', val)
  const item = list.value.find(it => getLabel(it) === val)
  // change 事件带完整对象 + _searchKeyword(原契约)
  emit('change', item ? { ...item, _searchKeyword: searchKeyword.value } : null)
}

// 下拉可见性变化:autoLoad 模式下,打开即加载全量(只加载一次,避免重复请求)
const autoLoaded = ref(false)
function handleVisibleChange(visible) {
  if (visible && isAutoLoad.value && !autoLoaded.value && !loading.value) {
    autoLoaded.value = true
    handleSearch()
  }
}

// ─────────── 外部值同步 + 回显占位项 ───────────
// 切换账号(modelValue 由父组件联动)时重置
watch(() => props.modelValue, (val) => {
  selectedValue.value = val
  // 有值但列表没有对应项 → 用 data 补一个占位项保证回显
  if (val && props.data && !list.value.find(it => getLabel(it) === val)) {
    list.value = [props.data, ...list.value]
  }
}, { immediate: true })
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.remote-search-select {
  width: 100%;
  // 触发器:让 el-select 融入暗色主题
  :deep(.el-select__wrapper) {
    background: $bg-surface;
    box-shadow: 0 0 0 1px $border inset;
    transition: box-shadow 0.2s;

    &:hover {
      box-shadow: 0 0 0 1px $border-active inset;
    }
    &.is-focused {
      box-shadow: 0 0 0 1px rgba($brand-start, 0.5) inset;
    }
  }
  :deep(.el-select__placeholder),
  :deep(.el-select__selected-item) {
    color: $text-primary;
  }
}
</style>

<!-- 全局样式(作用于 popper,无 scoped) -->
<style lang="scss">
@use '@/styles/variables' as *;

.rss-popper.el-popper {
  // 整体面板:暗色 + 磨砂 + 圆角 + 阴影
  background: rgba($bg-elevated-rgb, 0.96);
  backdrop-filter: blur(16px);
  border: 1px solid $border;
  border-radius: 14px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba($brand-start, 0.05);
  overflow: hidden;
  padding: 0;

  // 去掉 el-popper 默认箭头
  .el-popper__arrow { display: none; }

  .el-select-dropdown__wrap {
    max-height: 320px;
    padding: 0;
  }

  // ─────────── 搜索区 ───────────
  .rss-header {
    position: sticky;
    top: 0;
    z-index: 2;
    padding: 14px 14px 10px;
    background: linear-gradient(180deg, rgba($bg-elevated-rgb, 0.98) 70%, rgba($bg-elevated-rgb, 0));
    // 底部渐隐分隔线(替代生硬实线)
    &::after {
      content: '';
      position: absolute;
      left: 14px; right: 14px; bottom: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, $border 20%, $border 80%, transparent);
    }
  }

  .rss-search {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 38px;
    padding: 0 12px;
    background: rgba($overlay-rgb, 0.04);
    border: 1px solid $border;
    border-radius: 10px;
    transition: all 0.2s;

    &.is-focused {
      background: rgba($overlay-rgb, 0.06);
      border-color: rgba($brand-start, 0.5);
      box-shadow: 0 0 0 3px rgba($brand-start, 0.12);
    }
  }
  .rss-search-icon {
    color: $text-secondary;
    font-size: 15px;
    flex-shrink: 0;
  }
  .rss-search-input {
    flex: 1;
    min-width: 0;
    // el-input 透明融入搜索区(去掉自身 wrapper 背景/边框/阴影)
    :deep(.el-input__wrapper) {
      background: transparent;
      box-shadow: none !important;
      padding: 0;
    }
    :deep(.el-input__inner) {
      color: $text-primary;
      font-size: 14px;
      height: 38px;
      &::placeholder { color: $text-placeholder; }
    }
  }
  .rss-search-clear {
    color: $text-muted;
    cursor: pointer;
    flex-shrink: 0;
    transition: color 0.15s;
    &:hover { color: $text-secondary; }
  }
  .rss-hint {
    display: flex;
    align-items: center;
    gap: 5px;
    margin-top: 8px;
    padding-left: 2px;
    color: $text-muted;
    font-size: 11.5px;
    .el-icon { font-size: 12px; }
  }

  // ─────────── 列表项 ───────────
  .el-select-dropdown__item {
    height: auto;
    min-height: 56px;
    padding: 0;
    margin: 2px 8px;
    border-radius: 10px;
    background: transparent !important;
    transition: background 0.15s, transform 0.15s;

    &:hover,
    &.hover {
      background: rgba($overlay-rgb, 0.05) !important;
      transform: translateX(2px);
    }
    &.selected {
      background: rgba($brand-start, 0.08) !important;
      font-weight: normal;
    }
  }

  .rss-option {
    position: relative;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    min-height: 56px;

    // 选中态左侧紫蓝渐变条
    .rss-option-bar {
      position: absolute;
      left: 0; top: 14px; bottom: 14px;
      width: 3px;
      border-radius: 0 3px 3px 0;
      background: $gradient-brand;
      opacity: 0;
      transition: opacity 0.15s;
    }
    &.is-selected .rss-option-bar { opacity: 1; }
  }

  .rss-option-cover {
    flex-shrink: 0;
    width: 44px; height: 44px;
    border-radius: 8px;
    overflow: hidden;
    background: rgba($overlay-rgb, 0.03);
    img {
      width: 100%; height: 100%;
      object-fit: cover;
    }
  }
  .rss-cover-placeholder {
    width: 100%; height: 100%;
    display: flex; align-items: center; justify-content: center;
    color: $text-muted;
    background: linear-gradient(135deg, rgba($brand-start, 0.1), rgba($brand-end, 0.06));
  }

  .rss-option-info {
    flex: 1;
    min-width: 0;
  }
  .rss-option-label {
    font-size: 14px;
    font-weight: 500;
    color: $text-primary;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rss-option-desc {
    margin-top: 3px;
    font-size: 12px;
    color: $text-secondary;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rss-option-check {
    flex-shrink: 0;
    color: $brand-start;
    font-size: 16px;
  }

  // ─────────── 空态 ───────────
  .rss-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 40px 20px;
    color: $text-muted;
    font-size: 13px;
    text-align: center;
  }
  .rss-empty-icon {
    font-size: 28px;
    color: $text-placeholder;
  }

  // ─────────── loading:三个脉冲点 ───────────
  .rss-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 10px 0 4px;
    // autoLoad 模式:无搜索框包裹,独立显示时加大上下间距
    &.rss-loading--standalone {
      padding: 18px 0 14px;
    }
  }
  .rss-loading-text {
    margin-left: 6px;
    font-size: 12.5px;
    color: $text-secondary;
  }
  .rss-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: $gradient-brand;
    animation: rss-pulse 1.2s ease-in-out infinite;
    &:nth-child(2) { animation-delay: 0.18s; }
    &:nth-child(3) { animation-delay: 0.36s; }
  }
  @keyframes rss-pulse {
    0%, 80%, 100% { opacity: 0.3; transform: scale(0.7); }
    40% { opacity: 1; transform: scale(1); }
  }
}
</style>
