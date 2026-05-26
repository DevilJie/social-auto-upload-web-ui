<template>
  <el-dialog
    v-model="visible"
    title="编辑封面"
    width="960px"
    class="cover-editor-dialog"
    :close-on-click-modal="false"
    @closed="onClosed"
    append-to-body
  >

    <div class="cover-editor-body">
      <div class="editor-main">
        <!-- Crop area -->
        <div class="crop-area">
          <div v-if="!currentImageSrc" class="crop-empty">
            <el-icon :size="32"><Picture /></el-icon>
            <span>选择时间轴帧、上传图片或从素材库选取</span>
          </div>
          <div v-else class="crop-canvas-wrap" ref="canvasWrapRef">
            <canvas ref="cropCanvasRef" class="crop-canvas"></canvas>
            <div class="crop-selection" :style="cropSelectionStyle" @mousedown="startCropDrag">
              <div class="crop-handle top-left" data-handle="tl"></div>
              <div class="crop-handle top-right" data-handle="tr"></div>
              <div class="crop-handle bottom-left" data-handle="bl"></div>
              <div class="crop-handle bottom-right" data-handle="br"></div>
              <div class="crop-ratio-badge">{{ activeTab === 'portrait' ? '9:16' : '16:9' }}</div>
            </div>
          </div>
        </div>

        <!-- Timeline -->
        <div class="timeline-section" v-if="frames.length > 0">
          <div class="section-label-row">
            <span class="section-label-text">视频时间轴</span>
            <span class="section-label-hint">拖动选择帧画面</span>
          </div>
          <VideoTimeline :frames="frames" :duration="videoDuration" :extracting="extracting" v-model="selectedSecond" @update:modelValue="onTimelineSelect" />
        </div>

        <!-- Upload button -->
        <div class="editor-actions">
          <el-button size="small" @click="triggerLocalUpload">
            <el-icon><Upload /></el-icon> 上传图片
          </el-button>
        </div>
        <input ref="fileInputRef" type="file" accept="image/*" style="display: none" @change="onLocalFileSelected" />
      </div>

      <!-- Material library sidebar -->
      <div class="editor-sidebar">
        <div class="sidebar-header">
          <span class="sidebar-title">素材库</span>
          <span class="sidebar-count">{{ imageMaterials.length }}</span>
        </div>
        <div class="sidebar-scroll">
          <div class="sidebar-grid" v-if="imageMaterials.length > 0">
            <div v-for="mat in imageMaterials" :key="mat.id" class="sidebar-thumb" @click="onMaterialClick(mat)">
              <img :src="getMaterialUrl(mat)" :alt="mat.filename" />
              <div class="thumb-overlay">
                <el-icon :size="12"><Check /></el-icon>
              </div>
            </div>
          </div>
          <div v-else class="sidebar-empty">
            <el-icon :size="20"><Picture /></el-icon>
            <span>暂无图片素材</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="confirmCrop">
          <el-icon><Check /></el-icon> 确认裁剪
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Picture, Check } from '@element-plus/icons-vue'
import { http } from '@/utils/request'
import { materialApi } from '@/api/material'
import { frameApi } from '@/api/frame'
import VideoTimeline from './VideoTimeline.vue'

const props = defineProps({
  videoLandscape: { type: Object, default: null },
  videoPortrait: { type: Object, default: null },
  coverLandscape: { type: Object, default: null },
  coverPortrait: { type: Object, default: null },
  materials: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:coverLandscape', 'update:coverPortrait'])

const visible = ref(false)
const activeTab = ref('landscape')

const frames = ref([])
const videoDuration = ref(0)
const selectedSecond = ref(0)
const extracting = ref(false)
let pollingTimer = null

const cropCanvasRef = ref(null)
const canvasWrapRef = ref(null)
const fileInputRef = ref(null)
const cropImage = ref(null)
const currentImageSrc = ref('')
const cropDisplayScale = ref(1)
const cropRect = reactive({ x: 0, y: 0, w: 0, h: 0 })
const cropDragState = ref(null)

const tabState = reactive({
  landscape: { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } },
  portrait: { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } },
})

const imageMaterials = computed(() => {
  const imgExts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
  return props.materials.filter(m => imgExts.some(ext => m.filename.toLowerCase().endsWith(ext)))
})

