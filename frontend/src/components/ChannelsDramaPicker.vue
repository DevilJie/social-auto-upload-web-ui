<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="handleVisibilityChange"
    width="900px"
    top="5vh"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :before-close="handleClose"
    class="drama-picker-dialog"
  >
    <template #header>
      <div class="picker-header">
        <h3>关联视频号剧集</h3>
        <span class="picker-tip">每条视频只能关联 1 部剧集,关联后会自动带入剧集授权信息</span>
      </div>
    </template>

    <div class="picker-toolbar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索剧集名称"
        clearable
        @keyup.enter="onSearch"
      >
        <template #suffix>
          <el-icon class="cursor-pointer" @click="onSearch"><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <div class="picker-content" v-loading="loading" element-loading-text="加载中...">
      <div class="drama-table">
        <el-table
          :data="items"
          height="100%"
          stripe
          @row-click="onRowClick"
          :row-class-name="rowClassName"
        >
          <el-table-column type="index" label="#" width="56" />
          <el-table-column label="剧集" min-width="220">
            <template #default="{ row }">
              <div class="drama-info-cell">
                <img v-if="row.cover" :src="row.cover" class="drama-cover" :alt="row.title" referrerpolicy="no-referrer" />
                <div class="drama-cover-empty" v-else>
                  <el-icon :size="20"><Picture /></el-icon>
                </div>
                <div class="drama-text">
                  <div class="drama-title" :title="row.title">{{ row.title }}</div>
                  <div v-if="row.extinfo" class="drama-extinfo">{{ row.extinfo }}</div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="sourceLeft" label="播放小程序" min-width="160">
            <template #default="{ row }">
              <span v-if="row.sourceLeft">{{ row.sourceLeft }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="sourceRight" label="版权所属" min-width="160">
            <template #default="{ row }">
              <span v-if="row.sourceRight">{{ row.sourceRight }}</span>
              <span v-else class="muted">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="center">
            <template #default="{ row }">
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="row.unusable"
                @click.stop="onRowClick(row)"
              >选择</el-button>
            </template>
          </el-table-column>
          <!-- 空态只在这里渲染一次(替代 el-table 默认的「暂无数据」) -->
          <template #empty>
            <div class="empty-tip">
              <el-icon class="empty-icon"><DocumentRemove /></el-icon>
              <span>暂无剧集,请调整搜索词</span>
            </div>
          </template>
        </el-table>
      </div>

      <!-- 页码直接同步后端读到的视频号分页器(totalPages/当前页),不按条数换算 -->
      <div v-if="totalPages > 1" class="pagination-wrap">
        <el-pagination
          background
          layout="prev, pager, next, jumper"
          :page-count="totalPages"
          :current-page="page"
          @current-change="onPageChange"
        />
      </div>
    </div>

    <template #footer>
      <div class="picker-footer">
        <span class="selected-summary" v-if="selectedDrama">
          已选:<b>{{ selectedDrama.title }}</b>
          <span v-if="selectedDrama.extinfo" class="muted">({{ selectedDrama.extinfo }})</span>
        </span>
        <span v-else class="muted">点击行选择剧集</span>
        <div class="footer-actions">
          <el-button @click="handleClose">取消</el-button>
          <el-button type="primary" :disabled="!selectedDrama" @click="onConfirm">确认选择</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Picture, DocumentRemove } from '@element-plus/icons-vue'
import { channelsDramaApi } from '@/api/channels_drama'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  accountId: { type: [String, Number], required: true },
  // 初始已选(用于回显),[{ key, title, cover, extinfo, sourceLeft, sourceRight, trace }]
  initSelected: { type: Array, default: () => [] },
  // 链接类型: 'drama'(视频号剧集) / 'mini_drama'(小程序短剧)
  linkType: { type: String, default: 'drama' },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

// 表格分页:页码完全以视频号弹窗分页器为准(page/totalPages 由后端同步)
const items = ref([])
const page = ref(1)
const totalPages = ref(1)
const loading = ref(false)
const searchKeyword = ref('')
const selectedDrama = ref(null)  // 当前选中的剧集(临时态,confirm 时才提交)
const sessionActive = ref(false)  // 后端 picker session 是否在跑

function normalizeSelected(arr) {
  if (!Array.isArray(arr)) return []
  return arr
    .map((d) => {
      if (typeof d === 'string') return { key: d, title: d, trace: undefined }
      return { ...d, trace: d.trace || undefined }
    })
    .filter((d) => d.key || d.title)
    .slice(0, 1)  // 视频号只支持关联 1 部剧集
}

async function ensureSession() {
  if (sessionActive.value) return true
  loading.value = true
  try {
    const res = await channelsDramaApi.open(props.accountId, props.linkType)
    const d = res?.data || {}
    items.value = d.items || []
    page.value = d.page || 1
    totalPages.value = d.total_pages || 1
    sessionActive.value = true
    return true
  } catch (e) {
    ElMessage.error('打开剧集选择面板失败: ' + (e?.message || e))
    return false
  } finally {
    loading.value = false
  }
}

