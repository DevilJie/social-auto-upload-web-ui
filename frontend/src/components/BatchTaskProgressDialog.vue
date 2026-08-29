<template>
  <el-dialog
    :model-value="visible"
    title="批量发布进度"
    width="660px"
    :close-on-click-modal="false"
    class="batch-task-progress-dialog"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div class="progress-head">
      <el-progress
        :percentage="progress"
        :status="allDone ? 'success' : ''"
        :stroke-width="10"
      />
      <div class="progress-line">
        <span v-if="allDone" class="current done">
          全部完成：成功 {{ successCount }}<template v-if="failedCount > 0"> · 失败 {{ failedCount }}</template>
        </span>
        <span v-else-if="currentRunning" class="current">
          正在发布：{{ currentRunning.account_name }}（{{ currentRunning.platform }}）
        </span>
        <span v-else-if="countdownActive" class="current countdown">
          距下一个视频发布还有
          <b class="countdown-num">{{ countdownText }}</b>
        </span>
        <span v-else-if="intervalModeOn && hasActive" class="current countdown-muted">
          视频间隔
          <b class="countdown-num">{{ intervalHintText }}</b>
          ，第一个视频立即开始
        </span>
        <span v-else class="current muted">队列调度中…</span>
        <span class="stats">{{ finishedCount }} / {{ totalTasks }} 个任务</span>
      </div>
    </div>

    <div v-if="failedNotes.length > 0" class="submit-fail">
      <div class="submit-fail-title">以下视频未提交成功（已保留在队列中，可修复后重新发布）：</div>
      <div v-for="(n, i) in failedNotes" :key="i" class="submit-fail-item">{{ n }}</div>
    </div>

    <div v-if="sortedGroups.length > 0" class="task-list">
      <div
        v-for="g in sortedGroups"
        :key="g.id"
        :class="['video-card', `card-${g.summaryType}`]"
      >
        <div class="card-head" @click="toggleExpand(g)">
          <div class="group-cover">
            <img v-if="g.coverUrl" :src="g.coverUrl" alt="" />
            <el-icon v-else :size="14"><VideoCameraFilled /></el-icon>
          </div>
          <div class="card-title" :title="g.title">{{ g.title || '（无标题）' }}</div>
          <span :class="['status-chip', `chip-${g.summaryType}`]">
            <i v-if="g.summaryType === 'running'" class="chip-dot spin"></i>
            <i v-else class="chip-dot"></i>
            {{ g.summaryLabel }}
          </span>
          <!-- 仅「下一个等待视频」显示倒计时；后续排队视频无法预测时长，不展示 -->
          <span
            v-if="countdownActive && g.id === nextWaitingGroupId"
            class="card-countdown"
            :title="`间隔 ${intervalMinutes} 分钟`"
          >
            <el-icon class="card-countdown-icon"><Timer /></el-icon>
            {{ countdownText }}
          </span>
          <span :class="['group-count', { 'is-done': g.doneCount === g.items.length }]">
            {{ g.doneCount }}/{{ g.items.length }}
          </span>
          <el-icon :class="['chevron', { open: g.expanded }]"><ArrowDown /></el-icon>
        </div>
        <div :class="['card-body', { open: g.expanded }]">
          <div class="card-body-inner">
            <div v-for="it in g.items" :key="it.id" :class="['task-row', `is-${it.status}`]">
              <div class="row-main">
                <el-icon v-if="it.status === 'running'" class="spin row-icon"><Loading /></el-icon>
                <el-icon v-else-if="it.status === 'success'" class="row-icon is-ok"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="it.status === 'failed'" class="row-icon is-fail"><CircleCloseFilled /></el-icon>
                <el-icon v-else class="row-icon is-wait"><Clock /></el-icon>
                <span class="row-platform">{{ it.platform }}</span>
                <span class="row-account" :title="it.account_name">{{ it.account_name }}</span>
                <span class="row-status">{{ statusLabel(it.status) }}</span>
                <button
                  v-if="isActive(it.status)"
                  class="row-cancel"
                  @click.stop="cancelOne(it)"
                >取消</button>
                <a v-if="it.publish_url" :href="it.publish_url" target="_blank" class="row-link">查看</a>
              </div>
              <div
                v-if="it.status === 'failed' && it.error_message"
                class="row-error"
                :title="it.error_message"
              >{{ it.error_message }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="loading-block">
      <el-icon class="spin"><Loading /></el-icon>
      <span>正在获取任务状态…</span>
    </div>

    <template #footer>
      <div class="dialog-footer-right">
        <template v-if="allDone">
          <el-button @click="$emit('update:visible', false)">关闭</el-button>
          <el-button type="primary" @click="$emit('go-history')">去发布历史</el-button>
        </template>
        <template v-else>
          <span class="bg-hint">任务在后端队列执行，关闭窗口不影响发布</span>
          <el-button
            type="danger"
            plain
            :disabled="!hasActive"
            @click="cancelAllActive"
          >取消所有剩余</el-button>
          <el-button type="primary" @click="$emit('update:visible', false)">后台运行</el-button>
        </template>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount, onMounted, triggerRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, Clock, CircleCheckFilled, CircleCloseFilled, VideoCameraFilled, ArrowDown, Timer } from '@element-plus/icons-vue'
