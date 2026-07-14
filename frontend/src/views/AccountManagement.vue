<template>
  <div class="account-management">
    <div class="page-header">
      <div class="header-content">
        <div class="header-text">
          <h1>账号管理</h1>
          <p class="page-subtitle">管理所有平台账号</p>
        </div>
        <div class="header-actions">
          <el-button type="primary" class="add-btn" @click="handleAddAccount">
            <el-icon><Plus /></el-icon>
            添加账号
          </el-button>
          <el-button class="add-btn import-btn" @click="handleImportAccount">
            <el-icon><Upload /></el-icon>
            导入用户
          </el-button>
        </div>
      </div>
    </div>

    <!-- 平台筛选标签 -->
    <div class="platform-tabs">
      <button
        v-for="tab in filterOptions"
        :key="tab.value"
        :class="['tab-item', { active: activeTab === tab.value }]"
        @click="activeTab = tab.value"
      >
        <span class="tab-label">{{ tab.label }}</span>
        <span v-if="tab.count" class="tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <!-- 搜索栏 -->
    <div class="search-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索名称或账号..."
        prefix-icon="Search"
        clearable
        class="search-input"
      />
      <el-button class="refresh-btn" @click="fetchAccountsQuick" :loading="appStore.isAccountRefreshing">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
      <el-button class="check-all-btn" @click="fetchAccounts" :loading="appStore.isAccountRefreshing">
        <el-icon v-if="!appStore.isAccountRefreshing"><Loading /></el-icon>
        批量检查
      </el-button>
      <el-button class="batch-tag-btn" @click="batchTagDialogVisible = true">
        <el-icon><CollectionTag /></el-icon>
        批量设置标签
      </el-button>
    </div>

    <!-- 标签筛选 -->
    <div v-if="tagFilterOptions.length > 0" class="tag-filter-bar">
      <button
        :class="['tag-filter-item', { active: !activeTagId }]"
        @click="activeTagId = null"
      >全部标签</button>
      <button
        v-for="tag in tagFilterOptions"
        :key="tag.id"
        :class="['tag-filter-item', { active: activeTagId === tag.id }]"
        @click="activeTagId = activeTagId === tag.id ? null : tag.id"
      >
        <span class="tag-dot" :style="{ background: tag.color }"></span>
        {{ tag.name }}
      </button>
    </div>

    <!-- 账号卡片列表 -->
    <div v-if="filteredAccounts.length > 0" class="account-grid">
      <div
        v-for="account in filteredAccounts"
        :key="account.id"
        :data-account-id="account.id"
        :class="['account-card', `platform-${getPlatformClass(account.platform)}`]"
      >
        <!-- 卡片主体：头像 + 用户信息 -->
        <div class="card-body">
          <img :src="proxyAvatar(account.avatar) || getDefaultAvatar(account.name)" class="user-avatar" />
          <div class="user-info">
            <span class="user-name">{{ account.name }}</span>
            <div class="platform-row">
              <span class="platform-name">{{ account.platform }}</span>
              <el-tag
                v-if="isAccountDisabled(account)"
                type="info"
                size="small"
                effect="plain"
                class="disabled-tag"
              >
                已拉黑
              </el-tag>
              <span :class="['status-badge', getStatusClass(account.status)]">
                <span class="status-dot"></span>
                {{ account.status }}
              </span>
            </div>
          </div>
          <div class="platform-logo">
            <img v-if="getPlatformLogo(account.platform)" :src="getPlatformLogo(account.platform)" :alt="account.platform" class="platform-icon" />
            <span v-else class="platform-letter" :style="{ color: getPlatformColor(account.platform) }">
              {{ getPlatformLetter(account.platform) }}
            </span>
          </div>
        </div>

        <!-- 标签行(独立一行,溢出跑马灯) -->
        <div class="account-tags-row">
          <span class="account-tags-label">标签:</span>
          <div
            v-if="account.tags && account.tags.length > 0"
            :class="['account-tags-viewport', { 'is-overflow': tagOverflowMap[account.id] }]"
          >
            <div
              class="account-tags-track"
              :class="{ marquee: tagOverflowMap[account.id] }"
            >
              <span
                v-for="tag in tagOverflowMap[account.id] ? [...account.tags, ...account.tags] : account.tags"
                :key="tag.id + '-' + (tagOverflowMap[account.id] ? 'b' : 'a')"
                class="account-tag"
                :style="{ borderColor: tag.color, color: tag.color }"
              >
                {{ tag.name }}
                <span
                  class="account-tag-remove"
                  title="从该账号移除此标签"
                  @click.stop="handleRemoveAccountTag(account, tag)"
                >×</span>
              </span>
            </div>
          </div>
          <TagPopover
            :visible="tagPopoverVisible && tagPopoverAccountId === account.id"
            :account-id="account.id"
            :selected-tags="account.tags || []"
            @update:visible="tagPopoverVisible = $event"
            @changed="onTagChanged"
          >
            <button class="tag-add-btn" @click.stop="openTagPopover(account.id)">
              <el-icon><Plus /></el-icon>
            </button>
          </TagPopover>
        </div>

        <!-- 卡片底部：操作按钮 -->
        <div class="card-footer">
          <div class="card-actions">
            <button
              v-if="account.status === '异常'"
              class="action-btn login"
              :class="{ 'is-blacklisted': isAccountDisabled(account) }"
              :disabled="isAccountDisabled(account)"
              :title="isAccountDisabled(account) ? '该渠道已被加入黑名单,请先在系统设置中移除' : ''"
              @click="handleReLogin(account)"
            >
              <el-icon><Key /></el-icon>
              {{ isAccountDisabled(account) ? '已拉黑' : '登录' }}
            </button>
            <button v-else class="action-btn check" @click="handleCheckAccount(account)" :disabled="checkingIds.has(account.id)">
              <el-icon v-if="checkingIds.has(account.id)" class="is-loading"><Loading /></el-icon>
              <template v-else>
                <el-icon><Check /></el-icon>
                检查
              </template>
            </button>
            <button
              class="action-btn sync"
              :class="{ 'is-blacklisted': isAccountDisabled(account) }"
              :disabled="isAccountDisabled(account) || account.status === '异常' || syncingIds.has(account.id)"
              :title="isAccountDisabled(account) ? '该渠道已被加入黑名单,请先在系统设置中移除' : ''"
              @click="handleSyncProfile(account)"
            >
              <el-icon v-if="syncingIds.has(account.id)" class="is-loading"><Loading /></el-icon>
              <template v-else>
                <el-icon><Refresh /></el-icon>
                同步
              </template>
            </button>
            <button
              class="action-btn creator"
              :class="{ 'is-blacklisted': isAccountDisabled(account) }"
              :disabled="isAccountDisabled(account) || account.status === '异常'"
              :title="isAccountDisabled(account) ? '该渠道已被加入黑名单,请先在系统设置中移除' : ''"
              @click="handleOpenCreatorCenter(account)"
            >
              <el-icon><Link /></el-icon>
              创作中心
            </button>
            <button class="action-btn delete" @click="handleDelete(account)">
              <el-icon><Delete /></el-icon>
              删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <div class="empty-content">
        <el-icon class="empty-icon"><Folder /></el-icon>
        <h3>{{ searchKeyword ? '未找到匹配账号' : '暂无账号数据' }}</h3>
        <p>{{ searchKeyword ? '请尝试其他关键词搜索' : '点击上方"添加账号"开始绑定你的第一个平台账号' }}</p>
        <el-button v-if="!searchKeyword" type="primary" @click="handleAddAccount">
          <el-icon><Plus /></el-icon>
          添加账号
        </el-button>
      </div>
    </div>

    <!-- 添加/重新登录账号对话框 -->
    <LoginDialog
      v-model="loginDialogVisible"
      :mode="loginMode"
      :account="reloginAccount"
      @success="onLoginSuccess"
      @fail="onLoginFail"
    />

    <!-- 批量设置标签对话框 -->
    <BatchTagDialog
      v-model="batchTagDialogVisible"
      @done="onBatchTagDone"
    />

    <!-- 批量检查对话框（复用发布前检查的 4 阶段进度 + 失效自动重登） -->
    <PrePublishCheckDialog
      ref="prePublishCheckRef"
      v-model="prePublishCheckVisible"
      mode="account-check"
    />

    <!-- 导入用户对话框：粘贴 cookie 字符串 → 后端 4 步进度 -->
    <el-dialog
      v-model="importDialogVisible"
      :show-close="!importStarted || importDone"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :width="importStarted ? '520px' : '660px'"
      align-center
      class="import-account-dialog"
      @close="closeImportDialog"
    >
      <template #header>
        <div class="import-dialog-header">
          <div class="import-dialog-title">
            <el-icon class="title-icon"><Upload /></el-icon>
            <span>导入用户账号</span>
          </div>
          <div class="import-dialog-sub">通过 Cookie 字符串快速绑定已有平台账号</div>
        </div>
      </template>

      <!-- 输入阶段：左右分栏（左选平台 / 右输入 cookie） -->
      <template v-if="!importStarted">
        <div class="import-form-split">
          <!-- 左：平台扁平卡片列表 -->
          <div class="split-left">
            <div class="split-section-label">
              <span class="dot">●</span>
              <span>选择平台</span>
            </div>
            <el-input
              v-model="platformSearch"
              class="platform-search"
              placeholder="搜索平台..."
              :prefix-icon="Search"
              clearable
              size="small"
            />
            <div class="platform-list">
              <div
                v-for="p in filteredImportPlatforms"
                :key="p.id"
                :class="['platform-card-flat', { 'is-selected': importForm.platformId === p.id }]"
                @click="importForm.platformId = p.id"
              >
                <div class="card-logo-wrap" :style="{ background: getPlatformBg(p.name) }">
                  <img
                    v-if="getPlatformLogo(p.name)"
                    :src="getPlatformLogo(p.name)"
                    :alt="p.name"
                    class="card-logo"
                  />
                  <span v-else class="card-letter" :style="{ color: getPlatformColor(p.name) }">
                    {{ p.letter }}
                  </span>
                </div>
                <div class="card-text">
                  <div class="card-name">{{ p.name }}</div>
                </div>
                <el-icon v-if="importForm.platformId === p.id" class="card-check">
                  <Select />
                </el-icon>
              </div>
              <div v-if="!filteredImportPlatforms.length" class="empty-platform">
                {{ importSupportedPlatforms.length ? '未匹配到平台' : '暂无支持导入的平台' }}
              </div>
            </div>
          </div>

          <!-- 右：cookie 输入 -->
          <div class="split-right">
            <div class="split-section-label">
              <span class="dot">●</span>
              <span>Cookie 字符串</span>
            </div>
            <el-input
              v-model="importForm.cookieStr"
              type="textarea"
              resize="none"
              class="import-textarea"
              placeholder="k1=v1; k2=v2; k3=v3 ..."
            />
            <div class="cookie-tip">
              <el-icon><InfoFilled /></el-icon>
              <span>从浏览器 DevTools → Network → 任意请求 → Request Headers → Cookie 复制整段</span>
            </div>
          </div>
        </div>
      </template>

      <!-- 进度阶段：自绘 4 步进度条 -->
      <template v-else>
        <div class="import-progress">
          <div class="import-progress-header">
            <div class="platform-pill" v-if="currentImportPlatform">
              <span class="platform-letter" :style="{ background: getPlatformColor(currentImportPlatform.name) }">
                {{ currentImportPlatform.letter }}
              </span>
              <span class="platform-name">{{ currentImportPlatform.name }}</span>
            </div>
          </div>

          <!-- 顶部进度条 (n/4) -->
          <div class="progress-bar-wrap">
            <div class="progress-bar">
              <div
                class="progress-bar-fill"
                :class="{ 'is-error': importFailed }"
                :style="{ width: progressPercent + '%' }"
              ></div>
            </div>
            <div class="progress-bar-text">
              {{ importFailed ? '已中断' : `${importActiveStep}/${importSteps.length}` }}
            </div>
          </div>

          <!-- 步骤列表 -->
          <ul class="step-list">
            <li
              v-for="(s, idx) in importSteps"
              :key="idx"
              :class="['step-item', `is-${s.status}`]"
            >
              <div class="step-indicator">
                <el-icon v-if="s.status === 'finish'" class="step-icon finish"><CircleCheckFilled /></el-icon>
                <el-icon v-else-if="s.status === 'error'" class="step-icon error"><CircleCloseFilled /></el-icon>
                <el-icon v-else-if="s.status === 'process'" class="step-icon process is-loading"><Loading /></el-icon>
                <span v-else class="step-num">{{ idx + 1 }}</span>
              </div>
              <div class="step-content">
                <div class="step-title">{{ s.title }}</div>
                <div class="step-description" :class="{ 'is-error': s.status === 'error' }">
                  {{ s.description || '等待中...' }}
                </div>
              </div>
            </li>
          </ul>

          <!-- 完成态：账号预览卡片 -->
          <transition name="fade-up">
            <div v-if="importDone && importResult" class="result-card">
              <img
                v-if="importResult.avatar"
                :src="importResult.avatar"
                class="result-avatar"
                @error="importResult.avatar = ''"
              />
              <div v-else class="result-avatar-fallback">
                {{ (importResult.userName || '?').charAt(0) }}
              </div>
              <div class="result-info">
                <div class="result-name">{{ importResult.userName || '未识别昵称' }}</div>
                <div class="result-meta">已成功导入为账号 #{{ importResult.accountId }}</div>
              </div>
            </div>
          </transition>
        </div>
      </template>

      <template #footer>
        <template v-if="!importStarted">
          <el-button @click="closeImportDialog" class="footer-btn">取消</el-button>
          <el-button
            type="primary"
            :loading="importStarting"
            :disabled="!importForm.platformId || !importForm.cookieStr.trim()"
            class="footer-btn-primary"
            @click="submitImport"
          >
            <el-icon v-if="!importStarting"><Position /></el-icon>
            <span>开始导入</span>
          </el-button>
        </template>
        <template v-else>
          <el-button
            :disabled="!importDone"
            :type="importFailed ? 'danger' : 'primary'"
            class="footer-btn-primary"
            @click="closeImportDialog"
          >
            {{ importFailed ? '关闭' : (importDone ? '完成' : '处理中...') }}
          </el-button>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { Refresh, Loading, Link, Plus, Edit, Delete, Check, Folder, Key, CollectionTag, Close, Upload, SuccessFilled, CircleCheckFilled, CircleCloseFilled, Position, InfoFilled, Select, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { accountApi } from '@/api/account'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { http } from '@/utils/request'
import { platformList, platformNameToId, platformNameToKey, platformCssMap, getPlatformByName } from '@/config/platforms'
import { getDefaultAvatar, proxyAvatar } from '@/utils/avatar'
import LoginDialog from '@/components/LoginDialog.vue'
import TagPopover from '@/components/TagPopover.vue'
import PrePublishCheckDialog from '@/components/PrePublishCheckDialog.vue'
import BatchTagDialog from '@/components/BatchTagDialog.vue'

const accountStore = useAccountStore()
const appStore = useAppStore()

/** 平台是否已被加入黑名单（account.platform 是中文名,需先转为 key） */
const isAccountDisabled = (account) => {
  const key = platformNameToKey[account.platform]
  return !!(key && appStore.isPlatformDisabled(key))
}

const activeTagId = ref(null)
const tagPopoverVisible = ref(false)
const tagPopoverAccountId = ref(null)

// 哪些账号的标签溢出(决定是否跑马灯):key=accountId
const tagOverflowMap = ref({})

const tagFilterOptions = computed(() => accountStore.allTags)

function openTagPopover(accountId) {
  tagPopoverAccountId.value = accountId
  tagPopoverVisible.value = true
}

// 检测每张卡片标签行是否溢出,溢出时启用跑马灯
function checkTagOverflow() {
  nextTick(() => {
    const rows = document.querySelectorAll('.account-tags-viewport')
    const next = {}
    rows.forEach(viewport => {
      const track = viewport.querySelector('.account-tags-track')
      const card = viewport.closest('.account-card')
      const id = Number(card?.dataset?.accountId)
      if (id && track) {
        next[id] = track.scrollWidth > viewport.clientWidth + 1
      }
    })
    tagOverflowMap.value = next
  })
}

watch(() => accountStore.accounts, () => {
  checkTagOverflow()
}, { deep: true })

let tagResizeObserver = null

onMounted(() => {
  fetchAccountsQuick()
  accountStore.loadTags()
  nextTick(() => {
    checkTagOverflow()
    tagResizeObserver = new ResizeObserver(() => checkTagOverflow())
    document.querySelectorAll('.account-tags-viewport').forEach(el => tagResizeObserver.observe(el))
  })
})

onBeforeUnmount(() => {
  tagResizeObserver?.disconnect()
  if (importEventSource) {
    importEventSource.close()
    importEventSource = null
  }
})

async function onTagChanged() {
  await fetchAccountsQuick()
}

async function handleRemoveAccountTag(account, tag) {
  const remaining = (account.tags || []).filter(t => t.id !== tag.id).map(t => t.id)
  try {
    const res = await accountApi.setAccountTags(account.id, remaining)
    if (res.code === 200) {
      await fetchAccountsQuick()
      ElMessage.success(`已从「${account.name}」移除标签「${tag.name}」`)
    } else {
      ElMessage.error(res.msg || '移除失败')
    }
  } catch (e) {
    console.error('移除标签失败:', e)
    ElMessage.error('移除标签失败')
  }
}

const activeTab = ref('all')
const searchKeyword = ref('')
const currentPage = ref(1)
const pageSize = ref(12)

const filterOptions = computed(() => {
  const counts = {}
  accountStore.accounts.forEach(a => {
    counts[a.platform] = (counts[a.platform] || 0) + 1
  })
  return [
    { label: '全部', value: 'all', count: accountStore.accounts.length },
    ...platformList.map(p => ({ label: p.name, value: p.name, count: counts[p.name] || 0 }))
  ].filter(opt => opt.value === 'all' || (opt.count && opt.count > 0))
})

const fetchAccountsQuick = async () => {
  try {
    const res = await accountApi.getAccounts()
    if (res.code === 200 && res.data) {
      accountStore.setAccounts(res.data)
    }
  } catch (error) {
    console.error('快速获取账号数据失败:', error)
  }
}

// 模板里用 ref 拿到 PrePublishCheckDialog 组件实例
const prePublishCheckRef = ref(null)
const prePublishCheckVisible = ref(false)

const fetchAccounts = async () => {
  if (appStore.isAccountRefreshing) return
  if (!accountStore.accounts.length) {
    ElMessage.warning('暂无账号可检查')
    return
  }
  appStore.setAccountRefreshing(true)
  // 复用发布前检查的 4 阶段进度弹窗（与发布流程交互一致）:
  // 1) checking → 进度条 + 卡片实时状态
  // 2) all-valid → 全部正常，1.2s 后自动关闭
  // 3) fixing   → 失效账号自动打开 SSE 登录
  // 4) done     → 全部修复完成，1.2s 后自动关闭
  try {
    const allValid = await prePublishCheckRef.value.open(accountStore.accounts)
    // dialog 内部已逐张更新 accountStore；这里再拉一次最新状态保证 UI 同步
    await fetchAccountsQuick()
    if (allValid && appStore.isFirstTimeAccountManagement) {
      appStore.setAccountManagementVisited()
    }
  } catch (error) {
    console.error('批量检查失败:', error)
    ElMessage.error('批量检查失败')
  } finally {
    appStore.setAccountRefreshing(false)
  }
}

const getPlatformClass = (platform) => {
  return platformCssMap[platform] || ''
}

const getPlatformColor = (platform) => {
  const p = getPlatformByName(platform)
  return p?.color || '#8b5cf6'
}

const getPlatformBg = (platform) => {
  const p = getPlatformByName(platform)
  return p?.bgColor || 'rgba(139, 92, 246, 0.15)'
}

const getPlatformLogo = (platform) => {
  const p = getPlatformByName(platform)
  return p?.logo || null
}

const getPlatformLetter = (platform) => {
  const p = getPlatformByName(platform)
  return p?.letter || platform?.charAt(0) || '?'
}

const getStatusClass = (status) => {
  if (status === '验证中') return 'pending'
  if (status === '正常') return 'normal'
  return 'error'
}

const isStatusClickable = (status) => status === '异常'

const getStatusTagType = (status) => {
  if (status === '验证中') return 'info'
  if (status === '正常') return 'success'
  return 'danger'
}

const handleStatusClick = (row) => {
  if (isStatusClickable(row.status)) handleReLogin(row)
}

const filteredAccounts = computed(() => {
  let accounts = accountStore.accounts
  if (activeTab.value !== 'all') {
    accounts = accounts.filter(a => a.platform === activeTab.value)
  }
  if (activeTagId.value) {
    accounts = accounts.filter(a => a.tags?.some(t => t.id === activeTagId.value))
  }
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    accounts = accounts.filter(a => a.name.toLowerCase().includes(keyword))
  }
  return accounts
})

