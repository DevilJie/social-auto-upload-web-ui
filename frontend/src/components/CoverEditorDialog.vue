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
          <div
            v-else
            class="crop-canvas-wrap"
            ref="canvasWrapRef"
            @wheel.prevent="onWheel"
            @pointerdown="onPointerDown"
          >
            <canvas ref="cropCanvasRef" class="crop-canvas" :style="canvasStyle"></canvas>
            <div class="crop-selection" :style="cropSelectionStyle">
              <div class="crop-ratio-badge">{{ currentRatioLabel }}</div>
            </div>
            <div class="crop-hint">滚轮缩放 · 拖动移动</div>
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

        <!-- Upload + Material Library buttons -->
        <div class="editor-actions">
          <button class="action-btn action-upload" @click="triggerLocalUpload">
            <el-icon :size="18"><Upload /></el-icon>
            <span>上传图片</span>
          </button>
          <button class="action-btn action-material" @click="materialSelectRef?.open()">
            <el-icon :size="18"><PictureFilled /></el-icon>
            <span>素材库</span>
          </button>
        </div>
        <input ref="fileInputRef" type="file" accept="image/*" style="display: none" @change="onLocalFileSelected" />
        <MaterialSelectDialog ref="materialSelectRef" filter-type="image" @select="onMaterialSelect" />
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
import { Upload, Picture, PictureFilled, Check } from '@element-plus/icons-vue'
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
import { frameApi } from '@/api/frame'
import VideoTimeline from './VideoTimeline.vue'
import MaterialSelectDialog from './MaterialSelectDialog.vue'

