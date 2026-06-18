<template>
  <div class="account-management">
    <div class="page-header">
      <div class="header-content">
        <div class="header-text">
          <h1>账号管理</h1>
          <p class="page-subtitle">管理所有平台账号</p>
        </div>
        <el-button type="primary" class="add-btn" @click="handleAddAccount">
          <el-icon><Plus /></el-icon>
          添加账号
        </el-button>
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
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { Refresh, Loading, Link, Plus, Edit, Delete, Check, Folder, Key, CollectionTag, Close } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { accountApi } from '@/api/account'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { http } from '@/utils/request'
import { platformList, platformNameToId, platformNameToKey, platformCssMap, getPlatformByName } from '@/config/platforms'
import { getDefaultAvatar, proxyAvatar } from '@/utils/avatar'
import LoginDialog from '@/components/LoginDialog.vue'
import TagPopover from '@/components/TagPopover.vue'
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

const fetchAccounts = async () => {
  if (appStore.isAccountRefreshing) return
  appStore.setAccountRefreshing(true)
  try {
    const res = await accountApi.getValidAccounts()
    if (res.code === 200 && res.data) {
      accountStore.setAccounts(res.data)
      ElMessage.success('账号数据获取成功')
      if (appStore.isFirstTimeAccountManagement) {
        appStore.setAccountManagementVisited()
      }
    } else {
      ElMessage.error('获取账号数据失败')
    }
  } catch (error) {
    console.error('获取账号数据失败:', error)
    ElMessage.error('获取账号数据失败')
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
        background: rgba(255, 255, 255, 0.1);
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 12px;
      }

      &.active .tab-count {
        background: rgba(255, 255, 255, 0.2);
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
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
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
      border: 1px dashed rgba(255,255,255,0.2);
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
        background: rgba(255, 255, 255, 0.05);
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
</style>