const aspectRatio = computed(() => activeTab.value === 'portrait' ? 9 / 16 : 16 / 9)

const cropSelectionStyle = computed(() => ({
  left: cropRect.x * cropDisplayScale.value + 'px',
  top: cropRect.y * cropDisplayScale.value + 'px',
  width: cropRect.w * cropDisplayScale.value + 'px',
  height: cropRect.h * cropDisplayScale.value + 'px',
}))

function getMaterialUrl(mat) {
  return materialApi.getMaterialPreviewUrl(mat.file_path.split('/').pop())
}

function open(tab = 'landscape') {
  activeTab.value = tab
  visible.value = true
  loadFrames()
  loadTabState()
}

function currentVideoPath() {
  if (activeTab.value === 'landscape') {
    return props.videoLandscape?.path || props.videoPortrait?.path || ''
  }
  return props.videoPortrait?.path || props.videoLandscape?.path || ''
}

async function loadFrames() {
  const videoPath = currentVideoPath()
  if (!videoPath) return
  stopPolling()
  try {
    extracting.value = true
    const resp = await frameApi.extractFrames(videoPath)
    if (resp.data) {
      frames.value = resp.data.frames || []
      videoDuration.value = resp.data.duration || 0
      if (resp.data.status === 'processing') {
        startPolling(videoPath)
      } else {
        extracting.value = false
      }
    }
  } catch {
    extracting.value = false
  }
}

function startPolling(videoPath) {
  pollingTimer = setInterval(async () => {
    try {
      const resp = await frameApi.getFrames(videoPath)
      if (resp.data) {
        frames.value = resp.data.frames || []
        videoDuration.value = resp.data.duration || 0
        if (resp.data.status === 'done') {
          stopPolling()
          extracting.value = false
        }
      }
    } catch {
      stopPolling()
      extracting.value = false
    }
  }, 1500)
}

function stopPolling() {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

function loadTabState() {
  const state = tabState[activeTab.value]
  if (state.imageSrc) {
    currentImageSrc.value = state.imageSrc
    loadImageToCanvas(state.imageSrc)
  } else {
    const cover = activeTab.value === 'landscape' ? props.coverLandscape : props.coverPortrait
    if (cover?.url) {
      let src = cover.url
      if (cover._fromFrame !== undefined) {
        const videoPath = currentVideoPath()
        if (videoPath) {
          src = frameApi.getFrameImageUrl(videoPath, cover._fromFrame, false)
        }
      }
      currentImageSrc.value = src
      loadImageToCanvas(src)
    } else {
      currentImageSrc.value = ''
      cropImage.value = null
    }
  }
}

function saveTabState() {
  const state = tabState[activeTab.value]
  state.imageSrc = currentImageSrc.value
  state.cropRect = { ...cropRect }
}

function switchTab(tab) {
  saveTabState()
  activeTab.value = tab
  loadTabState()
}

function loadImageToCanvas(src) {
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    cropImage.value = img
    nextTick(() => initCropCanvas(img))
  }
  img.src = src
}

function initCropCanvas(img) {
  const canvas = cropCanvasRef.value
  if (!canvas) return
  const maxW = 520
  const maxH = 380
  const scale = Math.min(maxW / img.width, maxH / img.height, 1)
  cropDisplayScale.value = scale
  canvas.width = img.width * scale
  canvas.height = img.height * scale
  const ctx = canvas.getContext('2d')
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  const saved = tabState[activeTab.value].cropRect
  if (saved.w > 0 && saved.h > 0) {
    Object.assign(cropRect, saved)
    return
  }
  const ratio = aspectRatio.value
  let rw = img.width * 0.8
  let rh = rw / ratio
  if (rh > img.height * 0.8) { rh = img.height * 0.8; rw = rh * ratio }
  cropRect.x = (img.width - rw) / 2
  cropRect.y = (img.height - rh) / 2
  cropRect.w = rw
  cropRect.h = rh
}

function onTimelineSelect(seconds) {
  const videoPath = currentVideoPath()
  const url = frameApi.getFrameImageUrl(videoPath, seconds, false)
  currentImageSrc.value = url
  loadImageToCanvas(url)
}

function onMaterialClick(mat) {
  const url = getMaterialUrl(mat)
  currentImageSrc.value = url
  loadImageToCanvas(url)
}

