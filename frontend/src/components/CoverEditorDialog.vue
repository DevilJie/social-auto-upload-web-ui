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
      <!-- 左侧：裁剪画布（主体） -->
      <div class="editor-crop">
        <div class="crop-area">
          <div v-if="!currentImageSrc" class="crop-empty">
            <el-icon :size="32"><Picture /></el-icon>
            <span>选择右侧时间轴帧、上传图片或从素材库选取</span>
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
      </div>

      <!-- 右侧：尺寸 tab + 时间轴 + 操作（侧栏） -->
      <div class="editor-sidebar">
        <!-- 尺寸 tab -->
        <div class="sidebar-block">
          <div class="sidebar-label">封面尺寸</div>
          <div class="ratio-tabs">
            <button
              v-for="r in ratioTabs"
              :key="r"
              :class="['ratio-tab', { active: activeTab === r }]"
              @click="switchTab(r)"
            >{{ r }}</button>
          </div>
        </div>

        <!-- Timeline -->
        <div class="sidebar-block" v-if="frames.length > 0">
          <div class="sidebar-label">
            视频时间轴
            <span class="sidebar-hint">拖动选帧</span>
          </div>
          <VideoTimeline :frames="frames" :duration="videoDuration" :extracting="extracting" v-model="selectedSecond" @update:modelValue="onTimelineSelect" />
        </div>

        <!-- 图片来源 -->
        <div class="sidebar-block">
          <div class="sidebar-label">图片来源</div>
          <div class="editor-actions">
            <button class="action-btn action-upload" @click="triggerLocalUpload">
              <el-icon :size="16"><Upload /></el-icon>
              <span>上传图片</span>
            </button>
            <button class="action-btn action-material" @click="materialSelectRef?.open()">
              <el-icon :size="16"><PictureFilled /></el-icon>
              <span>素材库</span>
            </button>
          </div>
        </div>
      </div>

      <input ref="fileInputRef" type="file" accept="image/*" style="display: none" @change="onLocalFileSelected" />
      <MaterialSelectDialog ref="materialSelectRef" filter-type="image" @select="onMaterialSelect" />
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
  // 当前弹窗方向：'landscape'（横版）或 'portrait'（竖版）
  orientation: { type: String, default: 'landscape' },
  // 主尺寸封面（横版=4:3，竖版=3:4）
  coverPrimary: { type: Object, default: null },
  // 次尺寸封面（横版=16:9，竖版=9:16）
  coverSecondary: { type: Object, default: null },
})

const emit = defineEmits(['coverSaved'])

const visible = ref(false)
// 当前编辑方向（由 open(orientation) 同步设置，不依赖 props 异步更新，避免切换横竖版时 ratio 错乱）
const activeOrientation = ref('landscape')

// 根据方向决定两个尺寸 tab
const ratioTabs = computed(() =>
  activeOrientation.value === 'portrait' ? ['3:4', '9:16'] : ['4:3', '16:9']
)
// 主尺寸对应的 ratio（第一个 tab）
const primaryRatio = computed(() => ratioTabs.value[0])
const secondaryRatio = computed(() => ratioTabs.value[1])

const frames = ref([])
const videoDuration = ref(0)
const selectedSecond = ref(0)
const extracting = ref(false)
let pollingTimer = null

const cropCanvasRef = ref(null)
const canvasWrapRef = ref(null)
const fileInputRef = ref(null)
const materialSelectRef = ref(null)
const dragState = ref(null)

// 每个 ratio 一个独立的裁剪面板状态（图片源、缩放、偏移各自隔离）
// panels: { '4:3': { imageSrc, img, zoom, offset, displayScale, cropRect }, ... }
const panels = reactive({})
const activeTab = ref('4:3')

// 当前激活面板（便捷访问）
const activePanel = computed(() => panels[activeTab.value])

const currentRatioLabel = computed(() => activeTab.value)
const currentImageSrc = computed(() => activePanel.value?.imageSrc || '')

const aspectRatio = computed(() => {
  const [w, h] = currentRatioLabel.value.split(':').map(Number)
  return w / h
})