const props = defineProps({
  videoLandscape: { type: Object, default: null },
  videoPortrait: { type: Object, default: null },
  coverLandscape: { type: Object, default: null },
  coverPortrait: { type: Object, default: null },
  portraitRatio: { type: String, default: '9:16' },
  landscapeRatio: { type: String, default: '16:9' },
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
const materialSelectRef = ref(null)
const cropImage = ref(null)
const currentImageSrc = ref('')
const cropDisplayScale = ref(1)
// 裁剪框固定（居中、撑满最大、锁定比例）；图片可缩放可平移
const cropRect = reactive({ x: 0, y: 0, w: 0, h: 0 }) // 图片像素空间的裁剪源矩形
const imgZoom = ref(1)     // 图片在 canvas 上的额外缩放（>=1）
const imgOffset = reactive({ x: 0, y: 0 }) // 图片在 canvas 显示像素空间的偏移
const dragState = ref(null)

const tabState = reactive({
  landscape: { imageSrc: '', zoom: 1, offset: { x: 0, y: 0 } },
  portrait: { imageSrc: '', zoom: 1, offset: { x: 0, y: 0 } },
})

const currentRatioLabel = computed(() => activeTab.value === 'portrait' ? props.portraitRatio : props.landscapeRatio)

const aspectRatio = computed(() => {
  const [w, h] = currentRatioLabel.value.split(':').map(Number)
  return activeTab.value === 'portrait' ? w / h : w / h
})

// 裁剪框固定居中（canvas 显示像素空间）；canvas 用 transform 平移/缩放图片
const cropSelectionStyle = computed(() => {
  const cw = cropRect.w * cropDisplayScale.value
  const ch = cropRect.h * cropDisplayScale.value
  const canvas = cropCanvasRef.value
  const cwTotal = canvas ? canvas.width : cw
  const chTotal = canvas ? canvas.height : ch
  return {
    left: (cwTotal - cw) / 2 + 'px',
    top: (chTotal - ch) / 2 + 'px',
    width: cw + 'px',
    height: ch + 'px',
  }
})

const canvasStyle = computed(() => ({
  transform: `translate(${imgOffset.x}px, ${imgOffset.y}px) scale(${imgZoom.value})`,
  transformOrigin: '0 0',
}))

function open(tab = 'landscape') {
  activeTab.value = tab
  visible.value = true
  loadFrames()
  loadTabState()
}

function currentVideoMaterialId() {
  // 视频上传已不区分横竖版（统一写入 videoLandscape），
  // 这里不再按 activeTab 区分，统一取可用视频 id（横版优先，竖版兜底），
  // 避免旧草稿里残留的已失效 videoPortrait.id 被优先命中导致抽帧 404。
  return props.videoLandscape?.id || props.videoPortrait?.id || ''
}

async function loadFrames() {
  const materialId = currentVideoMaterialId()
  if (!materialId) return
  stopPolling()
  try {
    extracting.value = true
    const resp = await frameApi.extractFrames(materialId)
    if (resp.data) {
      frames.value = resp.data.frames || []
      videoDuration.value = resp.data.duration || 0
      if (resp.data.status === 'processing') {
        startPolling(materialId)
      } else {
        extracting.value = false
      }
    }
  } catch {
    extracting.value = false
  }
}

function startPolling(materialId) {
  pollingTimer = setInterval(async () => {
    try {
      const resp = await frameApi.getFrames(materialId)
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
    loadImageToCanvas(state.imageSrc, { zoom: state.zoom, offset: state.offset })
  } else {
    const cover = activeTab.value === 'landscape' ? props.coverLandscape : props.coverPortrait
    if (cover?.url) {
      let src = cover.url
      if (cover._fromFrame !== undefined) {
        const materialId = currentVideoMaterialId()
        if (materialId) {
          src = frameApi.getFrameImageUrl(materialId, cover._fromFrame, false)
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
  state.zoom = imgZoom.value
  state.offset = { x: imgOffset.x, y: imgOffset.y }
}

function switchTab(tab) {
  saveTabState()
  activeTab.value = tab
  loadTabState()
}

function loadImageToCanvas(src, restore) {
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    cropImage.value = img
    nextTick(() => initCropCanvas(img, restore))
  }
  img.src = src
}

function initCropCanvas(img, restore) {
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

  // 裁剪框：固定居中、撑满最大（cover 模式，保证图片覆盖裁剪框）
  const ratio = aspectRatio.value
  let rw = img.width
  let rh = rw / ratio
  if (rh > img.height) { rh = img.height; rw = rh * ratio }
  cropRect.x = (img.width - rw) / 2
  cropRect.y = (img.height - rh) / 2
  cropRect.w = rw
  cropRect.h = rh

  // 图片缩放/平移：恢复或默认居中(zoom=1)
  if (restore && restore.zoom >= 1) {
    imgZoom.value = restore.zoom
    imgOffset.x = restore.offset.x
    imgOffset.y = restore.offset.y
  } else {
    imgZoom.value = 1
    imgOffset.x = 0
    imgOffset.y = 0
  }
}

function onTimelineSelect(seconds) {
  const materialId = currentVideoMaterialId()
  const url = frameApi.getFrameImageUrl(materialId, seconds, false)
  currentImageSrc.value = url
  loadImageToCanvas(url)
}

function onMaterialSelect(material) {
  const url = material.url || getFileUrl(material.stored_path)
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

// 滚轮缩放图片：以鼠标位置为锚点
function onWheel(e) {
  if (!cropImage.value) return
  const oldZoom = imgZoom.value
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
  let newZoom = oldZoom * factor
  newZoom = Math.max(1, Math.min(8, newZoom))
  if (newZoom === oldZoom) return
  // 锚点（鼠标在 canvas 显示像素空间的位置）缩放后不动
  const rect = cropCanvasRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  imgOffset.x = mx - (mx - imgOffset.x) * (newZoom / oldZoom)
  imgOffset.y = my - (my - imgOffset.y) * (newZoom / oldZoom)
  imgZoom.value = newZoom
  clampImgOffset()
}

// 拖动平移图片
function onPointerDown(e) {
  if (!cropImage.value) return
  e.preventDefault()
  try { e.target.setPointerCapture(e.pointerId) } catch {}
  dragState.value = {
    startX: e.clientX, startY: e.clientY,
    origX: imgOffset.x, origY: imgOffset.y,
    pointerId: e.pointerId,
  }
  const onMove = (ev) => {
    if (!dragState.value) return
    imgOffset.x = dragState.value.origX + (ev.clientX - dragState.value.startX)
    imgOffset.y = dragState.value.origY + (ev.clientY - dragState.value.startY)
    clampImgOffset()
  }
  const onUp = () => {
    dragState.value = null
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
}

// 约束：图片缩放/平移后，裁剪框四边始终被图片覆盖（不露白）。
// 裁剪框在 canvas 显示像素空间居中，尺寸 selW×selH；
// 图片经 transform 后左上角=imgOffset，右下角=canvasSize*zoom + imgOffset。
// 需满足：imgLeft <= selX 且 imgRight >= selX+selW（Y 同理）。
function clampImgOffset() {
  const canvas = cropCanvasRef.value
  if (!canvas) return
  const selW = cropRect.w * cropDisplayScale.value
  const selH = cropRect.h * cropDisplayScale.value
  const selX = (canvas.width - selW) / 2
  const selY = (canvas.height - selH) / 2
  const dispW = canvas.width * imgZoom.value
  const dispH = canvas.height * imgZoom.value
  // imgOffset 的合法区间：[selX+selW-dispW, selX]（保证图片覆盖裁剪框）
  const minX = selX + selW - dispW
  const maxX = selX
  const minY = selY + selH - dispH
  const maxY = selY
  imgOffset.x = Math.max(minX, Math.min(maxX, imgOffset.x))
  imgOffset.y = Math.max(minY, Math.min(maxY, imgOffset.y))
}

async function confirmCrop() {
  saveTabState()
  const img = cropImage.value
  if (!img) { ElMessage.warning('请先选择一张图片'); return }
  const [rw, rh] = currentRatioLabel.value.split(':').map(Number)
  let targetW, targetH
  if (activeTab.value === 'portrait') {
    targetH = 1920
    targetW = Math.round(1920 * rw / rh)
  } else {
    targetW = 1920
    targetH = Math.round(1920 * rh / rw)
  }
  // 反推裁剪源矩形（图片原始像素空间）。
  // canvas 上画的是完整图片；裁剪框居中，尺寸 selW×selH（canvas 显示像素）。
  // 图片经 transform: translate(imgOffset) scale(zoom) 显示。
  // 裁剪框在 canvas 坐标系的位置 selX，换算到未变换图片显示像素 = (selX - imgOffset)/zoom，
  // 再除以 cropDisplayScale 得到原图像素。
  const canvas = cropCanvasRef.value
  const selW = cropRect.w * cropDisplayScale.value
  const selH = cropRect.h * cropDisplayScale.value
  const selX = (canvas.width - selW) / 2
  const selY = (canvas.height - selH) / 2
  const srcX = (selX - imgOffset.x) / imgZoom.value / cropDisplayScale.value
  const srcY = (selY - imgOffset.y) / imgZoom.value / cropDisplayScale.value
  const srcW = selW / imgZoom.value / cropDisplayScale.value
  const srcH = selH / imgZoom.value / cropDisplayScale.value
  const offscreen = document.createElement('canvas')
  offscreen.width = targetW; offscreen.height = targetH
  const ctx = offscreen.getContext('2d')
  ctx.drawImage(img, srcX, srcY, srcW, srcH, 0, 0, targetW, targetH)
  const blob = await new Promise(resolve => offscreen.toBlob(resolve, 'image/jpeg', 0.92))
  if (!blob) { ElMessage.error('裁剪导出失败'); return }
  const formData = new FormData()
  formData.append('file', blob, `cover_${activeTab.value}_${Date.now()}.jpg`)
  try {
    // 用封面专用接口：写入 covers/ 目录，不入素材库（materials 表）
    const resp = await materialsApi.coversUpload(formData)
    if (resp.code === 200) {
      const d = resp.data
      const coverData = { name: d.original_filename, url: getFileUrl(d.stored_path), stored_path: d.stored_path, size: d.file_size, type: d.mime_type }
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
    box-shadow: 0 25px 60px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba($overlay-rgb, 0.03);
    overflow: hidden;
  }
  .el-dialog__header {
    background: linear-gradient(180deg, rgba($overlay-rgb, 0.04), transparent);
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
  scrollbar-color: rgba($overlay-rgb, 0.08) transparent;
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba($overlay-rgb, 0.1); border-radius: 2px; }
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
  cursor: grab;
  touch-action: none;
  user-select: none;
  &:active { cursor: grabbing; }
}

.crop-canvas {
  display: block;
  max-width: 100%;
}

.crop-selection {
  position: absolute;
  border: 2px solid $brand-start;
  box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.55);
  pointer-events: none;
  transition: box-shadow 0.15s;
}

.crop-ratio-badge {
  position: absolute;
  top: 6px;
  left: 6px;
  padding: 2px 6px;
  background: rgba(0, 0, 0, 0.6);
  border-radius: 3px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.85);
  pointer-events: none;
  font-family: monospace;
}

.crop-hint {
  position: absolute;
  top: 6px;
  right: 6px;
  padding: 2px 6px;
  background: rgba(0, 0, 0, 0.55);
  border-radius: 3px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.7);
  pointer-events: none;
  font-family: monospace;
}

.editor-actions {
  display: flex;
  gap: 12px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 10px;
  border: 1px solid $border;
  background: rgba($overlay-rgb, 0.04);
  color: $text-secondary;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: $border-active;
    color: $text-primary;
    background: rgba($overlay-rgb, 0.08);
  }

  .el-icon {
    font-size: 18px;
  }
}

.action-upload {
  &:hover {
    color: $brand-start;
    border-color: rgba($brand-start, 0.4);
    background: rgba($brand-start, 0.08);
  }
}

.action-material {
  &:hover {
    color: $brand-start;
    border-color: rgba($brand-start, 0.4);
    background: rgba($brand-start, 0.08);
  }
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
