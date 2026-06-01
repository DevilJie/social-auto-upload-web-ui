<template>
  <el-dialog
    v-model="visible"
    :width="920"
    :close-on-click-modal="false"
    class="material-select-dialog"
    destroy-on-close
    @closed="onClosed"
    append-to-body
  >
    <template #header>
      <div class="msd-header">
        <div class="msd-header-title">
          <span class="msd-header-dot" />
          <span>选择素材</span>
        </div>
        <div class="msd-header-stats">
          共 <b>{{ total }}</b> 个素材
          <span v-if="hasFilter" class="msd-header-filter-hint">（已筛选）</span>
        </div>
      </div>
    </template>

    <!-- Toolbar: search + type filter -->
    <div class="msd-toolbar">
      <div class="msd-search">
        <el-input
          v-model="searchKeyword"
          placeholder="按文件名搜索..."
          clearable
          :prefix-icon="Search"
          @input="onSearchInput"
          @clear="onSearchClear"
        />
      </div>
      <div class="msd-type-filter">
        <button
          v-for="opt in typeOptions"
          :key="opt.value"
          :class="['msd-type-btn', { active: typeFilter === opt.value }]"
          @click="onTypeChange(opt.value)"
        >
          <el-icon :size="14"><component :is="opt.icon" /></el-icon>
          <span>{{ opt.label }}</span>
        </button>
      </div>
    </div>

    <!-- Body -->
    <div class="msd-body" v-loading="loading">
      <div v-if="items.length > 0" class="msd-grid">
        <div
          v-for="mat in items"
          :key="mat.id"
          class="msd-card"
          :class="{ selected: selectedId === mat.id }"
          @click="selectedId = mat.id"
        >
          <!-- Preview -->
          <div class="msd-card-preview">
            <img
              v-if="mat.file_type === 'image'"
              :src="getThumbUrl(mat)"
              :alt="mat.original_filename"
              loading="lazy"
              @error="onImageError"
            />
            <template v-else>
              <img
                v-if="mat.thumbnail_url"
                :src="getThumbUrl(mat)"
                :alt="mat.original_filename"
                loading="lazy"
                class="msd-card-video-thumb"
                @error="onImageError"
              />
              <div v-else class="msd-card-video-fallback">
                <el-icon :size="32"><VideoPlay /></el-icon>
              </div>
              <div class="msd-card-video-badge">
                <el-icon :size="11"><VideoPlay /></el-icon>
                <span>视频</span>
              </div>
            </template>

            <!-- Selected check -->
            <div v-if="selectedId === mat.id" class="msd-card-check">
              <el-icon :size="14"><Check /></el-icon>
            </div>

            <!-- Hover overlay -->
            <div class="msd-card-hover-info">
              <span class="msd-card-size">{{ formatSize(mat.file_size) }}</span>
              <span class="msd-card-date">{{ formatDate(mat.upload_time) }}</span>
            </div>
          </div>
          <!-- Caption -->
          <div class="msd-card-caption">
            <span class="msd-card-name" :title="mat.original_filename">
              {{ mat.original_filename }}
            </span>
          </div>
        </div>
      </div>

      <div v-else-if="!loading" class="msd-empty">
        <div class="msd-empty-icon">
          <el-icon :size="48"><Picture /></el-icon>
        </div>
        <div class="msd-empty-title">
          {{ hasFilter ? '没有匹配的素材' : '素材库还是空的' }}
        </div>
        <div class="msd-empty-desc">
          {{ hasFilter ? '试试其他关键词或类型' : '上传你的第一个素材吧' }}
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > 0" class="msd-pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[12, 24, 48, 96]"
        :total="total"
        layout="sizes, prev, pager, next, jumper"
        background
        small
        @current-change="loadPage"
        @size-change="onPageSizeChange"
      />
    </div>

    <template #footer>
      <div class="msd-footer">
        <div class="msd-footer-status">
          <span v-if="selectedMat" class="msd-footer-selected">
            <el-icon :size="14" color="var(--brand-start, #5b8cff)"><Check /></el-icon>
            <span>已选：{{ selectedMat.original_filename }}</span>
          </span>
          <span v-else class="msd-footer-hint">未选择素材</span>
        </div>
        <div class="msd-footer-actions">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :disabled="!selectedId" @click="confirmSelect">
            确定
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  Search,
  VideoPlay,
  Check,
  Picture,
  PictureFilled,
  VideoCamera,
  Grid,
} from '@element-plus/icons-vue'
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'

