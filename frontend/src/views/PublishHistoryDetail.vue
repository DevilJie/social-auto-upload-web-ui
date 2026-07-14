<template>
  <div class="publish-history-detail">
    <!-- 顶部导航条 -->
    <header class="page-header">
      <el-button link :icon="ArrowLeft" @click="goBack">返回</el-button>
      <div class="header-info">
        <h1 class="batch-title">{{ batch?.title || '加载中...' }}</h1>
        <span v-if="batch" class="status-tag" :class="`status-${batch.status}`">
          {{ statusLabel(batch.status) }}
        </span>
        <span v-if="batch?.created_at" class="header-time">{{ formatTime(batch.created_at) }}</span>
      </div>
    </header>

    <div class="detail-body">
      <!-- 左侧：账号栏 -->
      <aside v-if="batch" class="detail-sidebar">
        <AccountSidebar
          :mode="'readonly'"
          :account-groups="readonlyAccountGroups"
          :total-count="batchAccounts.length"
          :selected-platform="null"
          :selected-account-id="selectedAccountId"
          :expanded-groups="expandedGroups"
          :publish-account-ids="readonlyPublishAccountIds"
          :has-account-override="() => false"
          @toggle-group="toggleGroup"
          @select-account="selectAccount"
        />
      </aside>

      <!-- 右侧：主区域 -->
      <main class="detail-main" v-loading="loading">
        <!-- 5xx 重试条 -->
        <div v-if="error" class="error-bar">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ error }}</span>
          <el-button size="small" @click="fetchDetail">重试</el-button>
        </div>

        <!-- 空状态 -->
        <div v-else-if="!selectedItem" class="empty-state">
          <el-icon class="empty-icon"><DocumentRemove /></el-icon>
          <p>该批次暂无账号数据</p>
          <p v-if="batchAccounts.length === 0 && batch?.account_count > 0" class="empty-hint">
            该批次的账号已被全部删除，请前往
            <router-link to="/account-management">账号管理</router-link>
            查看
          </p>
        </div>

        <template v-else>
          <!-- 1. 账号信息头 -->
          <section class="account-header">
            <div class="avatar" :style="{ borderColor: currentPlatformConfig?.color || '#666' }">
              {{ selectedAccount?.name?.charAt(0) || '?' }}
            </div>
            <div class="header-text">
              <div class="line-1">
                <span class="account-name">{{ selectedAccount?.name || '已删除账号' }}</span>
                <span v-if="currentPlatformConfig" class="platform-badge" :style="{ background: currentPlatformConfig.color + '20', color: currentPlatformConfig.color }">
                  {{ currentPlatformConfig.name }}
                </span>
                <span class="status-tag" :class="`status-${selectedItem.status}`">{{ statusLabel(selectedItem.status) }}</span>
              </div>
              <div class="line-2">
                <span class="meta-time">{{ formatTime(selectedItem.created_at) }}</span>
                <span v-if="selectedItem.duration" class="meta-time">耗时 {{ formatDuration(selectedItem.duration) }}</span>
              </div>
            </div>
            <a
              v-if="selectedItem.status === 'success' && selectedItem.publish_url"
              :href="selectedItem.publish_url"
              target="_blank"
              rel="noopener noreferrer"
              class="view-link"
            >
              查看发布作品 →
            </a>
          </section>

          <!-- 2. 内容快照：成功 + 失败都渲染完整内容；失败时额外在顶部加错误横幅 -->
          <section class="content-snapshot" :class="{ 'content-snapshot--failed': selectedItem.status === 'failed' }">
            <!-- 失败错误横幅：仅失败时显示 -->
            <div v-if="selectedItem.status === 'failed'" class="error-banner">
              <el-icon :size="18"><CircleCloseFilled /></el-icon>
              <div class="error-banner-body">
                <strong>发布失败</strong>
                <span>{{ selectedItem.error_message || '未知错误' }}</span>
              </div>
            </div>
            <!-- 完整内容快照：成功 + 失败都显示 -->
            <div class="snapshot-body-row">
              <div class="snapshot-cover">
                <img v-if="getCoverUrl(selectedItem)" :src="getCoverUrl(selectedItem)" :alt="batch?.title" />
                <div v-else class="cover-placeholder">
                  <el-icon :size="40"><Picture /></el-icon>
                </div>
              </div>
              <div class="snapshot-body">
                <h3 class="snapshot-title">{{ getCfgField(selectedItem, 'title') || batch?.title || '无标题' }}</h3>
                <p class="snapshot-desc">{{ getCfgField(selectedItem, 'description') || batch?.description || '无描述' }}</p>
                <div v-if="getCfgField(selectedItem, 'tags')?.length" class="snapshot-tags">
                  <el-tag v-for="t in getCfgField(selectedItem, 'tags')" :key="t" size="small" effect="plain">#{{ t }}</el-tag>
                </div>
                <div v-if="getCfgField(selectedItem, 'creationDeclaration')" class="snapshot-meta">
                  <span class="meta-label">作品声明</span>
                  <span>{{ getCfgField(selectedItem, 'creationDeclaration') }}</span>
                </div>
                <div v-if="getCfgField(selectedItem, 'scheduleTime')" class="snapshot-meta">
                  <span class="meta-label">定时发布时间</span>
                  <span>{{ getCfgField(selectedItem, 'scheduleTime') }}</span>
                </div>
              </div>
            </div>
          </section>

          <!-- 3. 数据统计 -->
          <section class="data-stats">
            <h3 class="section-title">数据统计</h3>
            <PublishStats />
          </section>

          <!-- 4. 批次元信息 -->
          <section class="batch-meta">
            <el-collapse v-model="metaOpen">
              <el-collapse-item title="批次元信息" name="meta">
                <div class="meta-grid">
                  <div class="meta-item">
                    <span class="meta-label">批次 ID</span>
                    <span class="meta-value">
                      <code>{{ batch?.id }}</code>
                      <el-button link size="small" @click="copyBatchId">复制</el-button>
                    </span>
                  </div>
                  <div class="meta-item">
                    <span class="meta-label">定时发布时间</span>
                    <span class="meta-value">{{ batch?.schedule_time || '未设置' }}</span>
                  </div>
                  <div class="meta-item">
                    <span class="meta-label">开始时间</span>
                    <span class="meta-value">{{ batch?.started_at || '—' }}</span>
                  </div>
                  <div class="meta-item">
                    <span class="meta-label">结束时间</span>
                    <span class="meta-value">{{ batch?.finished_at || '—' }}</span>
                  </div>
                  <div class="meta-item">
                    <span class="meta-label">账号数</span>
                    <span class="meta-value">
                      批次记录 {{ batch?.account_count }} ·
                      实际展示 {{ batchAccounts.length }}
                    </span>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </section>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, WarningFilled, DocumentRemove, CircleCloseFilled, Picture } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { accountApi } from '@/api/account'
