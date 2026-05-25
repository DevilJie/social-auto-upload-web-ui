<template>
  <el-dialog
    v-model="visible"
    title="编辑封面"
    width="900px"
    class="cover-editor-dialog"
    :close-on-click-modal="false"
    @closed="onClosed"
  >
    <div class="cover-editor-tabs">
      <button :class="['tab-btn', { active: activeTab === 'landscape' }]" @click="switchTab('landscape')">横版 16:9</button>
      <button :class="['tab-btn', { active: activeTab === 'portrait' }]" @click="switchTab('portrait')">竖版 9:16</button>
    </div>

    <div class="cover-editor-body">
      <div class="editor-main">
        <div class="crop-area">
          <div v-if="!currentImageSrc" class="crop-empty">
            <span>选择时间轴帧、上传图片或从右侧素材库选取</span>
          </div>
          <div v-else class="crop-canvas-wrap" ref="canvasWrapRef">
            <canvas ref="cropCanvasRef" class="crop-canvas"></canvas>
            <div class="crop-selection" :style="cropSelectionStyle" @mousedown="startCropDrag">
              <div class="crop-handle top-left" data-handle="tl"></div>
              <div class="crop-handle top-right" data-handle="tr"></div>
              <div class="crop-handle bottom-left" data-handle="bl"></div>
              <div class="crop-handle bottom-right" data-handle="br"></div>
            </div>
          </div>
          <div v-if="currentImageSrc" class="crop-info">
            <span>{{ activeTab === 'portrait' ? '9:16' : '16:9' }}</span>
          </div>
        </div>

        <div class="timeline-section" v-if="frames.length > 0">
          <VideoTimeline :frames="frames" :duration="videoDuration" v-model="selectedSecond" @update:modelValue="onTimelineSelect" />
        </div>

        <div class="editor-upload">
          <el-button size="small" @click="triggerLocalUpload">
            <el-icon><Upload /></el-icon> 上传图片
          </el-button>
          <input ref="fileInputRef" type="file" accept="image/*" style="display: none" @change="onLocalFileSelected" />
        </div>
      </div>

      <div class="editor-sidebar">
        <div class="sidebar-title">素材库</div>
        <div class="sidebar-grid" v-if="imageMaterials.length > 0">
          <div v-for="mat in imageMaterials" :key="mat.id" class="sidebar-thumb" @click="onMaterialClick(mat)">
            <img :src="getMaterialUrl(mat)" :alt="mat.filename" />
          </div>
        </div>
        <div v-else class="sidebar-empty">暂无图片素材</div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer-right">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="confirmCrop">确认</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
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
  try { await frameApi.extractFrames(videoPath) } catch {}
  const poll = async (retries = 30) => {
    for (let i = 0; i < retries; i++) {
      try {
        const resp = await frameApi.getFramesStatus(videoPath)
        if (resp.data?.status === 'done') break
      } catch {}
      await new Promise(r => setTimeout(r, 1000))
    }
  }
  await poll()
  try {
    const resp = await frameApi.getFrames(videoPath)
    if (resp.data) {
      frames.value = resp.data.frames || []
      videoDuration.value = resp.data.duration || 0
    }
  } catch {}
}

function loadTabState() {
  const state = tabState[activeTab.value]
  if (state.imageSrc) {
    currentImageSrc.value = state.imageSrc
    loadImageToCanvas(state.imageSrc)
  } else {
    const cover = activeTab.value === 'landscape' ? props.coverLandscape : props.coverPortrait
    if (cover?.url) {
      currentImageSrc.value = cover.url
      loadImageToCanvas(cover.url)
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
    if (type === 'move') {
      cropRect.x = Math.max(0, Math.min(img.width - orig.w, orig.x + dx))
      cropRect.y = Math.max(0, Math.min(img.height - orig.h, orig.y + dy))
    } else {
      let newW = orig.w, newH = orig.h
      if (type === 'br') { newW = orig.w + dx; newH = newW / ratio }
      else if (type === 'bl') { newW = orig.w - dx; newH = newW / ratio }
      else if (type === 'tr') { newW = orig.w + dx; newH = newW / ratio }
      else if (type === 'tl') { newW = orig.w - dx; newH = newW / ratio }
      newW = Math.max(60, newW); newH = newW / ratio
      if (type === 'tl' || type === 'bl') cropRect.x = orig.x + orig.w - newW
      if (type === 'tl' || type === 'tr') cropRect.y = orig.y + orig.h - newH
      cropRect.x = Math.max(0, cropRect.x); cropRect.y = Math.max(0, cropRect.y)
      if (cropRect.x + newW > img.width) newW = img.width - cropRect.x
      if (cropRect.y + newH > img.height) newH = img.height - cropRect.y
      newH = newW / ratio
      cropRect.w = newW; cropRect.h = newH
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
  frames.value = []; videoDuration.value = 0; currentImageSrc.value = ''; cropImage.value = null
  tabState.landscape = { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } }
  tabState.portrait = { imageSrc: '', cropRect: { x: 0, y: 0, w: 0, h: 0 } }
}

defineExpose({ open })
</script>

<style scoped lang="scss">
.cover-editor-tabs { display: flex; gap: 8px; margin-bottom: 16px; }
.tab-btn { padding: 6px 16px; border: 1px solid #dcdfe6; border-radius: 4px; background: #fff; cursor: pointer; font-size: 14px;
  &.active { background: var(--el-color-primary); color: #fff; border-color: var(--el-color-primary); } }
.cover-editor-body { display: flex; gap: 16px; }
.editor-main { flex: 1; display: flex; flex-direction: column; gap: 12px; }
.crop-area { background: #111; border-radius: 4px; min-height: 240px; display: flex; align-items: center; justify-content: center; }
.crop-empty { color: #999; font-size: 13px; }
.crop-canvas-wrap { position: relative; display: inline-block; }
.crop-canvas { display: block; max-width: 100%; }
.crop-selection { position: absolute; border: 2px solid var(--el-color-primary); box-shadow: 0 0 0 9999px rgba(0,0,0,0.5); cursor: move; }
.crop-handle { position: absolute; width: 10px; height: 10px; background: #fff; border: 1px solid var(--el-color-primary); border-radius: 50%;
  &.top-left { top: -5px; left: -5px; cursor: nw-resize; }
  &.top-right { top: -5px; right: -5px; cursor: ne-resize; }
  &.bottom-left { bottom: -5px; left: -5px; cursor: sw-resize; }
  &.bottom-right { bottom: -5px; right: -5px; cursor: se-resize; } }
.crop-info { text-align: center; color: #999; font-size: 12px; margin-top: 4px; }
.editor-upload { display: flex; gap: 8px; }
.editor-sidebar { width: 180px; border-left: 1px solid #eee; padding-left: 12px; overflow-y: auto; max-height: 420px; }
.sidebar-title { font-size: 13px; font-weight: 500; margin-bottom: 8px; color: #666; }
.sidebar-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.sidebar-thumb { aspect-ratio: 1; border-radius: 4px; overflow: hidden; cursor: pointer; border: 2px solid transparent;
  &:hover { border-color: var(--el-color-primary); }
  img { width: 100%; height: 100%; object-fit: cover; } }
.sidebar-empty { color: #999; font-size: 12px; text-align: center; padding: 20px 0; }
</style>