import { historyApi, taskApi } from '@/api/v2'

// 批量视频发布实时进度弹窗：
// 提交 /api/v2/videos/batch-publish 后由父组件打开，传入后端返回的 batch_ids。
// 数据源 = 初载/轮询 GET /api/v2/history/<batch_id>（权威状态）+ SSE /api/v2/tasks/stream
// （实时推送，命中本次任务 id 才应用），任务在后端持久化队列执行，关闭弹窗不影响。
//
// 布局（卡片式）：
// - 每个视频一张小卡片，点卡片头展开/收起该视频下每个账号的发布进度
// - 有任务发布中的卡片自动展开，全部结束后自动收起（手动操作过则尊重手动状态）
// - 列表限高 56vh，超出滚动；已完成（成功/失败）的视频卡片自动沉底
const props = defineProps({
  visible: { type: Boolean, default: false },
  // 后端 batch-publish 返回的 batch_ids（每个视频 1 个 batch，含 N 个账号任务）
  batchIds: { type: Array, default: () => [] },
  // 提交阶段就失败的视频（未生成任务），文案由父组件拼好
  failedNotes: { type: Array, default: () => [] },
  // 本次批量间隔（分钟），用于在等待阶段显示「距下一个视频发布还有 mm:ss」倒计时。
  // 0 或不传 = 不显示倒计时（= 连续发布）。
  intervalMinutes: { type: Number, default: 0 },
})

const emit = defineEmits(['update:visible', 'go-history'])

const TERMINAL = ['success', 'failed', 'cancelled']

// 原始批次数据：[{id, title, coverUrl, items: [{id, account_name, platform, status, error_message, publish_url}]}]
const batches = ref([])

// 展开/收起的手动覆盖记录（isExpanded 依据运行态自动判定 + 这两个集合微调）
const manualExpanded = ref(new Set())
const manualCollapsed = ref(new Set())

function isGroupExpanded(g) {
  const running = g.items.some(it => it.status === 'running')
  // 发布中的卡片默认展开（除非用户手动收起）；其余默认收起（除非用户手动展开）
  if (running) return !manualCollapsed.value.has(g.id)
  return manualExpanded.value.has(g.id)
}

function toggleExpand(g) {
  const running = g.items.some(it => it.status === 'running')
  const target = running ? manualCollapsed : manualExpanded
  const next = new Set(target.value)
  if (next.has(g.id)) next.delete(g.id)
  else next.add(g.id)
  target.value = next
}

// 账号行排序权重：发布中 > 等待/排队 > 成功 > 失败/取消
// （用户要求：已经成功或失败的排到后面去，进行中的留在前面）
function rowRank(status) {
  if (status === 'running') return 0
  if (status === 'pending' || status === 'queued') return 1
  if (status === 'success') return 2
  return 3 // failed / cancelled
}

function isActive(status) {
  return status === 'pending' || status === 'queued' || status === 'running'
}