function triggerLocalUpload() { fileInputRef.value?.click() }

function onLocalFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const url = URL.createObjectURL(file)
  currentImageSrc.value = url
  loadImageToCanvas(url)
  e.target.value = ''
}

function startCropDrag(e) {
  e.preventDefault()
  const handle = e.target.dataset.handle
  cropDragState.value = { type: handle || 'move', startX: e.clientX, startY: e.clientY, origRect: { ...cropRect } }
  const onMove = (ev) => {
    if (!cropDragState.value) return
    const dx = (ev.clientX - cropDragState.value.startX) / cropDisplayScale.value
    const dy = (ev.clientY - cropDragState.value.startY) / cropDisplayScale.value
    const orig = cropDragState.value.origRect
    const img = cropImage.value
    if (!img) return
    const ratio = aspectRatio.value
    const type = cropDragState.value.type
    const imgW = img.width, imgH = img.height
    const minSize = 60

    if (type === 'move') {
      cropRect.x = Math.max(0, Math.min(imgW - orig.w, orig.x + dx))
      cropRect.y = Math.max(0, Math.min(imgH - orig.h, orig.y + dy))
    } else {
      let newW, newX, newY
      if (type === 'br') {
        newW = Math.max(minSize, orig.w + dx)
        newX = orig.x
      } else if (type === 'bl') {
        newW = Math.max(minSize, orig.w - dx)
        newX = orig.x + orig.w - newW
      } else if (type === 'tr') {
        newW = Math.max(minSize, orig.w + dx)
        newX = orig.x
      } else if (type === 'tl') {
        newW = Math.max(minSize, orig.w - dx)
        newX = orig.x + orig.w - newW
      }
      let newH = newW / ratio

      if (newX < 0) { newX = 0; newW = orig.x + orig.w; newH = newW / ratio }
      if (newX + newW > imgW) { newW = imgW - newX; newH = newW / ratio }

      if (type === 'tl' || type === 'tr') {
        newY = orig.y + orig.h - newH
      } else {
        newY = orig.y
      }

      if (newY < 0) {
        newY = 0
        newH = orig.y + orig.h
        newW = newH * ratio
        if (type === 'tl' || type === 'bl') { newX = orig.x + orig.w - newW }
        if (newX < 0) { newX = 0; newW = Math.min(newW, imgW); newH = newW / ratio }
      }
      if (newY + newH > imgH) {
        newH = imgH - newY
        newW = newH * ratio
        if (type === 'tl' || type === 'bl') { newX = orig.x + orig.w - newW }
        if (newX < 0) { newX = 0; newW = Math.min(newW, imgW); newH = newW / ratio }
      }

      newW = Math.max(minSize, newW)
      newH = newW / ratio

      cropRect.x = newX
      cropRect.y = newY
      cropRect.w = newW
      cropRect.h = newH
    }
  }
  const onUp = () => {
    cropDragState.value = null
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

async function confirmCrop() {
  saveTabState()
  const img = cropImage.value
  if (!img) { ElMessage.warning('请先选择一张图片'); return }
  const targetW = activeTab.value === 'portrait' ? 1080 : 1920
  const targetH = activeTab.value === 'portrait' ? 1920 : 1080
  const offscreen = document.createElement('canvas')
  offscreen.width = targetW; offscreen.height = targetH
  const ctx = offscreen.getContext('2d')
  ctx.drawImage(img, cropRect.x, cropRect.y, cropRect.w, cropRect.h, 0, 0, targetW, targetH)
  const blob = await new Promise(resolve => offscreen.toBlob(resolve, 'image/jpeg', 0.92))
  if (!blob) { ElMessage.error('裁剪导出失败'); return }
  const formData = new FormData()
  formData.append('file', blob, `cover_${activeTab.value}_${Date.now()}.jpg`)
  try {
    const resp = await http.post('/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
    if (resp.code === 200) {
      const filePath = resp.data.filepath || resp.data
      const filename = filePath.split('/').pop()
      const coverData = { name: `cover_${activeTab.value}.jpg`, url: materialApi.getMaterialPreviewUrl(filename), path: filePath, size: blob.size, type: 'image/jpeg' }
      if (activeTab.value === 'portrait') emit('update:coverPortrait', coverData)
      else emit('update:coverLandscape', coverData)
      ElMessage.success('封面设置成功')
      visible.value = false
    } else { ElMessage.error(resp.msg || '上传失败') }
  } catch { ElMessage.error('封面上传失败') }
}

function onClosed() {
  stopPolling()
  frames.value = []; videoDuration.value = 0; currentImageSrc.value = ''; cropImage.value = null; extracting.value = false
  tabState.landscape = { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } }
  tabState.portrait = { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } }
}

defineExpose({ open })
</script>

<!-- Unscoped styles for Element Plus dialog overrides -->
<style lang="scss">
@use '@/styles/variables' as *;

.cover-editor-dialog {
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


.cover-editor-body {
  display: flex;
  gap: 0;
  padding: 20px 24px;
  max-height: 70vh;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.08) transparent;
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 2px; }
}

