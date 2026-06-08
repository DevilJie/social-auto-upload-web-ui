<template>
  <div class="task-center-page">
    <div class="page-header">
      <h1>任务中心</h1>
      <p class="page-subtitle">查看和管理发布任务</p>
    </div>

    <!-- Queue status bar -->
    <div class="queue-status-bar">
      <div class="queue-status-item">
        <span class="queue-label">活跃 Worker:</span>
        <span class="queue-value active">{{ queueStatus.active || 0 }}</span>
      </div>
      <div class="queue-divider"></div>
      <div class="queue-status-item">
        <span class="queue-label">等待中:</span>
        <span class="queue-value waiting">{{ queueStatus.waiting || 0 }}</span>
      </div>
    </div>

    <div class="task-container">
      <div class="task-toolbar">
        <div class="toolbar-left">
          <div class="status-filters">
            <div v-for="f in filterOptions" :key="f.value"
              :class="['filter-chip', { active: activeFilter === f.value }]"
              @click="activeFilter = f.value">
              {{ f.label }}
            </div>
          </div>
        </div>
        <div class="toolbar-right">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索标题或账号"
            prefix-icon="Search"
            clearable
            style="width: 240px"
          />
          <el-button @click="handleRefresh" :loading="loading">
            <el-icon v-if="!loading"><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div v-if="filteredTasks.length > 0" class="task-list">
        <el-table :data="paginatedTasks" style="width: 100%">
          <el-table-column label="任务ID" width="100">
            <template #default="scope">
              <span class="task-id">{{ shortId(scope.row.id) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="platform" label="平台" width="110">
            <template #default="scope">
              <span :class="['platform-tag', getPlatformClass(scope.row.platform)]">
                {{ scope.row.platform }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="account_name" label="账号" width="140">
            <template #default="scope">
              <span class="account-name">{{ scope.row.account_name || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="batch_title" label="批次标题" min-width="200">
            <template #default="scope">
              <span class="task-title" :title="scope.row.batch_title">{{ scope.row.batch_title || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="110">
            <template #default="scope">
              <span :class="['status-tag', getStatusClass(scope.row.status)]">
                {{ scope.row.status }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="scope">
              <span class="time-text">{{ formatTime(scope.row.created_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <div class="action-cell">
                <button v-if="scope.row.status === '排队中' || scope.row.status === '发布中'"
                  class="action-btn danger" @click="handleCancel(scope.row)">取消</button>
                <button v-else-if="scope.row.status === '失败'"
                  class="action-btn primary" @click="handleRetry(scope.row)">重试</button>
                <button v-else-if="scope.row.status === '成功'"
                  class="action-btn disabled" disabled>查看</button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-wrapper" v-if="totalPages > 1">
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="filteredTasks.length"
            layout="prev, pager, next"
            background
            small
          />
        </div>
      </div>

      <div v-else class="empty-data">
        <div class="empty-state">
          <el-icon class="empty-icon"><List /></el-icon>
          <p class="empty-text">{{ searchKeyword || activeFilter !== 'all' ? '未找到匹配的任务' : '暂无任务数据' }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { Refresh, List } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { taskApi } from '@/api/v2'
import { platformCssMap } from '@/config/platforms'

const tasks = ref([])
const loading = ref(false)
const activeFilter = ref('all')
const searchKeyword = ref('')
const queueStatus = ref({ active: 0, waiting: 0 })
const currentPage = ref(1)
const pageSize = 15

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '排队中', value: '排队中' },
  { label: '发布中', value: '发布中' },
  { label: '成功', value: '成功' },
  { label: '失败', value: '失败' },
]

// Fetch tasks
const fetchTasks = async () => {
  loading.value = true
  try {
    const res = await taskApi.getTasks()
    if (res.code === 200) tasks.value = res.data || []
  } catch (e) {
    console.error('获取任务列表失败:', e)
  } finally {
    loading.value = false
  }
}

// Fetch queue status
const fetchQueueStatus = async () => {
  try {
    const res = await taskApi.getQueueStatus()
    if (res.code === 200) queueStatus.value = res.data || { active: 0, waiting: 0 }
  } catch (e) {
    console.error('获取队列状态失败:', e)
  }
}

// SSE connection for real-time updates
let eventSource = null
const connectSSE = () => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  eventSource = new EventSource(`${baseUrl}/api/v2/tasks/stream`)
  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      const idx = tasks.value.findIndex(t => t.id === data.id)
      if (idx !== -1) {
        tasks.value[idx] = { ...tasks.value[idx], ...data }
      } else {
        // New task, prepend to list
        tasks.value.unshift(data)
      }
      // Refresh queue status on updates
      fetchQueueStatus()
    } catch (err) {
      // Ignore parse errors
    }
  }
  eventSource.onerror = () => {
    eventSource?.close()
    eventSource = null
  }
}

// Filtered tasks
const filteredTasks = computed(() => {
  let result = tasks.value
  if (activeFilter.value !== 'all') {
    result = result.filter(t => t.status === activeFilter.value)
  }
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    result = result.filter(t =>
      (t.batch_title || '').toLowerCase().includes(kw) ||
      (t.account_name || '').toLowerCase().includes(kw)
    )
  }
  return result
})

// Pagination
const totalPages = computed(() => Math.ceil(filteredTasks.value.length / pageSize))
const paginatedTasks = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredTasks.value.slice(start, start + pageSize)
})

// Actions
const handleCancel = async (task) => {
  try {
    await taskApi.cancelTask(task.id)
    ElMessage.success('任务已取消')
    fetchTasks()
    fetchQueueStatus()
  } catch (e) {
    console.error('取消任务失败:', e)
    ElMessage.error('取消任务失败')
  }
}

const handleRetry = async (task) => {
  try {
    await taskApi.retryTask(task.id)
    ElMessage.success('任务已重新提交')
    fetchTasks()
    fetchQueueStatus()
  } catch (e) {
    console.error('重试任务失败:', e)
    ElMessage.error('重试任务失败')
  }
}

const handleRefresh = () => {
  fetchTasks()
  fetchQueueStatus()
}

// Helpers
const shortId = (id) => {
  if (!id) return '-'
  const str = String(id)
  return str.length > 8 ? str.slice(0, 8) : str
}

const getPlatformClass = (platform) => {
  return platformCssMap[platform] || ''
}

const getStatusClass = (status) => {
  const classMap = {
    '排队中': 'pending',
    '发布中': 'running',
    '成功': 'success',
    '失败': 'failed',
  }
  return classMap[status] || ''
}

const formatTime = (time) => {
  if (!time) return '-'
  try {
    const d = new Date(time)
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return time
  }
}

onMounted(() => {
  fetchTasks()
  fetchQueueStatus()
  connectSSE()
})

onBeforeUnmount(() => {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.task-center-page {
  .page-header {
    margin-bottom: 24px;

    h1 {
      font-size: 26px;
      font-weight: 700;
      color: $text-primary;
      margin: 0;
      letter-spacing: -0.5px;
    }

    .page-subtitle {
      margin: 6px 0 0;
      font-size: 14px;
      color: $text-muted;
      font-weight: 400;
    }
  }

  // Queue status bar
  .queue-status-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 12px 20px;
    margin-bottom: 16px;
    background: $gradient-brand-subtle;
    border: 1px solid $border-active;
    border-radius: $radius-card;

    .queue-status-item {
      display: flex;
      align-items: center;
      gap: 6px;

      .queue-label {
        font-size: 13px;
        color: $text-secondary;
      }

      .queue-value {
        font-size: 14px;
        font-weight: 600;

        &.active {
          color: $success-color;
        }

        &.waiting {
          color: $info-color;
        }
      }
    }

    .queue-divider {
      width: 1px;
      height: 16px;
      background: $border;
    }
  }

  .task-container {
    background-color: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 4px 24px 24px;

    .task-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      gap: 16px;

      .toolbar-left {
        display: flex;
        align-items: center;
        gap: 16px;
        flex: 1;
      }

      .toolbar-right {
        display: flex;
        gap: 10px;
        flex-shrink: 0;
      }
    }

    // Status filter chips
    .status-filters {
      display: flex;
      gap: 8px;
      align-items: center;

      .filter-chip {
        padding: 6px 16px;
        border-radius: $radius-base;
        border: 1px solid $border;
        background: transparent;
        color: $text-secondary;
        font-size: 13px;
        cursor: pointer;
        transition: $transition-base;
        white-space: nowrap;
        user-select: none;

        &:hover {
          border-color: $border-active;
          color: $text-primary;
        }

        &.active {
          background: $gradient-brand-subtle;
          border-color: $border-active;
          color: $text-primary;
          font-weight: 500;
        }
      }
    }

    // Task table
    .task-list {
      :deep(.el-table) {
        --el-table-bg-color: transparent;
        --el-table-tr-bg-color: transparent;
        --el-table-header-bg-color: transparent;
        --el-table-row-hover-bg-color: rgba(255, 255, 255, 0.03);
        --el-table-border-color: #{$border};
        --el-table-text-color: #{$text-primary};
        --el-table-header-text-color: #{$text-secondary};

        th.el-table__cell {
          font-weight: 500;
          font-size: 13px;
          border-bottom-color: $border;
        }

        td.el-table__cell {
          border-bottom-color: $border;
        }
      }

      .task-id {
        font-family: 'SF Mono', 'Fira Code', monospace;
        font-size: 12px;
        color: $text-muted;
        background: rgba(255, 255, 255, 0.04);
        padding: 2px 6px;
        border-radius: 4px;
      }

      .account-name {
        font-weight: 500;
        color: $text-primary;
      }

      .task-title {
        color: $text-primary;
        display: -webkit-box;
        -webkit-line-clamp: 1;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .time-text {
        font-size: 13px;
        color: $text-secondary;
      }

      // Platform tags
      .platform-tag {
        display: inline-flex;
        align-items: center;
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
        line-height: 1.5;
        white-space: nowrap;

        &.douyin {
          background: $platform-douyin-bg;
          color: $platform-douyin;
        }

        &.kuaishou {
          background: $platform-kuaishou-bg;
          color: $platform-kuaishou;
        }

        &.channels {
          background: $platform-channels-bg;
          color: $platform-channels;
        }

        &.xiaohongshu {
          background: $platform-xiaohongshu-bg;
          color: $platform-xiaohongshu;
        }

        &.bilibili {
          background: $platform-bilibili-bg;
          color: $platform-bilibili;
        }
      }

      // Status tags
      .status-tag {
        display: inline-flex;
        align-items: center;
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
        line-height: 1.5;
        white-space: nowrap;

        &.pending {
          background: rgba(59, 130, 246, 0.15);
          color: $info-color;
        }

        &.running {
          background: rgba(139, 92, 246, 0.15);
          color: $brand-start;
          animation: pulse 2s ease-in-out infinite;
        }

        &.success {
          background: rgba(34, 197, 94, 0.15);
          color: $success-color;
        }

        &.failed {
          background: rgba(239, 68, 68, 0.15);
          color: $danger-color;
        }
      }

      // Action buttons
      .action-cell {
        display: flex;
        align-items: center;
        gap: 4px;

        .action-btn {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 4px 10px;
          border: none;
          border-radius: $radius-sm;
          background: transparent;
          color: $text-secondary;
          font-size: 13px;
          cursor: pointer;
          transition: $transition-base;

          &:hover {
            color: $text-primary;
            background: rgba(255, 255, 255, 0.06);
          }

          &.primary:hover {
            color: $brand-end;
            background: rgba(59, 130, 246, 0.1);
          }

          &.danger:hover {
            color: $danger-color;
            background: rgba(239, 68, 68, 0.1);
          }

          &.disabled {
            opacity: 0.4;
            cursor: not-allowed;

            &:hover {
              color: $text-secondary;
              background: transparent;
            }
          }
        }
      }
    }

    // Pagination
    .pagination-wrapper {
      display: flex;
      justify-content: center;
      margin-top: 20px;

      :deep(.el-pagination) {
        --el-pagination-bg-color: transparent;
        --el-pagination-text-color: #{$text-secondary};
        --el-pagination-button-bg-color: transparent;
        --el-pagination-hover-color: #{$text-primary};

        .btn-prev, .btn-next {
          background: transparent;
          border: 1px solid $border;
          border-radius: $radius-sm;
        }

        .el-pager li {
          background: transparent;
          border: 1px solid $border;
          border-radius: $radius-sm;

          &.is-active {
            background: $gradient-brand-subtle;
            border-color: $border-active;
            color: $text-primary;
          }
        }
      }
    }

    // Empty state
    .empty-data {
      padding: 60px 0;

      .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 12px;

        .empty-icon {
          font-size: 48px;
          color: $text-muted;
        }

        .empty-text {
          font-size: 14px;
          color: $text-secondary;
          margin: 0;
        }
      }
    }
  }
}
</style>
