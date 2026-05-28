<template>
  <el-dialog
    v-model="visible"
    title="选择素材"
    width="860px"
    class="material-select-dialog"
    :close-on-click-modal="false"
    destroy-on-close
    @closed="onClosed"
    append-to-body
  >
    <!-- Toolbar: search + filter -->
    <div class="msd-toolbar">
      <el-input
        v-model="searchQuery"
        placeholder="搜索文件名..."
        clearable
        class="msd-search"
        :prefix-icon="Search"
      />
      <el-radio-group v-model="typeFilter" class="msd-filter">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="image">图片</el-radio-button>
        <el-radio-button value="video">视频</el-radio-button>
      </el-radio-group>
    </div>

    <!-- Material grid -->
    <div class="msd-body" v-loading="loading">
      <div v-if="filteredMaterials.length > 0" class="msd-grid">
        <div
          v-for="mat in filteredMaterials"
          :key="mat.id"
          class="msd-card"
          :class="{ selected: selectedId === mat.id }"
          @click="selectedId = mat.id"
        >
          <!-- Preview -->
          <div class="msd-card-preview">
            <img
              v-if="isImage(mat)"
              :src="getMaterialUrl(mat)"
              :alt="mat.filename"
              loading="lazy"
              @error="onImageError"
            />
            <div v-else class="msd-card-video-icon">
              <el-icon :size="28"><VideoPlay /></el-icon>
            </div>
            <!-- Selected check -->
            <div class="msd-card-check" v-if="selectedId === mat.id">
              <el-icon :size="16"><Check /></el-icon>
            </div>
          </div>
          <!-- Info -->
          <div class="msd-card-info">
            <span class="msd-card-name" :title="mat.filename">{{ mat.filename }}</span>
            <span class="msd-card-meta">{{ formatSize(mat.filesize) }}</span>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-else class="msd-empty">
        <el-icon :size="40"><Picture /></el-icon>
        <span>{{ loading ? '加载中...' : '暂无匹配素材' }}</span>
      </div>
    </div>

    <!-- Footer -->
    <template #footer>
      <div class="msd-footer">
        <span class="msd-footer-count" v-if="selectedId">已选择 1 个素材</span>
        <span class="msd-footer-count" v-else>请选择素材</span>
        <div class="msd-footer-actions">
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" :disabled="!selectedId" @click="confirmSelect">确定</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, VideoPlay, Check, Picture } from '@element-plus/icons-vue'
import { materialApi } from '@/api/material'

const props = defineProps({
  /** 'all' | 'image' | 'video' - 默认过滤类型 */
  filterType: { type: String, default: 'all' },
})

const emit = defineEmits(['select'])

const visible = ref(false)
const loading = ref(false)
const materials = ref([])
const searchQuery = ref('')
const typeFilter = ref('all')
const selectedId = ref(null)

// File extension sets
const imageExts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
const videoExts = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.m4v']

function isImage(mat) {
  const name = (mat.filename || '').toLowerCase()
  return imageExts.some(ext => name.endsWith(ext))
}

function isVideo(mat) {
  const name = (mat.filename || '').toLowerCase()
  return videoExts.some(ext => name.endsWith(ext))
}

const filteredMaterials = computed(() => {
  let list = materials.value
  // Type filter
  if (typeFilter.value === 'image') {
    list = list.filter(m => isImage(m))
  } else if (typeFilter.value === 'video') {
    list = list.filter(m => isVideo(m))
  }
  // Search filter
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(m => (m.filename || '').toLowerCase().includes(q))
  }
  return list
})

function getMaterialUrl(mat) {
  const filename = (mat.file_path || '').split('/').pop() || mat.filename
  return materialApi.getMaterialPreviewUrl(filename)
}

function formatSize(mb) {
  if (!mb && mb !== 0) return ''
  if (mb < 1) return `${(mb * 1024).toFixed(0)} KB`
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  return `${(mb / 1024).toFixed(1)} GB`
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0iIzIyMiIvPjx0ZXh0IHg9IjUwIiB5PSI1MCIgZm9udC1mYW1pbHk9IkFyaWFsIiBmb250LXNpemU9IjEyIiBmaWxsPSIjNjY2IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+5Zu+54mH5Yqg6L295aSx6LSlPC90ZXh0Pjwvc3ZnPg=='
}

async function open() {
  visible.value = true
  typeFilter.value = props.filterType || 'all'
  searchQuery.value = ''
  selectedId.value = null
  await loadMaterials()
}

async function loadMaterials() {
  loading.value = true
  try {
    const resp = await materialApi.getAllMaterials()
    if (resp.code === 200) {
      materials.value = resp.data || []
    } else {
      ElMessage.error('获取素材列表失败')
    }
  } catch (err) {
    console.error('获取素材列表出错:', err)
    ElMessage.error('获取素材列表失败')
  } finally {
    loading.value = false
  }
}

