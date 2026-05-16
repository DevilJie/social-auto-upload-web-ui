<template>
  <div class="account-management">
    <div class="page-header">
      <h1>账号管理</h1>
      <p class="page-subtitle">管理所有平台账号</p>
    </div>

    <div class="account-container">
      <div class="account-toolbar">
        <div class="toolbar-left">
          <el-select v-model="activeTab" style="width: 160px">
            <el-option v-for="f in filterOptions" :key="f.value" :label="f.label" :value="f.value" />
          </el-select>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索名称或账号"
            prefix-icon="Search"
            clearable
            style="width: 240px"
          />
        </div>
        <div class="toolbar-right">
          <el-button @click="fetchAccountsQuick">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
          <el-button @click="fetchAccounts" :loading="appStore.isAccountRefreshing">
            <el-icon v-if="!appStore.isAccountRefreshing"><Loading /></el-icon>
            批量检查
          </el-button>
          <el-button type="primary" @click="handleAddAccount">添加账号</el-button>
        </div>
      </div>

      <div v-if="filteredAccounts.length > 0" class="account-list">
        <el-table :data="filteredAccounts" style="width: 100%">
          <el-table-column label="头像" width="70">
            <template #default="scope">
              <el-avatar :src="scope.row.avatar || getDefaultAvatar(scope.row.name)" :size="36" />
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" width="180">
            <template #default="scope">
              <span class="account-name">{{ scope.row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="platform" label="平台" width="120">
            <template #default="scope">
              <span :class="['platform-tag', getPlatformClass(scope.row.platform)]">
                {{ scope.row.platform }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="120">
            <template #default="scope">
              <span :class="['status-tag', getStatusClass(scope.row.status), { clickable: isStatusClickable(scope.row.status) }]"
                @click="handleStatusClick(scope.row)">
                <el-icon :class="scope.row.status === '验证中' ? 'is-loading' : ''" v-if="scope.row.status === '验证中'">
                  <Loading />
                </el-icon>
                {{ scope.row.status }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="320">
            <template #default="scope">
              <div class="action-cell">
                <button class="action-btn" @click="handleCheckAccount(scope.row)"
                  :disabled="checkingIds.has(scope.row.id)">
                  <el-icon v-if="checkingIds.has(scope.row.id)" class="is-loading"><Loading /></el-icon>
                  {{ checkingIds.has(scope.row.id) ? '检查中' : '检查' }}
                </button>
                <button class="action-btn" @click="handleEdit(scope.row)">编辑</button>
                <button class="action-btn primary" @click="handleSyncProfile(scope.row)"
                  :disabled="syncingIds.has(scope.row.id)">
                  <el-icon v-if="syncingIds.has(scope.row.id)" class="is-loading"><Loading /></el-icon>
                  {{ syncingIds.has(scope.row.id) ? '同步中' : '同步资料' }}
                </button>
                <button class="action-btn info" @click="handleOpenCreatorCenter(scope.row)">
                  <el-icon><Link /></el-icon> 创作中心
                </button>
                <button class="action-btn info" @click="handleDownloadCookie(scope.row)">
                  <el-icon><Download /></el-icon> Cookie
                </button>
                <button class="action-btn info" @click="handleUploadCookie(scope.row)">
                  <el-icon><Upload /></el-icon> Cookie
                </button>
                <button class="action-btn danger" @click="handleDelete(scope.row)">删除</button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-else class="empty-data">
        <el-empty :description="searchKeyword ? '未找到匹配账号' : '暂无账号数据'" />
      </div>
    </div>

    <!-- 添加/编辑账号对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? '添加账号' : '编辑账号'"
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

        <!-- 二维码显示区域 -->
        <div v-if="sseConnecting" class="qrcode-container">
          <div v-if="qrCodeData && !loginStatus" class="qrcode-wrapper">
            <p class="qrcode-tip">请使用对应平台APP扫描二维码登录</p>
            <img :src="qrCodeData" alt="登录二维码" class="qrcode-image" />
          </div>
          <div v-else-if="!qrCodeData && !loginStatus" class="loading-wrapper">
            <el-icon class="is-loading"><Refresh /></el-icon>
            <span>请求中...</span>
          </div>
          <div v-else-if="loginStatus === '200'" class="status-wrapper success">
            <el-icon><CircleCheckFilled /></el-icon>
            <span>添加成功</span>
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
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { Refresh, CircleCheckFilled, CircleCloseFilled, Download, Upload, Loading, Link } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { accountApi } from '@/api/account'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { http } from '@/utils/request'
import { platformList, platformNameToId, platformCssMap, getPlatformByName } from '@/config/platforms'

const accountStore = useAccountStore()
const appStore = useAppStore()

const activeTab = ref('all')
const searchKeyword = ref('')

const filterOptions = [
  { label: '全部', value: 'all' },
  ...platformList.map(p => ({ label: p.name, value: p.name }))
]

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
      accountStore.updateAccount(row.id, { ...row, status: valid ? '正常' : '失效' })
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

const onPlatformSelect = () => {
  accountFormRef.value?.validateField('platform')
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
  setTimeout(() => connectSSE(row.platform), 300)
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

const connectSSE = (platform) => {
  closeSSEConnection()
  sseConnecting.value = true
  qrCodeData.value = ''
  loginStatus.value = ''

  const type = platformNameToId[platform] ? String(platformNameToId[platform]) : '1'
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  // 使用 UUID 作为临时标识，不再需要用户输入名称
  const tempId = crypto.randomUUID()
  const url = `${baseUrl}/login?type=${type}&id=${encodeURIComponent(tempId)}`

  eventSource = new EventSource(url)

  eventSource.onmessage = (event) => {
    const data = event.data

    // 先尝试解析 JSON（登录响应）
    try {
      const result = JSON.parse(data)
      if (result.status === '200') {
        loginStatus.value = '200'
        setTimeout(() => {
          closeSSEConnection()
          setTimeout(() => {
            dialogVisible.value = false
            sseConnecting.value = false
            ElMessage.success(dialogType.value === 'edit' ? '重新登录成功' : '账号添加成功')
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
      setTimeout(() => {
        closeSSEConnection()
        setTimeout(() => {
          dialogVisible.value = false
          sseConnecting.value = false
          ElMessage.success(dialogType.value === 'edit' ? '重新登录成功' : '账号添加成功')
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

  .account-container {
    background-color: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 4px 24px 24px;

    .account-toolbar {
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

    // Table overrides
    .account-list {
      margin-bottom: 20px;

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

      .account-name {
        font-weight: 500;
        color: $text-primary;
      }

      // Platform tags with gradient backgrounds
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
        gap: 4px;
        padding: 3px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
        line-height: 1.5;
        white-space: nowrap;

        &.normal {
          background: rgba(34, 197, 94, 0.15);
          color: $success-color;
        }

        &.pending {
          background: rgba(59, 130, 246, 0.15);
          color: $info-color;
        }

        &.error {
          background: rgba(239, 68, 68, 0.15);
          color: $danger-color;
        }

        &.clickable {
          cursor: pointer;
          transition: $transition-base;

          &:hover {
            transform: scale(1.05);
            box-shadow: 0 0 8px rgba(0, 0, 0, 0.2);
          }
        }

        .el-icon.is-loading {
          animation: rotate 1s linear infinite;
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

          &.info:hover {
            color: $text-secondary;
            background: rgba(148, 163, 184, 0.1);
          }

          &.danger:hover {
            color: $danger-color;
            background: rgba(239, 68, 68, 0.1);
          }
        }
      }
    }

    .empty-data {
      padding: 60px 0;
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
</style>
