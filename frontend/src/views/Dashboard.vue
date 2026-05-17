<template>
  <div class="dashboard">
    <!-- Page title area -->
    <h1 class="page-title">仪表盘</h1>
    <p class="page-subtitle">数据概览与快捷操作</p>

    <!-- 4 Stat cards row -->
    <div class="stat-cards">
      <!-- 账号总数 (purple) -->
      <div class="stat-card stat-purple">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><User /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ accountStats.total }}</div>
            <div class="stat-label">账号总数</div>
          </div>
          <button class="batch-check-btn" @click="handleBatchCheck" :disabled="isChecking">
            <el-icon v-if="isChecking" class="is-loading"><Loading /></el-icon>
            <template v-else>
              <el-icon><Refresh /></el-icon>
              批量检查
            </template>
          </button>
        </div>
        <div class="stat-bottom">
          <div class="stat-detail">
            <span>正常: {{ accountStats.normal }}</span>
            <span class="divider"></span>
            <span>异常: {{ accountStats.abnormal }}</span>
          </div>
        </div>
      </div>

      <!-- 已接入平台 (blue) -->
      <div class="stat-card stat-blue">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><Platform /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ platformStats.total }}</div>
            <div class="stat-label">已接入平台</div>
          </div>
        </div>
        <div class="stat-bottom">
          <div class="stat-detail platform-tags">
            <span v-for="p in platformList" :key="p.id" :class="['platform-tag', p.cssClass]">
              {{ p.name }} {{ platformStats[p.cssClass] || 0 }}
            </span>
          </div>
        </div>
      </div>

      <!-- 素材总数 (cyan) -->
      <div class="stat-card stat-cyan">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><Document /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">{{ contentStats.total }}</div>
            <div class="stat-label">素材总数</div>
          </div>
        </div>
        <div class="stat-bottom">
          <div class="stat-detail">
            <span>视频: {{ contentStats.videos }}</span>
            <span class="divider"></span>
            <span>图片: {{ contentStats.images }}</span>
            <span class="divider"></span>
            <span>其他: {{ contentStats.others }}</span>
          </div>
        </div>
      </div>

      <!-- 今日发布 (green) -->
      <div class="stat-card stat-green">
        <div class="stat-top">
          <div class="stat-icon">
            <el-icon><Upload /></el-icon>
          </div>
          <div class="stat-info">
            <div class="stat-value">&mdash;</div>
            <div class="stat-label">今日发布</div>
          </div>
        </div>
        <div class="stat-bottom">
          <div class="stat-detail">
            <span>成功率: &mdash;</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Quick actions row -->
    <div class="quick-actions">
      <div class="action-card" @click="navigateTo('/publish-center')">
        <div class="action-icon action-icon-purple">
          <el-icon><Upload /></el-icon>
        </div>
        <div class="action-title">快速发布</div>
        <div class="action-desc">发布内容到各平台</div>
      </div>
      <div class="action-card" @click="navigateTo('/material-management')">
        <div class="action-icon action-icon-blue">
          <el-icon><Document /></el-icon>
        </div>
        <div class="action-title">上传素材</div>
        <div class="action-desc">上传和管理视频素材</div>
      </div>
      <div class="action-card" @click="navigateTo('/settings')">
        <div class="action-icon action-icon-cyan">
          <el-icon><Setting /></el-icon>
        </div>
        <div class="action-title">系统设置</div>
        <div class="action-desc">配置系统参数和选项</div>
      </div>
      <div class="action-card" @click="navigateTo('/account-management')">
        <div class="action-icon action-icon-green">
          <el-icon><UserFilled /></el-icon>
        </div>
        <div class="action-title">账号管理</div>
        <div class="action-desc">管理所有平台账号</div>
      </div>
    </div>

    <!-- Recent materials table -->
    <div class="materials-card">
      <div class="materials-header">
        <h2>最近素材</h2>
        <a class="view-all-link" @click="navigateTo('/material-management')">查看全部</a>
      </div>

      <el-table
        :data="recentMaterials"
        style="width: 100%"
        v-loading="loading"
        :header-cell-style="{ background: 'transparent', borderBottom: `1px solid ${$options.borderColor}` }"
        class="materials-table"
      >
        <el-table-column prop="filename" label="文件名" min-width="260">
          <template #default="scope">
            <span class="filename-cell">{{ scope.row.filename }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="filesize" label="大小" width="120">
          <template #default="scope">
            <span class="size-cell">{{ scope.row.filesize }} MB</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="100">
          <template #default="scope">
            <span
              class="type-tag"
              :class="{
                'type-video': getFileType(scope.row.filename) === '视频',
                'type-image': getFileType(scope.row.filename) === '图片',
                'type-other': getFileType(scope.row.filename) === '其他'
              }"
            >
              {{ getFileType(scope.row.filename) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="upload_time" label="上传时间" width="200">
          <template #default="scope">
            <span class="time-cell">{{ scope.row.upload_time }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && recentMaterials.length === 0" class="empty-state">
        暂无素材数据
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  User, UserFilled, Platform, Document,
  Upload, Timer, DataAnalysis, Loading, Refresh, Setting
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { accountApi } from '@/api/account'
import { materialApi } from '@/api/material'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { platformList } from '@/config/platforms'

const router = useRouter()
const accountStore = useAccountStore()
const appStore = useAppStore()
const loading = ref(false)
const isChecking = ref(false)

// 批量检查账号
const handleBatchCheck = async () => {
  if (isChecking.value) return
  isChecking.value = true
  try {
    const res = await accountApi.getValidAccounts()
    if (res.code === 200 && res.data) {
      accountStore.setAccounts(res.data)
      ElMessage.success('账号检查完成')
    } else {
      ElMessage.error(res.msg || '检查失败')
    }
  } catch (error) {
    console.error('批量检查失败:', error)
    ElMessage.error('批量检查失败')
  } finally {
    isChecking.value = false
  }
}

// 账号统计数据 - 从真实数据计算
const accountStats = computed(() => {
  const accounts = accountStore.accounts
  const normal = accounts.filter(a => a.status === '正常').length
  const abnormal = accounts.filter(a => a.status !== '正常' && a.status !== '验证中').length
  return {
    total: accounts.length,
    normal,
    abnormal
  }
})

// 平台统计数据 - 从真实数据计算
const platformStats = computed(() => {
  const accounts = accountStore.accounts
  const counts = {}
  platformList.forEach(p => {
    counts[p.cssClass] = accounts.filter(a => a.platform === p.name).length
  })
  // 统计有账号的平台数量
  const total = platformList.filter(p => counts[p.cssClass] > 0).length
  return { total, ...counts }
})

// 素材统计数据 - 从真实数据计算
const videoExtensions = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv']
const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']

const contentStats = computed(() => {
  const materials = appStore.materials
  const videos = materials.filter(m => videoExtensions.some(ext => m.filename.toLowerCase().endsWith(ext))).length
  const images = materials.filter(m => imageExtensions.some(ext => m.filename.toLowerCase().endsWith(ext))).length
  return {
    total: materials.length,
    videos,
    images,
    others: materials.length - videos - images
  }
})

// 最近上传的素材（最多显示5条）
const recentMaterials = computed(() => {
  return [...appStore.materials]
    .sort((a, b) => new Date(b.upload_time) - new Date(a.upload_time))
    .slice(0, 5)
})

// 获取文件类型
const getFileType = (filename) => {
  if (videoExtensions.some(ext => filename.toLowerCase().endsWith(ext))) return '视频'
  if (imageExtensions.some(ext => filename.toLowerCase().endsWith(ext))) return '图片'
  return '其他'
}

// 获取文件类型标签颜色
const getFileTypeTag = (filename) => {
  const type = getFileType(filename)
  return { '视频': 'success', '图片': 'warning', '其他': 'info' }[type] || 'info'
}

// 导航到指定路由
const navigateTo = (path) => {
  router.push(path)
}

// 加载数据
const fetchDashboardData = async () => {
  loading.value = true
  try {
    // 并行获取账号和素材数据
    const [accountRes, materialRes] = await Promise.allSettled([
      accountApi.getAccounts(),
      materialApi.getAllMaterials()
    ])

    if (accountRes.status === 'fulfilled' && accountRes.value.code === 200) {
      accountStore.setAccounts(accountRes.value.data)
    }
    if (materialRes.status === 'fulfilled' && materialRes.value.code === 200) {
      appStore.setMaterials(materialRes.value.data)
    }
  } catch (error) {
    console.error('获取仪表盘数据失败:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchDashboardData()
})
</script>

<script>
// Expose border color for template usage
export default {
  borderColor: 'rgba(255,255,255,0.08)'
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.dashboard {
  // Page title area
  padding: 0 28px;

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

  // ========== Stat Cards ==========
  .stat-cards {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
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

    &.stat-green {
      background: $stat-green-bg;
      border: 1px solid $stat-green-border;

      &:hover {
        border-color: rgba($accent-green, 0.35);
        box-shadow: 0 0 24px rgba($accent-green, 0.08);
      }

      .stat-icon {
        background: rgba($accent-green, 0.2);
        .el-icon { color: $accent-green; }
      }
    }

    .stat-top {
      display: flex;
      align-items: center;
      margin-bottom: 16px;

      .batch-check-btn {
        margin-left: auto;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 6px 14px;
        border: 1px solid rgba($success-color, 0.3);
        border-radius: 8px;
        font-size: 12px;
        font-weight: 500;
        cursor: pointer;
        transition: all $transition-base;
        background: rgba($success-color, 0.1);
        color: $success-color;
        white-space: nowrap;
        flex-shrink: 0;

        .el-icon {
          font-size: 14px;
        }

        &:hover:not(:disabled) {
          background: rgba($success-color, 0.2);
          border-color: rgba($success-color, 0.5);
          transform: translateY(-1px);
        }

        &:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        &.is-loading .el-icon {
          animation: rotate 1s linear infinite;
        }
      }
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

    .stat-bottom {
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      padding-top: 12px;
    }

    .stat-detail {
      display: flex;
      align-items: center;
      color: $text-secondary;
      font-size: 13px;
      gap: 8px;
      flex-wrap: wrap;

      .divider {
        width: 1px;
        height: 12px;
        background: rgba(255, 255, 255, 0.1);
      }
    }

    .platform-tags {
      gap: 6px;
    }

    .platform-tag {
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      color: #ffffff;

      &.douyin {
        background: $platform-douyin-bg;
      }

      &.kuaishou {
        background: $platform-kuaishou-bg;
      }

      &.channels {
        background: $platform-channels-bg;
      }

      &.xiaohongshu {
        background: $platform-xiaohongshu-bg;
      }

      &.bilibili {
        background: $platform-bilibili-bg;
      }

      &.baijiahao {
        background: $platform-baijiahao-bg;
      }

      &.tiktok {
        background: rgba(0, 200, 150, 0.25);
      }

      &.youtube {
        background: $platform-youtube-bg;
      }
    }
  }

  // ========== Quick Actions ==========
  .quick-actions {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-top: 24px;
  }

  .action-card {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 24px;
    cursor: pointer;
    transition: $transition-base;
    display: flex;
    flex-direction: column;
    align-items: flex-start;

    &:hover {
      transform: translateY(-4px);
      border-color: $border-active;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2), 0 0 0 1px rgba($brand-start, 0.15);
    }

    .action-icon {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 14px;

      .el-icon {
        font-size: 22px;
        color: #fff;
      }

      &.action-icon-purple {
        background: linear-gradient(135deg, $brand-start, $brand-end);
      }

      &.action-icon-blue {
        background: linear-gradient(135deg, $brand-end, $accent-cyan);
      }

      &.action-icon-cyan {
        background: linear-gradient(135deg, $accent-cyan, $accent-green);
      }

      &.action-icon-green {
        background: linear-gradient(135deg, $accent-green, $accent-amber);
      }
    }

    .action-title {
      font-size: 15px;
      font-weight: 600;
      color: $text-primary;
      margin-bottom: 4px;
    }

    .action-desc {
      font-size: 12px;
      color: $text-muted;
    }
  }

  // ========== Materials Table ==========
  .materials-card {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 24px;
    margin-top: 24px;

    .materials-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;

      h2 {
        font-size: 18px;
        font-weight: 600;
        color: $text-primary;
        margin: 0;
      }

      .view-all-link {
        font-size: 14px;
        color: $brand-start;
        cursor: pointer;
        transition: $transition-base;

        &:hover {
          color: $brand-end;
        }
      }
    }

    .materials-table {
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
    }

    .filename-cell {
      color: $text-primary;
      font-weight: 500;
    }

    .size-cell {
      color: $text-secondary;
    }

    .time-cell {
      color: $text-secondary;
      font-size: 13px;
    }

    .type-tag {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;

      &.type-video {
        color: $accent-green;
        background: rgba($accent-green, 0.12);
      }

      &.type-image {
        color: $accent-amber;
        background: rgba($accent-amber, 0.12);
      }

      &.type-other {
        color: $text-muted;
        background: rgba(255, 255, 255, 0.06);
      }
    }

    .empty-state {
      text-align: center;
      color: $text-muted;
      padding: 40px 0;
      font-size: 14px;
    }
  }
}
</style>
