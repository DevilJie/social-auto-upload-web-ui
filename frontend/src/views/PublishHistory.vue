<template>
  <div class="publish-history-page">
    <h1 class="page-title">发布历史</h1>
    <p class="page-subtitle">回顾所有发布记录</p>

    <!-- 3 Stat cards row -->
    <div class="stat-cards">
      <div class="stat-card stat-purple">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><Upload /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.total }}</div>
            <div class="stat-label">总发布数</div>
          </div>
        </div>
      </div>

      <div class="stat-card stat-blue">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><CircleCheck /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.successRate }}%</div>
            <div class="stat-label">成功率</div>
          </div>
        </div>
      </div>

      <div class="stat-card stat-cyan">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><Calendar /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.monthlyTotal }}</div>
            <div class="stat-label">本月发布</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Filter toolbar -->
    <div class="filter-card">
      <div class="filter-row">
        <div class="filter-controls">
          <el-select
            v-model="timeRange"
            placeholder="时间范围"
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="今天" value="today" />
            <el-option label="最近7天" value="7days" />
            <el-option label="最近30天" value="30days" />
            <el-option label="全部" value="all" />
          </el-select>

          <el-select
            v-model="typeFilter"
            placeholder="类型"
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="全部" value="all" />
            <el-option label="视频" value="video" />
            <el-option label="图集" value="image" />
          </el-select>

          <el-select
            v-model="platformFilter"
            placeholder="平台"
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="全部" value="all" />
            <el-option v-for="p in platformList" :key="p.key" :label="p.name" :value="p.key" />
          </el-select>

          <el-select
            v-model="statusFilter"
            placeholder="状态"
            class="filter-select"
            @change="handleFilterChange"
          >
            <el-option label="全部" value="all" />
            <el-option label="全部成功" value="success" />
            <el-option label="部分失败" value="partial" />
            <el-option label="全部失败" value="failed" />
          </el-select>
        </div>

        <div class="filter-actions">
          <el-button
            v-if="!selectMode"
            class="select-trigger-btn"
            :icon="Select"
            :disabled="batches.length === 0"
            @click="toggleSelectMode"
          >
            多选
          </el-button>
          <el-button
            class="refresh-btn"
            :icon="Refresh"
            @click="fetchHistory"
            :loading="loading"
          >
            刷新
          </el-button>
        </div>
      </div>
    </div>

    <!-- Batch operations toolbar -->
    <div class="batch-toolbar" v-if="selectMode">
      <el-checkbox
        :model-value="isAllSelected"
        :indeterminate="isIndeterminate"
        class="toolbar-select-all"
        @change="toggleSelectAll"
      >
        全选
      </el-checkbox>

      <div class="selected-info">
        <el-icon class="selected-icon"><Check /></el-icon>
        <span>已选 <strong>{{ selection.size }}</strong> / {{ batches.length }}</span>
      </div>

      <div class="toolbar-spacer"></div>

      <el-button
        size="default"
        :icon="Delete"
        type="danger"
        :disabled="selection.size === 0 || isDeleting"
        @click="onBatchDelete"
      >
        批量删除<template v-if="selection.size > 0"> ({{ selection.size }})</template>
      </el-button>
      <el-button
        size="default"
        :icon="Close"
        class="toolbar-exit"
        @click="toggleSelectMode"
      >
        退出多选
      </el-button>
    </div>

    <!-- 卡片网格 -->
    <div class="cards-grid" v-loading="loading">
      <div v-if="!loading && batches.length === 0" class="empty-state">
        <el-icon class="empty-icon"><Clock /></el-icon>
        <p>暂无发布记录</p>
      </div>
      <div
        v-for="batch in batches"
        :key="batch.id"
        class="batch-card"
        :class="{
          'is-selected': selection.has(batch.id),
          'select-mode': selectMode,
        }"
        @click="onCardClick(batch.id)"
      >
        <div
          v-if="selectMode"
          class="card-selector"
          :class="{ 'is-checked': selection.has(batch.id) }"
          @click.stop="toggleSelection(batch.id, !selection.has(batch.id))"
        >
          <el-icon class="selector-icon"><Check /></el-icon>
        </div>
        <div class="card-cover">
          <img v-if="batch.cover_url" :src="batch.cover_url" :alt="batch.title" />
          <div v-else class="cover-placeholder">
            <el-icon :size="32"><Picture /></el-icon>
          </div>
        </div>
        <div class="card-body">
          <h3 class="card-title">{{ batch.title || '无标题' }}</h3>
          <ChannelSummary
            :channels="computeChannelsSummary(batch.items)"
            :overflow-key="batch.id"
          />
          <div class="card-meta">
            <span class="meta-time">{{ formatCardTime(batch.created_at) }}</span>
            <span class="status-tag" :class="`status-${batch.status}`">{{ statusLabel(batch.status) }}</span>
          </div>
          <div class="card-stats">
            <PublishStats compact />
          </div>
        </div>

        <!-- 单条删除按钮（非多选模式下显示） -->
        <button
          v-if="!selectMode"
          class="card-delete-btn"
          @click.stop="confirmDelete(batch)"
        >
          <el-icon><Delete /></el-icon>
        </button>
      </div>
    </div>

    <!-- Pagination -->
    <div class="pagination-wrapper" v-if="total > 0">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
        background
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Picture, Refresh, Upload, CircleCheck, Calendar, Delete, Check, Select, Close } from '@element-plus/icons-vue'
import { historyApi, statsApi } from '@/api/v2'
import { platformList, getPlatformByKey } from '@/config/platforms'
import ChannelSummary from '@/components/ChannelSummary.vue'
import PublishStats from '@/components/PublishStats.vue'