// 裁剪框固定居中（与图片同比例 / 共享 displayScale，避免依赖 canvas DOM 尺寸来回切换错位）
const cropSelectionStyle = computed(() => {
  const p = activePanel.value
  if (!p || !p.img) return { left: 0, top: 0, width: 0, height: 0 }
  const s = p.displayScale
  const selW = p.cropRect.w * s
  const selH = p.cropRect.h * s
  // canvas 总尺寸 = 图片 × displayScale（与 redrawActivePanel 里 canvas.width = img.width * s 一致）
  const cwTotal = p.img.width * s
  const chTotal = p.img.height * s
  return {
    left: (cwTotal - selW) / 2 + 'px',
    top: (chTotal - selH) / 2 + 'px',
    width: selW + 'px',
    height: selH + 'px',
  }
})

const canvasStyle = computed(() => {
  const p = activePanel.value
  if (!p) return { transform: 'none', transformOrigin: '0 0' }
  return {
    transform: `translate(${p.offset.x}px, ${p.offset.y}px) scale(${p.zoom})`,
    transformOrigin: '0 0',
  }
})

function open(orientation) {
  activeOrientation.value = orientation || 'landscape'
  // 重置：每个 ratio 一个独立面板
  Object.keys(panels).forEach((k) => delete panels[k])
  ratioTabs.value.forEach((r) => {
    panels[r] = { imageSrc: '', img: null, zoom: 1, offset: { x: 0, y: 0 }, displayScale: 1, cropRect: { x: 0, y: 0, w: 0, h: 0 } }
  })
  activeTab.value = primaryRatio.value
  visible.value = true
  loadFrames()
  // 等 canvas 挂载后，为已有 cover 的面板加载图片
  nextTick(() => ratioTabs.value.forEach((r) => maybeLoadPanelCover(r)))
}

function currentVideoMaterialId() {
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

// 当前 ratio 对应的封面 prop（用于打开时回填已有封面）
function coverForTab(ratio) {
  return ratio === secondaryRatio.value ? props.coverSecondary : props.coverPrimary
}

// 若该面板还没有图、但已有 cover，则加载 cover 图
function maybeLoadPanelCover(ratio) {
  const p = panels[ratio]
  if (!p || p.imageSrc) return
  const cover = coverForTab(ratio)
  if (cover?.url) {
    let src = cover.url
    if (cover._fromFrame !== undefined) {
      const materialId = currentVideoMaterialId()
      if (materialId) src = frameApi.getFrameImageUrl(materialId, cover._fromFrame, false)
    }
    loadImageToPanel(ratio, src)
  }
}

// 切换 tab：直接切 activeTab，把该面板的图重画到 canvas
function switchTab(tab) {
  if (tab === activeTab.value) return
  activeTab.value = tab
  nextTick(() => redrawActivePanel())
}

// 为某面板加载图片
function loadImageToPanel(ratio, src) {
  const p = panels[ratio]
  if (!p) return
  p.imageSrc = src
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    p.img = img
    initPanelCropRect(ratio, img)
    if (ratio === activeTab.value) nextTick(() => redrawActivePanel())
  }
  img.src = src
}

// 计算某面板的裁剪框（居中、撑满最大、锁定该 ratio）
function initPanelCropRect(ratio, img) {
  const p = panels[ratio]
  if (!p) return
  const [w, h] = ratio.split(':').map(Number)
  const r = w / h
  let rw = img.width
  let rh = rw / r
  if (rh > img.height) { rh = img.height; rw = rh * r }
  p.cropRect.x = (img.width - rw) / 2
  p.cropRect.y = (img.height - rh) / 2
  p.cropRect.w = rw
  p.cropRect.h = rh
  p.zoom = 1
  p.offset.x = 0
  p.offset.y = 0
}

