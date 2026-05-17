<template>
  <div class="publish-history-page">
    <!-- Page title area -->
    <h1 class="page-title">发布历史</h1>
    <p class="page-subtitle">回顾所有发布记录</p>

    <!-- 3 Stat cards row -->
    <div class="stat-cards">
      <!-- 总发布数 (purple) -->
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

      <!-- 成功率 (blue) -->
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

      <!-- 本月发布 (cyan) -->
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
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>
        </div>

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

    <!-- History table -->
    <div class="table-card">
      <el-table
        :data="history"
        style="width: 100%"
        v-loading="loading"
        row-key="id"
        :row-class-name="tableRowClassName"
        @row-click="(row) => toggleRowExpansion(row)"
        ref="historyTableRef"
        class="history-table"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-content">
              <div class="expand-row" v-if="row.description">
                <span class="expand-label">描述:</span>
                <span class="expand-value">{{ row.description }}</span>
              </div>
              <div class="expand-row" v-if="row.tags && row.tags.length">
                <span class="expand-label">标签:</span>
                <div class="expand-tags">
                  <span class="expand-tag" v-for="tag in row.tags" :key="tag">{{ tag }}</span>
                </div>
              </div>
              <div class="expand-row" v-if="row.status === 'failed' && row.error_message">
                <span class="expand-label">错误信息:</span>
                <span class="expand-value error-text">{{ row.error_message }}</span>
              </div>
              <div class="expand-row" v-if="row.status === 'success' && row.publish_url">
                <span class="expand-label">发布链接:</span>
                <a :href="row.publish_url" target="_blank" rel="noopener noreferrer" class="expand-link" @click.stop>
                  {{ row.publish_url }}
                </a>
              </div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="platform" label="平台" width="120">
          <template #default="{ row }">
            <span class="platform-tag" :class="getPlatformClass(row.platform)">
              {{ getPlatformLabel(row.platform) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="account" label="账号" min-width="140">
          <template #default="{ row }">
            <span class="account-cell">{{ row.account || row.account_name || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="title" label="标题" min-width="220">
          <template #default="{ row }">
            <span class="title-cell">{{ row.title || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <span class="status-tag" :class="row.status === 'success' ? 'status-success' : 'status-failed'">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="publish_time" label="发布时间" width="180">
          <template #default="{ row }">
            <span class="time-cell">{{ row.publish_time || row.created_at || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="duration" label="耗时" width="100">
          <template #default="{ row }">
            <span class="duration-cell">{{ formatDuration(row.duration) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- Empty state -->
      <div v-if="!loading && history.length === 0" class="empty-state">
        <el-icon class="empty-icon"><Clock /></el-icon>
        <p>暂无发布记录</p>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Upload, CircleCheck, Calendar, Refresh, Clock } from '@element-plus/icons-vue'
import { historyApi, statsApi } from '@/api/v2'
import { platformList } from '@/config/platforms'

const history = ref([])
const stats = ref({ total: 0, successRate: 0, monthlyTotal: 0 })
const loading = ref(false)
const historyTableRef = ref(null)

// Filters
const timeRange = ref('all')
const platformFilter = ref('all')
const statusFilter = ref('all')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// Fetch history
const fetchHistory = async () => {
  loading.value = true
  try {
    const params = { page: currentPage.value, pageSize: pageSize.value }
    if (timeRange.value !== 'all') params.timeRange = timeRange.value
    if (platformFilter.value !== 'all') params.platform = platformFilter.value
    if (statusFilter.value !== 'all') params.status = statusFilter.value
    const res = await historyApi.getHistory(params)
    if (res.code === 200) {
      const items = res.data?.items || res.data?.list
      history.value = Array.isArray(items) ? items : []
      total.value = res.data?.total || 0
    }
  } catch (e) {
    console.error('Failed to fetch history:', e)
  } finally {
    loading.value = false
  }
}

// Fetch stats
const fetchStats = async () => {
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
  fetchHistory()
}

const handleSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  fetchHistory()
}

const handleFilterChange = () => {
  currentPage.value = 1
  fetchHistory()
}

// Toggle row expansion on click
const expandedRows = ref(new Set())
const toggleRowExpansion = (row) => {
  if (!historyTableRef.value) return
  historyTableRef.value.toggleRowExpansion(row)
}

// Row class name based on status
const tableRowClassName = ({ row }) => {
  if (row.status === 'success') return 'row-success'
  if (row.status === 'failed') return 'row-failed'
  return ''
}

// Platform helpers
const platformMap = Object.fromEntries(
  platformList.map(p => [p.key, { label: p.name, class: `tag-${p.cssClass}` }])
)

const getPlatformLabel = (platform) => {
  return platformMap[platform]?.label || platform || '-'
}

const getPlatformClass = (platform) => {
  return platformMap[platform]?.class || ''
}

// Duration formatter
const formatDuration = (seconds) => {
  if (!seconds && seconds !== 0) return '-'
  if (seconds < 60) return `${seconds}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`
}

onMounted(() => {
  fetchHistory()
  fetchStats()
})
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
      background: rgba(255, 255, 255, 0.06);
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
        background: rgba(255, 255, 255, 0.04);
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
      background: rgba(255, 255, 255, 0.04);
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
  }

  // ========== History Table ==========
  .table-card {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 24px;
    margin-top: 24px;
    max-height: calc(100vh - 280px);
    overflow-y: auto;

    &::-webkit-scrollbar {
      width: 6px;
    }

    &::-webkit-scrollbar-thumb {
      background: $border;
      border-radius: 3px;
    }

    .history-table {
      --el-table-bg-color: transparent;
      --el-table-tr-bg-color: transparent;
      --el-table-header-bg-color: transparent;
      --el-table-row-hover-bg-color: rgba(255, 255, 255, 0.03);
      --el-table-border-color: #{$border};
      --el-table-text-color: #{$text-secondary};
      --el-table-header-text-color: #{$text-muted};

      :deep(.el-table__inner-wrapper) {
        &::before {
          display: none;
        }
      }

      :deep(th.el-table__cell) {
        background: transparent !important;
        font-weight: 500;
        font-size: 13px;
        border-bottom: 1px solid $border;
      }

      :deep(td.el-table__cell) {
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      }

      :deep(.el-table__empty-block) {
        background: transparent;
      }

      // Row status borders
      :deep(.el-table__row) {
        cursor: pointer;
        transition: $transition-base;

        &.row-success {
          border-left: 3px solid $success-color;
        }

        &.row-failed {
          border-left: 3px solid $danger-color;
        }
      }

      // Expand icon styling
      :deep(.el-table__expand-icon) {
        color: $text-muted;
        transition: $transition-base;

        &:hover {
          color: $brand-start;
        }
      }

      // Expanded row content area
      :deep(.el-table__expanded-cell) {
        background: rgba(255, 255, 255, 0.02);
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      }
    }

    // Platform tags
    .platform-tag {
      display: inline-flex;
      align-items: center;
      padding: 3px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;

      &.tag-douyin {
        color: $platform-douyin;
        background: $platform-douyin-bg;
      }

      &.tag-kuaishou {
        color: $platform-kuaishou;
        background: $platform-kuaishou-bg;
      }

      &.tag-channels {
        color: $platform-channels;
        background: $platform-channels-bg;
      }

      &.tag-xiaohongshu {
        color: $platform-xiaohongshu;
        background: $platform-xiaohongshu-bg;
      }

      &.tag-bilibili {
        color: $platform-bilibili;
        background: $platform-bilibili-bg;
      }
    }

    // Status tags
    .status-tag {
      display: inline-flex;
      align-items: center;
      padding: 3px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;

      &.status-success {
        color: $success-color;
        background: rgba($success-color, 0.12);
      }

      &.status-failed {
        color: $danger-color;
        background: rgba($danger-color, 0.12);
      }
    }

    .account-cell {
      color: $text-primary;
      font-weight: 500;
    }

    .title-cell {
      color: $text-primary;
      font-weight: 500;
    }

    .time-cell {
      color: $text-secondary;
      font-size: 13px;
    }

    .duration-cell {
      color: $text-secondary;
      font-size: 13px;
    }

    // Expand content
    .expand-content {
      padding: 12px 20px 12px 50px;
    }

    .expand-row {
      display: flex;
      align-items: flex-start;
      margin-bottom: 8px;
      font-size: 13px;

      &:last-child {
        margin-bottom: 0;
      }
    }

    .expand-label {
      color: $text-muted;
      min-width: 70px;
      flex-shrink: 0;
      margin-right: 8px;
    }

    .expand-value {
      color: $text-secondary;
      line-height: 1.5;

      &.error-text {
        color: $danger-color;
      }
    }

    .expand-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .expand-tag {
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 12px;
      color: $text-secondary;
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .expand-link {
      color: $brand-start;
      text-decoration: none;
      font-size: 13px;
      word-break: break-all;

      &:hover {
        color: $brand-end;
        text-decoration: underline;
      }
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

    // Pagination
    .pagination-wrapper {
      display: flex;
      justify-content: flex-end;
      margin-top: 20px;
      padding-top: 16px;
      border-top: 1px solid rgba(255, 255, 255, 0.04);

      :deep(.el-pagination) {
        --el-pagination-bg-color: transparent;
        --el-pagination-text-color: #{$text-secondary};
        --el-pagination-button-bg-color: rgba(255, 255, 255, 0.06);
        --el-pagination-hover-color: #{$brand-start};

        .btn-prev,
        .btn-next {
          background: rgba(255, 255, 255, 0.06);
          border: 1px solid $border;
          border-radius: $radius-sm;
          color: $text-secondary;

          &:hover {
            border-color: $border-active;
            color: $brand-start;
          }
        }

        .el-pager li {
          background: rgba(255, 255, 255, 0.04);
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
            background: rgba(255, 255, 255, 0.04);
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
}
</style>