const router = useRouter()
const batches = ref([])
const stats = ref({ total: 0, successRate: 0, monthlyTotal: 0 })
const loading = ref(false)

// Filters
const timeRange = ref('all')
const typeFilter = ref('all')
const platformFilter = ref('all')
const statusFilter = ref('all')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// 多选 + 删除状态
const selection = ref(new Set())           // 选中的批次 id
const selectMode = ref(false)              // 多选模式开关
const isDeleting = ref(false)

function computeChannelsSummary(items) {
  const groups = {}
  for (const it of items || []) {
    const key = it.platform
    if (!groups[key]) {
      const cfg = getPlatformByKey(
        platformList.find(p => p.name === key)?.key
      )
      groups[key] = { platform: key, name: it.platform, count: 0, logo: cfg?.logo || null }
    }
    groups[key].count++
  }
  return Object.values(groups)
}

function statusLabel(status) {
  return ({
    pending: '等待中',
    running: '发布中',
    success: '全部成功',
    partial: '部分失败',
    failed: '全部失败',
    cancelled: '已取消',
  }[status] || status)
}

function formatCardTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = (now - d) / 1000
  if (diff < 86400) {
    if (diff < 60) return '刚刚'
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
    return `${Math.floor(diff / 3600)} 小时前`
  }
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function fetchHistory() {
  loading.value = true
  try {
    const params = { page: currentPage.value, pageSize: pageSize.value }
    if (timeRange.value !== 'all') params.timeRange = timeRange.value
    if (typeFilter.value !== 'all') params.type = typeFilter.value
    if (platformFilter.value !== 'all') params.platform = platformFilter.value
    if (statusFilter.value !== 'all') params.status = statusFilter.value
    const res = await historyApi.getHistory(params)
    if (res.code === 200) {
      batches.value = res.data?.items || []
      total.value = res.data?.total || 0
    }
  } catch (e) {
    console.error('Failed to fetch history:', e)
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  try {
    const res = await statsApi.getStats()
    if (res.code === 200 && res.data) {
      const d = res.data
      stats.value = {
        total: d.total ?? d.tasks?.total ?? 0,
        successRate: d.successRate ?? d.tasks?.successRate ?? 0,
        monthlyTotal: d.monthlyTotal ?? 0,
      }
    }
  } catch (e) {
    console.error('Failed to fetch stats:', e)
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
  if (selectMode.value) selection.value = new Set()
  fetchHistory()
}
const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  if (selectMode.value) selection.value = new Set()
  fetchHistory()
}
const handleFilterChange = () => {
  currentPage.value = 1
  if (selectMode.value) selection.value = new Set()
  fetchHistory()
}

function goDetail(batchId) {
  router.push(`/publish-history/${batchId}`)
}

// ===== 多选操作 =====
const isAllSelected = computed(() => {
  const cnt = batches.value.length
  return cnt > 0 && selection.value.size >= cnt
})
const isIndeterminate = computed(() => {
  return selection.value.size > 0 && selection.value.size < batches.value.length
})

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) {
    selection.value = new Set()
  }
}

function toggleSelectAll(checked) {
  selection.value = checked ? new Set(batches.value.map((b) => b.id)) : new Set()
}

