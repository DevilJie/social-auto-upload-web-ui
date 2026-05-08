<template>
  <div class="publish-center">
    <!-- Tab管理区域 -->
    <div class="tab-bar">
      <div class="tab-list">
        <div
          v-for="tab in tabs"
          :key="tab.name"
          :class="['tab-item', { active: activeTab === tab.name }]"
          @click="activeTab = tab.name"
        >
          <span class="tab-label">{{ tab.label }}</span>
          <el-icon
            v-if="tabs.length > 1"
            class="tab-close"
            @click.stop="removeTab(tab.name)"
          >
            <Close />
          </el-icon>
        </div>
      </div>
      <div class="tab-actions">
        <el-button
          size="small"
          @click="addTab"
          class="action-btn add-tab-btn"
        >
          <el-icon><Plus /></el-icon>
          添加Tab
        </el-button>
        <el-button
          size="small"
          @click="batchPublish"
          :loading="batchPublishing"
          class="action-btn batch-publish-btn"
        >
          批量发布
        </el-button>
      </div>
    </div>

    <!-- 内容区域 -->
    <div class="publish-content">
      <div
        v-for="tab in tabs"
        :key="tab.name"
        v-show="activeTab === tab.name"
        class="tab-content"
      >
        <!-- 发布状态提示 -->
        <div v-if="tab.publishStatus" class="publish-status">
          <el-alert
            :title="tab.publishStatus.message"
            :type="tab.publishStatus.type"
            :closable="false"
            show-icon
          />
        </div>

        <!-- 两栏布局 -->
        <div class="publish-layout">
          <!-- ===== 左侧栏 (60%) ===== -->
          <div class="column-left">
            <!-- 视频上传区域 -->
            <section class="form-section upload-section">
              <h3 class="section-title">视频</h3>
              <div class="upload-actions">
                <el-button type="primary" @click="showUploadOptions(tab)" class="upload-btn">
                  <el-icon><Upload /></el-icon>
                  上传视频
                </el-button>
                <el-button plain @click="selectMaterialLibraryDirect(tab)" class="material-btn">
                  <el-icon><Folder /></el-icon>
                  素材库
                </el-button>
              </div>

              <!-- 已上传文件列表 -->
              <div v-if="tab.fileList.length > 0" class="uploaded-files">
                <div class="file-list">
                  <div v-for="(file, index) in tab.fileList" :key="index" class="file-item">
                    <div class="file-info">
                      <el-link :href="file.url" target="_blank" type="primary" class="file-name">{{ file.name }}</el-link>
                      <span class="file-size">{{ (file.size / 1024 / 1024).toFixed(2) }}MB</span>
                    </div>
                    <el-button type="danger" size="small" text @click="removeFile(tab, index)" class="file-remove">删除</el-button>
                  </div>
                </div>
              </div>
            </section>

            <!-- 标题输入 -->
            <section class="form-section title-section">
              <h3 class="section-title">标题</h3>
              <el-input
                v-model="tab.title"
                type="textarea"
                :rows="3"
                placeholder="请输入标题"
                maxlength="100"
                show-word-limit
                class="title-input"
              />
            </section>

            <!-- 话题输入 -->
            <section class="form-section topic-section">
              <h3 class="section-title">话题</h3>
              <div class="topic-display">
                <div class="selected-topics" v-if="tab.selectedTopics.length > 0">
                  <el-tag
                    v-for="(topic, index) in tab.selectedTopics"
                    :key="index"
                    closable
                    @close="removeTopic(tab, index)"
                    class="topic-tag"
                  >
                    #{{ topic }}
                  </el-tag>
                </div>
                <el-button
                  type="primary"
                  plain
                  size="small"
                  @click="openTopicDialog(tab)"
                  class="add-topic-btn"
                >
                  添加话题
                </el-button>
              </div>
            </section>
          </div>

          <!-- ===== 右侧栏 (40%) ===== -->
          <div class="column-right">
            <!-- 平台选择 — 卡片式 -->
            <section class="form-section platform-section">
              <h3 class="section-title">平台</h3>
              <div class="platform-cards">
                <div
                  v-for="p in platforms"
                  :key="p.key"
                  :class="['platform-card', `platform-${getPlatformKey(p.key)}`, { active: tab.selectedPlatform === p.key }]"
                  @click="tab.selectedPlatform = p.key"
                >
                  <div class="platform-letter">{{ p.name.charAt(0) }}</div>
                  <div class="platform-name">{{ p.name }}</div>
                </div>
              </div>
            </section>

            <!-- 账号选择 -->
            <section class="form-section account-section">
              <h3 class="section-title">账号</h3>
              <div class="account-display">
                <div class="selected-accounts" v-if="tab.selectedAccounts.length > 0">
                  <el-tag
                    v-for="(account, index) in tab.selectedAccounts"
                    :key="index"
                    closable
                    @close="removeAccount(tab, index)"
                    class="account-tag"
                  >
                    {{ getAccountDisplayName(account) }}
                  </el-tag>
                </div>
                <el-button
                  type="primary"
                  plain
                  size="small"
                  @click="openAccountDialog(tab)"
                  class="select-account-btn"
                >
                  选择账号
                </el-button>
              </div>
            </section>

            <!-- 原创声明 -->
            <section class="form-section original-section">
              <div class="toggle-row">
                <span class="toggle-label">声明原创</span>
                <el-switch v-model="tab.isOriginal" />
              </div>
            </section>

            <!-- 草稿选项 (仅在视频号可见) -->
            <section v-if="tab.selectedPlatform === 2" class="form-section draft-section">
              <div class="toggle-row">
                <span class="toggle-label">视频号仅保存草稿(用手机发布)</span>
                <el-switch v-model="tab.isDraft" />
              </div>
            </section>

            <!-- 商品链接 (仅在抖音可见) -->
            <section v-if="tab.selectedPlatform === 3" class="form-section product-section">
              <h3 class="section-title">商品链接</h3>
              <el-input
                v-model="tab.productTitle"
                type="text"
                placeholder="请输入商品名称"
                maxlength="200"
                class="product-input"
              />
              <el-input
                v-model="tab.productLink"
                type="text"
                placeholder="请输入商品链接"
                maxlength="200"
                class="product-input"
              />
            </section>

            <!-- 定时发布 -->
            <section class="form-section schedule-section">
              <div class="toggle-row">
                <span class="toggle-label">定时发布</span>
                <el-switch v-model="tab.scheduleEnabled" />
              </div>
              <div v-if="tab.scheduleEnabled" class="schedule-settings">
                <div class="schedule-item">
                  <span class="label">每天发布视频数：</span>
                  <el-select v-model="tab.videosPerDay" placeholder="选择发布数量" size="small">
                    <el-option
                      v-for="num in 55"
                      :key="num"
                      :label="num"
                      :value="num"
                    />
                  </el-select>
                </div>
                <div class="schedule-item">
                  <span class="label">每天发布时间：</span>
                  <div class="time-list">
                    <el-time-select
                      v-for="(time, index) in tab.dailyTimes"
                      :key="index"
                      v-model="tab.dailyTimes[index]"
                      start="00:00"
                      step="00:30"
                      end="23:30"
                      placeholder="选择时间"
                      size="small"
                    />
                  </div>
                  <el-button
                    v-if="tab.dailyTimes.length < tab.videosPerDay"
                    type="primary"
                    size="small"
                    @click="tab.dailyTimes.push('10:00')"
                  >
                    添加时间
                  </el-button>
                </div>
                <div class="schedule-item">
                  <span class="label">开始天数：</span>
                  <el-select v-model="tab.startDays" placeholder="选择开始天数" size="small">
                    <el-option :label="'明天'" :value="0" />
                    <el-option :label="'后天'" :value="1" />
                  </el-select>
                </div>
              </div>
            </section>

            <!-- 操作按钮 -->
            <div class="action-buttons">
              <el-button @click="cancelPublish(tab)">取消</el-button>
              <el-button
                type="primary"
                @click="confirmPublish(tab)"
                :loading="tab.publishing || false"
                class="publish-btn"
              >
                {{ tab.publishing ? '发布中...' : '发布' }}
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 弹窗部分 (全局) ===== -->

    <!-- 上传选项弹窗 -->
    <el-dialog
      v-model="uploadOptionsVisible"
      title="选择上传方式"
      width="400px"
      class="upload-options-dialog"
    >
      <div class="upload-options-content">
        <el-button type="primary" @click="selectLocalUpload" class="option-btn">
          <el-icon><Upload /></el-icon>
          本地上传
        </el-button>
        <el-button type="success" @click="selectMaterialLibrary" class="option-btn">
          <el-icon><Folder /></el-icon>
          素材库
        </el-button>
      </div>
    </el-dialog>

    <!-- 本地上传弹窗 -->
    <el-dialog
      v-model="localUploadVisible"
      title="本地上传"
      width="600px"
      class="local-upload-dialog"
    >
      <el-upload
        class="video-upload"
        drag
        :auto-upload="true"
        :action="`${apiBaseUrl}/upload`"
        :on-success="(response, file) => handleUploadSuccess(response, file, currentUploadTab)"
        :on-error="handleUploadError"
        multiple
        accept="video/*"
        :headers="authHeaders"
      >
        <el-icon class="el-icon--upload"><Upload /></el-icon>
        <div class="el-upload__text">
          将视频文件拖到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持MP4、AVI等视频格式，可上传多个文件
          </div>
        </template>
      </el-upload>
    </el-dialog>

    <!-- 批量发布进度对话框 -->
    <el-dialog
      v-model="batchPublishDialogVisible"
      title="批量发布进度"
      width="500px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
    >
      <div class="publish-progress">
        <el-progress
          :percentage="publishProgress"
          :status="publishProgress === 100 ? 'success' : ''"
        />
        <div v-if="currentPublishingTab" class="current-publishing">
          正在发布：{{ currentPublishingTab.label }}
        </div>

        <!-- 发布结果列表 -->
        <div class="publish-results" v-if="publishResults.length > 0">
          <div
            v-for="(result, index) in publishResults"
            :key="index"
            :class="['result-item', result.status]"
          >
            <el-icon v-if="result.status === 'success'"><Check /></el-icon>
            <el-icon v-else-if="result.status === 'error'"><Close /></el-icon>
            <el-icon v-else><InfoFilled /></el-icon>
            <span class="label">{{ result.label }}</span>
            <span class="message">{{ result.message }}</span>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button
            @click="cancelBatchPublish"
            :disabled="publishProgress === 100"
          >
            取消发布
          </el-button>
          <el-button
            type="primary"
            @click="batchPublishDialogVisible = false"
            v-if="publishProgress === 100"
          >
            关闭
          </el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 素材库选择弹窗 -->
    <el-dialog
      v-model="materialLibraryVisible"
      title="选择素材"
      width="800px"
      class="material-library-dialog"
    >
      <div class="material-library-content">
        <el-checkbox-group v-model="selectedMaterials">
          <div class="material-list">
            <div
              v-for="material in materials"
              :key="material.id"
              class="material-item"
            >
              <el-checkbox :label="material.id" class="material-checkbox">
                <div class="material-info">
                  <div class="material-name">{{ material.filename }}</div>
                  <div class="material-details">
                    <span class="file-size">{{ material.filesize }}MB</span>
                    <span class="upload-time">{{ material.upload_time }}</span>
                  </div>
                </div>
              </el-checkbox>
            </div>
          </div>
        </el-checkbox-group>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="materialLibraryVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmMaterialSelection">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 账号选择弹窗 -->
    <el-dialog
      v-model="accountDialogVisible"
      title="选择账号"
      width="600px"
      class="account-dialog"
    >
      <div class="account-dialog-content">
        <el-checkbox-group v-model="tempSelectedAccounts">
          <div class="account-list">
            <el-checkbox
              v-for="account in availableAccounts"
              :key="account.id"
              :label="account.id"
              class="account-item"
            >
              <div class="account-info">
                <span class="account-name">{{ account.name }}</span>
              </div>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="accountDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmAccountSelection">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 添加话题弹窗 -->
    <el-dialog
      v-model="topicDialogVisible"
      title="添加话题"
      width="600px"
      class="topic-dialog"
    >
      <div class="topic-dialog-content">
        <!-- 自定义话题输入 -->
        <div class="custom-topic-input">
          <el-input
            v-model="customTopic"
            placeholder="输入自定义话题"
            class="custom-input"
          >
            <template #prepend>#</template>
          </el-input>
          <el-button type="primary" @click="addCustomTopic">添加</el-button>
        </div>

        <!-- 推荐话题 -->
        <div class="recommended-topics">
          <h4>推荐话题</h4>
          <div class="topic-grid">
            <el-button
              v-for="topic in recommendedTopics"
              :key="topic"
              :type="currentTab?.selectedTopics?.includes(topic) ? 'primary' : 'default'"
              @click="toggleRecommendedTopic(topic)"
              class="topic-btn"
            >
              {{ topic }}
            </el-button>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="topicDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmTopicSelection">确定</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { Upload, Plus, Close, Folder } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { materialApi } from '@/api/material'