// 把当前激活面板的图重画到 canvas
function redrawActivePanel() {
  const canvas = cropCanvasRef.value
  const p = activePanel.value
  if (!canvas || !p || !p.img) return
  const maxW = 520
  const maxH = 380
  const scale = Math.min(maxW / p.img.width, maxH / p.img.height, 1)
  p.displayScale = scale
  canvas.width = p.img.width * scale
  canvas.height = p.img.height * scale
  const ctx = canvas.getContext('2d')
  ctx.drawImage(p.img, 0, 0, canvas.width, canvas.height)
  clampPanelOffset(p)
}

function onTimelineSelect(seconds) {
  const materialId = currentVideoMaterialId()
  const url = frameApi.getFrameImageUrl(materialId, seconds, false)
  loadImageToPanel(activeTab.value, url)
}

function onMaterialSelect(material) {
  const url = material.url || getFileUrl(material.stored_path)
  loadImageToPanel(activeTab.value, url)
}

function triggerLocalUpload() { fileInputRef.value?.click() }

function onLocalFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const url = URL.createObjectURL(file)
  loadImageToPanel(activeTab.value, url)
  e.target.value = ''
}

// 滚轮缩放图片：以鼠标位置为锚点
function onWheel(e) {
  const p = activePanel.value
  if (!p || !p.img) return
  const oldZoom = p.zoom
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
  let newZoom = oldZoom * factor
  newZoom = Math.max(1, Math.min(8, newZoom))
  if (newZoom === oldZoom) return
  const rect = cropCanvasRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  p.offset.x = mx - (mx - p.offset.x) * (newZoom / oldZoom)
  p.offset.y = my - (my - p.offset.y) * (newZoom / oldZoom)
  p.zoom = newZoom
  clampPanelOffset(p)
}