const paginatedAccounts = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return filteredAccounts.value.slice(start, end)
})

watch([activeTab, searchKeyword], () => {
  currentPage.value = 1
})

const dialogVisible = ref(false)
const dialogType = ref('add')
const accountFormRef = ref(null)

const accountForm = reactive({ id: null, name: '', platform: '', status: '正常' })

const rules = {
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }]
}

const checkingIds = ref(new Set())

// LoginDialog 弹窗控制
const loginDialogVisible = ref(false)
const loginMode = ref('add')        // 'add' | 'relogin'
const reloginAccount = ref(null)

// ── 导入用户（cookie 字符串）弹窗控制 ──────────────────────────
const importDialogVisible = ref(false)
const importSupportedPlatforms = ref([])  // [{id, key, name, letter}, ...]
// 平台搜索关键词（导入弹窗左侧）
const platformSearch = ref('')
const filteredImportPlatforms = computed(() => {
  const kw = platformSearch.value.trim().toLowerCase()
  if (!kw) return importSupportedPlatforms.value
  return importSupportedPlatforms.value.filter(p =>
    p.name.toLowerCase().includes(kw) ||
    (p.key || '').toLowerCase().includes(kw)
  )
})
const importForm = reactive({
  platformId: null,
  cookieStr: '',
})
const importStarted = ref(false)
const importStarting = ref(false)
const importActiveStep = ref(0)   // 当前进行到的 step (0-based)
const importDone = ref(false)      // 全部完成 / 失败时为 true，允许关闭
const importFailed = ref(false)    // 失败态：进度条标红，关闭按钮变 danger
const importResult = ref(null)     // { accountId, userName, avatar } 完成态展示
// EventSource 是非响应式对象，用普通 let 持有；放在 ref 里会被 Vue proxy 包一层
// 导致 close() 等行为不可靠。仿 LoginDialog.vue 的 eventSources Map 写法。
let importEventSource = null