// 展示用分组：doneCount + 汇总标签 + 展开态
// 注意：不改变视频卡片的提交顺序（用户要求：已完成不要沉底）—— 严格按 batch_ids 顺序
// （也就是 batches.value 的原顺序，由 refreshAll / refreshBatch 入队时按提交顺序插入）。
// 视频内 task 行排序仍按 rowRank（进行中靠前），符合用户已有诉求。
const sortedGroups = computed(() => batches.value
  .map((b, gIdx) => {
    const items = (b.items || [])
      .map((it, idx) => ({ ...it, _idx: idx }))
      .sort((a, b2) => rowRank(a.status) - rowRank(b2.status) || a._idx - b2._idx)
    const doneCount = items.filter(it => TERMINAL.includes(it.status)).length
    const total = items.length
    const done = total > 0 && doneCount === total
    const fails = items.filter(it => it.status === 'failed' || it.status === 'cancelled').length
    const running = items.some(it => it.status === 'running')
    const g = { ...b, items, doneCount, _gIdx: gIdx }
    if (done) {
      g.summaryType = fails > 0 ? 'fail' : 'ok'
      g.summaryLabel = fails > 0 ? (fails === total ? '全部失败' : '部分失败') : '全部成功'
    } else if (running) {
      g.summaryType = 'running'
      g.summaryLabel = '发布中'
    } else {
      g.summaryType = 'wait'
      g.summaryLabel = '等待中'
    }
    g.expanded = isGroupExpanded(g)
    return g
  })
  // 保持提交顺序：batches 数组顺序就是 batch_ids 顺序（refreshAll/refreshBatch
  // 都按 batchIds 顺序写入）。这里不再二次 sort，避免把已完成的视频卡片
  // "沉底" 让用户觉得顺序被改动。
  .sort((a, b) => a._gIdx - b._gIdx))

let eventSource = null
let pollTimer = null

// ========== 「距下一个视频发布」倒计时 ==========
// 三种文案：
//   1. intervalMinutes === 0：完全无倒计时（连续发布，每发完一个立即发下一个）
//   2. intervalMinutes > 0 且还没有任何 task 完成：提示"间隔 N 分钟，第一个视频立即开始"
//   3. intervalMinutes > 0 且已有 task 完成、还有等待中的视频：实时倒计时
//      锚点 = 最近一次 task 进入终态的时刻（取后端 finished_at，避免前端 Date.now() 误差）
//      目标时间 = 锚点 + intervalMinutes 分钟
//
// 后续等待的视频不预测（用户反馈：每个视频实际发布时长不一，无法估算）。
//
// 实现：倒计时直接读后端写好的 scheduled_at（发布链调度，DB 驱动），
// 每秒 ticker 刷新 countdownNow 驱动 mm:ss 文本递减。
let countdownNow = ref(Date.now())    // 每秒刷新驱动 mm:ss 文本

// 间隔模式开启：用户填了 > 0 的间隔。仅作模式开关，不强制要求有已完成 task。
const intervalModeOn = computed(() =>
  props.intervalMinutes != null && Number(props.intervalMinutes) > 0
)

// 「下一个待发布视频」：第一个等待中且已被排程（scheduled_at 非空）的视频。
// 后端发布链：前驱视频全部完成后写 scheduled_at = 完成时刻 + 间隔，
// 调度器到点自动入队发布。前端倒计时 = scheduled_at - 当前时间（用户设计）。
const nextScheduled = computed(() => {
  const g = sortedGroups.value.find(
    g => g.summaryType === 'wait' && g.scheduledAt
  )
  if (!g) return null
  const ts = Date.parse(g.scheduledAt)
  return Number.isNaN(ts) ? null : { id: g.id, at: ts }
})

// 真实倒计时条件：间隔模式 + 存在已排程的等待视频 + 未全部完成
const countdownActive = computed(() => {
  if (!intervalModeOn.value) return false
  if (nextScheduled.value === null) return false
  return !allDone.value
})

const countdownMs = computed(() => {
  if (!countdownActive.value) return 0
  return Math.max(0, nextScheduled.value.at - countdownNow.value)
})

