<template>
  <teleport to="body">
    <div v-if="visible" class="guide-tour">
      <!-- 遮罩：拦截页面交互；无高亮目标时兼做背景压暗 -->
      <div class="guide-overlay" :style="{ background: rect ? 'transparent' : 'rgba(2, 6, 23, 0.6)' }"></div>

      <!-- 高亮挖孔区（box-shadow 铺满全屏形成聚光效果） -->
      <div
        v-if="rect"
        class="guide-spotlight"
        :style="{
          top: rect.top + 'px',
          left: rect.left + 'px',
          width: rect.width + 'px',
          height: rect.height + 'px'
        }"
      ></div>

      <!-- 引导气泡（key=index 让每步重放入场动画） -->
      <div ref="popoverRef" :key="index" class="guide-popover" :style="popoverStyle">
        <span
          v-if="rect && arrow.side"
          class="guide-arrow"
          :class="'is-' + arrow.side"
          :style="arrow.style"
        ></span>

        <div class="guide-header">
          <span class="guide-badge">{{ index + 1 }} / {{ steps.length }}</span>
          <button class="guide-skip" type="button" @click="skip">跳过引导</button>
        </div>

        <div class="guide-title">
          <span v-if="step.icon" class="guide-icon">{{ step.icon }}</span>
          <span>{{ step.title }}</span>
        </div>
        <div class="guide-content">{{ step.content }}</div>

        <div class="guide-footer">
          <div class="guide-dots">
            <span
              v-for="(s, i) in steps"
              :key="i"
              class="guide-dot"
              :class="{ active: i === index, done: i < index }"
            ></span>
          </div>
          <div class="guide-btns">
            <button v-if="index > 0" class="guide-btn ghost" type="button" @click="prev">上一步</button>
            <button class="guide-btn primary" type="button" @click="next">
              {{ index === steps.length - 1 ? '完成' : '下一步' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup>
/**
 * 通用新手引导组件（零第三方依赖）
 *
 * 用法：
 *   <GuideTour ref="tourRef" :steps="steps" @finish="..." @skip="..." />
 *   tourRef.value.start()   // 开始播放
 *
 * steps 项：
 *   {
 *     target: '[data-tour="xxx"]',  // CSS 选择器，省略/null 则气泡居中显示
 *     title: '步骤标题',
 *     content: '气泡正文',
 *     icon: '🎉',                   // 可选，标题前 emoji
 *     placement: 'bottom',          // 可选：气泡首选方位 bottom/top/left/right
 *     skipIfMissing: true           // 可选：目标元素不存在时自动跳过该步
 *   }
 */
import { ref, reactive, computed, nextTick, onBeforeUnmount } from 'vue'

const props = defineProps({
  steps: { type: Array, required: true }
})
const emit = defineEmits(['finish', 'skip'])

const PAD = 10      // 高亮区外扩像素
const GAP = 14      // 气泡与高亮区间距
const POP_WIDTH = 380
const EDGE = 16     // 气泡距视口边缘最小距离

const visible = ref(false)
const index = ref(0)
const rect = ref(null)                       // 高亮区矩形（视口坐标），null = 居中模式
const pos = ref({ top: 0, left: 0 })
const popPlaced = ref(false)                 // 测量完成前把气泡放到屏幕外，避免闪跳
const arrow = reactive({ side: '', style: {} })
const popoverRef = ref(null)

const step = computed(() => props.steps[index.value] || {})

const popoverStyle = computed(() => ({
  top: pos.value.top + 'px',
  left: (popPlaced.value ? pos.value.left : -99999) + 'px',
  width: POP_WIDTH + 'px',
  visibility: popPlaced.value ? 'visible' : 'hidden'
}))

let currentEl = null
let rafId = 0

// ---------- 对外 API ----------
function start (from = 0) {
  if (!props.steps.length) return
  const first = _firstValid(from, 1)
  if (first === -1) { emit('finish'); return }
  visible.value = true
  index.value = first
  _bind(true)
  _locate(true)
}

function stop () {
  visible.value = false
  _bind(false)
}

// ---------- 步骤流转 ----------
function next () {
  if (index.value >= props.steps.length - 1) {
    stop()
    emit('finish')
    return
  }
  const ni = _firstValid(index.value + 1, 1)
  if (ni === -1) { stop(); emit('finish'); return }
  index.value = ni
  _locate(true)
}

function prev () {
  if (index.value <= 0) return
  const pi = _firstValid(index.value - 1, -1)
  if (pi === -1) return
  index.value = pi
  _locate(true)
}

function skip () {
  stop()
  emit('skip')
}

// 目标是否存在（无 target 的居中步骤视为存在；display:none / v-show 隐藏或零尺寸视为不存在）
function _exists (st) {
  if (!st.target) return true
  try {
    const el = document.querySelector(st.target)
    if (!el) return false
    const b = el.getBoundingClientRect()
    return b.width > 1 && b.height > 1
  } catch { return false }
}

// 从 from 开始沿 dir 方向找第一个有效步骤（skipIfMissing 且目标缺失的步骤被跳过）
function _firstValid (from, dir) {
  let i = from
  while (i >= 0 && i < props.steps.length) {
    const st = props.steps[i]
    if (_exists(st) || !(st.skipIfMissing && st.target)) return i
    i += dir
  }
  return -1
}

// ---------- 定位 ----------
async function _locate (scroll = false) {
  const st = step.value
  currentEl = null
  if (st.target) {
    try { currentEl = document.querySelector(st.target) } catch { currentEl = null }
  }

  popPlaced.value = false
  await nextTick()

  if (currentEl && scroll) {
    currentEl.scrollIntoView({ block: 'center', behavior: 'auto' })
    await new Promise(r => { rafId = requestAnimationFrame(r) })
  }

  if (currentEl) {
    const b = currentEl.getBoundingClientRect()
    if (b.width > 1 && b.height > 1) {
      rect.value = {
        top: Math.round(b.top - PAD),
        left: Math.round(b.left - PAD),
        width: Math.round(b.width + PAD * 2),
        height: Math.round(b.height + PAD * 2)
      }
    } else {
      currentEl = null // 隐藏元素（如 v-show 面板）退化为居中模式
      rect.value = null
    }
  } else {
    rect.value = null
  }

  _place()
}

function _place () {
  const popH = popoverRef.value?.offsetHeight || 180
  const vw = window.innerWidth
  const vh = window.innerHeight
  const clamp = (v, min, max) => Math.min(Math.max(v, min), Math.max(min, max))

  // 居中模式（无高亮目标）
  if (!rect.value) {
    pos.value = {
      top: Math.round(Math.max(EDGE, (vh - popH) / 2)),
      left: Math.round((vw - POP_WIDTH) / 2)
    }
    arrow.side = ''
    popPlaced.value = true
    return
  }

  const r = rect.value
  const prefer = step.value.placement || 'bottom'
  const order = {
    bottom: ['bottom', 'top', 'right', 'left'],
    top: ['top', 'bottom', 'right', 'left'],
    right: ['right', 'left', 'bottom', 'top'],
    left: ['left', 'right', 'bottom', 'top']
  }[prefer] || ['bottom', 'top', 'right', 'left']

  const space = {
    bottom: vh - (r.top + r.height) - GAP - popH - EDGE,
    top: r.top - GAP - popH - EDGE,
    right: vw - (r.left + r.width) - GAP - POP_WIDTH - EDGE,
    left: r.left - GAP - POP_WIDTH - EDGE
  }
  const side = order.find(s => space[s] >= 0) || (space.bottom > space.top ? 'bottom' : 'top')

  let top = 0
  let left = 0
  if (side === 'bottom') { top = r.top + r.height + GAP; left = r.left + r.width / 2 - POP_WIDTH / 2 }
  else if (side === 'top') { top = r.top - GAP - popH; left = r.left + r.width / 2 - POP_WIDTH / 2 }
  else if (side === 'right') { top = r.top + r.height / 2 - popH / 2; left = r.left + r.width + GAP }
  else { top = r.top + r.height / 2 - popH / 2; left = r.left - GAP - POP_WIDTH }

  pos.value = {
    top: clamp(Math.round(top), EDGE, vh - popH - EDGE),
    left: clamp(Math.round(left), EDGE, vw - POP_WIDTH - EDGE)
  }

  // 小箭头：气泡在下 → 箭头指向气泡顶边，以此类推
  if (side === 'bottom' || side === 'top') {
    arrow.side = side === 'bottom' ? 'top' : 'bottom'
    const ax = clamp(r.left + r.width / 2 - pos.value.left, 26, POP_WIDTH - 26)
    arrow.style = { left: ax + 'px' }
  } else {
    arrow.side = side === 'right' ? 'left' : 'right'
    const ay = clamp(r.top + r.height / 2 - pos.value.top, 26, popH - 26)
    arrow.style = { top: ay + 'px' }
  }
  popPlaced.value = true
}

// ---------- 事件 ----------
// 滚动/缩放时静默重算位置（不滚动页面、不隐藏气泡）
function _onScroll () {
  if (!visible.value) return
  cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => {
    if (!visible.value) return
    if (currentEl && currentEl.isConnected) {
      const b = currentEl.getBoundingClientRect()
      if (b.width > 1 && b.height > 1) {
        rect.value = {
          top: Math.round(b.top - PAD),
          left: Math.round(b.left - PAD),
          width: Math.round(b.width + PAD * 2),
          height: Math.round(b.height + PAD * 2)
        }
      }
    }
    _place()
  })
}

function _onKey (e) {
  if (!visible.value) return
  if (e.key === 'Escape') skip()
  else if (e.key === 'ArrowRight' || e.key === 'Enter') next()
  else if (e.key === 'ArrowLeft') prev()
}

function _bind (on) {
  if (on) {
    window.addEventListener('resize', _onScroll)
    window.addEventListener('keydown', _onKey)
    document.addEventListener('scroll', _onScroll, true)
  } else {
    window.removeEventListener('resize', _onScroll)
    window.removeEventListener('keydown', _onKey)
    document.removeEventListener('scroll', _onScroll, true)
    cancelAnimationFrame(rafId)
  }
}

onBeforeUnmount(() => _bind(false))

defineExpose({ start, stop })
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.guide-tour {
  position: fixed;
  inset: 0;
  z-index: 3000; // 高于 el-dialog(2000)，引导时压住所有弹层
}

.guide-overlay {
  position: absolute;
  inset: 0;
  transition: background $transition-base;
}

.guide-spotlight {
  position: absolute;
  border-radius: 12px;
  pointer-events: none;
  box-shadow:
    0 0 0 2px rgba($brand-start, 0.9),
    0 0 22px rgba($brand-start, 0.45),
    0 0 0 9999px rgba(2, 6, 23, 0.6);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  animation: guide-fade 0.25s ease;
}

.guide-popover {
  position: absolute;
  background: var(--popper-bg, #1e293b);
  border: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
  border-radius: 14px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.35);
  padding: 14px 16px 12px;
  color: var(--popper-text, var(--text-primary, #e5e7eb));
  animation: guide-pop 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.guide-arrow {
  position: absolute;
  width: 12px;
  height: 12px;
  background: var(--popper-bg, #1e293b);
  transform: rotate(45deg);

  &.is-top {
    top: -6.5px;
    border-left: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
    border-top: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
  }
  &.is-bottom {
    bottom: -6.5px;
    border-right: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
    border-bottom: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
  }
  &.is-left {
    left: -6.5px;
    border-left: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
    border-bottom: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
  }
  &.is-right {
    right: -6.5px;
    border-right: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
    border-top: 1px solid var(--popper-border, rgba(255, 255, 255, 0.12));
  }
}

.guide-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.guide-badge {
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: $gradient-brand;
  padding: 2px 10px;
  border-radius: 999px;
  letter-spacing: 0.05em;
}

.guide-skip {
  border: 0;
  background: transparent;
  color: var(--popper-text-muted, #94a3b8);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
  transition: color $transition-fast;

  &:hover { color: $accent-rose; }
}

.guide-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 8px;
}

.guide-icon {
  font-size: 18px;
  line-height: 1;
}

.guide-content {
  font-size: 13px;
  line-height: 1.75;
  color: var(--popper-text-muted, var(--text-secondary, #94a3b8));
  margin-bottom: 12px;
}

.guide-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.guide-dots {
  display: flex;
  gap: 5px;
  align-items: center;
}

.guide-dot {
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: rgba($overlay-rgb, 0.25);
  transition: all $transition-base;

  &.done { background: rgba($brand-start, 0.5); }
  &.active {
    width: 16px;
    background: $gradient-brand;
  }
}

.guide-btns {
  display: flex;
  gap: 8px;
}

.guide-btn {
  border: 0;
  border-radius: 8px;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all $transition-fast;

  &.ghost {
    background: transparent;
    border: 1px solid var(--popper-border, rgba(255, 255, 255, 0.14));
    color: var(--popper-text-muted, #94a3b8);

    &:hover {
      color: var(--popper-text, var(--text-primary, #e5e7eb));
      border-color: rgba($brand-start, 0.5);
    }
  }

  &.primary {
    background: $gradient-brand;
    color: #fff;
    box-shadow: 0 4px 12px rgba($brand-start, 0.35);

    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 6px 16px rgba($brand-start, 0.45);
    }
  }
}

@keyframes guide-fade {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes guide-pop {
  from { opacity: 0; transform: translateY(6px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
</style>