// 顶部进度条百分比 (0/25/50/75/100)
const progressPercent = computed(() => {
  if (importFailed.value) return 100
  const done = importSteps.value.filter(s => s.status === 'finish').length
  return Math.round((done / importSteps.value.length) * 100)
})

// 当前正在导入的平台（用于头部 pill 展示）
const currentImportPlatform = computed(() => {
  if (!importForm.platformId) return null
  return importSupportedPlatforms.value.find(p => p.id === importForm.platformId) || null
})

// 4 步进度，每项 { title, description, status: 'wait'|'process'|'finish'|'error' }
const importSteps = ref([
  { title: '解析 cookie 字符串', description: '等待中...', status: 'wait' },
  { title: '生成 cookie 文件',   description: '等待中...', status: 'wait' },
  { title: '同步用户资料',        description: '等待中...', status: 'wait' },
  { title: '导入完成',            description: '等待中...', status: 'wait' },
])

const resetImportDialog = () => {
  importStarted.value = false
  importStarting.value = false
  importActiveStep.value = 0
  importDone.value = false
  importFailed.value = false
  importResult.value = null
  importForm.platformId = null
  importForm.cookieStr = ''
  platformSearch.value = ''
  importSteps.value = [
    { title: '解析 cookie 字符串', description: '等待中...', status: 'wait' },
    { title: '生成 cookie 文件',   description: '等待中...', status: 'wait' },
    { title: '同步用户资料',        description: '等待中...', status: 'wait' },
    { title: '导入完成',            description: '等待中...', status: 'wait' },
  ]
  if (importEventSource) {
    importEventSource.close()
    importEventSource = null
  }
}