// 把毫秒格式化成 "mm:ss"（>= 1 小时显示 "H:MM:SS"），仅用于显示
function formatCountdown(ms) {
  const total = Math.ceil(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = n => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}
const countdownText = computed(() => formatCountdown(countdownMs.value))

// 间隔模式下"提示文案"使用的最大间隔（mm:ss 形式）
const intervalHintText = computed(() => formatCountdown(props.intervalMinutes * 60 * 1000))

// 「下一个等待的视频」id：已排程的优先（显示倒计时标签）；
// 未排程时退回第一个等待视频（前驱还在发布，暂时无法预测，不显示倒计时）。
const nextWaitingGroupId = computed(() => {
  if (nextScheduled.value) return nextScheduled.value.id
  const g = sortedGroups.value.find(g => g.summaryType === 'wait')
  return g?.id ?? null
})

const allItems = computed(() => batches.value.flatMap(b => b.items))
const totalTasks = computed(() => allItems.value.length)
const finishedCount = computed(() => allItems.value.filter(it => TERMINAL.includes(it.status)).length)
const successCount = computed(() => allItems.value.filter(it => it.status === 'success').length)
const failedCount = computed(() => allItems.value.filter(it => it.status === 'failed').length)
const allDone = computed(() => totalTasks.value > 0 && finishedCount.value === totalTasks.value)
const progress = computed(() =>
  totalTasks.value === 0 ? 0 : Math.floor((finishedCount.value / totalTasks.value) * 100)
)
const currentRunning = computed(() => allItems.value.find(it => it.status === 'running'))
const hasActive = computed(() => allItems.value.some(it => isActive(it.status)))

async function cancelOne(it) {
  if (!isActive(it.status)) return
  try {
    await taskApi.cancelTask(it.id)
    ElMessage.success(`已请求取消「${it.account_name}」(${it.platform})`)
    refreshAll()
  } catch (e) {
    ElMessage.error('取消失败: ' + (e?.message || e))
  }
}

async function cancelAllActive() {
  const active = allItems.value.filter(it => isActive(it.status))
  if (!active.length) return
  try {
    await ElMessageBox.confirm(
      `将取消 ${active.length} 个剩余任务（进行中的任务会立即终止），确定？`,
      '取消剩余任务',
      { type: 'warning', confirmButtonText: '取消发布', cancelButtonText: '再想想' },
    )
  } catch { return }
  try {
    const res = await taskApi.cancelTasks(active.map(it => it.id))
    const d = res?.data || {}
    const ok = typeof d.cancelled === 'number' ? d.cancelled : active.length
    ElMessage.success(`已请求取消 ${ok}/${active.length} 个任务`)
  } catch (e) {
    ElMessage.error('取消失败: ' + (e?.message || e))
  }
  refreshAll()
}

function statusLabel(status) {
  return ({
    pending: '等待中',
    queued: '排队中',
    running: '发布中',
    success: '成功',
    failed: '失败',
    cancelled: '已取消',
  }[status] || status)
}

function mapBatch(b) {
  return {
    id: b.id,
    title: b.title,
    coverUrl: b.cover_url,
    // 发布链排程时间（ISO）：前驱视频完成后写入 = 完成时刻 + 间隔，
    // 前端据此显示"距下一个视频发布还有 mm:ss"倒计时
    scheduledAt: b.scheduled_at || '',
    items: (b.items || []).map(it => ({ ...it })),
  }
}

// 拉全部批次（权威状态；同时是 SSE 断连/漏事件时的兜底）
async function refreshAll() {
  if (props.batchIds.length === 0) return
  try {
    const results = await Promise.all(
      props.batchIds.map(id => historyApi.getBatch(id).catch(() => null))
    )
    const mapped = results.filter(r => r && r.data).map(r => mapBatch(r.data))
    // 保持提交顺序（batch_ids 顺序），而不是接口返回顺序
    const order = new Map(props.batchIds.map((id, i) => [id, i]))
    mapped.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0))
    batches.value = mapped
    // 显式 triggerRef 兜底：batches = mapped 会触发 ref，但某些浏览器/Vue
    // 边界场景下可能漏触发；显式调用让 nextScheduled computed 立刻重算。
    triggerRef(batches)
    if (allDone.value) stopTracking()
  } catch { /* 下次轮询重试 */ }
}

// 拉单个批次：任务到终态后补齐 publish_url / 完整 error_message
async function refreshBatch(batchId) {
  try {
    const res = await historyApi.getBatch(batchId)
    if (!res?.data) return
    const mapped = mapBatch(res.data)
    const idx = batches.value.findIndex(b => b.id === mapped.id)
    if (idx >= 0) batches.value[idx] = mapped
    else batches.value.push(mapped)
    triggerRef(batches)
    if (allDone.value) stopTracking()
  } catch { /* 下次轮询兜底 */ }
}

