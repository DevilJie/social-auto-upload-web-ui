<template>
  <div class="image-uploader">
    <!-- Header with count -->
    <div class="uploader-header">
      <div class="uploader-title">
        <span class="title-dot"></span>
        <span>图片列表</span>
      </div>
      <span class="uploader-count">已上传 {{ images.length }}/{{ maxCount }} 张</span>
    </div>

    <!-- Image grid -->
    <div
      class="image-grid"
      ref="gridRef"
      :class="{ 'has-scroll': images.length > visibleRows * columns }"
    >
      <div
        v-for="(image, index) in images"
        :key="image.id || index"
        class="image-item"
        :data-index="index"
      >
        <!-- Image preview -->
        <div class="image-preview">
          <img :src="image.url" :alt="image.name" @error="onImageError($event, image)" />
          <!-- Uploading overlay -->
          <div v-if="image.uploading" class="uploading-overlay">
            <el-progress
              type="circle"
              :percentage="image.progress || 0"
              :width="48"
              :stroke-width="4"
              color="#8b5cf6"
            />
          </div>
          <!-- Hover overlay -->
          <div v-else class="image-overlay">
            <button class="overlay-btn" @click.stop="reUpload(index)" title="重新上传">
              <el-icon :size="16"><RefreshRight /></el-icon>
            </button>
            <button class="overlay-btn" @click.stop="openMaterialLibrary(index)" title="从素材库选择">
              <el-icon :size="16"><FolderOpened /></el-icon>
            </button>
            <button class="overlay-btn danger" @click.stop="removeImage(index)" title="删除">
              <el-icon :size="16"><Delete /></el-icon>
            </button>
          </div>
          <!-- Sort handle -->
          <div class="sort-handle" title="拖拽排序">
            <el-icon :size="14"><Rank /></el-icon>
          </div>
          <!-- Index badge -->
          <span class="index-badge">{{ index + 1 }}</span>
        </div>
        <div class="image-name" :title="image.name">{{ image.name }}</div>
      </div>

      <!-- Upload button -->
      <div
        v-if="images.length < maxCount"
        class="upload-trigger-wrapper"
      >
        <div
          class="upload-trigger"
          @click="triggerUpload"
          @dragover.prevent="onDragOver"
          @dragleave="onDragLeave"
          @drop.prevent="onDrop"
          :class="{ 'drag-over': isDragOver }"
        >
          <el-icon :size="28"><Plus /></el-icon>
          <span class="upload-text">上传图片</span>
          <span class="upload-hint">支持拖拽上传</span>
        </div>
        <div class="upload-placeholder-name"></div>
      </div>
    </div>

    <!-- Hidden file input -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      style="display: none"
      @change="onFileSelected"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete, RefreshRight, FolderOpened, Rank } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  maxCount: { type: Number, default: 35 },
  visibleRows: { type: Number, default: 3 },
  columns: { type: Number, default: 5 },
})

const emit = defineEmits(['update:modelValue', 'open-material-library'])

const fileInputRef = ref(null)
const gridRef = ref(null)
const isDragOver = ref(false)
let sortableInstance = null

// Local copy of images for two-way binding
const images = ref([])

// Sync with parent
watch(() => props.modelValue, (newVal) => {
  images.value = newVal || []
}, { immediate: true, deep: true })

// Emit changes back to parent
watch(images, (newVal) => {
  emit('update:modelValue', newVal)
}, { deep: true })

// Initialize SortableJS
onMounted(() => {
  initSortable()
})

onBeforeUnmount(() => {
  if (sortableInstance) {
    sortableInstance.destroy()
    sortableInstance = null
  }
})

function initSortable() {
  if (!gridRef.value) return

  sortableInstance = Sortable.create(gridRef.value, {
    animation: 200,
    handle: '.sort-handle',
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    dragClass: 'sortable-drag',
    filter: '.upload-trigger',
    onEnd(evt) {
      const { oldIndex, newIndex } = evt
      if (oldIndex === newIndex) return

      // Reorder the array
      const movedItem = images.value.splice(oldIndex, 1)[0]
      images.value.splice(newIndex, 0, movedItem)
    },
  })
}

