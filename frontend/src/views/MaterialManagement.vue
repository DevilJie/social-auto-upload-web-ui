<template>
  <div class="material-management">
    <!-- Page Header -->
    <div class="page-header">
      <h1>素材管理</h1>
      <p class="page-subtitle">统一管理所有上传的视频与图片素材</p>
    </div>

    <!-- Toolbar -->
    <div class="toolbar-card">
      <div class="search-input-wrap">
        <el-input
          v-model="searchKeyword"
          placeholder="按文件名搜索..."
          clearable
          :prefix-icon="Search"
          @input="onSearchInput"
          @clear="onSearchClear"
        />
      </div>
      <div class="type-filter">
        <button
          v-for="opt in typeOptions"
          :key="opt.value"
          :class="['type-btn', { active: typeFilter === opt.value }]"
          @click="onTypeChange(opt.value)"
        >
          <el-icon :size="14"><component :is="opt.icon" /></el-icon>
          <span>{{ opt.label }}</span>
        </button>
      </div>
      <div class="action-buttons">
        <el-button class="btn-refresh" @click="fetchMaterials" :loading="false">
          <el-icon :class="{ 'is-loading': isRefreshing }"><Refresh /></el-icon>
          <span v-if="isRefreshing">刷新中</span>
          <span v-else>刷新</span>
        </el-button>
        <el-button type="primary" class="btn-upload" @click="handleUploadMaterial">
          <el-icon><Upload /></el-icon>
          <span>上传素材</span>
        </el-button>
      </div>
    </div>

    <!-- Cards Grid -->
    <div class="cards-container" v-loading="loading">
      <div v-if="items.length > 0" class="cards-grid">
        <div
          v-for="mat in items"
          :key="mat.id"
          class="mat-card"
        >
          <!-- Preview -->
          <div class="mat-card-preview">
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
                class="mat-card-video-thumb"
                @error="onImageError"
              />
              <div v-else class="mat-card-video-fallback">
                <el-icon :size="32"><VideoPlay /></el-icon>
              </div>
              <!-- 居中播放按钮 -->
              <button
                class="mat-card-play-btn"
                :aria-label="`预览 ${mat.original_filename}`"
                @click.stop="openPreview(mat)"
              >
                <el-icon :size="20"><VideoPlay /></el-icon>
              </button>
              <!-- 类型徽章 -->
              <div class="mat-card-video-badge">
                <el-icon :size="11"><VideoPlay /></el-icon>
                <span>视频</span>
              </div>
            </template>

            <!-- 存储方式标识 -->
            <span class="mat-card-storage-badge" :class="{ s3: mat.storage_type === 's3' }">
              <el-icon :size="11"><component :is="mat.storage_type === 's3' ? 'Upload' : 'Monitor'" /></el-icon>
              {{ mat.storage_type === 's3' ? 'S3' : '本地' }}
            </span>

            <!-- 删除按钮（hover 浮现） -->
            <button
              class="mat-card-delete-btn"
              :aria-label="`删除 ${mat.original_filename}`"
              @click.stop="handleDelete(mat)"
            >
              <el-icon :size="14"><Delete /></el-icon>
            </button>

            <!-- 底部悬停信息 -->
            <div class="mat-card-hover-info">
              <span>{{ mat.file_type === 'image' ? '图片' : '视频' }}</span>
            </div>
          </div>

          <!-- 卡片元信息 -->
          <div class="mat-card-meta">
            <div class="mat-card-name" :title="mat.original_filename">
              {{ mat.original_filename }}
            </div>
            <div class="mat-card-stats">
              <span class="mat-card-size">{{ formatFileSize(mat.file_size) }}</span>
              <span class="mat-card-dot">·</span>
              <span class="mat-card-time">{{ formatDate(mat.upload_time) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="!loading" class="empty-data">
        <div class="empty-icon">
          <el-icon :size="48"><Picture /></el-icon>
        </div>
        <div class="empty-title">
          {{ hasFilter ? '没有匹配的素材' : '素材库还是空的' }}
        </div>
        <div class="empty-desc">
          {{ hasFilter ? '试试其他关键词或类型' : '上传你的第一个素材吧' }}
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > 0" class="pagination-wrap">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[12, 24, 48, 96]"
        :total="total"
        layout="sizes, prev, pager, next, jumper"
        background
        @current-change="loadPage"
        @size-change="onPageSizeChange"
      />
    </div>

    <!-- Upload Dialog -->
    <MaterialUploader
      v-model="uploadDialogVisible"
      accept="*"
      :multiple="true"
      :max-count="20"
      title="上传素材"
      tip="支持图片、视频，单文件不限大小"
      @all-uploaded="onMaterialsUploaded"
    />

    <!-- Preview Dialog -->
    <el-dialog
      v-model="previewDialogVisible"
      title="素材预览"
      width="60%"
      :top="'8vh'"
      class="preview-dialog"
    >
      <div class="preview-container" v-if="currentMaterial">
        <div v-if="currentMaterial.file_type === 'video'" class="video-preview">
          <video :src="getFullUrl(currentMaterial)" controls autoplay />
        </div>
        <div v-else class="image-preview">
          <img :src="getFullUrl(currentMaterial)" :alt="currentMaterial.original_filename" />
        </div>
        <div class="preview-meta">
          <span class="preview-name">{{ currentMaterial.original_filename }}</span>
          <span class="preview-size">{{ formatFileSize(currentMaterial.file_size) }}</span>
          <span class="preview-time">{{ formatDate(currentMaterial.upload_time) }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  Search,
  Refresh,
  Upload,
  Delete,
  VideoPlay,
  Picture,
  PictureFilled,
  VideoCamera,
  Grid,
  Monitor,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
import { useAppStore } from '@/stores/app'
import MaterialUploader from '@/components/MaterialUploader.vue'

const appStore = useAppStore()

// 搜索/筛选/分页
const searchKeyword = ref('')
const typeFilter = ref('all')
const page = ref(1)
const pageSize = ref(24)
const items = ref([])
const total = ref(0)
const loading = ref(false)
const isRefreshing = ref(false)

const typeOptions = [
  { value: 'all', label: '全部', icon: Grid },
  { value: 'image', label: '图片', icon: PictureFilled },
  { value: 'video', label: '视频', icon: VideoCamera },
]

const hasFilter = computed(
  () => searchKeyword.value.trim() !== '' || typeFilter.value !== 'all',
)

// 对话框控制
const uploadDialogVisible = ref(false)
const previewDialogVisible = ref(false)
const currentMaterial = ref(null)

function onSearchInput() {
  page.value = 1
  loadPage()
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
    }
  } catch (e) {
    console.error('获取素材列表出错:', e)
    ElMessage.error('获取素材列表失败')
  } finally {
    loading.value = false
  }
}

async function fetchMaterials() {
  isRefreshing.value = true
  try {
    await loadPage()
    ElMessage.success('刷新成功')
  } finally {
    isRefreshing.value = false
  }
}

function getThumbUrl(mat) {
  if (mat.thumbnail_url) return mat.thumbnail_url
  return getFileUrl(mat.stored_path)
}

function getFullUrl(mat) {
  return getFileUrl(mat.stored_path)
}

const placeholderSvg =
  'data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyMDAiIGhlaWdodD0iMjAwIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iIzFhMWQyNCIvPjx0ZXh0IHg9IjEwMCIgeT0iMTA1IiBmb250LWZhbWlseT0ic2Fucy1zZXJpZiIgZm9udC1zaXplPSIxNCIgZmlsbD0iIzY2NiIgdGV4dC1hbmNob3I9Im1pZGRsZSI+TG9hZGluZyBmYWlsZWQ8L3RleHQ+PC9zdmc+'

function onImageError(e) {
  e.target.src = placeholderSvg
}

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
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

function openPreview(mat) {
  currentMaterial.value = mat
  previewDialogVisible.value = true
}

// 上传素材
function handleUploadMaterial() {
  uploadDialogVisible.value = true
}

async function onMaterialsUploaded() {
  await loadPage()
  // 同步 store（保持左侧菜单/发布界面等使用 store 的视图一致）
  materialsApi.list({ page_size: 200 }).then((r) => {
    if (r.code === 200) appStore.setMaterials(r.data.items || [])
  })
}

function handleDelete(mat) {
  ElMessageBox.confirm(
    `确定要删除素材「${mat.original_filename}」吗？\n将同时删除对应的文件，该操作不可恢复。`,
    '删除素材',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )
    .then(async () => {
      try {
        const response = await materialsApi.delete(mat.id)
        if (response.code === 200) {
          appStore.removeMaterial(mat.id)
          ElMessage.success('删除成功')
          // 当前页删完后若空了，回退到前一页
          if (items.value.length === 1 && page.value > 1) {
            page.value -= 1
          }
          await loadPage()
          // 同步 store
          materialsApi.list({ page_size: 200 }).then((r) => {
            if (r.code === 200) appStore.setMaterials(r.data.items || [])
          })
        } else {
          ElMessage.error(response.msg || '删除失败')
        }
      } catch (error) {
        console.error('删除素材出错:', error)
        ElMessage.error('删除失败')
      }
    })
    .catch(() => {})
}

onMounted(() => {
  loadPage()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

$brand-1: #5b8cff;
$brand-2: #8b5cff;
$text-1: #e5e7eb;
$text-2: #9ca3af;
$text-3: #6b7280;
$border: rgba($overlay-rgb, 0.08);
$danger: #ef4444;

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.material-management {
  padding: 0 28px 28px;
}

.page-header {
  margin-bottom: $spacing-lg;

  h1 {
    font-size: 26px;
    font-weight: 700;
    color: $text-primary;
    margin: 0 0 4px 0;
    letter-spacing: -0.5px;
  }

  .page-subtitle {
    font-size: 14px;
    color: $text-muted;
    margin: 0;
  }
}

// ========== Toolbar ==========
.toolbar-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: $spacing-md $spacing-lg;
  margin-bottom: $spacing-lg;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
}

.search-input-wrap {
  width: 280px;
  flex-shrink: 0;

  :deep(.el-input__wrapper) {
    background: $bg-base;
    border: 1px solid $border;
    border-radius: 8px;
    box-shadow: none;
    padding: 3px 12px;
    &:hover { border-color: rgba($overlay-rgb, 0.16); }
    &.is-focus {
      border-color: rgba($brand-1, 0.5);
      box-shadow: 0 0 0 3px rgba($brand-1, 0.12);
    }
    .el-input__inner { color: $text-1; &::placeholder { color: $text-3; } }
    .el-input__prefix .el-icon { color: $text-2; }
  }
}

.type-filter {
  display: flex;
  gap: 4px;
  padding: 3px;
  background: $bg-base;
  border: 1px solid $border;
  border-radius: 8px;
  flex-shrink: 0;
}

.type-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: $text-2;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover { color: $text-1; background: rgba($overlay-rgb, 0.04); }

  &.active {
    color: #fff;
    background: linear-gradient(135deg, rgba($brand-1, 0.9), rgba($brand-2, 0.9));
    box-shadow: 0 2px 8px rgba($brand-1, 0.3);
  }
}

.action-buttons {
  display: flex;
  gap: 10px;
  margin-left: auto;

  .is-loading { animation: rotate 1s linear infinite; }

  .btn-refresh {
    background: rgba($overlay-rgb, 0.04);
    border: 1px solid $border;
    color: $text-secondary;
    &:hover { border-color: $border-active; color: $text-primary; }
  }

  .btn-upload {
    background: linear-gradient(135deg, $brand-1, $brand-2);
    border: none;
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 500;
    box-shadow: 0 2px 8px rgba($brand-1, 0.3);
    &:hover { opacity: 0.92; }
  }
}

// ========== Cards Grid ==========
.cards-container {
  min-height: 320px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 14px;
}

.mat-card {
  border-radius: 10px;
  background: $bg-elevated;
  border: 1px solid $border;
  overflow: hidden;
  transition: all 0.2s ease;

  &:hover {
    border-color: rgba($brand-1, 0.4);
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);

    .mat-card-preview img { transform: scale(1.05); }
    .mat-card-delete-btn { opacity: 1; }
  }
}