const props = defineProps({
  /** 'all' | 'image' | 'video' - 限制可选项，默认 'all' */
  filterType: { type: String, default: 'all' },
  /** 多选模式：返回数组；单选模式：返回单个 */
  multiple: { type: Boolean, default: false },
})

const emit = defineEmits(['select'])

const visible = ref(false)
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(24)
const searchKeyword = ref('')
const typeFilter = ref('all')
const selectedId = ref(null)

const typeOptions = computed(() => {
  const opts = [{ value: 'all', label: '全部', icon: Grid }]
  if (props.filterType === 'all' || props.filterType === 'image') {
    opts.push({ value: 'image', label: '图片', icon: PictureFilled })
  }
  if (props.filterType === 'all' || props.filterType === 'video') {
    opts.push({ value: 'video', label: '视频', icon: VideoCamera })
  }
  return opts
})

const hasFilter = computed(
  () => searchKeyword.value.trim() !== '' || typeFilter.value !== 'all',
)

const selectedMat = computed(
  () => items.value.find((m) => m.id === selectedId.value) || null,
)

function getThumbUrl(mat) {
  if (mat.thumbnail_url) return mat.thumbnail_url
  return getFileUrl(mat.stored_path)
}

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso.replace(' ', 'T') + (iso.endsWith('Z') ? '' : 'Z'))
  if (isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const placeholderSvg =
  'data:image/svg+xml;base64,' +
  btoa(`<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">
    <rect width="200" height="200" fill="#1a1d24"/>
    <text x="100" y="105" font-family="sans-serif" font-size="14" fill="#666"
      text-anchor="middle">加载失败</text>
  </svg>`)

function onImageError(e) {
  e.target.src = placeholderSvg
}

let searchDebounce = null
function onSearchInput() {
  clearTimeout(searchDebounce)
  searchDebounce = setTimeout(() => {
    page.value = 1
    loadPage()
  }, 300)
}

function onSearchClear() {
  page.value = 1
  loadPage()
}

function onTypeChange(value) {
  typeFilter.value = value
  page.value = 1
  loadPage()
}

function onPageSizeChange() {
  page.value = 1
  loadPage()
}

async function loadPage() {
  loading.value = true
  try {
    const resp = await materialsApi.list({
      type: typeFilter.value,
      keyword: searchKeyword.value.trim(),
      page: page.value,
      page_size: pageSize.value,
    })
    if (resp.code === 200) {
      items.value = resp.data.items || []
      total.value = resp.data.total || 0
      // 翻页后，如果当前选中不在新页面则清空
      if (selectedId.value && !items.value.some((m) => m.id === selectedId.value)) {
        selectedId.value = null
      }
    }
  } catch (e) {
    console.error('加载素材失败:', e)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function confirmSelect() {
  if (!selectedId.value) return
  const material = items.value.find((m) => m.id === selectedId.value)
  if (!material) return
  emit('select', {
    id: material.id,
    name: material.original_filename,
    url: getFileUrl(material.stored_path),
    stored_path: material.stored_path,
    size: material.file_size,
    type: material.mime_type,
  })
  visible.value = false
}

function onClosed() {
  searchKeyword.value = ''
  typeFilter.value = 'all'
  page.value = 1
  selectedId.value = null
  items.value = []
  total.value = 0
}

async function open() {
  visible.value = true
  typeFilter.value = props.filterType || 'all'
  page.value = 1
  selectedId.value = null
  await loadPage()
}

defineExpose({ open })
</script>

<style lang="scss">
.material-select-dialog {
  --msd-radius: 14px;
  --msd-glass: rgba(20, 22, 28, 0.85);
  --msd-border: rgba(255, 255, 255, 0.08);
  --msd-brand-1: #5b8cff;
  --msd-brand-2: #8b5cff;

  .el-dialog {
    background: var(--msd-glass);
    backdrop-filter: blur(20px) saturate(140%);
    -webkit-backdrop-filter: blur(20px) saturate(140%);
    border: 1px solid var(--msd-border);
    border-radius: var(--msd-radius);
    box-shadow:
      0 25px 60px rgba(0, 0, 0, 0.5),
      0 0 0 1px rgba(255, 255, 255, 0.03),
      inset 0 1px 0 rgba(255, 255, 255, 0.04);
    overflow: hidden;
  }

  .el-dialog__header {
    padding: 0;
    margin-right: 0;
  }

  .el-dialog__body {
    padding: 0;
    background:
      radial-gradient(ellipse at top, rgba(91, 140, 255, 0.08), transparent 60%),
      var(--msd-glass);
  }

  .el-dialog__footer {
    padding: 14px 20px;
    border-top: 1px solid var(--msd-border);
    background: rgba(0, 0, 0, 0.2);
  }
}
</style>

<style scoped lang="scss">
$brand-1: #5b8cff;
$brand-2: #8b5cff;
$text-1: #e5e7eb;
$text-2: #9ca3af;
$text-3: #6b7280;
$border: rgba(255, 255, 255, 0.08);
$bg-card: rgba(255, 255, 255, 0.03);
$bg-card-hover: rgba(255, 255, 255, 0.05);

// ===== Header =====
.msd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid $border;
  background:
    linear-gradient(180deg, rgba(91, 140, 255, 0.08), transparent);
}

.msd-header-title {
  display: flex;
  align-items: center;
  gap: 10px;
  color: $text-1;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.msd-header-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, $brand-1, $brand-2);
  box-shadow: 0 0 10px rgba($brand-1, 0.6);
}

.msd-header-stats {
  font-size: 12px;
  color: $text-2;

  b {
    color: $text-1;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
}

.msd-header-filter-hint {
  margin-left: 4px;
  color: $brand-1;
}

// ===== Toolbar =====
.msd-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 22px 12px;
}

.msd-search {
  flex: 1;
  max-width: 360px;

  :deep(.el-input__wrapper) {
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid $border;
    border-radius: 10px;
    box-shadow: none;
    padding: 4px 12px;
    transition: all 0.2s ease;
    &:hover { border-color: rgba(255, 255, 255, 0.16); }
    &.is-focus {
      border-color: rgba($brand-1, 0.5);
      box-shadow: 0 0 0 3px rgba($brand-1, 0.12);
      background: rgba(0, 0, 0, 0.35);
    }
    .el-input__inner {
      color: $text-1;
      &::placeholder { color: $text-3; }
    }
    .el-input__prefix .el-icon { color: $text-2; }
  }
}

.msd-type-filter {
  display: flex;
  gap: 4px;
  padding: 3px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid $border;
  border-radius: 10px;
}

.msd-type-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  background: transparent;
  border: none;
  border-radius: 7px;
  color: $text-2;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover { color: $text-1; background: $bg-card-hover; }

  &.active {
    color: #fff;
    background: linear-gradient(135deg, rgba($brand-1, 0.9), rgba($brand-2, 0.9));
    box-shadow: 0 2px 8px rgba($brand-1, 0.3);
  }
}