import { http } from '@/utils/request'

// API base URL
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

// Authorization headers
const authHeaders = computed(() => ({
  'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
}))

// 当前激活的tab
const activeTab = ref('tab1')

// tab计数器
let tabCounter = 1

// 获取应用状态管理
const appStore = useAppStore()

// 上传相关状态
const uploadOptionsVisible = ref(false)
const localUploadVisible = ref(false)
const materialLibraryVisible = ref(false)
const currentUploadTab = ref(null)
const selectedMaterials = ref([])
const materials = computed(() => appStore.materials)

// 批量发布相关状态
const batchPublishing = ref(false)
const batchPublishMessage = ref('')
const batchPublishType = ref('info')

// 平台列表 - 对应后端type字段
const platforms = [
  { key: 3, name: '抖音' },
  { key: 4, name: '快手' },
  { key: 2, name: '视频号' },
  { key: 1, name: '小红书' }
]

// 平台key到CSS名称的映射
const getPlatformKey = (key) => {
  const map = { 3: 'douyin', 4: 'kuaishou', 2: 'channels', 1: 'xiaohongshu' }
  return map[key] || 'default'
}

const defaultTabInit = {
  name: 'tab1',
  label: '发布1',
  fileList: [], // 后端返回的文件名列表
  displayFileList: [], // 用于显示的文件列表
  selectedAccounts: [], // 选中的账号ID列表
  selectedPlatform: 1, // 选中的平台（单选）
  title: '',
  productLink: '', // 商品链接
  productTitle: '', // 商品名称
  selectedTopics: [], // 话题列表（不带#号）
  scheduleEnabled: false, // 定时发布开关
  videosPerDay: 1, // 每天发布视频数量
  dailyTimes: ['10:00'], // 每天发布时间点列表
  startDays: 0, // 从今天开始计算的发布天数，0表示明天，1表示后天
  publishStatus: null, // 发布状态，包含message和type
  publishing: false, // 发布状态，用于控制按钮loading效果
  isDraft: false, // 是否保存为草稿，仅视频号平台可见
  isOriginal: false // 是否标记为原创
}