function confirmSelect() {
  if (!selectedId.value) {
    ElMessage.warning('请选择一个素材')
    return
  }
  const material = materials.value.find(m => m.id === selectedId.value)
  if (!material) {
    ElMessage.warning('所选素材不存在')
    return
  }
  // Build the result object compatible with the rest of the app
  const filename = (material.file_path || '').split('/').pop() || material.filename
  const result = {
    id: material.id,
    name: material.filename,
    url: materialApi.getMaterialPreviewUrl(filename),
    path: material.file_path,
    size: (material.filesize || 0) * 1024 * 1024,
    type: isImage(material) ? 'image/jpeg' : 'video/mp4',
  }
  emit('select', result)
  visible.value = false
}

function onClosed() {
  searchQuery.value = ''
  selectedId.value = null
  materials.value = []
}

defineExpose({ open })
</script>

<style lang="scss">
@use '@/styles/variables' as *;

.material-select-dialog {
  .el-dialog {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-dialog;
    box-shadow: 0 25px 60px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.03);
    overflow: hidden;
  }
  .el-dialog__header {
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), transparent);
    border-bottom: 1px solid $border;
    padding: 18px 24px;
    margin-right: 0;
    .el-dialog__title {
      color: $text-primary;
      font-size: 16px;
      font-weight: 600;
    }
    .el-dialog__headerbtn .el-dialog__close {
      color: $text-muted;
      &:hover { color: $text-primary; }
    }
  }
  .el-dialog__body {
    padding: 0;
  }
  .el-dialog__footer {
    border-top: 1px solid $border;
    padding: 14px 24px;
    background: rgba(0, 0, 0, 0.15);
  }
}
</style>

<style scoped lang="scss">
@use '@/styles/variables' as *;

// ===== Toolbar =====
.msd-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 24px 0;
}

.msd-search {
  flex: 1;
  max-width: 320px;

  :deep(.el-input__wrapper) {
    background: $bg-base;
    border: 1px solid $border;
    border-radius: $radius-sm;
    box-shadow: none;
    &:hover { border-color: $border-active; }
    &.is-focus { border-color: $brand-start; box-shadow: 0 0 0 2px rgba($brand-start, 0.15); }
    .el-input__inner { color: $text-primary; }
    .el-input__prefix .el-icon { color: $text-muted; }
  }
}

.msd-filter {
  :deep(.el-radio-button__inner) {
    background: $bg-base;
    border-color: $border;
    color: $text-secondary;
    font-size: 12px;
    padding: 6px 14px;
    &:hover { color: $brand-start; }
  }
  :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
    background: rgba($brand-start, 0.15);
    border-color: $brand-start;
    color: $brand-start;
    box-shadow: none;
  }
}

// ===== Body =====
.msd-body {
  padding: 16px 24px 8px;
  min-height: 320px;
  max-height: 55vh;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.08) transparent;

  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 2px; }
}

// ===== Grid =====
.msd-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

// ===== Card =====
.msd-card {
  border-radius: $radius-sm;
  border: 2px solid transparent;
  background: $bg-base;
  overflow: hidden;
  cursor: pointer;
  transition: $transition-fast;

  &:hover {
    border-color: rgba($brand-start, 0.4);
    .msd-card-preview img { transform: scale(1.03); }
  }

  &.selected {
    border-color: $brand-start;
    box-shadow: 0 0 0 2px rgba($brand-start, 0.2);
  }
}

.msd-card-preview {
  aspect-ratio: 1;
  overflow: hidden;
  position: relative;
  background: rgba(255, 255, 255, 0.02);

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    transition: transform 0.25s ease;
  }
}

.msd-card-video-icon {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: $text-muted;
  background: rgba(255, 255, 255, 0.02);
}

.msd-card-check {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: $brand-start;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

.msd-card-info {
  padding: 6px 8px 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.msd-card-name {
  font-size: 11px;
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.msd-card-meta {
  font-size: 10px;
  color: $text-muted;
}

// ===== Empty =====
.msd-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: $text-muted;
  font-size: 13px;
  padding: 60px 0;

  .el-icon { opacity: 0.3; }
}

// ===== Footer =====
.msd-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.msd-footer-count {
  font-size: 12px;
  color: $text-muted;
}

.msd-footer-actions {
  display: flex;
  gap: 10px;

  :deep(.el-button--primary) {
    background: $gradient-brand;
    border: none;
    &:hover { opacity: 0.9; }
    &.is-disabled {
      opacity: 0.4;
      background: $gradient-brand;
    }
  }
}
</style>