// 拖动平移图片
function onPointerDown(e) {
  const p = activePanel.value
  if (!p || !p.img) return
  e.preventDefault()
  try { e.target.setPointerCapture(e.pointerId) } catch {}
  dragState.value = {
    startX: e.clientX, startY: e.clientY,
    origX: p.offset.x, origY: p.offset.y,
    pointerId: e.pointerId,
  }
  const onMove = (ev) => {
    if (!dragState.value) return
    const pp = activePanel.value
    pp.offset.x = dragState.value.origX + (ev.clientX - dragState.value.startX)
    pp.offset.y = dragState.value.origY + (ev.clientY - dragState.value.startY)
    clampPanelOffset(pp)
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

// 约束：图片覆盖裁剪框四边（不露白）
function clampPanelOffset(p) {
  const canvas = cropCanvasRef.value
  if (!canvas || !p) return
  const selW = p.cropRect.w * p.displayScale
  const selH = p.cropRect.h * p.displayScale
  const selX = (canvas.width - selW) / 2
  const selY = (canvas.height - selH) / 2
  const dispW = canvas.width * p.zoom
  const dispH = canvas.height * p.zoom
  const minX = selX + selW - dispW
  const maxX = selX
  const minY = selY + selH - dispH
  const maxY = selY
  p.offset.x = Math.max(minX, Math.min(maxX, p.offset.x))
  p.offset.y = Math.max(minY, Math.min(maxY, p.offset.y))
}

// 裁剪单个面板并上传，返回 coverData
async function cropAndUploadPanel(ratio) {
  const p = panels[ratio]
  if (!p || !p.img) return null
  const [rw, rh] = ratio.split(':').map(Number)
  let targetW, targetH
  if (activeOrientation.value === 'portrait') {
    targetH = 1920
    targetW = Math.round(1920 * rw / rh)
  } else {
    targetW = 1920
    targetH = Math.round(1920 * rh / rw)
  }
  const canvas = cropCanvasRef.value
  // 用该面板的 displayScale 计算源矩形（切换 tab 时 canvas 已重画为当前面板的图）
  const dispW = p.img.width * p.displayScale
  const dispH = p.img.height * p.displayScale
  const selW = p.cropRect.w * p.displayScale
  const selH = p.cropRect.h * p.displayScale
  const selX = (dispW - selW) / 2
  const selY = (dispH - selH) / 2
  const srcX = (selX - p.offset.x) / p.zoom / p.displayScale
  const srcY = (selY - p.offset.y) / p.zoom / p.displayScale
  const srcW = selW / p.zoom / p.displayScale
  const srcH = selH / p.zoom / p.displayScale
  const offscreen = document.createElement('canvas')
  offscreen.width = targetW
  offscreen.height = targetH
  offscreen.getContext('2d').drawImage(p.img, srcX, srcY, srcW, srcH, 0, 0, targetW, targetH)
  const blob = await new Promise(resolve => offscreen.toBlob(resolve, 'image/jpeg', 0.92))
  if (!blob) return null
  const formData = new FormData()
  formData.append('file', blob, `cover_${activeOrientation.value}_${ratio.replace(':', 'x')}_${Date.now()}.jpg`)
  const resp = await materialsApi.coversUpload(formData)
  if (resp.code !== 200) return null
  const d = resp.data
  return { name: d.original_filename, url: getFileUrl(d.stored_path), stored_path: d.stored_path, size: d.file_size, type: d.mime_type }
}

async function confirmCrop() {
  // 校验：两个尺寸面板都必须选了图片
  const missing = ratioTabs.value.filter((r) => !panels[r] || !panels[r].img)
  if (missing.length > 0) {
    ElMessage.warning(`请先为 ${missing.join('、')} 尺寸选择图片`)
    if (missing[0]) switchTab(missing[0])
    return
  }
  // 逐个裁剪上传（裁剪前先把该面板重画到 canvas，确保 canvas 内容匹配）
  try {
    for (const r of ratioTabs.value) {
      activeTab.value = r
      await nextTick()
      redrawActivePanel()
      await nextTick()
      const coverData = await cropAndUploadPanel(r)
      if (!coverData) {
        ElMessage.error(`${r} 封面保存失败`)
        return
      }
      emit('coverSaved', { orientation: activeOrientation.value, ratio: r, cover: coverData })
    }
    ElMessage.success('封面设置成功')
    visible.value = false
  } catch {
    ElMessage.error('封面上传失败')
  }
}

function onClosed() {
  stopPolling()
  frames.value = []
  videoDuration.value = 0
  extracting.value = false
  Object.keys(panels).forEach((k) => delete panels[k])
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
    background: rgba($bg-elevated-rgb, 0.04);
  }
}
</style>

<style scoped lang="scss">
@use '@/styles/variables' as *;


.cover-editor-body {
  display: flex;
  gap: 16px;
  padding: 16px 20px;
  max-height: 72vh;
  overflow: hidden;
}

// 左侧裁剪区：占满剩余宽度
.editor-crop {
  flex: 1;
  min-width: 0;
  display: flex;
}

// 右侧侧栏：固定宽度，纵向堆叠
.editor-sidebar {
  flex-shrink: 0;
  width: 280px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba($overlay-rgb, 0.08) transparent;
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba($overlay-rgb, 0.1); border-radius: 2px; }
}

.sidebar-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sidebar-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
  color: $text-secondary;
}
.sidebar-hint {
  font-size: 11px;
  font-weight: 400;
  color: $text-muted;
}

// 尺寸 tab（侧栏内，撑满宽度）
.ratio-tabs {
  display: flex;
  gap: 6px;
  padding: 3px;
  background: rgba($overlay-rgb, 0.04);
  border: 1px solid $border;
  border-radius: 9px;
}
.ratio-tab {
  flex: 1;
  padding: 7px 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: $text-muted;
  font-size: 13px;
  font-weight: 600;
  font-family: monospace;
  cursor: pointer;
  transition: all 0.18s ease;
  &:hover { color: $text-primary; }
  &.active {
    background: $gradient-brand;
    color: #fff;
    box-shadow: 0 2px 8px rgba($brand-start, 0.35);
  }
}

.crop-area {
  flex: 1;
  background: $bg-surface;
  border: 1px solid $border;
  border-radius: $radius-base;
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
  flex-direction: column;
  gap: 8px;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 9px 14px;
  border-radius: 8px;
  border: 1px solid $border;
  background: rgba($overlay-rgb, 0.04);
  color: $text-secondary;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    border-color: $border-active;
    color: $text-primary;
    background: rgba($overlay-rgb, 0.08);
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