function connectSSE() {
  closeSSE()
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  const es = new EventSource(`${baseUrl}/api/v2/tasks/stream`)
  eventSource = es
  es.onmessage = (e) => {
    let d
    try { d = JSON.parse(e.data) } catch { return }
    if (!d?.id) return
    const b = batches.value.find(b => b.items.some(it => it.id === d.id))
    if (!b) return // 不是本次提交的任务，忽略
    const it = b.items.find(it => it.id === d.id)
    it.status = d.status
    if (d.error) it.error_message = d.error
    // SSE 直接改对象属性（it.status = X）不会触发 batches ref 的响应式追踪,
    // 显式 triggerRef 让 nextScheduled computed 重算（refreshBatch 还会拉到
    // 后端排程好的 scheduled_at，倒计时随之出现）。
    if (TERMINAL.includes(d.status)) {
      triggerRef(batches)
      refreshBatch(b.id)
    }
  }
  // 断连不重连（EventSource 默认自动重连），交给 5s 轮询兜底
  es.onerror = () => closeSSE()
}

function closeSSE() {
  if (eventSource) { eventSource.close(); eventSource = null }
}

function stopTracking() {
  closeSSE()
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (tickerTimer) { clearInterval(tickerTimer); tickerTimer = null }
}

// 每秒刷新倒计时文本（仅在弹窗打开期间跑，关闭即停）
let tickerTimer = null

watch(
  () => props.visible,
  (vis) => {
    stopTracking()
    if (vis) {
      batches.value = []
      manualExpanded.value = new Set()
      manualCollapsed.value = new Set()
      countdownNow.value = Date.now()
      refreshAll()
      connectSSE()
      pollTimer = setInterval(refreshAll, 5000)
      tickerTimer = setInterval(() => {
        countdownNow.value = Date.now()
      }, 1000)
    }
  }
)

