<template>
  <el-dialog
    v-model="visible"
    :show-close="false"
    :close-on-click-modal="true"
    :close-on-press-escape="true"
    class="image-preview-dialog"
    width="90vw"
    top="3vh"
    destroy-on-close
    @closed="onClosed"
    append-to-body
  >
    <!-- Header -->
    <template #header>
      <div class="preview-header">
        <span class="preview-title">{{ currentIndex + 1 }} / {{ images.length }}</span>
        <div class="preview-header-actions">
          <button class="header-btn" @click="zoomOut" title="缩小">
            <el-icon :size="18"><ZoomOut /></el-icon>
          </button>
          <span class="zoom-label">{{ Math.round(scale * 100) }}%</span>
          <button class="header-btn" @click="zoomIn" title="放大">
            <el-icon :size="18"><ZoomIn /></el-icon>
          </button>
          <span class="header-divider"></span>
          <button class="header-btn" @click="rotateLeft" title="向左旋转">
            <el-icon :size="18"><RefreshLeft /></el-icon>
          </button>
          <button class="header-btn" @click="rotateRight" title="向右旋转">
            <el-icon :size="18"><RefreshRight /></el-icon>
          </button>
          <span class="header-divider"></span>
          <button class="header-btn" @click="toggleFullscreen" :title="isFullscreen ? '退出全屏' : '全屏'">
            <el-icon :size="18"><FullScreen /></el-icon>
          </button>
          <button class="header-btn close-btn" @click="visible = false" title="关闭">
            <el-icon :size="18"><Close /></el-icon>
          </button>
        </div>
      </div>
    </template>

    <!-- Body: image viewer -->
    <div class="preview-body" ref="bodyRef">
      <!-- Left arrow -->
      <button
        class="nav-arrow left"
        :class="{ disabled: currentIndex <= 0 }"
        :disabled="currentIndex <= 0"
        @click="prev"
      >
        <el-icon :size="28"><ArrowLeft /></el-icon>
      </button>

      <!-- Image area -->
      <div
        class="image-container"
        ref="containerRef"
        @wheel.prevent="onWheel"
        @mousedown="startDrag"
      >
        <img
          v-if="currentImageSrc"
          :src="currentImageSrc"
          :style="imageStyle"
          class="preview-image"
          draggable="false"
          @load="onImageLoad"
          @error="onImageError"
        />
        <div v-else class="preview-empty">
          <el-icon :size="48"><Picture /></el-icon>
          <span>暂无图片</span>
        </div>
      </div>

      <!-- Right arrow -->
      <button
        class="nav-arrow right"
        :class="{ disabled: currentIndex >= images.length - 1 }"
        :disabled="currentIndex >= images.length - 1"
        @click="next"
      >
        <el-icon :size="28"><ArrowRight /></el-icon>
      </button>
    </div>

    <!-- Bottom indicator dots -->
    <div class="preview-indicators" v-if="images.length > 1">
      <span
        v-for="(img, index) in images"
        :key="img.id || index"
        class="indicator-dot"
        :class="{ active: index === currentIndex }"
        @click="goTo(index)"
      ></span>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  ZoomIn, ZoomOut, RefreshLeft, RefreshRight,
  FullScreen, Close, ArrowLeft, ArrowRight, Picture
} from '@element-plus/icons-vue'

const props = defineProps({
  images: { type: Array, default: () => [] },
  initialIndex: { type: Number, default: 0 },
})

const emit = defineEmits(['change', 'closed'])

const visible = ref(false)
const currentIndex = ref(0)
const scale = ref(1)
const rotation = ref(0)
const translateX = ref(0)
const translateY = ref(0)
const isFullscreen = ref(false)

const bodyRef = ref(null)
const containerRef = ref(null)

// Drag state
const isDragging = ref(false)
let dragStartX = 0
let dragStartY = 0
let dragStartTranslateX = 0
let dragStartTranslateY = 0