.mat-card-preview {
  position: relative;
  aspect-ratio: 1;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba($overlay-rgb, 0.02), rgba(0, 0, 0, 0.1));

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 0.35s ease;
  }
}

.mat-card-video-fallback {
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

.mat-card-video-badge {
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
  z-index: 2;
}

.mat-card-storage-badge {
  position: absolute;
  top: 6px;
  right: 6px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  border: 1px solid rgba($overlay-rgb, 0.15);
  border-radius: 4px;
  color: #d1d5db;
  font-size: 11px;
  font-weight: 600;
  z-index: 2;
  letter-spacing: 0.3px;
  transition: opacity 0.15s ease;

  &.s3 {
    color: #fff;
    background: rgba($info-color, 0.7);
    border-color: rgba($info-color, 0.5);
  }
}

.mat-card:hover .mat-card-storage-badge {
  opacity: 0;
}

.mat-card-play-btn {
  position: absolute;
  inset: 0;
  margin: auto;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(8px);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 0 0 3px;
  opacity: 0.85;
  transition: all 0.2s ease;
  z-index: 2;

  &:hover {
    opacity: 1;
    transform: scale(1.08);
    background: linear-gradient(135deg, $brand-1, $brand-2);
  }
}

.mat-card-delete-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.15s ease;
  z-index: 3;

  &:hover {
    background: rgba($danger, 0.9);
    transform: scale(1.1);
  }
}