.editor-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;

  .section-label-text {
    font-size: 12px;
    font-weight: 500;
    color: $text-secondary;
  }
  .section-label-hint {
    font-size: 11px;
    color: $text-muted;
  }
}

.timeline-section {
  overflow: hidden;
}

.crop-area {
  background: $bg-base;
  border: 1px solid $border;
  border-radius: $radius-base;
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
}

.crop-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  color: $text-muted;
  font-size: 13px;
  padding: 30px;

  .el-icon { opacity: 0.3; }
}

.crop-canvas-wrap {
  position: relative;
  display: inline-block;
  line-height: 0;
}

.crop-canvas {
  display: block;
  max-width: 100%;
}

.crop-selection {
  position: absolute;
  border: 2px solid $brand-start;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55);
  cursor: move;
  transition: box-shadow 0.15s;
}

.crop-handle {
  position: absolute;
  width: 12px;
  height: 12px;
  background: #fff;
  border: 2px solid $brand-start;
  border-radius: 2px;
  z-index: 2;
  transition: transform 0.1s;

  &:hover { transform: scale(1.3); }

  &.top-left { top: -6px; left: -6px; cursor: nw-resize; }
  &.top-right { top: -6px; right: -6px; cursor: ne-resize; }
  &.bottom-left { bottom: -6px; left: -6px; cursor: sw-resize; }
  &.bottom-right { bottom: -6px; right: -6px; cursor: se-resize; }
}

.crop-ratio-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 2px 6px;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 3px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.8);
  pointer-events: none;
  font-family: monospace;
}

.editor-actions {
  display: flex;
  gap: 8px;

  :deep(.el-button) {
    background: rgba(255, 255, 255, 0.04);
    border-color: $border;
    color: $text-secondary;

    &:hover {
      border-color: $border-active;
      color: $brand-start;
      background: rgba($brand-start, 0.06);
    }
  }
}

// ===== Sidebar =====
.editor-sidebar {
  width: 160px;
  flex-shrink: 0;
  border-left: 1px solid $border;
  margin-left: 20px;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;

  .sidebar-title {
    font-size: 12px;
    font-weight: 600;
    color: $text-secondary;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .sidebar-count {
    font-size: 10px;
    color: $text-muted;
    background: rgba(255, 255, 255, 0.06);
    padding: 1px 6px;
    border-radius: 8px;
  }
}

.sidebar-scroll {
  flex: 1;
  overflow-y: auto;
  max-height: 420px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.08) transparent;
  &::-webkit-scrollbar { width: 3px; }
  &::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 2px; }
}

.sidebar-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.sidebar-thumb {
  aspect-ratio: 1;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: $transition-fast;
  position: relative;

  img { width: 100%; height: 100%; object-fit: cover; display: block; }

  .thumb-overlay {
    position: absolute;
    inset: 0;
    background: rgba($brand-start, 0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff;
    opacity: 0;
    transition: opacity 0.15s;
  }

  &:hover {
    border-color: rgba($brand-start, 0.5);
    .thumb-overlay { opacity: 1; }
  }
}

.sidebar-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  color: $text-muted;
  font-size: 12px;
  padding: 30px 0;
  text-align: center;

  .el-icon { opacity: 0.25; }
}

// ===== Footer =====
.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;

  :deep(.el-button--primary) {
    background: $gradient-brand;
    border: none;
    &:hover { opacity: 0.9; }
  }
}
</style>
