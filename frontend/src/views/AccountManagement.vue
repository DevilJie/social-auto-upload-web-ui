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
    </div>

    <!-- 账号卡片列表 -->
    <div v-if="filteredAccounts.length > 0" class="account-grid">
      <div
        v-for="account in filteredAccounts"
        :key="account.id"
        :class="['account-card', `platform-${getPlatformClass(account.platform)}`]"
      >
        <!-- 卡片主体：头像 + 用户信息 -->
        <div class="card-body">
          <el-avatar :src="account.avatar || getDefaultAvatar(account.name)" :size="48" class="user-avatar" />
          <div class="user-info">
            <span class="user-name">{{ account.name }}</span>
            <div class="platform-row">
              <span class="platform-name">{{ account.platform }}</span>
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

        <!-- 卡片底部：操作按钮 -->
        <div class="card-footer">
          <div class="card-actions">
            <button v-if="account.status === '异常'" class="action-btn login" @click="handleReLogin(account)">
              <el-icon><Key /></el-icon>
              登录
            </button>
            <button v-else class="action-btn check" @click="handleCheckAccount(account)" :disabled="checkingIds.has(account.id)">
              <el-icon v-if="checkingIds.has(account.id)" class="is-loading"><Loading /></el-icon>
              <template v-else>
                <el-icon><Check /></el-icon>
                检查
              </template>
            </button>
            <button class="action-btn sync" @click="handleSyncProfile(account)" :disabled="account.status === '异常' || syncingIds.has(account.id)">
              <el-icon v-if="syncingIds.has(account.id)" class="is-loading"><Loading /></el-icon>
              <template v-else>
                <el-icon><Refresh /></el-icon>
                同步
              </template>
            </button>
            <button class="action-btn creator" @click="handleOpenCreatorCenter(account)" :disabled="account.status === '异常'">
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

    <!-- 添加/编辑账号对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? '添加账号' : (accountForm.id ? '重新登录' : '编辑账号')"
      width="500px"
      :close-on-click-modal="false"
      :close-on-press-escape="!sseConnecting"
      :show-close="!sseConnecting"
    >
      <el-form :model="accountForm" label-width="80px" :rules="rules" ref="accountFormRef">
        <el-form-item label="平台" prop="platform">
          <el-select
            v-model="accountForm.platform"
            placeholder="请选择平台"
            :disabled="dialogType === 'edit' || sseConnecting"
            style="width: 100%"
            @change="onPlatformSelect"
          >
            <el-option
              v-for="p in platformOptions"
              :key="p.value"
              :label="p.label"
              :value="p.label"
            />
          </el-select>
        </el-form-item>
        <el-form-item v-if="dialogType === 'edit'" label="名称" prop="name">
          <el-input
            v-model="accountForm.name"
            placeholder="扫码后自动同步"
            disabled
          />
        </el-form-item>

        <!-- 登录状态提示 -->
        <div v-if="sseConnecting" class="qrcode-container">
          <div v-if="!loginStatus" class="loading-wrapper">
            <el-icon class="is-loading"><Refresh /></el-icon>
            <span>等待登录中...</span>
          </div>
          <div v-else-if="loginStatus === '200'" class="status-wrapper success">
            <el-icon><CircleCheckFilled /></el-icon>
            <span>{{ dialogType === 'edit' ? '登录成功' : '添加成功' }}</span>
          </div>
          <div v-else-if="loginStatus === '500'" class="status-wrapper error">
            <el-icon><CircleCloseFilled /></el-icon>
            <span>添加失败，请稍后再试</span>
          </div>
        </div>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button
            type="primary"
            @click="submitAccountForm"
            :loading="sseConnecting"
            :disabled="sseConnecting"
          >
            {{ sseConnecting ? '请求中' : '确认' }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { Refresh, CircleCheckFilled, CircleCloseFilled, Loading, Link, Plus, Edit, Delete, Check, Folder, Key } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { accountApi } from '@/api/account'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { http } from '@/utils/request'
import { platformList, platformNameToId, platformCssMap, getPlatformByName, PLATFORMS } from '@/config/platforms'

const accountStore = useAccountStore()
const appStore = useAppStore()

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

const platformOptions = platformList.map(p => ({
  label: p.name,
  value: String(p.id),
  logo: p.logo,
  color: p.color,
  bg: p.bgColor,
}))

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

onMounted(() => {
  fetchAccountsQuick()
})

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

const sseConnecting = ref(false)
const checkingIds = ref(new Set())

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
const qrCodeData = ref('')
const loginStatus = ref('')

const onPlatformSelect = async (value) => {
  accountFormRef.value?.validateField('platform')
  if (value === '小红书') {
    try {
      await ElMessageBox.confirm(
        '由于小红书反检测机制比较恶心，如果出现被警告的情况！请立即停止使用小红书渠道！',
        '风险警告',
        { confirmButtonText: '我已知悉，继续添加', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      accountForm.platform = ''
    }
  }
}

const handleAddAccount = () => {
  dialogType.value = 'add'
  Object.assign(accountForm, { id: null, name: '', platform: '', status: '正常' })
  sseConnecting.value = false
  qrCodeData.value = ''
  loginStatus.value = ''
  dialogVisible.value = true
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
  dialogType.value = 'edit'
  Object.assign(accountForm, { id: row.id, name: row.name, platform: row.platform, status: row.status })
  sseConnecting.value = false
  qrCodeData.value = ''
  loginStatus.value = ''
  dialogVisible.value = true
  setTimeout(() => connectSSE(row.platform, row.id), 300)
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

const getDefaultAvatar = (name) => {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=random`
}

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

let eventSource = null

const closeSSEConnection = () => {
  if (eventSource) { eventSource.close(); eventSource = null }
}

const connectSSE = (platform, accountId) => {
  closeSSEConnection()
  sseConnecting.value = true
  qrCodeData.value = ''
  loginStatus.value = ''

  const type = platformNameToId[platform] ? String(platformNameToId[platform]) : '1'
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  // 使用 UUID 作为临时标识，不再需要用户输入名称
  const tempId = crypto.randomUUID()
  let url = `${baseUrl}/login?type=${type}&id=${encodeURIComponent(tempId)}`
  if (accountId) {
    url += `&account_id=${encodeURIComponent(accountId)}`
  }

  eventSource = new EventSource(url)

  eventSource.onmessage = (event) => {
    const data = event.data

    // 先尝试解析 JSON（登录响应）
    try {
      const result = JSON.parse(data)
      if (result.status === '200') {
        loginStatus.value = '200'
        closeSSEConnection()
        setTimeout(() => {
          setTimeout(() => {
            dialogVisible.value = false
            sseConnecting.value = false
            ElMessage.success(dialogType.value === 'edit' ? '登录成功' : '账号添加成功')
            ElMessage({ type: 'info', message: '正在同步账号信息...', duration: 0 })
            fetchAccountsQuick().then(() => { ElMessage.closeAll(); ElMessage.success('账号信息已更新') })
          }, 1000)
        }, 1000)
        return
      }
      if (result.status === '500') {
        loginStatus.value = '500'
        closeSSEConnection()
        sseConnecting.value = false
        qrCodeData.value = ''
        ElMessage.error(result.msg || '登录失败，请稍后再试')
        setTimeout(() => { loginStatus.value = '' }, 2000)
        return
      }
      if (result.status === '0' || result.status === 'error') {
        loginStatus.value = '500'
        closeSSEConnection()
        sseConnecting.value = false
        qrCodeData.value = ''
        ElMessage.error(result.msg || result.error || '登录已取消')
        setTimeout(() => { loginStatus.value = '' }, 2000)
        return
      }
    } catch (e) {}

    if (data === '500') {
      loginStatus.value = '500'
      closeSSEConnection()
      setTimeout(() => { sseConnecting.value = false; qrCodeData.value = ''; loginStatus.value = '' }, 2000)
    } else if (!qrCodeData.value && data.length > 100) {
      // 二维码图片
      try {
        qrCodeData.value = data.startsWith('data:image') ? data : `data:image/png;base64,${data}`
      } catch (error) {}
    } else if (data === '200') {
      // 兼容旧格式
      loginStatus.value = '200'
      closeSSEConnection()
      setTimeout(() => {
        setTimeout(() => {
          dialogVisible.value = false
          sseConnecting.value = false
          ElMessage.success(dialogType.value === 'edit' ? '登录成功' : '账号添加成功')
          ElMessage({ type: 'info', message: '正在同步账号信息...', duration: 0 })
          fetchAccountsQuick().then(() => { ElMessage.closeAll(); ElMessage.success('账号信息已更新') })
        }, 1000)
      }, 1000)
    }
  }

  eventSource.onerror = (error) => {
    console.error('SSE连接错误:', error)
    ElMessage.error('连接服务器失败，请稍后再试')
    closeSSEConnection()
    sseConnecting.value = false
  }
}

const submitAccountForm = () => {
  accountFormRef.value.validate(async (valid) => {
    if (valid) {
      if (dialogType.value === 'add') {
        connectSSE(accountForm.platform)
      } else {
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
    }
  })
}

onBeforeUnmount(() => { closeSSEConnection() })
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

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

    .refresh-btn, .check-all-btn {
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

    .card-footer {
      display: flex;
      align-items: center;
      padding-top: 12px;
      border-top: 1px solid $border-light;

      .card-actions {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
      }

      .action-btn {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 6px 12px;
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

  
  // QR code area
  .qrcode-container {
    margin-top: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 250px;

    .qrcode-wrapper {
      text-align: center;

      .qrcode-tip {
        margin-bottom: 16px;
        color: $text-secondary;
      }

      .qrcode-image {
        max-width: 200px;
        max-height: 200px;
        border: 1px solid $border;
        background-color: #000;
        border-radius: $radius-sm;
      }
    }

    .loading-wrapper, .status-wrapper {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 12px;

      .el-icon {
        font-size: 48px;
        &.is-loading { animation: rotate 1s linear infinite; }
      }
      span { font-size: 16px; }
    }

    .success .el-icon { color: $success-color; }
    .error .el-icon { color: $danger-color; }
  }

  .dialog-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
  }
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