// helper to create a fresh deep-copied tab from defaultTabInit
const makeNewTab = () => {
  // prefer structuredClone when available (newer browsers/node), fallback to JSON
  try {
    return typeof structuredClone === 'function' ? structuredClone(defaultTabInit) : JSON.parse(JSON.stringify(defaultTabInit))
  } catch (e) {
    return JSON.parse(JSON.stringify(defaultTabInit))
  }
}

// tab页数据 - 默认只有一个tab (use deep copy to avoid shared refs)
const tabs = reactive([
  makeNewTab()
])

// 账号相关状态
const accountDialogVisible = ref(false)
const tempSelectedAccounts = ref([])
const currentTab = ref(null)

// 获取账号状态管理
const accountStore = useAccountStore()

// 根据选择的平台获取可用账号列表
const availableAccounts = computed(() => {
  const platformMap = {
    3: '抖音',
    2: '视频号',
    1: '小红书',
    4: '快手'
  }
  const currentPlatform = currentTab.value ? platformMap[currentTab.value.selectedPlatform] : null
  return currentPlatform ? accountStore.accounts.filter(acc => acc.platform === currentPlatform) : []
})

// 话题相关状态
const topicDialogVisible = ref(false)
const customTopic = ref('')

// 推荐话题列表
const recommendedTopics = [
  '游戏', '电影', '音乐', '美食', '旅行', '文化',
  '科技', '生活', '娱乐', '体育', '教育', '艺术',
  '健康', '时尚', '美妆', '摄影', '宠物', '汽车'
]