onBeforeUnmount(stopTracking)
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.batch-task-progress-dialog {
  .progress-head {
    .progress-line {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-top: 10px;
      font-size: 13px;

      .current {
        color: $text-secondary;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;

        &.done { color: $success-color; }
        &.muted { color: $text-muted; }
        &.countdown {
          display: inline-flex;
          align-items: baseline;
          gap: 6px;
          color: $brand-start;
        }
        .countdown-num {
          font-variant-numeric: tabular-nums;
          font-size: 15px;
          font-weight: 600;
          letter-spacing: 0.5px;
        }
        &.countdown-muted {
          // 还没开始真实倒计时：文案比正在倒计时更克制，避免误以为已经等了 N 分钟
          color: $text-secondary;

          .countdown-num { font-size: 14px; }
        }
      }

      .stats { color: $text-muted; flex-shrink: 0; }
    }
  }

  .submit-fail {
    margin-top: 12px;
    padding: 8px 12px;
    background: rgba($overlay-rgb, 0.04);
    border-left: 3px solid $danger-color;
    border-radius: 4px;

    .submit-fail-title {
      font-size: 12px;
      color: $danger-color;
      margin-bottom: 4px;
    }

    .submit-fail-item {
      font-size: 12px;
      color: $text-secondary;
      line-height: 1.8;
      word-break: break-all;
    }
  }

  // ---- 卡片列表：限高滚动，超出部分上下滑动查看 ----
  .task-list {
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    max-height: 56vh;
    overflow-y: auto;
    padding: 2px 6px 2px 2px;

    &::-webkit-scrollbar { width: 6px; }
    &::-webkit-scrollbar-thumb {
      background: rgba($overlay-rgb, 0.15);
      border-radius: 3px;
    }
    &::-webkit-scrollbar-track { background: transparent; }
  }

  .video-card {
    flex-shrink: 0;
    border: 1px solid rgba($overlay-rgb, 0.1);
    border-radius: 8px;
    background: rgba($overlay-rgb, 0.02);
    overflow: hidden;
    transition: border-color 0.2s ease;

    &.card-running { border-color: color-mix(in srgb, $brand-start 45%, transparent); }
    &.card-ok { border-color: color-mix(in srgb, $success-color 40%, transparent); }
    &.card-fail { border-color: color-mix(in srgb, $danger-color 40%, transparent); }

    .card-head {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 9px 12px;
      cursor: pointer;
      user-select: none;
      transition: background 0.15s ease;

      &:hover { background: rgba($overlay-rgb, 0.04); }
    }

    .group-cover {
      width: 48px;
      height: 30px;
      border-radius: 4px;
      overflow: hidden;
      flex-shrink: 0;
      background: rgba($overlay-rgb, 0.06);
      display: flex;
      align-items: center;
      justify-content: center;
      color: $text-muted;

      img { width: 100%; height: 100%; object-fit: cover; display: block; }
    }

    .card-title {
      flex: 1;
      min-width: 0;
      font-size: 13px;
      font-weight: 600;
      color: $popper-text;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .status-chip {
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      line-height: 1;
      padding: 4px 9px;
      border-radius: 10px;
      border: 1px solid currentColor;

      .chip-dot {
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: currentColor;
        flex-shrink: 0;
      }
    }

    .chip-wait { color: $text-muted; }
    .chip-running { color: $brand-start; }
    .chip-ok { color: $success-color; }
    .chip-fail { color: $danger-color; }

    .group-count {
      flex-shrink: 0;
      font-size: 12px;
      color: $text-muted;
      font-variant-numeric: tabular-nums;

      &.is-done { color: $success-color; }
    }

    // 下一个等待视频卡上的小倒计时标签
    .card-countdown {
      flex-shrink: 0;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 12px;
      line-height: 1;
      padding: 4px 8px;
      border-radius: 10px;
      background: color-mix(in srgb, $brand-start 12%, transparent);
      color: $brand-start;
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.3px;

      .card-countdown-icon {
        font-size: 12px;
        animation: spin-rotate 2s linear infinite;
      }
    }

    .chevron {
      flex-shrink: 0;
      font-size: 13px;
      color: $text-muted;
      transition: transform 0.2s ease;

      &.open { transform: rotate(180deg); }
    }

    // 展开/收起动画：grid-template-rows 0fr ↔ 1fr
    .card-body {
      display: grid;
      grid-template-rows: 0fr;
      transition: grid-template-rows 0.25s ease;

      &.open { grid-template-rows: 1fr; }

      // 展开后账号列表固定高度，超出部分出垂直滚动条
      .card-body-inner {
        min-height: 0;
        overflow: hidden;
        max-height: 300px;
        overflow-y: auto;
        overscroll-behavior: contain;

        &::-webkit-scrollbar { width: 6px; }
        &::-webkit-scrollbar-thumb {
          background: rgba($overlay-rgb, 0.15);
          border-radius: 3px;
        }
        &::-webkit-scrollbar-track { background: transparent; }
      }
    }

    .task-row {
      display: flex;
      flex-direction: column;
      padding: 7px 14px 7px 74px;
      border-top: 1px dashed rgba($overlay-rgb, 0.08);
      transition: background 0.15s ease;

      &:hover { background: rgba($overlay-rgb, 0.03); }

      .row-main {
        display: flex;
        align-items: center;
        gap: 8px;
        min-width: 0;
      }

      .row-icon { flex-shrink: 0; font-size: 15px; color: $text-muted; }
      .row-icon.is-ok { color: $success-color; }
      .row-icon.is-fail { color: $danger-color; }

      .row-platform {
        flex-shrink: 0;
        font-size: 12px;
        color: $text-secondary;
      }

      .row-account {
        flex: 1;
        min-width: 0;
        font-size: 13px;
        color: $text-secondary;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .row-status { flex-shrink: 0; font-size: 12px; color: $text-muted; }
      &.is-running .row-status { color: $brand-start; }
      &.is-success .row-status { color: $success-color; }
      &.is-failed .row-status { color: $danger-color; }

      .row-cancel {
        flex-shrink: 0;
        border: none;
        background: none;
        padding: 0 2px;
        font-size: 12px;
        color: $danger-color;
        cursor: pointer;
        opacity: 0.75;

        &:hover { opacity: 1; text-decoration: underline; }
      }

      .row-link {
        flex-shrink: 0;
        font-size: 12px;
        color: $brand-start;
        text-decoration: none;

        &:hover { text-decoration: underline; }
      }

      .row-error {
        margin-top: 3px;
        font-size: 12px;
        color: $danger-color;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }
  }

  .loading-block {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 40px 0;
    color: $text-muted;
    font-size: 13px;
  }
}

.dialog-footer-right {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;

  .bg-hint {
    margin-right: auto;
    font-size: 12px;
    color: $text-muted;
  }
}

.spin {
  animation: spin-rotate 1s linear infinite;
}

@keyframes spin-rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