async function onSearch() {
  loading.value = true
  try {
    const res = await channelsDramaApi.search(props.accountId, searchKeyword.value || '')
    const d = res?.data || {}
    items.value = d.items || []
    page.value = d.page || 1
    totalPages.value = d.total_pages || 1
  } catch (e) {
    ElMessage.error('搜索失败: ' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

async function onPageChange(newPage) {
  if (newPage === page.value) return
  loading.value = true
  try {
    const res = await channelsDramaApi.goPage(props.accountId, newPage)
    const d = res?.data || {}
    items.value = d.items || []
    page.value = d.page || newPage
    totalPages.value = d.total_pages || 1
  } catch (e) {
    ElMessage.error('翻页失败: ' + (e?.message || e))
  } finally {
    loading.value = false
  }
}

function onRowClick(row) {
  if (!row || row.unusable) return
  selectedDrama.value = row
}

function rowClassName({ row }) {
  return selectedDrama.value?.key === row.key ? 'is-selected-row' : ''
}

function onConfirm() {
  if (!selectedDrama.value) return
  // trace: 发布时按 (linkType, keyword, page) 复现选中
  const trace = {
    linkType: props.linkType,
    keyword: searchKeyword.value || '',
    page: page.value || 1,
  }
  emit(
    'confirm',
    [{ ...selectedDrama.value, linkType: props.linkType, trace }],
  )
  emit('update:modelValue', false)
}

function handleVisibilityChange(visible) {
  if (visible) {
    emit('update:modelValue', true)
  } else {
    handleClose()
  }
}

async function handleClose() {
  if (sessionActive.value) {
    try {
      await channelsDramaApi.close(props.accountId)
    } catch (e) {
      console.warn('close drama picker session failed', e)
    }
    sessionActive.value = false
  }
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible) return
    const init = normalizeSelected(props.initSelected)
    selectedDrama.value = init.length > 0 ? init[0] : null
    const ok = await ensureSession()
    if (!ok) return
    if (init[0]?.trace) {
      const kw = init[0].trace.keyword || ''
      if (kw) {
        searchKeyword.value = kw
        await onSearch()
      }
      const p = init[0].trace.page || 1
      if (p && p !== page.value) {
        await onPageChange(p)
      }
    }
  },
)

onBeforeUnmount(() => {
  if (sessionActive.value) {
    channelsDramaApi.close(props.accountId).catch(() => {})
  }
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.drama-picker-dialog {
  :deep(.el-dialog__body) {
    padding: 0 20px;
  }

  // loading 遮罩:跟随主题底色半透明(默认灰色蒙层在亮色模式下太重),spinner 用品牌紫
  :deep(.el-loading-mask) {
    background-color: rgba(var(--bg-elevated-rgb), 0.72);
    backdrop-filter: blur(2px);
    border-radius: 6px;
  }
  :deep(.el-loading-spinner) {
    .circular .path {
      stroke: $brand-start;
    }
    .el-loading-text {
      color: $brand-start;
    }
  }
}

.picker-header {
  display: flex;
  align-items: baseline;
  gap: 12px;

  h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
  .picker-tip {
    font-size: 12px;
    color: $text-muted;
  }
}

.picker-toolbar {
  padding: 14px 0 12px;
  border-bottom: 1px solid $border-light;
}

.picker-content {
  padding: 12px 0;
  min-height: 400px;
}

.drama-table {
  height: 400px;
  overflow: hidden;
  border: 1px solid $border-light;
  border-radius: 6px;

  :deep(.el-table) {
    height: 100%;
  }
  :deep(.el-table__row) {
    cursor: pointer;
  }
  :deep(.is-selected-row td) {
    background: rgba($brand-start, 0.08) !important;
  }
}

.drama-info-cell {
  display: flex;
  align-items: center;
  gap: 10px;

  .drama-cover,
  .drama-cover-empty {
    width: 40px;
    height: 40px;
    border-radius: 4px;
    flex-shrink: 0;
    object-fit: cover;
    background: $bg-surface;
    display: flex;
    align-items: center;
    justify-content: center;
    color: $text-muted;
  }
  .drama-text {
    flex: 1;
    min-width: 0;

    .drama-title {
      font-size: 13px;
      color: $text-primary;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .drama-extinfo {
      font-size: 11px;
      color: $text-muted;
      margin-top: 2px;
    }
  }
}

.pagination-wrap {
  margin-top: 12px;
  display: flex;
  justify-content: center;
}

.empty-tip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 0;
  color: $text-muted;

  .empty-icon {
    font-size: 42px;
    opacity: 0.5;
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
    font-size: 13px;
    color: $text-primary;

    b {
      color: $brand-start;
      margin: 0 4px;
    }
  }

  .muted {
    color: $text-muted;
  }

  .footer-actions {
    display: flex;
    gap: 8px;
  }
}

.muted {
  color: $text-muted;
}
</style>