function toggleSelection(id, checked) {
  const next = new Set(selection.value)
  if (checked) next.add(id)
  else next.delete(id)
  selection.value = next
}

function onCardClick(id) {
  if (!selectMode.value) {
    goDetail(id)
    return
  }
  toggleSelection(id, !selection.value.has(id))
}

// ===== 单条删除 =====
async function confirmDelete(batch) {
  const title = batch.title || '无标题'
  try {
    await ElMessageBox.confirm(
      `确定删除发布记录「${title}」吗？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await historyApi.deleteBatch(batch.id)
    ElMessage.success('记录已删除')
    // 本地移除并修正总数
    batches.value = batches.value.filter((b) => b.id !== batch.id)
    total.value = Math.max(0, total.value - 1)
    // 当前页空了且不是第一页时回退一页
    if (batches.value.length === 0 && currentPage.value > 1) {
      currentPage.value -= 1
      fetchHistory()
    } else if (batches.value.length === 0) {
      // 第一页也没有数据,刷新统计
      fetchStats()
    }
  } catch {
    // 错误提示已由响应拦截器处理
  }
}

// ===== 批量删除 =====
async function onBatchDelete() {
  const count = selection.value.size
  if (count === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${count} 条发布记录？此操作不可恢复。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  const ids = [...selection.value]
  isDeleting.value = true
  try {
    const resp = await historyApi.batchDelete(ids)
    const { deleted = [], failed = [] } = resp || {}
    if (deleted.length) {
      ElMessage.success(`已删除 ${deleted.length} 条记录`)
      batches.value = batches.value.filter((b) => !deleted.includes(b.id))
      total.value = Math.max(0, total.value - deleted.length)
    }
    if (failed.length) {
      ElMessage.warning(`${failed.length} 条删除失败：${failed.map((f) => f.reason).join('; ')}`)
    }
    selection.value = new Set()
    // 当前页删空了,回退或刷新
    if (batches.value.length === 0 && currentPage.value > 1) {
      currentPage.value -= 1
      fetchHistory()
    } else if (batches.value.length === 0) {
      fetchStats()
    } else if (deleted.length) {
      fetchStats()
    }
  } catch (e) {
    ElMessage.error(`批量删除失败：${e?.message || e}`)
  } finally {
    isDeleting.value = false
  }
}

onMounted(() => { fetchHistory(); fetchStats() })
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-history-page {
  padding: 0 28px;

  // Page title area
  .page-title {
    font-size: 26px;
    font-weight: 700;
    color: $text-primary;
    margin: 0;
    letter-spacing: -0.5px;
  }

  .page-subtitle {
    font-size: 14px;
    color: $text-muted;
    margin: 4px 0 24px;
  }

  // ========== Stat Cards (3-column) ==========
  .stat-cards {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }

  .stat-card {
    border-radius: $radius-card;
    padding: 20px 24px;
    transition: $transition-base;

    &.stat-purple {
      background: $stat-purple-bg;
      border: 1px solid $stat-purple-border;

      &:hover {
        border-color: rgba($brand-start, 0.35);
        box-shadow: 0 0 24px rgba($brand-start, 0.08);
      }

      .stat-icon {
        background: rgba($brand-start, 0.2);
        .el-icon { color: $brand-start; }
      }
    }

    &.stat-blue {
      background: $stat-blue-bg;
      border: 1px solid $stat-blue-border;

      &:hover {
        border-color: rgba($brand-end, 0.35);
        box-shadow: 0 0 24px rgba($brand-end, 0.08);
      }

      .stat-icon {
        background: rgba($brand-end, 0.2);
        .el-icon { color: $brand-end; }
      }
    }

    &.stat-cyan {
      background: $stat-cyan-bg;
      border: 1px solid $stat-cyan-border;

      &:hover {
        border-color: rgba($accent-cyan, 0.35);
        box-shadow: 0 0 24px rgba($accent-cyan, 0.08);
      }

      .stat-icon {
        background: rgba($accent-cyan, 0.2);
        .el-icon { color: $accent-cyan; }
      }
    }

    .stat-top {
      display: flex;
      align-items: center;
    }

    .stat-icon {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      background: rgba($overlay-rgb, 0.06);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-right: 16px;
      flex-shrink: 0;

      .el-icon {
        font-size: 24px;
      }
    }

    .stat-info {
      .stat-value {
        font-size: 28px;
        font-weight: 700;
        background: $gradient-brand;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        line-height: 1.2;
        letter-spacing: -0.5px;
      }

      .stat-label {
        font-size: 13px;
        color: $text-secondary;
        margin-top: 2px;
      }
    }
  }

  // ========== Filter Toolbar ==========
  .filter-card {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 16px 20px;
    margin-top: 24px;

    .filter-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }

    .filter-controls {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    .filter-select {
      width: 140px;

      :deep(.el-input__wrapper) {
        background: rgba($overlay-rgb, 0.04);
        border: 1px solid $border;
        border-radius: $radius-base;
        box-shadow: none;

        &:hover {
          border-color: $border-active;
        }

        &.is-focus {
          border-color: $brand-start;
        }
      }

      :deep(.el-input__inner) {
        color: $text-secondary;
        font-size: 13px;
      }

      :deep(.el-input__suffix) {
        color: $text-muted;
      }
    }

    .refresh-btn {
      background: rgba($overlay-rgb, 0.04);
      border: 1px solid $border;
      border-radius: $radius-base;
      color: $text-secondary;
      font-size: 13px;

      &:hover {
        border-color: $border-active;
        color: $brand-start;
        background: rgba($brand-start, 0.06);
      }
    }

    .filter-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .select-trigger-btn {
      background: rgba($overlay-rgb, 0.04);
      border: 1px solid $border;
      border-radius: $radius-base;
      color: $text-secondary;
      font-size: 13px;

      &:hover {
        border-color: rgba($brand-start, 0.4);
        color: lighten($brand-start, 12%);
        background: rgba($brand-start, 0.1);
      }

      &.is-disabled,
      &.is-disabled:hover {
        opacity: 0.5;
        background: rgba($overlay-rgb, 0.04);
        border-color: $border;
        color: $text-muted;
      }
    }
  }

  // ========== Batch Operations Toolbar ==========
  .batch-toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 16px;
    flex-wrap: wrap;
    padding: 10px 16px;
    border-radius: $radius-card;
    border: 1px solid $border-active;
    background: linear-gradient(135deg, rgba($brand-start, 0.1), rgba($brand-end, 0.06));
    box-shadow: 0 0 24px rgba($brand-start, 0.08);
    backdrop-filter: blur(8px);
  }

  .toolbar-select-all {
    :deep(.el-checkbox__label) {
      color: $text-secondary;
      font-size: 13px;
    }
  }

  .toolbar-spacer {
    flex: 1;
  }

  .selected-info {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 12px;
    background: linear-gradient(135deg, rgba($brand-start, 0.18), rgba($brand-end, 0.12));
    border: 1px solid rgba($brand-start, 0.25);
    color: lighten($brand-start, 12%);
    font-size: 13px;
    border-radius: 999px;
    font-variant-numeric: tabular-nums;

    .selected-icon {
      font-size: 12px;
      color: $brand-start;
    }

    strong {
      color: $text-primary;
      font-weight: 600;
    }
  }

  .toolbar-exit {
    --el-button-bg-color: rgba($overlay-rgb, 0.03);
    --el-button-border-color: rgba($overlay-rgb, 0.12);
    --el-button-text-color: $text-secondary;
    --el-button-hover-bg-color: rgba($accent-rose, 0.12);
    --el-button-hover-border-color: rgba($accent-rose, 0.4);
    --el-button-hover-text-color: lighten($accent-rose, 8%);
  }

  // ========== Cards Grid ==========
  .cards-grid {
    margin-top: 24px;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
  }

  .batch-card {
    position: relative;
    border: 1px solid $border;
    border-radius: $radius-card;
    background: $bg-elevated;
    overflow: hidden;
    cursor: pointer;
    transition: all 0.2s;
    display: flex;
    flex-direction: column;

    &:hover {
      border-color: rgba($brand-start, 0.5);
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
      transform: translateY(-1px);
    }

    &.select-mode {
      cursor: pointer;
    }

    &.is-selected {
      border-color: rgba($brand-start, 0.8);
      background: linear-gradient(135deg, rgba($brand-start, 0.15), rgba($brand-end, 0.08));
      box-shadow:
        0 0 0 2px $brand-start,
        0 8px 32px rgba($brand-start, 0.35);
      transform: translateY(-2px);

      // 多选模式下隐藏单条删除按钮,避免误触
      .card-delete-btn { display: none; }
    }
  }

  // 单条删除按钮(右上角,hover 显示)
  .card-delete-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 3;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.55);
    backdrop-filter: blur(8px);
    border: none;
    color: rgba($overlay-rgb, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    opacity: 0;
    transition: all 0.2s;
    font-size: 14px;

    &:hover {
      background: rgba($danger-color, 0.9);
      color: #fff;
    }

    .batch-card:hover & {
      opacity: 1;
    }
  }

  // 多选模式下的选择圆圈
  .card-selector {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 3;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(8px);
    border: 2px solid rgba($overlay-rgb, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.25s cubic-bezier(.22,.61,.36,1);
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);

    .selector-icon {
      font-size: 16px;
      font-weight: 900;
      color: white;
      opacity: 0;
      transform: scale(0) rotate(-90deg);
      transition: all 0.25s cubic-bezier(.22,.61,.36,1);
    }

    // 选中状态:以选择圆圈自身的 .is-checked 类为钩子(双保险)
    // (同时也兼容父级 .batch-card.is-selected 钩子)
    &.is-checked,
    .batch-card.is-selected & {
      background: linear-gradient(135deg, #8b5cf6 0%, #3b82f6 100%);
      border-color: rgba($overlay-rgb, 0.95);
      box-shadow:
        0 0 0 3px rgba($brand-start, 0.35),
        0 4px 16px rgba($brand-start, 0.55);
      transform: scale(1.1);

      .selector-icon {
        opacity: 1;
        transform: scale(1) rotate(0deg);
      }
    }

    &:hover {
      border-color: rgba($overlay-rgb, 0.95);
      transform: scale(1.05);
    }
  }

  .card-cover {
    width: 100%;
    aspect-ratio: 16/9;
    background: $bg-surface;
    overflow: hidden;
    position: relative;
    flex-shrink: 0;

    img { width: 100%; height: 100%; object-fit: cover; }

    .cover-placeholder {
      position: absolute; inset: 0;
      display: flex; align-items: center; justify-content: center;
      color: $text-muted;
    }
  }

  .card-body {
    padding: 12px 16px 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .card-title {
    font-size: 14px;
    font-weight: 600;
    color: $text-primary;
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .card-meta {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 12px;
    color: $text-muted;
    flex-wrap: wrap;
  }

  .meta-time {
    font-variant-numeric: tabular-nums;
  }

  .status-tag {
    padding: 1px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;

    &.status-success, &.status-partial {
      background: rgba($accent-green, 0.15); color: #67c23a;
    }
    &.status-failed {
      background: rgba($danger-color, 0.15); color: #f56c6c;
    }
    &.status-running {
      background: rgba($info-color, 0.15); color: #409eff;
    }
    &.status-pending, &.status-cancelled {
      background: rgba(0, 0, 0, 0.06); color: $text-muted;
    }
  }

  .card-stats {
    margin-top: 4px;
  }

  // Empty state
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;

    .empty-icon {
      font-size: 40px;
      color: $text-muted;
      margin-bottom: 12px;
    }

    p {
      font-size: 14px;
      color: $text-muted;
      margin: 0;
    }
  }

  // ========== Pagination ==========
  .pagination-wrapper {
    display: flex;
    justify-content: flex-end;
    margin-top: 20px;
    padding: 16px 20px;
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;

    :deep(.el-pagination) {
      --el-pagination-bg-color: transparent;
      --el-pagination-text-color: #{$text-secondary};
      --el-pagination-button-bg-color: rgba($overlay-rgb, 0.06);
      --el-pagination-hover-color: #{$brand-start};

      .btn-prev,
      .btn-next {
        background: rgba($overlay-rgb, 0.06);
        border: 1px solid $border;
        border-radius: $radius-sm;
        color: $text-secondary;

        &:hover {
          border-color: $border-active;
          color: $brand-start;
        }
      }

      .el-pager li {
        background: rgba($overlay-rgb, 0.04);
        border: 1px solid $border;
        border-radius: $radius-sm;
        color: $text-secondary;
        margin: 0 2px;

        &:hover {
          border-color: $border-active;
          color: $brand-start;
        }

        &.is-active {
          background: $gradient-brand;
          border-color: transparent;
          color: #fff;
        }
      }

      .el-pagination__total {
        color: $text-muted;
      }

      .el-pagination__sizes {
        .el-input__wrapper {
          background: rgba($overlay-rgb, 0.04);
          border: 1px solid $border;
          border-radius: $radius-sm;
          box-shadow: none;

          &:hover {
            border-color: $border-active;
          }
        }

        .el-input__inner {
          color: $text-secondary;
        }
      }
    }
  }
}
</style>
