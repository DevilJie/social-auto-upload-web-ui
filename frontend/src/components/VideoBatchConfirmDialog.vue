<template>
  <el-dialog
    :model-value="visible"
    title="批量发布确认"
    width="860px"
    top="6vh"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div v-if="rows.length === 0" class="empty">队列为空</div>
    <template v-else>
      <!-- ── 顶部统计条：结果一目了然，可点击筛选 ── -->
      <div class="stat-bar">
        <div class="stat-chips">
          <button
            :class="['stat-chip', 'is-all', { 'is-active': filter === 'all' }]"
            @click="filter = 'all'"
          >全部 {{ rows.length }}</button>
          <button
            :class="['stat-chip', 'is-ok', { 'is-active': filter === 'ok' }]"
            @click="filter = 'ok'"
          >
            <el-icon><CircleCheckFilled /></el-icon>可发布 {{ okCount }}
          </button>
          <button
            v-if="failedCount > 0"
            :class="['stat-chip', 'is-fail', { 'is-active': filter === 'failed' }]"
            @click="filter = 'failed'"
          >
            <el-icon><CircleCloseFilled /></el-icon>待处理 {{ failedCount }}
          </button>
        </div>
        <div class="stat-right">
          预计产生 <b>{{ estimatedAllTasks }}</b> 个发布任务
        </div>
      </div>

      <!-- ── 视频卡片列表 ── -->
      <div class="video-list">
        <div
          v-for="row in filteredRows"
          :key="row.index"
          :class="['video-card', {
            'is-selected': selectedIndexes.includes(row.index),
            'is-failed': row.errors.length > 0,
          }]"
          :role="row.errors.length ? undefined : 'checkbox'"
          :aria-checked="row.errors.length ? undefined : selectedIndexes.includes(row.index)"
          @click="row.errors.length === 0 && toggleRow(row.index)"
        >
          <!-- 勾选区 -->
          <div class="card-check">
            <el-checkbox
              :model-value="selectedIndexes.includes(row.index)"
              :disabled="row.errors.length > 0"
              @click.stop
              @change="(val) => toggleRow(row.index, val)"
            />
          </div>

          <!-- 视频信息 -->
          <div class="video-cell">
            <div class="video-thumb">
              <img v-if="row.coverUrl" :src="row.coverUrl" alt="" />
              <el-icon v-else :size="18"><VideoCameraFilled /></el-icon>
            </div>
            <div class="video-info">
              <div class="video-name" :title="row.name">{{ row.name }}</div>
              <div class="video-title" :title="row.title">{{ row.title || '（无标题）' }}</div>
            </div>
          </div>

          <!-- 元信息 -->
          <div class="card-meta">
            <span class="meta-item">{{ row.accountCount }} 个账号</span>
            <span class="meta-item">{{ row.hasSchedule ? '定时发布' : '立即发布' }}</span>
          </div>

          <!-- 状态 -->
          <div class="card-status">
            <el-tag v-if="row.errors.length === 0" type="success" size="small" effect="light" round>
              <el-icon class="tag-icon"><CircleCheckFilled /></el-icon>可发布
            </el-tag>
            <el-tag v-else type="danger" size="small" effect="light" round>
              <el-icon class="tag-icon"><CircleCloseFilled /></el-icon>{{ row.errors.length }} 个问题
            </el-tag>
          </div>

          <!-- ── 问题详情：直接内联展示，不用展开行 ── -->
          <div v-if="row.errors.length > 0" class="card-errors" @click.stop>
            <div v-for="(e, i) in row.errors" :key="i" class="err-block">
              <div class="err-head">
                <span class="err-type">{{ errType(e) }}</span>
                <span v-if="errHint(e)" class="err-hint">{{ errHint(e) }}</span>
              </div>
              <div v-if="errAccounts(e).length" class="err-accounts">
                <span class="err-accounts-label">影响账号（{{ errAccounts(e).length }}）</span>
                <el-tag
                  v-for="a in errAccounts(e)"
                  :key="a"
                  type="danger"
                  effect="plain"
                  size="small"
                  class="err-account-tag"
                >{{ a }}</el-tag>
              </div>
            </div>
          </div>
        </div>

        <div v-if="filteredRows.length === 0" class="empty">该分类下没有视频</div>
      </div>

      <!-- ── 发布间隔：紧凑一行 ── -->
      <div class="interval-row">
        <el-icon class="interval-icon"><Timer /></el-icon>
        <span class="interval-label">发布间隔</span>
        <el-input-number
          v-model="intervalMinutes"
          :min="0"
          :max="120"
          :step="1"
          controls-position="right"
          style="width: 110px"
        />
        <span class="interval-unit">分钟</span>
        <el-tooltip placement="top">
          <template #content>
            每发布完一个视频等待指定分钟数再发布下一个，避免平台风控。<br />
            填 0 表示立即发布下一个。仅对本次批量生效。
          </template>
          <el-icon class="interval-help"><QuestionFilled /></el-icon>
        </el-tooltip>
      </div>
    </template>

    <template #footer>
      <div class="footer-row">
        <div class="footer-summary">
          <template v-if="rows.length > 0">
            已选 <b>{{ selectedIndexes.length }}</b> / {{ rows.length }} 个视频
            <template v-if="failedCount > 0">
              · <span class="summary-fail">{{ failedCount }} 个视频需先修复上方问题</span>
            </template>
            <span class="hint">（提交后可关闭页面，任务在后端继续执行）</span>
          </template>
        </div>
        <div class="footer-btns">
          <el-button @click="$emit('update:visible', false)" :disabled="submitting">取消</el-button>
          <el-button
            type="primary"
            :disabled="selectedIndexes.length === 0"
            :loading="submitting"
            @click="onConfirm"
          >
            发布 {{ selectedIndexes.length }} 个视频
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { VideoCameraFilled, CircleCheckFilled, CircleCloseFilled, Timer, QuestionFilled } from '@element-plus/icons-vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  // [{index, name, coverUrl, title, accountCount, hasSchedule, errors: []}]
  // errors 项为 { type, hint, accounts }（兼容旧版纯文本字符串）
  rows: { type: Array, default: () => [] },
  submitting: { type: Boolean, default: false },
})