// Trigger file input click
function triggerUpload() {
  fileInputRef.value?.click()
}

// Handle file selection
function onFileSelected(e) {
  const files = Array.from(e.target.files || [])
  if (!files.length) return

  const remainingSlots = props.maxCount - images.value.length
  const filesToUpload = files.slice(0, remainingSlots)

  if (files.length > remainingSlots) {
    ElMessage.warning(`最多只能上传 ${props.maxCount} 张图片，已自动截取前 ${remainingSlots} 张`)
  }

  filesToUpload.forEach(file => uploadFile(file))

  // Reset input
  e.target.value = ''
}

// Upload a single file
async function uploadFile(file) {
  const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp']
  if (!validTypes.includes(file.type)) {
    ElMessage.warning('不支持的图片格式')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 10MB')
    return
  }

  const placeholder = {
    id: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: file.name,
    url: URL.createObjectURL(file),
    stored_path: '',
    size: file.size,
    type: file.type,
    uploading: true,
    progress: 0,
  }
  images.value.push(placeholder)
  const index = images.value.length - 1

  try {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await materialsApi.upload(formData, (percent) => {
      if (images.value[index]) {
        images.value[index].progress = percent
      }
    })
    if (resp.code === 200) {
      const d = resp.data
      images.value[index] = {
        id: d.id,
        name: d.original_filename,
        url: getFileUrl(d.stored_path),
        stored_path: d.stored_path,
        size: d.file_size,
        type: d.mime_type,
        uploading: false,
        progress: 100,
      }
    }
  } catch {
    images.value.splice(index, 1)
    ElMessage.error('图片上传失败')
  }
}

// Remove image
function removeImage(index) {
  images.value.splice(index, 1)
}

// Re-upload image
function reUpload(index) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/jpeg,image/png,image/webp'
  input.onchange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Remove old image and upload new one
    images.value.splice(index, 1)
    uploadFile(file)
  }
  input.click()
}

// Open material library
function openMaterialLibrary(index) {
  emit('open-material-library', index)
}

// Set image from material library (called by parent)
function setImageFromLibrary(index, imageData) {
  if (index >= 0 && index < images.value.length) {
    images.value[index] = { ...images.value[index], ...imageData }
  } else if (images.value.length < props.maxCount) {
    images.value.push({
      id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
      ...imageData,
      uploading: false,
      progress: 100,
    })
  }
}

// Drag and drop handlers
function onDragOver(e) {
  e.preventDefault()
  isDragOver.value = true
}

function onDragLeave() {
  isDragOver.value = false
}

function onDrop(e) {
  e.preventDefault()
  isDragOver.value = false

  const files = Array.from(e.dataTransfer?.files || [])
  const imageFiles = files.filter(f => f.type.startsWith('image/'))

  if (!imageFiles.length) {
    ElMessage.warning('请拖入图片文件')
    return
  }

  const remainingSlots = props.maxCount - images.value.length
  const filesToUpload = imageFiles.slice(0, remainingSlots)

  if (imageFiles.length > remainingSlots) {
    ElMessage.warning(`最多只能上传 ${props.maxCount} 张图片，已自动截取前 ${remainingSlots} 张`)
  }

  filesToUpload.forEach(file => uploadFile(file))
}

// Image error handler
function onImageError(e, image) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0iIzIyMiIvPjx0ZXh0IHg9IjUwIiB5PSI1MCIgZm9udC1mYW1pbHk9IkFyaWFsIiBmb250LXNpemU9IjEyIiBmaWxsPSIjNjY2IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+5Zu+54mH5Yqg6L295aSx6LSlPC90ZXh0Pjwvc3ZnPg=='
}

// Expose methods for parent
defineExpose({
  setImageFromLibrary,
  triggerUpload,
})
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.image-uploader {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

// ===== Header =====
.uploader-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.uploader-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
}