const handleImportAccount = async () => {
  resetImportDialog()
  importDialogVisible.value = true
  try {
    const res = await accountApi.getImportSupportedPlatforms()
    if (res.code === 200 && res.data) {
      importSupportedPlatforms.value = res.data
    }
  } catch (e) {
    ElMessage.error('获取支持导入的平台列表失败')
  }
}

const closeImportDialog = () => {
  if (importEventSource) {
    importEventSource.close()
    importEventSource = null
  }
  importDialogVisible.value = false
  // 给 el-dialog 关闭动画留 200ms 再清状态
  setTimeout(() => resetImportDialog(), 200)
}

const submitImport = async () => {
  if (!importForm.platformId || !importForm.cookieStr.trim()) {
    ElMessage.warning('请选择平台并粘贴 cookie 字符串')
    return
  }
  importStarting.value = true
  importStarted.value = true

  // 1. 启动任务
  let taskId
  try {
    const res = await accountApi.startImportAccount({
      type: importForm.platformId,
      cookie_str: importForm.cookieStr.trim(),
    })
    if (res.code !== 200 || !res.data || !res.data.task_id) {
      throw new Error(res.msg || '启动导入任务失败')
    }
    taskId = res.data.task_id
  } catch (e) {
    importStarting.value = false
    importSteps.value[0].status = 'error'
    importSteps.value[0].description = e.message || String(e)
    importDone.value = true
    importFailed.value = true
    return
  }
  importStarting.value = false

  // 2. SSE 监听进度
  const es = new EventSource(`/importAccount/stream?task_id=${taskId}`)
  importEventSource = es

  es.onmessage = (event) => {
    let payload
    try {
      payload = JSON.parse(event.data)
    } catch (_) {
      return
    }
    const step = Number(payload.step || 0)  // 1..4，error 时可能为 0

    if (payload.status === 'error') {
      // 标红当前 step（如果 step 缺失或越界，标红最后一个）
      const idx = step >= 1 && step <= 4 ? step - 1 : Math.max(0, importActiveStep.value)
      importSteps.value[idx].status = 'error'
      importSteps.value[idx].description = payload.msg || '未知错误'
      importDone.value = true
      importFailed.value = true
      es.close()
      importEventSource = null
      ElMessage.error(`导入失败: ${payload.msg || ''}`)
      return
    }

    if (payload.status === 'done') {
      importActiveStep.value = 4
      for (let i = 0; i < 4; i++) {
        importSteps.value[i].status = 'finish'
        importSteps.value[i].description = importSteps.value[i].description || '完成'
      }
      importSteps.value[3].description = '已完成'
      importResult.value = {
        accountId: payload.account_id,
        userName: payload.userName,
        avatar: payload.avatar,
      }
      importDone.value = true
      importFailed.value = false
      es.close()
      importEventSource = null
      ElMessage.success('导入成功')
      // 刷新账号列表
      fetchAccountsQuick()
      return
    }

    if (payload.status === 'running' && step >= 1 && step <= 4) {
      const idx = step - 1
      importActiveStep.value = idx
      importSteps.value[idx].status = 'process'
      importSteps.value[idx].description = payload.msg || '处理中...'
      // 已完成的前置步骤保持 finish
      for (let i = 0; i < idx; i++) {
        if (importSteps.value[i].status === 'process') {
          importSteps.value[i].status = 'finish'
        }
      }
    }
  }

  es.onerror = () => {
    // EventSource 出错时通常意味着后端已断开连接（task 已结束）。
    // 如果 importDone 还没置 true，说明后端异常断开，标红最后活跃 step。
    if (!importDone.value) {
      const idx = importActiveStep.value
      importSteps.value[idx].status = 'error'
      importSteps.value[idx].description = '连接中断，请稍后重试'
      importDone.value = true
      ElMessage.error('导入连接中断')
    }
    es.close()
    importEventSource = null
  }
}