// ===== Body =====
.msd-body {
  padding: 8px 22px 4px;
  min-height: 320px;
  max-height: 52vh;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.08) transparent;

  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
    &:hover { background: rgba(255, 255, 255, 0.18); }
  }
}

// ===== Grid =====
.msd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  padding: 4px 0 12px;
}

// ===== Card =====
.msd-card {
  position: relative;
  border-radius: 10px;
  background: $bg-card;
  border: 1px solid $border;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    border-color: rgba($brand-1, 0.4);
    background: $bg-card-hover;
    transform: translateY(-2px);
    box-shadow:
      0 8px 20px rgba(0, 0, 0, 0.3),
      0 0 0 1px rgba($brand-1, 0.1);

    .msd-card-preview img { transform: scale(1.05); }
    .msd-card-hover-info { opacity: 1; }
  }

  &.selected {
    border-color: $brand-1;
    background: rgba($brand-1, 0.06);
    box-shadow:
      0 0 0 2px rgba($brand-1, 0.4),
      0 8px 24px rgba(0, 0, 0, 0.35);

    .msd-card-name { color: $brand-1; }
  }
}

.msd-card-preview {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.02), rgba(0, 0, 0, 0.1)),
    repeating-linear-gradient(45deg, transparent, transparent 8px, rgba(255,255,255,0.01) 8px, rgba(255,255,255,0.01) 16px);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 0.35s ease;
  }
}