.title-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: $gradient-brand;
}

.uploader-count {
  font-size: 12px;
  color: $text-muted;
  background: rgba(255, 255, 255, 0.06);
  padding: 4px 10px;
  border-radius: 12px;
}

// ===== Image Grid =====
.image-grid {
  display: grid;
  grid-template-columns: repeat(v-bind(columns), 1fr);
  gap: 12px;
  max-height: calc(v-bind(visibleRows) * 200px + (v-bind(visibleRows) - 1) * 12px);
  overflow-y: auto;
  padding: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.1) transparent;

  &::-webkit-scrollbar {
    width: 4px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 2px;
  }
  &::-webkit-scrollbar-track {
    background: transparent;
  }
}

// ===== Image Item =====
.image-item {
  position: relative;
  cursor: grab;

  &:active {
    cursor: grabbing;
  }
}

.image-preview {
  position: relative;
  aspect-ratio: 3 / 4;
  border-radius: $radius-sm;
  overflow: hidden;
  background: rgba(10, 10, 26, 0.6);
  border: 2px solid transparent;
  transition: all 0.3s ease;

  &:hover {
    border-color: rgba(139, 92, 246, 0.3);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);

    .image-overlay {
      opacity: 1;
    }

    .sort-handle {
      opacity: 1;
    }
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}

.image-name {
  margin-top: 6px;
  font-size: 11px;
  color: $text-secondary;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0 2px;
}

// ===== Uploading Overlay =====
.uploading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
}

// ===== Hover Overlay =====
.image-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  opacity: 0;
  transition: opacity $transition-fast;
}

.overlay-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: $transition-fast;
  backdrop-filter: blur(4px);

  &:hover {
    background: rgba(255, 255, 255, 0.2);
    border-color: rgba(255, 255, 255, 0.4);
    transform: scale(1.1);
  }

  &.danger:hover {
    background: rgba($danger-color, 0.6);
    border-color: rgba($danger-color, 0.8);
  }
}

// ===== Sort Handle =====
.sort-handle {
  position: absolute;
  top: 4px;
  left: 4px;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.6);
  color: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  opacity: 0;
  transition: opacity $transition-fast;
  backdrop-filter: blur(4px);

  &:hover {
    background: rgba(0, 0, 0, 0.8);
  }

  &:active {
    cursor: grabbing;
  }
}

// ===== Index Badge =====
.index-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.6);
  color: rgba(255, 255, 255, 0.9);
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}

// ===== Upload Trigger =====
.upload-trigger-wrapper {
  display: flex;
  flex-direction: column;
}

.upload-trigger {
  aspect-ratio: 3 / 4;
  border: 2px dashed rgba(255, 255, 255, 0.1);
  border-radius: $radius-sm;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: rgba(255, 255, 255, 0.02);
  color: $text-muted;

  &:hover {
    border-color: $brand-start;
    color: $brand-start;
    background: rgba($brand-start, 0.04);
    box-shadow: 0 0 20px rgba(139, 92, 246, 0.08);
  }

  &.drag-over {
    border-color: $brand-start;
    background: rgba($brand-start, 0.08);
    border-style: solid;
    box-shadow: 0 0 24px rgba(139, 92, 246, 0.15);

    .el-icon {
      color: $brand-start;
      transform: scale(1.2);
    }
  }

  .el-icon {
    transition: transform 0.3s ease;
  }

  .upload-text {
    font-size: 13px;
    font-weight: 600;
  }

  .upload-hint {
    font-size: 11px;
    color: $text-placeholder;
  }
}

.upload-placeholder-name {
  margin-top: 6px;
  height: 16px; // 与 .image-name 高度一致
}

// ===== SortableJS Ghost =====
.sortable-ghost {
  opacity: 0.4;
  border: 2px dashed $brand-start !important;
}

.sortable-chosen {
  box-shadow: 0 0 0 2px $brand-start;
}

.sortable-drag {
  transform: scale(1.05);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
}
</style>