// 添加新tab
const addTab = () => {
  tabCounter++
  const newTab = makeNewTab()
  newTab.name = `tab${tabCounter}`
  newTab.label = `发布${tabCounter}`
  tabs.push(newTab)
  activeTab.value = newTab.name
}

// 删除tab
const removeTab = (tabName) => {
  const index = tabs.findIndex(tab => tab.name === tabName)
  if (index > -1) {
    tabs.splice(index, 1)
    // 如果删除的是当前激活的tab，切换到第一个tab
    if (activeTab.value === tabName && tabs.length > 0) {
      activeTab.value = tabs[0].name
    }
  }
}

// 处理文件上传成功
const handleUploadSuccess = (response, file, tab) => {
  if (response.code === 200) {
    // 获取文件路径
    const filePath = response.data.path || response.data
    // 从路径中提取文件名
    const filename = filePath.split('/').pop()

    // 保存文件信息到fileList，包含文件路径和其他信息
    const fileInfo = {
      name: file.name,
      url: materialApi.getMaterialPreviewUrl(filename), // 使用getMaterialPreviewUrl生成预览URL
      path: filePath,
      size: file.size,
      type: file.type
    }

    // 添加到文件列表
    tab.fileList.push(fileInfo)

    // 更新显示列表
    tab.displayFileList = [...tab.fileList.map(item => ({
      name: item.name,
      url: item.url
    }))]

    ElMessage.success('文件上传成功')
  } else {
    ElMessage.error(response.msg || '上传失败')
  }
}

// 处理文件上传失败
const handleUploadError = (error) => {
  ElMessage.error('文件上传失败')
}

// 删除已上传文件
const removeFile = (tab, index) => {
  // 从文件列表中删除
  tab.fileList.splice(index, 1)

  // 更新显示列表
  tab.displayFileList = [...tab.fileList.map(item => ({
    name: item.name,
    url: item.url
  }))]

  ElMessage.success('文件删除成功')
}

// 话题相关方法
// 打开添加话题弹窗
const openTopicDialog = (tab) => {
  currentTab.value = tab
  topicDialogVisible.value = true
}

// 添加自定义话题
const addCustomTopic = () => {
  if (!customTopic.value.trim()) {
    ElMessage.warning('请输入话题内容')
    return
  }
  if (currentTab.value && !currentTab.value.selectedTopics.includes(customTopic.value.trim())) {
    currentTab.value.selectedTopics.push(customTopic.value.trim())
    customTopic.value = ''
    ElMessage.success('话题添加成功')
  } else {
    ElMessage.warning('话题已存在')
  }
}