// ────────────────────────────────────────────────────────────

const handleCheckAccount = async (row) => {
  checkingIds.value.add(row.id)
  try {
    const res = await http.get('/checkAccount', { id: row.id })
    if (res.code === 200 && res.data) {
      const { valid, status } = res.data
      accountStore.updateAccount(row.id, { ...row, status: valid ? '正常' : '异常' })
      ElMessage({ type: valid ? 'success' : 'warning', message: res.msg })
    } else {
      ElMessage.error(res.msg || '检查失败')
    }
  } catch (e) {
    ElMessage.error('检查请求失败')
  } finally {
    checkingIds.value.delete(row.id)
  }
}

const handleAddAccount = () => {
  loginMode.value = 'add'
  reloginAccount.value = null
  loginDialogVisible.value = true
}

const handleEdit = (row) => {
  dialogType.value = 'edit'
  Object.assign(accountForm, { id: row.id, name: row.name, platform: row.platform, status: row.status })
  dialogVisible.value = true
}

const handleDelete = (row) => {
  ElMessageBox.confirm(`确定要删除账号 ${row.name} 吗？`, '警告', {
    confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning',
  }).then(async () => {
    try {
      const response = await accountApi.deleteAccount(row.id)
      if (response.code === 200) {
        accountStore.deleteAccount(row.id)
        ElMessage({ type: 'success', message: '删除成功' })
      } else {
        ElMessage.error(response.msg || '删除失败')
      }
    } catch (error) {
      console.error('删除账号失败:', error)
      ElMessage.error('删除账号失败')
    }
  }).catch(() => {})
}

const handleDownloadCookie = (row) => {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  const downloadUrl = `${baseUrl}/downloadCookie?filePath=${encodeURIComponent(row.filePath)}`
  const link = document.createElement('a')
  link.href = downloadUrl
  link.download = `${row.name}_cookie.json`
  link.target = '_blank'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

const handleUploadCookie = (row) => {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.style.display = 'none'
  document.body.appendChild(input)

  input.onchange = async (event) => {
    const file = event.target.files[0]
    if (!file) return
    if (!file.name.endsWith('.json')) {
      ElMessage.error('请选择JSON格式的Cookie文件')
      document.body.removeChild(input)
      return
    }
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('id', row.id)
      formData.append('platform', row.platform)
      await http.upload('/uploadCookie', formData)
      ElMessage.success('Cookie文件上传成功')
      fetchAccounts()
    } catch (error) {
      ElMessage.error('Cookie文件上传失败')
    } finally {
      document.body.removeChild(input)
    }
  }
  input.click()
}

const handleReLogin = (row) => {
  if (isAccountDisabled(row)) return
  loginMode.value = 'relogin'
  reloginAccount.value = row
  loginDialogVisible.value = true
}

const syncingIds = reactive(new Set())

const handleSyncProfile = async (row) => {
  if (syncingIds.has(row.id)) return
  syncingIds.add(row.id)
  try {
    const res = await accountApi.syncProfile(row.id)
    if (res.code === 200 && res.data) {
      accountStore.updateAccount(row.id, {
        id: row.id,
        name: res.data.name || row.name,
        avatar: res.data.avatar || row.avatar
      })
      ElMessage.success('资料同步成功')
    } else {
      ElMessage.error(res.msg || '同步失败')
    }
  } catch (error) {
    console.error('同步资料失败:', error)
    ElMessage.error('同步资料失败')
  } finally {
    syncingIds.delete(row.id)
  }
}

// getDefaultAvatar / proxyAvatar 已抽到 @/utils/avatar

const handleOpenCreatorCenter = async (row) => {
  try {
    const res = await http.post('/openCreatorCenter', { id: row.id })
    if (res.code === 200) {
      ElMessage.success('正在打开创作中心...')
    } else {
      ElMessage.error(res.msg || '打开失败')
    }
  } catch (error) {
    console.error('打开创作中心失败:', error)
    ElMessage.error('打开创作中心失败')
  }
}

// LoginDialog 回调:登录成功后刷新账号列表(后端 sync_profile 已写库)
const onLoginSuccess = ({ platform, accountId }) => {
  fetchAccountsQuick()
}

const onLoginFail = ({ platform, errMsg }) => {
  console.warn(`登录失败 [${platform}]:`, errMsg)
}

// 批量设置标签
const batchTagDialogVisible = ref(false)
const onBatchTagDone = async () => {
  await accountStore.loadTags()
  await fetchAccountsQuick()
}