import { historyApi } from '@/api/v2'
import { platformList, getPlatformByKey } from '@/config/platforms'
import AccountSidebar from '@/components/AccountSidebar.vue'
import PublishStats from '@/components/PublishStats.vue'

const route = useRoute()
const router = useRouter()
const accountStore = useAccountStore()

const batch = ref(null)
const loading = ref(false)
const error = ref('')
const selectedAccountId = ref(null)
const metaOpen = ref([])
const expandedGroups = reactive(new Set())
const readonlyPublishAccountIds = new Set()  // 空 Set，AccountSidebar 内部不过滤

const batchAccounts = computed(() => {
  if (!batch.value) return []
  return accountStore.accounts.filter(a =>
    batch.value.items.some(it => it.account_id === a.id)
  )
})

const readonlyAccountGroups = computed(() => {
  return platformList
    .map(p => ({
      key: p.key,
      name: p.name,
      logo: p.logo,
      color: p.color,
      letter: p.letter,
      accounts: batchAccounts.value.filter(a => a.platform === p.name),
    }))
    .filter(g => g.accounts.length > 0)
})

const selectedItem = computed(() => {
  if (!batch.value || !selectedAccountId.value) return null
  return batch.value.items.find(it => it.account_id === selectedAccountId.value) || null
})

const selectedAccount = computed(() => {
  if (!selectedItem.value) return null
  return accountStore.accounts.find(a => a.id === selectedItem.value.account_id) || null
})

const currentPlatformConfig = computed(() => {
  if (!selectedAccount.value) return null
  const key = platformList.find(p => p.name === selectedAccount.value.platform)?.key
  return key ? getPlatformByKey(key) : null
})

function getCfgField(item, field) {
  return item?.account_configs?.[field]
}