// 切换推荐话题
const toggleRecommendedTopic = (topic) => {
  if (!currentTab.value) return

  const index = currentTab.value.selectedTopics.indexOf(topic)
  if (index > -1) {
    currentTab.value.selectedTopics.splice(index, 1)
  } else {
    currentTab.value.selectedTopics.push(topic)
  }
}

// 删除话题
const removeTopic = (tab, index) => {
  tab.selectedTopics.splice(index, 1)
}

// 确认添加话题
const confirmTopicSelection = () => {
  topicDialogVisible.value = false
  customTopic.value = ''
  currentTab.value = null
  ElMessage.success('添加话题完成')
}

// 账号选择相关方法
// 打开账号选择弹窗
const openAccountDialog = (tab) => {
  currentTab.value = tab
  tempSelectedAccounts.value = [...tab.selectedAccounts]
  accountDialogVisible.value = true
}

// 确认账号选择
const confirmAccountSelection = () => {
  if (currentTab.value) {
    currentTab.value.selectedAccounts = [...tempSelectedAccounts.value]
  }
  accountDialogVisible.value = false
  currentTab.value = null
  ElMessage.success('账号选择完成')
}

// 删除选中的账号
const removeAccount = (tab, index) => {
  tab.selectedAccounts.splice(index, 1)
}

// 获取账号显示名称
const getAccountDisplayName = (accountId) => {
  const account = accountStore.accounts.find(acc => acc.id === accountId)
  return account ? account.name : accountId
}

// 取消发布
const cancelPublish = (tab) => {
  ElMessage.info('已取消发布')
}

// 确认发布
const confirmPublish = async (tab) => {
  // 防止重复点击
  if (tab.publishing) {
    throw new Error('正在发布中，请稍候...')
  }

  tab.publishing = true // 设置发布状态为进行中

  // 数据验证
  if (tab.fileList.length === 0) {
    ElMessage.error('请先上传视频文件')
    tab.publishing = false
    throw new Error('请先上传视频文件')
  }
  if (!tab.title.trim()) {
    ElMessage.error('请输入标题')
    tab.publishing = false
    throw new Error('请输入标题')
  }
  if (!tab.selectedPlatform) {
    ElMessage.error('请选择发布平台')
    tab.publishing = false
    throw new Error('请选择发布平台')
  }
  if (tab.selectedAccounts.length === 0) {
    ElMessage.error('请选择发布账号')
    tab.publishing = false
    throw new Error('请选择发布账号')
  }

  // 构造发布数据，符合后端API格式
  const publishData = {
    type: tab.selectedPlatform,
    title: tab.title,
    tags: tab.selectedTopics, // 不带#号的话题列表
    fileList: tab.fileList.map(file => file.path), // 只发送文件路径
    accountList: tab.selectedAccounts.map(accountId => {
      const account = accountStore.accounts.find(acc => acc.id === accountId)
      return account ? account.filePath : accountId
    }), // 发送账号的文件路径
    enableTimer: tab.scheduleEnabled ? 1 : 0,
    videosPerDay: tab.scheduleEnabled ? tab.videosPerDay || 1 : 1,
    dailyTimes: tab.scheduleEnabled ? tab.dailyTimes || ['10:00'] : ['10:00'],
    startDays: tab.scheduleEnabled ? tab.startDays || 0 : 0,
    category: tab.isOriginal ? 1 : 0, // 1表示原创，0表示非原创
    productLink: tab.productLink.trim() || '',
    productTitle: tab.productTitle.trim() || '',
    isDraft: tab.isDraft
  }

  // 调用后端发布API（使用统一的http封装）
  try {
    const data = await http.post('/postVideo', publishData)
    tab.publishStatus = {
      message: '发布成功',
      type: 'success'
    }
    // 清空当前tab的数据
    tab.fileList = []
    tab.displayFileList = []
    tab.title = ''
    tab.selectedTopics = []
    tab.selectedAccounts = []
    tab.scheduleEnabled = false
  } catch (error) {
    console.error('发布错误:', error)
    tab.publishStatus = {
      message: `发布失败：${error.message || '请检查网络连接'}`,
      type: 'error'
    }
    throw error
  } finally {
    tab.publishing = false
  }
}

// 显示上传选项
const showUploadOptions = (tab) => {
  currentUploadTab.value = tab
  uploadOptionsVisible.value = true
}

// 选择本地上传
const selectLocalUpload = () => {
  uploadOptionsVisible.value = false
  localUploadVisible.value = true
}

// 直接打开素材库
const selectMaterialLibraryDirect = (tab) => {
  currentUploadTab.value = tab
  selectMaterialLibrary()
}

// 选择素材库
const selectMaterialLibrary = async () => {
  uploadOptionsVisible.value = false

  // 如果素材库为空，先获取素材数据
  if (materials.value.length === 0) {
    try {
      const response = await materialApi.getAllMaterials()
      if (response.code === 200) {
        appStore.setMaterials(response.data)
      } else {
        ElMessage.error('获取素材列表失败')
        return
      }
    } catch (error) {
      console.error('获取素材列表出错:', error)
      ElMessage.error('获取素材列表失败')
      return
    }
  }

  selectedMaterials.value = []
  materialLibraryVisible.value = true
}