const submitAccountForm = () => {
  accountFormRef.value.validate(async (valid) => {
    if (valid) {
      try {
        const type = platformNameToId[accountForm.platform] || 1
        const res = await accountApi.updateAccount({ id: accountForm.id, type, userName: accountForm.name })
        if (res.code === 200) {
          accountStore.updateAccount(accountForm.id, { id: accountForm.id, name: accountForm.name, platform: accountForm.platform, status: accountForm.status })
          ElMessage.success('更新成功')
          dialogVisible.value = false
          fetchAccountsQuick()
        } else {
          ElMessage.error(res.msg || '更新账号失败')
        }
      } catch (error) {
        console.error('更新账号失败:', error)
        ElMessage.error('更新账号失败')
      }
    }
  })
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.account-management {
  padding: 24px;
  width: 100%;
  max-width: none;
  margin: 0;
  box-sizing: border-box;

  .page-header {
    margin-bottom: 24px;

    .header-content {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }

    .header-actions {
      display: flex;
      gap: 12px;
      flex-shrink: 0;
    }

    h1 {
      font-size: 28px;
      font-weight: 700;
      color: $text-primary;
      margin: 0;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #fff 0%, #a5b4fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .page-subtitle {
      margin: 8px 0 0;
      font-size: 14px;
      color: $text-muted;
      font-weight: 400;
    }

    .add-btn {
      background: $gradient-brand;
      border: none;
      padding: 10px 20px;
      font-weight: 600;
      border-radius: 10px;
      box-shadow: 0 4px 15px rgba($brand-start, 0.3);
      transition: all $transition-base;

      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba($brand-start, 0.4);
      }
    }

    /* 导入用户：次级按钮风格，不抢主按钮的视觉权重 */
    .add-btn.import-btn {
      background: rgba($overlay-rgb, 0.06);
      border: 1px solid rgba($overlay-rgb, 0.18);
      box-shadow: none;
      color: $text-primary;

      &:hover {
        background: rgba($overlay-rgb, 0.12);
        border-color: rgba($overlay-rgb, 0.3);
        transform: translateY(-1px);
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
      }
    }
  }

  // Platform tabs
  .platform-tabs {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    flex-wrap: wrap;

    .tab-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 16px;
      background: $bg-surface;
      border: 1px solid $border;
      border-radius: 10px;
      color: $text-secondary;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all $transition-base;

      &:hover {
        background: rgba($brand-start, 0.1);
        border-color: rgba($brand-start, 0.3);
        color: $text-primary;
      }

      &.active {
        background: rgba($brand-start, 0.15);
        border-color: $brand-start;
        color: #fff;
        box-shadow: 0 0 20px rgba($brand-start, 0.2);
      }

      .tab-count {
        background: rgba($overlay-rgb, 0.1);
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 12px;
      }

      &.active .tab-count {
        background: rgba($overlay-rgb, 0.2);
      }
    }
  }

  // Search bar
  .search-bar {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
    align-items: center;

    .search-input {
      flex: 1;
      max-width: 320px;

      :deep(.el-input__wrapper) {
        background: $bg-surface;
        border: 1px solid $border;
        border-radius: 10px;
        box-shadow: none;
        padding: 4px 16px;

        &:hover, &.is-focus {
          border-color: rgba($brand-start, 0.5);
          box-shadow: 0 0 0 3px rgba($brand-start, 0.1);
        }
      }
    }

    .refresh-btn, .check-all-btn, .batch-tag-btn {
      background: $bg-surface;
      border: 1px solid $border;
      border-radius: 10px;
      color: $text-secondary;
      padding: 8px 16px;
      transition: all $transition-base;

      &:hover {
        background: rgba($brand-start, 0.1);
        border-color: rgba($brand-start, 0.3);
        color: $text-primary;
      }
    }
  }

  .tag-filter-bar {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
    flex-wrap: wrap;

    .tag-filter-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: $bg-surface;
      border: 1px solid $border;
      border-radius: 8px;
      font-size: 13px;
      color: $text-secondary;
      cursor: pointer;
      transition: all $transition-base;

      &:hover { background: rgba($brand-start, 0.1); }
      &.active {
        background: rgba($brand-start, 0.15);
        border-color: $brand-start;
        color: #fff;
      }

      .tag-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }
    }
  }

  // Account grid
  .account-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 20px;
    margin-bottom: 24px;
    padding-bottom: 20px;
    overflow-y: visible;

    &::-webkit-scrollbar {
      width: 6px;
    }

    &::-webkit-scrollbar-track {
      background: transparent;
    }

    &::-webkit-scrollbar-thumb {
      background: $border;
      border-radius: 3px;
    }
  }

  // Account card
  .account-card {
    background: $bg-surface;
    border: 1px solid $border;
    border-radius: 16px;
    padding: 20px;
    transition: all $transition-base;
    position: relative;
    overflow: hidden;

    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, transparent, rgba($overlay-rgb, 0.1), transparent);
      opacity: 0;
      transition: opacity $transition-base;
    }

    &:hover {
      transform: translateY(-4px);
      border-color: rgba($brand-start, 0.4);
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 0 1px rgba($brand-start, 0.1);

      &::before {
        opacity: 1;
      }
    }

    // Platform-specific accent colors
    &.platform-douyin:hover { border-color: rgba($platform-douyin, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-douyin, 0.15); }
    &.platform-kuaishou:hover { border-color: rgba($platform-kuaishou, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-kuaishou, 0.15); }
    &.platform-channels:hover { border-color: rgba($platform-channels, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-channels, 0.15); }
    &.platform-xiaohongshu:hover { border-color: rgba($platform-xiaohongshu, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-xiaohongshu, 0.15); }
    &.platform-bilibili:hover { border-color: rgba($platform-bilibili, 0.5); box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3), 0 0 20px rgba($platform-bilibili, 0.15); }

    .card-body {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;

      .user-avatar {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        object-fit: cover;
        border: 2px solid $border;
        flex-shrink: 0;
      }

      .user-info {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 6px;

        .user-name {
          font-size: 16px;
          font-weight: 600;
          color: $text-primary;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .platform-row {
          display: flex;
          align-items: center;
          gap: 10px;

          .platform-name {
            font-size: 13px;
            color: $text-muted;
          }

          .disabled-tag {
            margin-left: 4px;
            border-style: dashed;
          }

          .status-badge {
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 11px;
            font-weight: 500;
            padding: 2px 8px;
            border-radius: 12px;

            .status-dot {
              width: 5px;
              height: 5px;
              border-radius: 50%;
            }

            &.normal {
              background: rgba($success-color, 0.15);
              color: $success-color;
              .status-dot { background: $success-color; }
            }

            &.pending {
              background: rgba($info-color, 0.15);
              color: $info-color;
              .status-dot { background: $info-color; animation: pulse 1.5s infinite; }
            }

            &.error {
              background: rgba($danger-color, 0.15);
              color: $danger-color;
              .status-dot { background: $danger-color; }
            }
          }
        }
      }

      .platform-logo {
        width: 48px;
        height: 48px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;

        .platform-icon {
          width: 40px;
          height: 40px;
          object-fit: contain;
        }

        .platform-letter {
          font-size: 20px;
          font-weight: 700;
        }
      }
    }

    // 标签行(独立一行,溢出跑马灯)
    .account-tags-row {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-top: 4px;
      margin-bottom: 12px;
      min-height: 22px;
    }

    .account-tags-label {
      font-size: 12px;
      color: $text-muted;
      font-weight: 500;
      flex: 0 0 auto;
      user-select: none;
    }

    .account-tags-viewport {
      // 按内容自适应,溢出时收缩并启用 mask + marquee
      flex: 0 1 auto;
      min-width: 0;
      overflow: hidden;
      position: relative;

      // 仅溢出时渐隐边缘(正常情况保持 chip 完整显示)
      &.is-overflow {
        mask-image: linear-gradient(to right, transparent 0, black 12px, black calc(100% - 12px), transparent 100%);
        -webkit-mask-image: linear-gradient(to right, transparent 0, black 12px, black calc(100% - 12px), transparent 100%);
      }
    }

    .account-tags-track {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      width: max-content;
      padding-right: 6px;

      &.marquee {
        animation: tag-marquee 18s linear infinite;

        &:hover { animation-play-state: paused; }
      }
    }

    @keyframes tag-marquee {
      from { transform: translateX(0); }
      to { transform: translateX(-50%); }
    }

    .account-tag {
      position: relative;
      display: inline-flex;
      align-items: center;
      padding: 1px 7px;
      border: 1px solid;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 500;
      line-height: 16px;
      white-space: nowrap;
      flex-shrink: 0;
      transition: all $transition-fast;

      &:hover {
        .account-tag-remove {
          opacity: 1;
          transform: scale(1);
        }
      }
    }

    .account-tag-remove {
      position: absolute;
      top: -5px;
      right: -5px;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: $danger-color;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      line-height: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      transform: scale(0.6);
      cursor: pointer;
      transition: all $transition-fast;
      box-shadow: 0 1px 4px rgba(0, 0, 0, 0.4);
      z-index: 1;

      &:hover {
        background: #dc2626;
        transform: scale(1.1);
      }
    }

    .tag-add-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      flex: 0 0 auto;
      border: 1px dashed rgba($overlay-rgb, 0.2);
      border-radius: 4px;
      background: transparent;
      color: $text-muted;
      cursor: pointer;
      font-size: 12px;
      transition: all $transition-base;

      &:hover {
        border-color: $brand-start;
        color: $brand-start;
        background: rgba($brand-start, 0.1);
      }
    }

    .card-footer {
      display: flex;
      align-items: center;
      padding-top: 12px;
      border-top: 1px solid $border-light;

      .card-actions {
        display: flex;
        align-items: center;
        gap: 6px;
      }

      .action-btn {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 6px 8px;
        border: none;
        border-radius: 8px;
        font-size: 12px;
        font-weight: 500;
        cursor: pointer;
        transition: all $transition-base;
        background: rgba($overlay-rgb, 0.05);
        color: $text-secondary;
        white-space: nowrap;
        flex-shrink: 0;

        .el-icon {
          font-size: 14px;
        }

        &:hover:not(:disabled) {
          transform: translateY(-1px);
        }

        &:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        &.is-blacklisted {
          opacity: 0.5;
          cursor: not-allowed;
        }

        &.check {
          background: rgba($success-color, 0.1);
          color: $success-color;
          &:hover:not(:disabled) { background: rgba($success-color, 0.2); box-shadow: 0 2px 10px rgba($success-color, 0.2); }
        }

        &.login {
          background: rgba($warning-color, 0.1);
          color: $warning-color;
          &:hover:not(:disabled) { background: rgba($warning-color, 0.2); box-shadow: 0 2px 10px rgba($warning-color, 0.2); }
        }

        &.sync {
          background: rgba($info-color, 0.1);
          color: $info-color;
          &:hover:not(:disabled) { background: rgba($info-color, 0.2); box-shadow: 0 2px 10px rgba($info-color, 0.2); }
        }

        &.creator {
          background: rgba($accent-cyan, 0.1);
          color: $accent-cyan;
          &:hover:not(:disabled) { background: rgba($accent-cyan, 0.2); box-shadow: 0 2px 10px rgba($accent-cyan, 0.2); }
        }

        &.delete {
          background: rgba($danger-color, 0.1);
          color: $danger-color;
          &:hover:not(:disabled) { background: rgba($danger-color, 0.2); box-shadow: 0 2px 10px rgba($danger-color, 0.2); }
        }
      }
    }
  }

  // Empty state
  .empty-state {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 300px;
    margin-bottom: 24px;

    .empty-content {
      text-align: center;
      padding: 48px;

      .empty-icon {
        font-size: 64px;
        color: $text-muted;
        margin-bottom: 16px;
      }

      h3 {
        font-size: 20px;
        font-weight: 600;
        color: $text-primary;
        margin: 0 0 8px;
      }

      p {
        font-size: 14px;
        color: $text-muted;
        margin: 0 0 24px;
      }
    }
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* ── 导入用户弹窗 ─────────────────────────────────────── */
.import-account-dialog {
  /* 紧凑化 dialog body / header / footer 间距 */
  :deep(.el-dialog__header) {
    padding: 14px 18px 10px;
    margin-right: 0;
  }
  :deep(.el-dialog__body) {
    padding: 14px 18px;
  }
  :deep(.el-dialog__footer) {
    padding: 10px 18px 14px;
  }

  .import-dialog-header {
    padding: 0;
    .import-dialog-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 16px;
      font-weight: 600;
      color: $text-primary;
      .title-icon {
        font-size: 18px;
        color: $brand-start;
      }
    }
    .import-dialog-sub {
      margin-top: 4px;
      font-size: 12px;
      color: $text-muted;
    }
  }

  .import-form-split {
    display: grid;
    grid-template-columns: 240px 1fr;
    gap: 16px;
    min-height: 260px;

    .split-left,
    .split-right {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }

    /* 让左侧搜索框固定，列表区独立滚动 */
    .split-left {
      .platform-search {
        margin-bottom: 8px;
        flex-shrink: 0;
      }
      .platform-search :deep(.el-input__wrapper) {
        background: $bg-base;
        box-shadow: 0 0 0 1px rgba($overlay-rgb, 0.1) inset;
        border-radius: 8px;
        padding: 4px 12px;
        &:hover, &.is-focus {
          box-shadow: 0 0 0 1px rgba($brand-start, 0.5) inset;
        }
      }
      .platform-search :deep(.el-input__inner) {
        height: 36px;
        color: $text-primary;
        &::placeholder { color: rgba($overlay-rgb, 0.3); }
      }

      .platform-list {
        flex: 1;
        min-height: 0;
      }
    }

    .split-section-label {
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 8px;
      font-size: 12.5px;
      font-weight: 500;
      color: $text-primary;
      flex-shrink: 0;

      .dot {
        color: $brand-start;
        font-size: 8px;
      }
    }

    /* 左侧：扁平卡片列表（参考 LoginDialog.platform-card 风格） */
    .platform-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      overflow-y: auto;
      max-height: 360px;
      padding-right: 4px;

      /* 自定义滚动条 */
      &::-webkit-scrollbar { width: 6px; }
      &::-webkit-scrollbar-track { background: transparent; }
      &::-webkit-scrollbar-thumb {
        background: rgba($overlay-rgb, 0.12);
        border-radius: 999px;
        &:hover { background: rgba($overlay-rgb, 0.2); }
      }
    }

    .platform-card-flat {
      display: flex;
      align-items: center;
      gap: 9px;
      padding: 7px 10px;
      background: $bg-surface;
      border: 1px solid $border;
      border-radius: $radius-sm;
      cursor: pointer;
      transition: all $transition-fast;
      position: relative;

      .card-logo-wrap {
        width: 26px;
        height: 26px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;

        .card-logo {
          width: 20px;
          height: 20px;
          border-radius: 4px;
          object-fit: contain;
        }
        .card-letter {
          font-size: 13px;
          font-weight: 700;
        }
      }

      .card-text {
        flex: 1;
        min-width: 0;
        display: flex;
        flex-direction: column;

        .card-name {
          font-size: 13px;
          font-weight: 500;
          color: $text-primary;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          line-height: 1.3;
        }
        .card-meta {
          font-size: 11px;
          color: $text-muted;
        }
      }

      .card-check {
        font-size: 15px;
        color: $brand-start;
      }

      &:hover {
        background: rgba($brand-start, 0.06);
        border-color: $border-active;
      }

      &.is-selected {
        background: rgba($brand-start, 0.08);
        border-color: $brand-start;

        .card-meta {
          color: $brand-start;
        }
      }
    }

    .empty-platform {
      padding: 30px 12px;
      text-align: center;
      font-size: 12px;
      color: $text-muted;
    }

    /* 右侧：cookie 输入 */
    .import-textarea {
      flex: 1;
    }
    .import-textarea :deep(textarea) {
      font-family: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
      font-size: 12.5px;
      line-height: 1.6;
      padding: 12px;
      background: $bg-base;
      border: 1px solid rgba($overlay-rgb, 0.1);
      border-radius: 8px;
      color: $text-primary;
      transition: all $transition-base;
      height: 100%;
      min-height: 220px;

      &:focus {
        background: $bg-base;
        border-color: $brand-start;
        box-shadow: 0 0 0 2px rgba($brand-start, 0.15);
      }
      &::placeholder {
        color: rgba($overlay-rgb, 0.25);
      }
    }

    .cookie-tip {
      display: flex;
      align-items: flex-start;
      gap: 6px;
      margin-top: 8px;
      padding: 7px 9px;
      background: rgba($brand-start, 0.05);
      border: 1px solid rgba($brand-start, 0.15);
      border-radius: 6px;
      font-size: 11px;
      color: $text-muted;
      line-height: 1.5;

      .el-icon {
        color: $brand-start;
        flex-shrink: 0;
        margin-top: 1px;
      }
    }
  }

  /* ── 进度阶段 ─────────────────────────────────────── */
  .import-progress {
    .import-progress-header {
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 16px;

      .platform-pill {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        padding: 6px 14px 6px 6px;
        background: rgba($overlay-rgb, 0.04);
        border: 1px solid rgba($overlay-rgb, 0.08);
        border-radius: 999px;
        font-size: 13px;

        .platform-letter {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 26px;
          height: 26px;
          border-radius: 50%;
          color: #fff;
          font-weight: 600;
          font-size: 13px;
        }
        .platform-name {
          color: $text-primary;
          font-weight: 500;
        }
      }
    }

    .progress-bar-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 20px;

      .progress-bar {
        flex: 1;
        height: 6px;
        background: rgba($overlay-rgb, 0.06);
        border-radius: 999px;
        overflow: hidden;
        position: relative;

        .progress-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, #{$brand-start} 0%, #{$brand-end} 100%);
          border-radius: 999px;
          transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);

          &.is-error {
            background: linear-gradient(90deg, #ef4444 0%, #f87171 100%);
          }
        }
      }
      .progress-bar-text {
        font-size: 12px;
        color: $text-muted;
        font-variant-numeric: tabular-nums;
        min-width: 36px;
        text-align: right;
      }
    }

    .step-list {
      list-style: none;
      padding: 0;
      margin: 0 0 16px;

      .step-item {
        display: flex;
        align-items: flex-start;
        gap: 14px;
        padding: 12px 0;
        position: relative;
        transition: opacity 0.3s;

        /* 步骤之间虚线连接 */
        &:not(:last-child)::after {
          content: '';
          position: absolute;
          left: 17px;
          top: 44px;
          bottom: -4px;
          width: 1px;
          background: rgba($overlay-rgb, 0.08);
        }

        .step-indicator {
          flex-shrink: 0;
          width: 34px;
          height: 34px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 50%;
          background: rgba($overlay-rgb, 0.04);
          border: 1px solid rgba($overlay-rgb, 0.1);
          color: $text-muted;
          font-size: 14px;
          font-weight: 600;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

          .step-icon {
            font-size: 22px;
            &.finish { color: #22c55e; }
            &.error { color: #ef4444; }
            &.process { color: $brand-start; }
          }
        }

        .step-content {
          flex: 1;
          min-width: 0;
          padding-top: 4px;

          .step-title {
            font-size: 14px;
            font-weight: 500;
            color: $text-primary;
            margin-bottom: 2px;
            transition: color 0.3s;
          }
          .step-description {
            font-size: 12px;
            color: $text-muted;
            line-height: 1.5;
            word-break: break-all;

            &.is-error {
              color: #fca5a5;
            }
          }
        }

        /* wait 状态：整体淡 */
        &.is-wait {
          opacity: 0.45;
        }

        /* process 状态：指示器脉动 */
        &.is-process .step-indicator {
          background: rgba($brand-start, 0.12);
          border-color: rgba($brand-start, 0.4);
          box-shadow: 0 0 0 4px rgba($brand-start, 0.08);
        }

        /* finish 状态 */
        &.is-finish .step-indicator {
          background: rgba($success-color, 0.12);
          border-color: rgba($success-color, 0.4);
        }

        /* error 状态 */
        &.is-error .step-indicator {
          background: rgba($danger-color, 0.12);
          border-color: rgba($danger-color, 0.4);
        }
      }
    }

    /* ── 完成态：账号预览卡片 ───────────────────────── */
    .result-card {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 14px;
      margin-top: 4px;
      background: linear-gradient(135deg,
        rgba($brand-start, 0.08) 0%,
        rgba($brand-end, 0.04) 100%);
      border: 1px solid rgba($brand-start, 0.25);
      border-radius: 12px;

      .result-avatar,
      .result-avatar-fallback {
        flex-shrink: 0;
        width: 48px;
        height: 48px;
        border-radius: 50%;
        object-fit: cover;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      }
      .result-avatar-fallback {
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, $brand-start, $brand-end);
        color: #fff;
        font-size: 20px;
        font-weight: 600;
      }
      .result-info {
        flex: 1;
        min-width: 0;
        .result-name {
          font-size: 15px;
          font-weight: 600;
          color: $text-primary;
          margin-bottom: 2px;
        }
        .result-meta {
          font-size: 12px;
          color: $text-muted;
        }
      }
    }
  }

  /* footer 按钮 */
  .footer-btn {
    background: rgba($overlay-rgb, 0.06);
    border: 1px solid rgba($overlay-rgb, 0.12);
    color: $text-primary;
    &:hover {
      background: rgba($overlay-rgb, 0.12);
      border-color: rgba($overlay-rgb, 0.2);
    }
  }
  .footer-btn-primary {
    min-width: 110px;
    background: linear-gradient(135deg, $brand-start, $brand-end);
    border: none;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    &:hover {
      opacity: 0.92;
      transform: translateY(-1px);
    }
  }
}

/* 完成态卡片上滑动画 */
.fade-up-enter-active,
.fade-up-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.fade-up-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
.fade-up-leave-to {
  opacity: 0;
  transform: translateY(-12px);
}
</style>
