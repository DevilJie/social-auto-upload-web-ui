<template>
  <div class="publish-calendar">
    <div class="cal-toolbar">
      <div class="cal-title">
        发布日历
        <span class="cal-sub">按批次展示：待发布看预定时点，已发布看创建时间</span>
      </div>
      <div class="cal-actions">
        <el-radio-group v-model="statusFilter" size="small" @change="render">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="pending">待发布</el-radio-button>
          <el-radio-button value="success">成功</el-radio-button>
          <el-radio-button value="failed">失败</el-radio-button>
        </el-radio-group>
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
      </div>
    </div>

    <div class="cal-legend">
      <span class="lg"><i class="dot pending" /> 待发布（定时/间隔排程）</span>
      <span class="lg"><i class="dot success" /> 成功</span>
      <span class="lg"><i class="dot partial" /> 部分成功</span>
      <span class="lg"><i class="dot failed" /> 失败</span>
      <span class="lg hint">点击条目查看批次详情</span>
    </div>

    <el-calendar v-model="currentDate" class="cal-body">
      <template #date-cell="{ data }">
        <div class="cal-cell">
          <div class="cal-day">{{ data.day.split('-')[2] }}</div>
          <div class="cal-events">
            <div
              v-for="it in itemsOfDay(data.day)"
              :key="it.id"
              class="cal-evt"
              :class="it.status"
              :title="tooltip(it)"
              @click.stop="openDetail(it)"
            >
              <i class="dot" :class="it.status" />
              <span class="evt-time" v-if="it.time">{{ it.time }}</span>
              <span class="evt-title">{{ it.title || '未命名批次' }}</span>
            </div>
          </div>
        </div>
      </template>
    </el-calendar>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { historyApi } from '../api/v2'

const router = useRouter()
const currentDate = ref(new Date())
const loading = ref(false)
const statusFilter = ref('')
const batches = ref([])

const STATUS_TEXT = { pending: '待发布', success: '成功', partial: '部分成功', failed: '失败' }

/** scheduled_at / created_at -> 'YYYY-MM-DD HH:mm'（后端已是北京时间） */
function toDateParts(raw) {
  if (!raw) return null
  const s = String(raw).replace('T', ' ')
  const m = s.match(/^(\d{4}-\d{2}-\d{2})(?:[ ](\d{2}:\d{2}))?/)
  if (!m) return null
  return { day: m[1], time: m[2] || '' }
}

const events = computed(() => {
  const list = []
  for (const b of batches.value) {
    if (statusFilter.value && b.status !== statusFilter.value) continue
    // 待发布且已排程：看预定时点；其余看创建时间
    const useSchedule = b.status === 'pending' && b.scheduled_at
    const parts = toDateParts(useSchedule ? b.scheduled_at : b.created_at)
    if (!parts) continue
    list.push({
      id: b.id,
      title: b.title || '',
      status: b.status || 'pending',
      day: parts.day,
      time: parts.time,
      scheduled: useSchedule,
      accountCount: b.account_count || 0,
    })
  }
  return list
})

const byDay = computed(() => {
  const map = new Map()
  for (const e of events.value) {
    if (!map.has(e.day)) map.set(e.day, [])
    map.get(e.day).push(e)
  }
  for (const arr of map.values()) {
    arr.sort((a, b) => String(a.time).localeCompare(String(b.time)))
  }
  return map
})

function itemsOfDay(day) {
  return byDay.value.get(day) || []
}

function tooltip(it) {
  const when = it.scheduled ? `预定 ${it.day} ${it.time}` : `创建于 ${it.day} ${it.time}`
  return `${it.title || '未命名批次'}\n状态：${STATUS_TEXT[it.status] || it.status}\n${when}\n账号数：${it.accountCount}`
}

function openDetail(it) {
  router.push(`/publish-history/${it.id}`)
}

async function load() {
  loading.value = true
  try {
    // 待发布（含定时/间隔排程）单拉一次，避免被分页挤出
    const [pendingRes, recentRes] = await Promise.all([
      historyApi.getHistory({ status: 'pending', page: 1, pageSize: 100 }),
      historyApi.getHistory({ page: 1, pageSize: 200 }),
    ])
    const merge = new Map()
    for (const list of [pendingRes?.data?.items || [], recentRes?.data?.items || []]) {
      for (const b of list) if (b && b.id) merge.set(b.id, b)
    }
    batches.value = [...merge.values()]
  } catch (e) {
    console.error('[发布日历] 加载失败', e)
  } finally {
    loading.value = false
  }
}

function render() {}

onMounted(load)
</script>

<style scoped>
.publish-calendar {
  padding: 4px 2px;
}
.cal-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.cal-title {
  font-size: 16px;
  font-weight: 600;
}
.cal-sub {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 400;
  opacity: 0.6;
}
.cal-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cal-legend {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 12px;
  opacity: 0.85;
  margin-bottom: 6px;
}
.cal-legend .lg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cal-legend .hint {
  opacity: 0.55;
}
.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-color-primary);
}
.dot.pending { background: var(--el-color-warning); }
.dot.success { background: var(--el-color-success); }
.dot.partial { background: var(--el-color-primary); }
.dot.failed { background: var(--el-color-danger); }

.cal-body :deep(.el-calendar-table .el-calendar-day) {
  height: auto;
  min-height: 96px;
  padding: 4px;
}
.cal-cell {
  height: 100%;
  min-height: 88px;
}
.cal-day {
  font-size: 12px;
  opacity: 0.7;
  margin-bottom: 2px;
}
.cal-events {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cal-evt {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  line-height: 1.5;
  padding: 1px 4px;
  border-radius: 4px;
  cursor: pointer;
  background: color-mix(in srgb, var(--el-color-primary) 8%, transparent);
}
.cal-evt:hover {
  background: color-mix(in srgb, var(--el-color-primary) 16%, transparent);
}
.cal-evt.pending { background: color-mix(in srgb, var(--el-color-warning) 10%, transparent); }
.cal-evt.success { background: color-mix(in srgb, var(--el-color-success) 10%, transparent); }
.cal-evt.failed { background: color-mix(in srgb, var(--el-color-danger) 10%, transparent); }
.evt-time {
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
  flex-shrink: 0;
}
.evt-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