// 确认素材选择
const confirmMaterialSelection = () => {
  if (selectedMaterials.value.length === 0) {
    ElMessage.warning('请选择至少一个素材')
    return
  }

  if (currentUploadTab.value) {
    // 将选中的素材添加到当前tab的文件列表
    selectedMaterials.value.forEach(materialId => {
      const material = materials.value.find(m => m.id === materialId)
      if (material) {
        const fileInfo = {
          name: material.filename,
          url: materialApi.getMaterialPreviewUrl(material.file_path.split('/').pop()),
          path: material.file_path,
          size: material.filesize * 1024 * 1024, // 转换为字节
          type: 'video/mp4'
        }

        // 检查是否已存在相同文件
        const exists = currentUploadTab.value.fileList.some(file => file.path === fileInfo.path)
        if (!exists) {
          currentUploadTab.value.fileList.push(fileInfo)
        }
      }
    })

    // 更新显示列表
    currentUploadTab.value.displayFileList = [...currentUploadTab.value.fileList.map(item => ({
      name: item.name,
      url: item.url
    }))]
  }

  const addedCount = selectedMaterials.value.length
  materialLibraryVisible.value = false
  selectedMaterials.value = []
  currentUploadTab.value = null
  ElMessage.success(`已添加 ${addedCount} 个素材`)
}

// 批量发布对话框状态
const batchPublishDialogVisible = ref(false)
const currentPublishingTab = ref(null)
const publishProgress = ref(0)
const publishResults = ref([])
const isCancelled = ref(false)

// 取消批量发布
const cancelBatchPublish = () => {
  isCancelled.value = true
  ElMessage.info('正在取消发布...')
}