function getCoverUrl(item) {
  if (!item) return ''
  const cfg = item.account_configs || {}
  // 优先用 per-account cover 自带的 .url 字段（后端已构造为绝对 URL）
  if (cfg.coverLandscape?.url) return cfg.coverLandscape.url
  if (cfg.coverPortrait?.url) return cfg.coverPortrait.url
  // 兜底：batch 级 cover_url
  return batch.value?.cover_url || ''
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

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatDuration(s) {
  if (s == null) return ''
  if (s < 60) return `${s}秒`
  return `${Math.floor(s / 60)}分${s % 60}秒`
}

async function copyBatchId() {
  try {
    await navigator.clipboard.writeText(batch.value.id)
    ElMessage.success('已复制批次 ID')
  } catch (e) {
    ElMessage.error('复制失败')
  }
}

function goBack() {
  router.push('/publish-history')
}

function toggleGroup(key) {
  if (expandedGroups.has(key)) expandedGroups.delete(key)
  else expandedGroups.add(key)
}

function selectAccount(account /*, group */) {
  selectedAccountId.value = account.id
}

async function fetchDetail() {
  error.value = ''
  loading.value = true
  try {
    const res = await historyApi.getBatch(route.params.batchId)
    // 拦截器只在 data.code === 200 时 resolve，否则 reject；到这里就是成功
    batch.value = res.data
    // 默认选中：找第一个 account_id 在 store 里能找到的 item
    const firstValid = batch.value.items.find(it =>
      it.account_id != null &&
      accountStore.accounts.some(a => a.id === it.account_id)
    )
    if (firstValid) selectedAccountId.value = firstValid.account_id
    // 展开所有有账号的组
    readonlyAccountGroups.value.forEach(g => expandedGroups.add(g.key))
  } catch (e) {
    // 拦截器已经 toast（4xx 用后端 msg，5xx 用通用文案）；这里只补行为
    if (e?.response?.status === 404) {
      // 批次不存在 → 跳回列表
      router.replace('/publish-history')
    } else if (e?.response?.status >= 500 || !e?.response) {
      // 服务端错误或网络错误 → 主区域顶部红条 + 重试按钮
      error.value = '加载失败，请稍后重试'
    } else {
      // 其它 4xx（401/403 等）→ 红条
      error.value = e.message || '加载失败'
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // 串行：先加载账号 store，再拉详情
  try {
    if (accountStore.accounts.length === 0) {
      const res = await accountApi.getAccounts()
      accountStore.setAccounts(res.data || [])
    }
  } catch (e) {
    console.error('加载账号列表失败:', e)
  }
  await fetchDetail()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-history-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: $bg-base;
  // 整体节奏：主区卡片间距 20px，卡片内 padding 20px，留白与卡片内文本密度平衡
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 56px;
  padding: 0 24px;
  border-bottom: 1px solid $border;
  background: $bg-elevated;
  flex-shrink: 0;

  .header-info {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    min-width: 0;
  }

  .batch-title {
    font-size: 16px;
    font-weight: 600;
    color: $text-primary;
    margin: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 400px;
    // 字距略紧，提升数据密集页的标题密度
    letter-spacing: -0.01em;
  }

  .header-time {
    font-size: 12px;
    color: $text-muted;
  }
}

.detail-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.detail-sidebar {
  width: 232px;
  flex-shrink: 0;
  overflow-y: auto;
  // 左侧栏与主区用 1px 透明 border 拉出节奏（与右侧圆角卡呼应）
  border-right: 1px solid $border-light;
}

.detail-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 20px 24px 28px;  // 顶部 20px 与 56px header 形成 8 倍数节奏
  display: flex;
  flex-direction: column;
  gap: 20px;  // 卡片间距：8 倍数节奏
}

.status-tag {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.02em;

  &.status-success, &.status-partial {
    background: rgba($accent-green, 0.15);
    color: #67c23a;
  }
  &.status-failed {
    background: rgba($danger-color, 0.15);
    color: #f56c6c;
  }
  &.status-running {
    background: rgba($info-color, 0.15);
    color: #409eff;
  }
  &.status-pending, &.status-cancelled {
    background: rgba(0, 0, 0, 0.06);
    color: $text-muted;
  }
}

// 5xx 错误降级红条：使用项目 danger 色 + 8px 圆角 + 浅红底 + 1px 红边
.error-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: rgba($danger-color, 0.1);
  border: 1px solid rgba($danger-color, 0.3);
  border-radius: 8px;
  color: #f56c6c;
  font-size: 14px;
  // 红条与下方卡片同节奏：margin-bottom 改为父级 gap 接管
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: $text-muted;
  text-align: center;
  gap: 8px;
  padding: 48px 16px;

  .empty-icon {
    font-size: 48px;
    opacity: 0.5;
  }

  p {
    margin: 0;
    font-size: 14px;
  }

  .empty-hint {
    font-size: 12px;
    a { color: $brand-start; text-decoration: none; }
    a:hover { text-decoration: underline; }
  }
}

// 1. 账号信息头：圆角 12px + 1px 边框 + 48px 头像，header 内部 16px gap
.account-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  transition: border-color $transition-base;
  &:hover { border-color: $border-active; }

  .avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: rgba($brand-start, 0.15);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    color: #c4b5fd;
    font-weight: 700;
    border: 2px solid transparent;
    flex-shrink: 0;
  }

  .header-text {
    flex: 1;
    min-width: 0;

    .line-1 {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 4px;
    }

    .account-name {
      font-size: 16px;
      font-weight: 600;
      color: $text-primary;
      letter-spacing: -0.01em;
    }

    .platform-badge {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 500;
      letter-spacing: 0.02em;
    }

    .line-2 {
      display: flex;
      gap: 12px;
      font-size: 12px;
      color: $text-muted;
    }
  }

  .view-link {
    color: $brand-start;
    font-size: 13px;
    text-decoration: none;
    flex-shrink: 0;
    transition: opacity $transition-fast;
    &:hover { text-decoration: underline; opacity: 0.85; }
  }
}

