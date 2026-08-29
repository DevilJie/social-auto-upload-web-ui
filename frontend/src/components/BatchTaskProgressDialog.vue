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
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, Clock, CircleCheckFilled, CircleCloseFilled, VideoCameraFilled, ArrowDown } from '@element-plus/icons-vue'
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

// 展示用分组：doneCount + 汇总标签 + 展开态 + 排序（未完成的在前，已完成的沉底）
const sortedGroups = computed(() => batches.value
  .map(b => {
    const items = (b.items || [])
      .map((it, idx) => ({ ...it, _idx: idx }))
      .sort((a, b2) => rowRank(a.status) - rowRank(b2.status) || a._idx - b2._idx)
    const doneCount = items.filter(it => TERMINAL.includes(it.status)).length
    const total = items.length
    const done = total > 0 && doneCount === total
    const fails = items.filter(it => it.status === 'failed' || it.status === 'cancelled').length
    const running = items.some(it => it.status === 'running')
    const g = { ...b, items, doneCount }
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
  .sort((a, b) => (a.doneCount === a.items.length ? 1 : 0) - (b.doneCount === b.items.length ? 1 : 0)))

let eventSource = null
let pollTimer = null

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
    if (TERMINAL.includes(d.status)) refreshBatch(b.id)
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
}

watch(
  () => props.visible,
  (vis) => {
    stopTracking()
    if (vis) {
      batches.value = []
      manualExpanded.value = new Set()
      manualCollapsed.value = new Set()
      refreshAll()
      connectSSE()
      pollTimer = setInterval(refreshAll, 5000)
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