// 批量发布方法
const batchPublish = async () => {
  if (batchPublishing.value) return

  batchPublishing.value = true
  currentPublishingTab.value = null
  publishProgress.value = 0
  publishResults.value = []
  isCancelled.value = false
  batchPublishDialogVisible.value = true

  try {
    for (let i = 0; i < tabs.length; i++) {
      if (isCancelled.value) {
        publishResults.value.push({
          label: tabs[i].label,
          status: 'cancelled',
          message: '已取消'
        })
        continue
      }

      const tab = tabs[i]
      currentPublishingTab.value = tab
      publishProgress.value = Math.floor((i / tabs.length) * 100)

      try {
        await confirmPublish(tab)
        publishResults.value.push({
          label: tab.label,
          status: 'success',
          message: '发布成功'
        })
      } catch (error) {
        publishResults.value.push({
          label: tab.label,
          status: 'error',
          message: error.message
        })
        // 不立即返回，继续显示发布结果
      }
    }

    publishProgress.value = 100

    // 统计发布结果
    const successCount = publishResults.value.filter(r => r.status === 'success').length
    const failCount = publishResults.value.filter(r => r.status === 'error').length
    const cancelCount = publishResults.value.filter(r => r.status === 'cancelled').length

    if (isCancelled.value) {
      ElMessage.warning(`发布已取消：${successCount}个成功，${failCount}个失败，${cancelCount}个未执行`)
    } else if (failCount > 0) {
      ElMessage.error(`发布完成：${successCount}个成功，${failCount}个失败`)
    } else {
      ElMessage.success('所有Tab发布成功')
      setTimeout(() => {
        batchPublishDialogVisible.value = false
      }, 1000)
    }

  } catch (error) {
    console.error('批量发布出错:', error)
    ElMessage.error('批量发布出错，请重试')
  } finally {
    batchPublishing.value = false
    isCancelled.value = false
  }
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.publish-center {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 20px;

  // ========== Tab Bar ==========
  .tab-bar {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px 20px;
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    flex-shrink: 0;

    .tab-list {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      flex: 1;
      min-width: 0;

      .tab-item {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 6px 14px;
        background: transparent;
        border: 1px solid $border;
        border-radius: $radius-base;
        cursor: pointer;
        transition: $transition-base;
        font-size: 14px;
        height: 34px;
        color: $text-secondary;
        user-select: none;

        &:hover {
          border-color: $border-active;
          color: $text-primary;
        }

        &.active {
          background: $gradient-brand;
          border-color: transparent;
          color: #fff;
          font-weight: 600;

          .tab-close {
            color: #fff;
            &:hover { background-color: rgba(255, 255, 255, 0.2); }
          }
        }

        .tab-label {
          line-height: 1;
        }

        .tab-close {
          padding: 2px;
          border-radius: 4px;
          cursor: pointer;
          transition: $transition-base;
          font-size: 12px;
          &:hover { background-color: rgba(255, 255, 255, 0.1); }
        }
      }
    }

    .tab-actions {
      display: flex;
      gap: 10px;
      flex-shrink: 0;

      .action-btn {
        display: flex;
        align-items: center;
        gap: 4px;
        height: 34px;
        font-size: 14px;
        white-space: nowrap;
      }

      .add-tab-btn {
        background: $gradient-brand;
        border-color: transparent;
        color: #fff;

        &:hover, &:focus {
          opacity: 0.9;
          color: #fff;
        }
      }

      .batch-publish-btn {
        background: $gradient-success;
        border-color: transparent;
        color: #fff;

        &:hover, &:focus {
          opacity: 0.9;
          color: #fff;
        }
      }
    }
  }

  // ========== Content Area ==========
  .publish-content {
    flex: 1;
    overflow-y: auto;
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: 24px;

    .tab-content {
      width: 100%;

      .publish-status {
        margin-bottom: 20px;
      }

      // ========== Two-Column Layout ==========
      .publish-layout {
        display: grid;
        grid-template-columns: 3fr 2fr;
        gap: 24px;
        align-items: start;
      }

      .column-left,
      .column-right {
        display: flex;
        flex-direction: column;
        gap: 0;
      }

      // ========== Form Section Base ==========
      .form-section {
        margin-bottom: 24px;
        padding-bottom: 24px;
        border-bottom: 1px solid $border;

        &:last-child {
          border-bottom: none;
          margin-bottom: 0;
          padding-bottom: 0;
        }
      }

      .section-title {
        font-size: 14px;
        font-weight: 600;
        color: $text-primary;
        margin: 0 0 12px 0;
        letter-spacing: -0.2px;
      }
    }
  }

  // ========== Upload Section ==========
  .upload-section {
    .upload-actions {
      display: flex;
      gap: 10px;

      .upload-btn {
        background: $gradient-brand;
        border-color: transparent;
        color: #fff;
        font-weight: 500;

        &:hover, &:focus {
          opacity: 0.9;
          color: #fff;
        }
      }

      .material-btn {
        border-color: $border-active;
        color: $text-primary;

        &:hover {
          border-color: $brand-start;
          color: $brand-start;
        }
      }
    }

    .uploaded-files {
      margin-top: 14px;

      .file-list {
        display: flex;
        flex-direction: column;
        gap: 8px;

        .file-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 10px 14px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid $border;
          border-radius: $radius-base;
          transition: $transition-base;

          &:hover {
            border-color: $border-active;
          }

          .file-info {
            display: flex;
            align-items: center;
            gap: 10px;
            min-width: 0;
            flex: 1;

            .file-name {
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
              max-width: 260px;
            }

            .file-size {
              color: $text-muted;
              font-size: 12px;
              flex-shrink: 0;
            }
          }

          .file-remove {
            flex-shrink: 0;
          }
        }
      }
    }
  }

  // ========== Title Section ==========
  .title-section {
    .title-input {
      :deep(.el-textarea__inner) {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid $border;
        border-radius: $radius-base;
        color: $text-primary;
        transition: $transition-base;

        &:focus {
          border-color: $border-active;
        }
      }
    }
  }

  // ========== Topic Section ==========
  .topic-section {
    .topic-display {
      display: flex;
      flex-direction: column;
      gap: 10px;

      .selected-topics {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }

      .topic-tag {
        background: $gradient-brand-subtle;
        border-color: $border-active;
        color: $text-primary;
      }

      .add-topic-btn {
        align-self: flex-start;
      }
    }
  }

  // ========== Platform Cards ==========
  .platform-section {
    .platform-cards {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
    }

    .platform-card {
      padding: 14px 12px;
      border-radius: $radius-card;
      border: 1px solid $border;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      transition: $transition-base;
      background: transparent;
      user-select: none;

      &:hover {
        border-color: $border-active;
      }

      &.active {
        border-color: $border-active;

        &.platform-douyin {
          background: $platform-douyin-bg;
          .platform-letter { background: $platform-douyin; }
        }
        &.platform-kuaishou {
          background: $platform-kuaishou-bg;
          .platform-letter { background: $platform-kuaishou; }
        }
        &.platform-channels {
          background: $platform-channels-bg;
          .platform-letter { background: $platform-channels; }
        }
        &.platform-xiaohongshu {
          background: $platform-xiaohongshu-bg;
          .platform-letter { background: $platform-xiaohongshu; }
        }
      }

      .platform-letter {
        width: 36px;
        height: 36px;
        border-radius: $radius-base;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #fff;
        font-weight: 700;
        font-size: 16px;
        background: $text-muted;
        transition: $transition-base;
      }

      .platform-name {
        font-size: 13px;
        color: $text-secondary;
        font-weight: 500;
        transition: $transition-base;
      }

      &.active .platform-name {
        color: $text-primary;
      }
    }
  }

  // ========== Account Section ==========
  .account-section {
    .account-display {
      display: flex;
      flex-direction: column;
      gap: 10px;

      .selected-accounts {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;

        .account-tag {
          background: $gradient-brand-subtle;
          border-color: $border-active;
          color: $text-primary;
        }
      }

      .select-account-btn {
        align-self: flex-start;
      }
    }
  }

  // ========== Toggle Rows (Original, Draft, Schedule) ==========
  .original-section,
  .draft-section {
    margin-bottom: 16px;
    padding-bottom: 16px;

    .toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;

      .toggle-label {
        font-size: 14px;
        color: $text-secondary;
        font-weight: 500;
      }
    }
  }

  // ========== Product Section ==========
  .product-section {
    .product-input {
      margin-bottom: 8px;

      &:last-child {
        margin-bottom: 0;
      }

      :deep(.el-input__wrapper) {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid $border;
        border-radius: $radius-base;
        box-shadow: none;
        transition: $transition-base;

        &:hover {
          border-color: $border-active;
        }
      }
    }
  }

  // ========== Schedule Section ==========
  .schedule-section {
    .toggle-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 4px;

      .toggle-label {
        font-size: 14px;
        color: $text-secondary;
        font-weight: 500;
      }
    }

    .schedule-settings {
      margin-top: 14px;
      padding: 14px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid $border;
      border-radius: $radius-base;

      .schedule-item {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 12px;

        &:last-child {
          margin-bottom: 0;
        }

        .label {
          min-width: 110px;
          color: $text-secondary;
          font-size: 13px;
        }

        .time-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
      }
    }
  }

  // ========== Action Buttons ==========
  .action-buttons {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 8px;
    padding-top: 20px;
    border-top: 1px solid $border;

    .publish-btn {
      background: $gradient-brand;
      border-color: transparent;
      color: #fff;
      font-weight: 600;
      padding: 8px 24px;

      &:hover, &:focus {
        opacity: 0.9;
        color: #fff;
      }
    }
  }

  // ========== Dialog Styles ==========
  .upload-options-content {
    display: flex;
    gap: 16px;
    justify-content: center;
    padding: 20px 0;

    .option-btn {
      width: 140px;
      height: 80px;
      font-size: 16px;
    }
  }

  .video-upload {
    width: 100%;
    :deep(.el-upload-dragger) {
      width: 100%;
      height: 180px;
    }
  }

  .publish-progress {
    padding: 20px;

    .current-publishing {
      margin: 15px 0;
      text-align: center;
      color: $text-secondary;
    }

    .publish-results {
      margin-top: 20px;
      border-top: 1px solid $border;
      padding-top: 15px;
      max-height: 300px;
      overflow-y: auto;

      .result-item {
        display: flex;
        align-items: center;
        padding: 8px 0;
        color: $text-secondary;

        .el-icon { margin-right: 8px; }
        .label { margin-right: 10px; font-weight: 500; color: $text-primary; }
        .message { color: $text-muted; }
        &.success { color: $success-color; .label { color: $success-color; } }
        &.error { color: $danger-color; .label { color: $danger-color; } }
        &.cancelled { color: $text-muted; }
      }
    }
  }

  .dialog-footer {
    text-align: right;
  }

  .topic-dialog {
    .topic-dialog-content {
      .custom-topic-input {
        display: flex;
        gap: 12px;
        margin-bottom: 24px;
        .custom-input { flex: 1; }
      }

      .recommended-topics {
        h4 {
          margin: 0 0 16px 0;
          font-size: 15px;
          font-weight: 600;
          color: $text-primary;
        }

        .topic-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
          gap: 10px;

          .topic-btn {
            height: 36px;
            font-size: 14px;
            border-radius: $radius-base;
            min-width: 100px;
            padding: 0 12px;
            white-space: nowrap;
            text-align: center;
            display: flex;
            align-items: center;
            justify-content: center;
          }
        }
      }
    }
  }

  .material-library-content {
    .material-list {
      display: flex;
      flex-direction: column;
      gap: 8px;

      .material-item {
        padding: 10px 14px;
        border: 1px solid $border;
        border-radius: $radius-base;
        transition: $transition-base;

        &:hover {
          border-color: $border-active;
        }

        .material-info {
          .material-name {
            font-size: 14px;
            color: $text-primary;
            font-weight: 500;
          }

          .material-details {
            display: flex;
            gap: 16px;
            margin-top: 4px;
            font-size: 12px;
            color: $text-muted;
          }
        }
      }
    }
  }

  .account-dialog-content {
    .account-list {
      display: flex;
      flex-direction: column;
      gap: 8px;

      .account-item {
        padding: 10px 14px;
        border: 1px solid $border;
        border-radius: $radius-base;
        transition: $transition-base;

        &:hover {
          border-color: $border-active;
        }

        .account-info {
          .account-name {
            font-size: 14px;
            color: $text-primary;
          }
        }
      }
    }
  }
}
</style>