// 2. 内容快照：列向布局，顶部可能为错误横幅，下方为左 cover + 右 body
.content-snapshot {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 20px;
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  transition: $transition-base;

  &--failed {
    border-color: rgba($danger-color, 0.3);
    background: rgba($danger-color, 0.03);
  }
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: rgba($danger-color, 0.1);
  border: 1px solid rgba($danger-color, 0.3);
  border-radius: $radius-base;
  color: #f56c6c;

  .el-icon { flex-shrink: 0; }

  .error-banner-body {
    display: flex;
    flex-direction: column;
    gap: 2px;

    strong { font-size: 13px; font-weight: 600; }
    span { font-size: 12px; color: $text-secondary; word-break: break-all; }
  }
}

.snapshot-body-row {
  display: flex;
  gap: 16px;
  align-items: stretch;
}

.snapshot-cover {
  flex-shrink: 0;
  width: 160px;
  aspect-ratio: 16/9;
  background: $bg-surface;
  border-radius: 8px;
  overflow: hidden;
  position: relative;

  img { width: 100%; height: 100%; object-fit: cover; }
  .cover-placeholder {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    color: $text-muted;
  }
}

.snapshot-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.snapshot-title {
  font-size: 15px;
  font-weight: 600;
  color: $text-primary;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.snapshot-desc {
  font-size: 13px;
  color: $text-secondary;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.snapshot-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.snapshot-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: $text-secondary;
  .meta-label { color: $text-muted; }
}

// 3. 数据统计：16/20 padding，标题与内容 12px 分隔
.data-stats {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: 16px 20px;

  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: $text-primary;
    margin: 0 0 12px;
    letter-spacing: -0.005em;
  }
}

// 4. 批次元信息折叠卡：左右 0/20 padding 配合 el-collapse-item 内部 padding 形成节奏
.batch-meta {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: 0 4px;  // 让 el-collapse-item 的内边距更接近主体节奏

  .meta-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px 24px;
    padding: 4px 16px 16px;
  }

  .meta-item {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 0;
  }

  .meta-label {
    font-size: 12px;
    color: $text-muted;
    letter-spacing: 0.02em;
  }

  .meta-value {
    font-size: 13px;
    color: $text-secondary;
    display: flex;
    align-items: center;
    gap: 8px;
    line-height: 1.5;

    code {
      font-family: 'Fira Code', 'JetBrains Mono', Menlo, monospace;
      font-size: 12px;
      background: rgba($overlay-rgb, 0.05);
      padding: 2px 8px;
      border-radius: 4px;
      color: $text-primary;
    }
  }
}
</style>
