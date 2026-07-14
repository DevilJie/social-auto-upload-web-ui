<template>
  <div class="changelog-page">
    <div class="changelog-header">
      <h2>更新日志</h2>
      <span class="changelog-count">{{ logs.length }} 条记录</span>
    </div>

    <div v-if="!loading && logs.length === 0" class="empty-state">
      <el-empty description="暂无更新日志" />
    </div>

    <div v-else class="changelog-list">
      <div
        v-for="log in logs"
        :key="log.filename"
        class="changelog-card"
        @click="openLog(log)"
      >
        <div class="card-date">
          <span class="date-day">{{ formatDay(log.date) }}</span>
          <span class="date-month">{{ formatMonth(log.date) }}</span>
        </div>
        <div class="card-info">
          <div class="card-title">更新日志 {{ log.date }}</div>
          <div class="card-hint">点击查看详情</div>
        </div>
        <el-icon class="card-arrow"><ArrowRight /></el-icon>
      </div>
    </div>

    <!-- 日志详情弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="80%"
      top="5vh"
      destroy-on-close
      class="changelog-dialog"
    >
      <div class="iframe-wrap">
        <iframe
          v-if="dialogVisible"
          :src="dialogUrl"
          frameborder="0"
          class="changelog-iframe"
        ></iframe>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import { changelogApi } from '@/api/changelog'

const logs = ref([])
const loading = ref(true)
const dialogVisible = ref(false)
const dialogTitle = ref('')
const dialogUrl = ref('')

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

function formatDay(dateStr) {
  if (!dateStr) return ''
  return dateStr.split('-')[2]
}

function formatMonth(dateStr) {
  if (!dateStr) return ''
  const months = ['一月', '二月', '三月', '四月', '五月', '六月', '七月', '八月', '九月', '十月', '十一月', '十二月']
  const month = parseInt(dateStr.split('-')[1], 10)
  return months[month - 1] || ''
}

function openLog(log) {
  dialogTitle.value = `更新日志 ${log.date}`
  dialogUrl.value = `${apiBaseUrl}${log.url}`
  dialogVisible.value = true
}

async function loadChangelog() {
  loading.value = true
  try {
    const resp = await changelogApi.getChangelogList()
    logs.value = resp.data || []
  } catch (e) {
    console.error('Failed to load changelog:', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadChangelog)
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.changelog-page {
  padding: 24px;
  min-height: 100%;
}

.changelog-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;

  h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    color: $text-primary;
  }

  .changelog-count {
    font-size: 13px;
    color: $text-muted;
  }
}

.empty-state {
  display: flex;
  justify-content: center;
  padding: 80px 0;
}

.changelog-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.changelog-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: rgba($overlay-rgb, 0.04);
  border: 1px solid $border;
  border-radius: $radius-lg;
  cursor: pointer;
  transition: $transition-base;

  &:hover {
    border-color: rgba($overlay-rgb, 0.15);
    background: rgba($overlay-rgb, 0.06);
  }
}

.card-date {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 48px;

  .date-day {
    font-size: 24px;
    font-weight: 700;
    color: $text-primary;
    line-height: 1;
  }

  .date-month {
    font-size: 12px;
    color: $text-muted;
    margin-top: 4px;
  }
}

.card-info {
  flex: 1;

  .card-title {
    font-size: 14px;
    font-weight: 500;
    color: $text-primary;
  }

  .card-hint {
    font-size: 12px;
    color: $text-muted;
    margin-top: 4px;
  }
}

.card-arrow {
  color: $text-muted;
  font-size: 16px;
}

.iframe-wrap {
  width: 100%;
  height: 70vh;
  border-radius: 8px;
  overflow: hidden;
  background: #0F172A;
}

.changelog-iframe {
  width: 100%;
  height: 100%;
  border: none;
}
</style>