const MIN_SCALE = 0.1
const MAX_SCALE = 10
const ZOOM_STEP = 0.15

// Computed
const currentImageSrc = computed(() => {
  const img = props.images[currentIndex.value]
  return img?.url || img?.src || ''
})

const imageStyle = computed(() => ({
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value}) rotate(${rotation.value}deg)`,
  transition: isDragging.value ? 'none' : 'transform 0.2s ease',
}))

// Methods
function open(index = 0) {
  currentIndex.value = Math.max(0, Math.min(index, props.images.length - 1))
  resetTransform()
  visible.value = true
}

function close() {
  visible.value = false
}

function resetTransform() {
  scale.value = 1
  rotation.value = 0
  translateX.value = 0
  translateY.value = 0
}

function prev() {
  if (currentIndex.value > 0) {
    currentIndex.value--
    resetTransform()
    emit('change', currentIndex.value)
  }
}

function next() {
  if (currentIndex.value < props.images.length - 1) {
    currentIndex.value++
    resetTransform()
    emit('change', currentIndex.value)
  }
}

function goTo(index) {
  if (index >= 0 && index < props.images.length && index !== currentIndex.value) {
    currentIndex.value = index
    resetTransform()
    emit('change', currentIndex.value)
  }
}

function zoomIn() {
  scale.value = Math.min(MAX_SCALE, scale.value + ZOOM_STEP)
}

function zoomOut() {
  scale.value = Math.max(MIN_SCALE, scale.value - ZOOM_STEP)
}

function rotateLeft() {
  rotation.value -= 90
}

function rotateRight() {
  rotation.value += 90
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().then(() => {
      isFullscreen.value = true
    }).catch(() => {})
  } else {
    document.exitFullscreen().then(() => {
      isFullscreen.value = false
    }).catch(() => {})
  }
}

function onWheel(e) {
  const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP
  const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale.value + delta))

  // Zoom towards cursor position
  if (containerRef.value) {
    const rect = containerRef.value.getBoundingClientRect()
    const cursorX = e.clientX - rect.left - rect.width / 2
    const cursorY = e.clientY - rect.top - rect.height / 2
    const scaleRatio = newScale / scale.value
    translateX.value = cursorX - scaleRatio * (cursorX - translateX.value)
    translateY.value = cursorY - scaleRatio * (cursorY - translateY.value)
  }

  scale.value = newScale
}

function startDrag(e) {
  if (e.button !== 0) return
  isDragging.value = true
  dragStartX = e.clientX
  dragStartY = e.clientY
  dragStartTranslateX = translateX.value
  dragStartTranslateY = translateY.value

  const onMove = (ev) => {
    if (!isDragging.value) return
    translateX.value = dragStartTranslateX + (ev.clientX - dragStartX)
    translateY.value = dragStartTranslateY + (ev.clientY - dragStartY)
  }

  const onUp = () => {
    isDragging.value = false
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

function onImageLoad() {
  // Image loaded successfully
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAwIiBoZWlnaHQ9IjMwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iNDAwIiBoZWlnaHQ9IjMwMCIgZmlsbD0iIzIyMiIvPjx0ZXh0IHg9IjIwMCIgeT0iMTUwIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTgiIGZpbGw9IiM2NjYiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj7lm77niYfliqDovb3lpLHotJU8L3RleHQ+PC9zdmc+'
}

function onKeyDown(e) {
  if (!visible.value) return
  switch (e.key) {
    case 'ArrowLeft':
      e.preventDefault()
      prev()
      break
    case 'ArrowRight':
      e.preventDefault()
      next()
      break
    case 'ArrowUp':
    case '+':
    case '=':
      e.preventDefault()
      zoomIn()
      break
    case 'ArrowDown':
    case '-':
      e.preventDefault()
      zoomOut()
      break
    case '0':
      e.preventDefault()
      resetTransform()
      break
    case 'Escape':
      close()
      break
  }
}

function onClosed() {
  resetTransform()
  emit('closed')
}

function onFullscreenChange() {
  if (!document.fullscreenElement) {
    isFullscreen.value = false
  }
}

// Lifecycle
watch(visible, (val) => {
  if (val) {
    window.addEventListener('keydown', onKeyDown)
    document.addEventListener('fullscreenchange', onFullscreenChange)
  } else {
    window.removeEventListener('keydown', onKeyDown)
    document.removeEventListener('fullscreenchange', onFullscreenChange)
  }
})

// Sync initial index when opened externally
watch(() => props.initialIndex, (val) => {
  if (val >= 0 && val < props.images.length) {
    currentIndex.value = val
  }
})

defineExpose({ open, close })
</script>

<style lang="scss">
@use '@/styles/variables' as *;

.image-preview-dialog {
  .el-dialog {
    background: rgba(0, 0, 0, 0.92);
    border: 1px solid rgba($overlay-rgb, 0.08);
    border-radius: $radius-dialog;
    box-shadow: 0 25px 80px rgba(0, 0, 0, 0.7);
    overflow: hidden;
  }

  .el-dialog__header {
    background: transparent;
    border-bottom: 1px solid rgba($overlay-rgb, 0.06);
    padding: 12px 20px;
    margin-right: 0;
  }

  .el-dialog__body {
    padding: 0;
  }

  .el-dialog__footer {
    padding: 0;
  }
}
</style>

<style scoped lang="scss">
@use '@/styles/variables' as *;

// ===== Header =====
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.preview-title {
  color: rgba($overlay-rgb, 0.85);
  font-size: 14px;
  font-weight: 500;
  user-select: none;
}

.preview-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-btn {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: rgba($overlay-rgb, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: $transition-fast;

  &:hover {
    background: rgba($overlay-rgb, 0.1);
    color: #fff;
  }

  &.close-btn:hover {
    background: rgba($danger-color, 0.3);
    color: #ef4444;
  }
}

.zoom-label {
  font-size: 12px;
  color: rgba($overlay-rgb, 0.5);
  min-width: 40px;
  text-align: center;
  user-select: none;
  font-family: monospace;
}

.header-divider {
  width: 1px;
  height: 16px;
  background: rgba($overlay-rgb, 0.1);
  margin: 0 4px;
}

// ===== Body =====
.preview-body {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  height: 75vh;
  overflow: hidden;
  user-select: none;
}

// ===== Navigation arrows =====
.nav-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 1px solid rgba($overlay-rgb, 0.15);
  background: rgba(0, 0, 0, 0.5);
  color: rgba($overlay-rgb, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: $transition-base;
  backdrop-filter: blur(8px);

  &:hover:not(:disabled) {
    background: rgba($brand-start, 0.3);
    border-color: rgba($brand-start, 0.5);
    color: #fff;
  }

  &.disabled,
  &:disabled {
    opacity: 0.2;
    cursor: not-allowed;
  }

  &.left {
    left: 20px;
  }

  &.right {
    right: 20px;
  }
}

// ===== Image container =====
.image-container {
  flex: 1;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: grab;

  &:active {
    cursor: grabbing;
  }
}

.preview-image {
  max-width: 90%;
  max-height: 90%;
  object-fit: contain;
  border-radius: 4px;
  will-change: transform;
}

.preview-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: rgba($overlay-rgb, 0.3);

  .el-icon {
    opacity: 0.5;
  }

  span {
    font-size: 14px;
  }
}

// ===== Bottom indicators =====
.preview-indicators {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 16px;
  flex-wrap: wrap;
}

.indicator-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba($overlay-rgb, 0.2);
  cursor: pointer;
  transition: $transition-fast;

  &:hover {
    background: rgba($overlay-rgb, 0.4);
  }

  &.active {
    width: 20px;
    border-radius: 4px;
    background: $brand-start;
  }
}
</style>