const emit = defineEmits(['update:visible', 'confirm'])

const selectedIndexes = ref([])
// 筛选：all / ok / failed
const filter = ref('all')
// 本次批量发布的视频间隔（分钟）。0 = 立即开始下一个；>0 = 等满分钟再发下一个。
// 仅本次批量生效，不影响 settings.batchTaskInterval 全局值。
// 默认 30 分钟：避免平台风控（用户反馈：默认 0 太隐蔽，容易忘记设置）。
const intervalMinutes = ref(30)

const okCount = computed(() => props.rows.filter((r) => r.errors.length === 0).length)
const failedCount = computed(() => props.rows.length - okCount.value)
const estimatedAllTasks = computed(() =>
  props.rows.reduce((sum, r) => sum + (r.accountCount || 0), 0)
)

const filteredRows = computed(() => {
  if (filter.value === 'ok') return props.rows.filter((r) => r.errors.length === 0)
  if (filter.value === 'failed') return props.rows.filter((r) => r.errors.length > 0)
  return props.rows
})

// 每次打开：勾选全部可发布视频、默认展示全部（问题已内联，无需定位）
watch(
  () => props.visible,
  (vis) => {
    if (vis) {
      filter.value = 'all'
      selectedIndexes.value = props.rows
        .filter((r) => r.errors.length === 0)
        .map((r) => r.index)
    }
  },
  { immediate: true }
)

const estimatedTasks = computed(() =>
  props.rows
    .filter((r) => selectedIndexes.value.includes(r.index))
    .reduce((sum, r) => sum + (r.accountCount || 0), 0)
)
// 保留在 summary 里显示已选任务量
void estimatedTasks

function toggleRow(index, checked) {
  const has = selectedIndexes.value.includes(index)
  if (checked === undefined) {
    // 整卡点击 = 切换
    if (has) selectedIndexes.value = selectedIndexes.value.filter((i) => i !== index)
    else selectedIndexes.value = [...selectedIndexes.value, index]
    return
  }
  if (checked && !has) selectedIndexes.value = [...selectedIndexes.value, index]
  if (!checked && has) selectedIndexes.value = selectedIndexes.value.filter((i) => i !== index)
}

// 兼容新旧两种错误格式
function errType(e) { return typeof e === 'string' ? '问题' : e.type }
function errHint(e) { return typeof e === 'string' ? e : (e.hint || '') }
function errAccounts(e) { return typeof e === 'string' ? [] : (e.accounts || []) }