.msd-card-video-thumb {
  // 视频缩略图保持 cover
}

.msd-card-video-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at center, rgba($brand-1, 0.1), transparent 70%),
    rgba(0, 0, 0, 0.2);
  color: $text-2;
}

.msd-card-video-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(8px);
  border-radius: 4px;
  color: #fff;
  font-size: 10px;
  font-weight: 500;
}

.msd-card-check {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, $brand-1, $brand-2);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    0 2px 8px rgba($brand-1, 0.5),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  animation: msd-check-pop 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes msd-check-pop {
  0% { transform: scale(0); }
  100% { transform: scale(1); }
}

.msd-card-hover-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 6px 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(180deg, transparent, rgba(0, 0, 0, 0.75));
  color: #fff;
  font-size: 10px;
  opacity: 0;
  transition: opacity 0.2s ease;
  pointer-events: none;
}

.msd-card-caption {
  padding: 7px 8px 9px;
}

.msd-card-name {
  display: block;
  font-size: 11px;
  color: $text-1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  transition: color 0.15s ease;
}

// ===== Empty =====
.msd-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 60px 0;
  color: $text-2;
}

.msd-empty-icon {
  color: $text-3;
  opacity: 0.5;
  margin-bottom: 4px;
}

.msd-empty-title {
  font-size: 13px;
  color: $text-1;
  font-weight: 500;
}

.msd-empty-desc {
  font-size: 12px;
  color: $text-3;
}

// ===== Pagination =====
.msd-pagination {
  display: flex;
  justify-content: center;
  padding: 8px 0 12px;
  border-top: 1px solid $border;
  margin-top: 4px;
  background: rgba(0, 0, 0, 0.1);

  :deep(.el-pagination) {
    --el-pagination-bg-color: transparent;
    --el-pagination-button-bg-color: rgba(255, 255, 255, 0.04);
    --el-pagination-hover-color: #{$brand-1};
    --el-pagination-button-color: #{$text-2};
    --el-pagination-button-disabled-bg-color: transparent;

    .btn-prev, .btn-next, .el-pager li {
      background: rgba(255, 255, 255, 0.04) !important;
      color: $text-2 !important;
      border: 1px solid transparent;

      &:hover {
        color: $brand-1 !important;
        border-color: rgba($brand-1, 0.3);
      }
    }

    .el-pager li.is-active {
      background: linear-gradient(135deg, $brand-1, $brand-2) !important;
      color: #fff !important;
      border-color: transparent;
    }

    .el-pagination__sizes .el-select .el-select__wrapper {
      background: rgba(255, 255, 255, 0.04);
      box-shadow: 0 0 0 1px $border;
    }
  }
}

// ===== Footer =====
.msd-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.msd-footer-status {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: $text-2;
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
}

.msd-footer-selected {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: $text-1;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100%;

  span:last-child {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.msd-footer-hint {
  color: $text-3;
}

.msd-footer-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;

  :deep(.el-button--primary) {
    background: linear-gradient(135deg, $brand-1, $brand-2);
    border: none;
    box-shadow: 0 2px 10px rgba($brand-1, 0.3);
    &:hover {
      opacity: 0.92;
      box-shadow: 0 4px 14px rgba($brand-1, 0.4);
    }
    &.is-disabled {
      opacity: 0.4;
      background: linear-gradient(135deg, $brand-1, $brand-2);
    }
  }
}
</style>