.mat-card-hover-info {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 5px 8px;
  display: flex;
  justify-content: flex-end;
  background: linear-gradient(180deg, transparent, rgba(0, 0, 0, 0.65));
  color: #fff;
  font-size: 10px;
  font-weight: 500;
  pointer-events: none;
  z-index: 1;
}

.mat-card-meta {
  padding: 8px 10px 10px;
}

.mat-card-name {
  font-size: 12px;
  color: $text-1;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.mat-card-stats {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: $text-3;
}

.mat-card-size, .mat-card-time {
  font-variant-numeric: tabular-nums;
}

.mat-card-dot {
  opacity: 0.6;
}

// ========== Empty ==========
.empty-data {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 80px 0;
  color: $text-2;
}

.empty-icon { color: $text-3; opacity: 0.5; margin-bottom: 6px; }
.empty-title { font-size: 14px; color: $text-1; font-weight: 500; }
.empty-desc { font-size: 12px; color: $text-3; }

// ========== Pagination ==========
.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 18px;
  padding: 14px;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;

  :deep(.el-pagination) {
    --el-pagination-bg-color: rgba($overlay-rgb, 0.04);
    --el-pagination-button-bg-color: rgba($overlay-rgb, 0.04);
    --el-pagination-button-color: #{$text-2};
    --el-pagination-hover-color: #{$brand-1};
    --el-pagination-button-disabled-bg-color: transparent;

    .btn-prev, .btn-next, .el-pager li {
      background: rgba($overlay-rgb, 0.04) !important;
      color: $text-2 !important;
      &:hover { color: $brand-1 !important; }
    }
    .el-pager li.is-active {
      background: linear-gradient(135deg, $brand-1, $brand-2) !important;
      color: #fff !important;
    }
  }
}

// ========== Preview Dialog ==========
.preview-dialog {
  :deep(.el-dialog) {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-dialog;
  }
  :deep(.el-dialog__header) {
    border-bottom: 1px solid $border;
    padding-bottom: 16px;
  }
  :deep(.el-dialog__title) { color: $text-primary; font-weight: 600; }
  :deep(.el-dialog__body) { background: rgba(0, 0, 0, 0.25); border-radius: 0 0 $radius-dialog $radius-dialog; }
}

.preview-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px 4px 4px;

  .video-preview, .image-preview {
    display: flex;
    justify-content: center;
    align-items: center;
    video, img {
      max-width: 100%;
      max-height: 65vh;
      border-radius: 8px;
      background: #000;
    }
  }
}

.preview-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  color: $text-secondary;
  font-size: 12px;
  padding-top: 6px;

  .preview-name { color: $text-primary; font-weight: 500; }
  .preview-size, .preview-time { color: $text-muted; font-variant-numeric: tabular-nums; }
}
</style>