function onConfirm() {
  if (selectedIndexes.value.length === 0) return
  // 父组件读取数值并传给后端（仅本次批量生效）。
  // el-input-number 已限制 min=0，组件无需重复校验。
  emit('confirm', {
    selectedIndexes: [...selectedIndexes.value],
    intervalMinutes: Number(intervalMinutes.value) || 0,
  })
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.empty {
  text-align: center;
  color: $text-muted;
  padding: 40px 0;
}

// ── 顶部统计条 ──
.stat-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;

  .stat-chips {
    display: flex;
    gap: 8px;
  }

  .stat-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 14px;
    border-radius: 999px;
    border: 1px solid $border;
    background: $bg-surface;
    font-size: 13px;
    color: $text-secondary;
    cursor: pointer;
    transition: all 0.15s;

    &:hover { border-color: $brand-start; }

    &.is-active {
      border-color: $brand-start;
      background: rgba($brand-start, 0.08);
      color: $brand-start;
      font-weight: 600;
    }

    &.is-ok .el-icon { color: $success-color; }
    &.is-fail .el-icon { color: $danger-color; }
  }

  .stat-right {
    font-size: 13px;
    color: $text-secondary;

    b { color: $brand-start; }
  }
}

// ── 视频卡片列表 ──
.video-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 46vh;
  overflow-y: auto;
  padding: 2px 4px 2px 2px;
}

.video-card {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  grid-template-areas:
    'check video meta status'
    'errors errors errors errors';
  align-items: center;
  gap: 6px 12px;
  padding: 10px 14px;
  background: $bg-surface;
  border: 1px solid $border;
  border-radius: 10px;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;

  &:not(.is-failed) {
    cursor: pointer;

    &:hover { border-color: $brand-start; }
  }

  &.is-selected {
    border-color: $brand-start;
    background: rgba($brand-start, 0.04);
    box-shadow: 0 0 0 1px $brand-start inset;
  }

  &.is-failed {
    border-left: 3px solid $danger-color;
    background: rgba($danger-color, 0.03);
    cursor: default;
  }

  .card-check {
    grid-area: check;
    display: flex;
    align-items: center;
  }

  .card-meta {
    grid-area: meta;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;

    .meta-item {
      font-size: 12px;
      color: $text-muted;
      white-space: nowrap;
    }
  }

  .card-status {
    grid-area: status;
    display: flex;
    align-items: center;

    .tag-icon {
      margin-right: 3px;
    }
  }
}

.video-cell {
  grid-area: video;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;

  .video-thumb {
    width: 64px;
    height: 36px;
    border-radius: 6px;
    overflow: hidden;
    flex-shrink: 0;
    background: rgba($overlay-rgb, 0.06);
    display: flex;
    align-items: center;
    justify-content: center;
    color: $text-muted;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
  }

  .video-info {
    min-width: 0;

    .video-name {
      font-size: 13px;
      font-weight: 500;
      color: $text-primary;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 340px;
    }

    .video-title {
      font-size: 12px;
      color: $text-muted;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 340px;
      margin-top: 2px;
    }
  }
}

// ── 内联错误详情 ──
.card-errors {
  grid-area: errors;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
  padding: 10px 12px;
  background: rgba($danger-color, 0.05);
  border-radius: 8px;

  .err-block {
    display: flex;
    flex-direction: column;
    gap: 6px;

    & + .err-block {
      padding-top: 8px;
      border-top: 1px dashed rgba($danger-color, 0.2);
    }
  }

  .err-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;

    .err-type {
      flex-shrink: 0;
      font-size: 13px;
      font-weight: 600;
      color: $danger-color;
    }

    .err-hint {
      font-size: 12px;
      color: $text-secondary;
      line-height: 1.6;
    }
  }

  .err-accounts {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;

    .err-accounts-label {
      font-size: 12px;
      color: $text-muted;
      flex-shrink: 0;
    }

    .err-account-tag {
      max-width: 240px;
      overflow: hidden;
      text-overflow: ellipsis;
    }
  }
}

// ── 发布间隔 ──
.interval-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding: 10px 14px;
  background: rgba($warning-color, 0.06);
  border: 1px solid rgba($warning-color, 0.25);
  border-radius: 8px;

  .interval-icon { color: $warning-color; }
  .interval-label { font-size: 13px; font-weight: 500; color: $text-primary; }
  .interval-unit { font-size: 13px; color: $text-secondary; }

  .interval-help {
    color: $text-muted;
    cursor: help;

    &:hover { color: $text-secondary; }
  }
}

// ── 底部 ──
.footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;

  .footer-summary {
    flex: 1;
    font-size: 13px;
    color: $text-secondary;
    min-width: 0;

    b { color: $brand-start; }

    .summary-fail { color: $danger-color; }

    .hint {
      color: $text-muted;
      font-size: 12px;
      margin-left: 4px;
    }
  }

  .footer-btns {
    display: flex;
    gap: 10px;
    flex-shrink: 0;
  }
}
</style>
