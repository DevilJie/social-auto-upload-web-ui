<template>
  <div class="publish-center">
    <!-- ========== LEFT SIDEBAR ========== -->
    <AccountSidebar
      :account-groups="accountGroups"
      :total-count="totalCount"
      :selected-platform="selectedPlatform"
      :selected-account-id="selectedAccountId"
      :expanded-groups="expandedGroups"
      :publish-account-ids="publishAccountIds"
      :has-account-override="hasAccountOverride"
      @toggle-group="toggleGroup"
      @select-account="selectAccount"
      @remove-account="removePublishAccount"
      @open-account-dialog="accountDialogVisible = true"
    />

    <!-- ========== RIGHT MAIN AREA ========== -->
    <main class="publish-main">
      <div class="main-body">
      <!-- Left: form + content -->
      <div class="main-form-col">
      <!-- Top bar -->
      <div class="main-header">
        <div class="header-left">
          <span class="page-title">发布视频</span>
          <span
            v-if="currentPlatformConfig"
            class="platform-tag"
            :style="{ background: currentPlatformConfig.bgColor, color: currentPlatformConfig.color }"
          >
            {{ currentPlatformConfig.name }} · 个性化设置
          </span>
        </div>
        <div class="header-right">
          <button class="draft-btn" @click="saveDraft">
            <el-icon><Document /></el-icon>
            {{ currentDraftId ? '更新草稿' : '保存草稿' }}
          </button>
          <button class="publish-btn" @click="publishAll" :disabled="publishing">
            {{ publishing ? '发布中...' : '一键发布' }}
          </button>
        </div>
      </div>

      <!-- Scrollable content -->
      <div class="main-content">
        <!-- ===== PUBLIC CONFIG ===== -->
        <div class="config-section">
          <div class="section-bar">
            <div class="bar purple"></div>
            <span class="section-label">公共配置</span>
            <span class="hint">所有账号共享</span>
          </div>

          <!-- Cover Section -->
          <div class="media-section cover-section">
            <div class="section-label">封面</div>
            <div class="cover-grid">
              <CoverCard
                label="竖版封面"
                :ratio-label="appStore.portraitRatio"
                v-model="commonConfig.coverPortrait"
                :has-video="!!(commonConfig.videoPortrait || commonConfig.videoLandscape)"
                @edit="openCoverEditor('portrait')"
                @open-library="selectFromLibrary('cover', 'portrait')"
              />
              <CoverCard
                label="横版封面"
                :ratio-label="appStore.landscapeRatio"
                v-model="commonConfig.coverLandscape"
                :has-video="!!(commonConfig.videoPortrait || commonConfig.videoLandscape)"
                @edit="openCoverEditor('landscape')"
                @open-library="selectFromLibrary('cover', 'landscape')"
              />
            </div>
          </div>

          <CoverEditorDialog
            ref="coverEditorRef"
            :video-landscape="commonConfig.videoLandscape"
            :video-portrait="commonConfig.videoPortrait"
            :cover-landscape="commonConfig.coverLandscape"
            :cover-portrait="commonConfig.coverPortrait"
            :portrait-ratio="appStore.portraitRatio"
            :landscape-ratio="appStore.landscapeRatio"
            @update:cover-landscape="commonConfig.coverLandscape = $event"
            @update:cover-portrait="commonConfig.coverPortrait = $event"
          />

          <!-- Batch title/description sync -->
          <div class="batch-sync-section">
            <div class="batch-sync-header" @click="batchSyncExpanded = !batchSyncExpanded">
              <span>批量设置标题和描述</span>
              <el-icon class="cursor-pointer">
                <component :is="batchSyncExpanded ? ArrowDown : ArrowRight" />
              </el-icon>
            </div>
            <div v-show="batchSyncExpanded" class="batch-sync-body">
              <div class="form-field">
                <div class="field-head">
                  <span>公共标题</span>
                </div>
                <el-input
                  v-model="batchTitle"
                  placeholder="输入标题后点击同步..."
                  maxlength="100"
                />
              </div>
              <div class="form-field">
                <div class="field-head">
                  <span>公共描述</span>
                </div>
                <el-input
                  v-model="batchDescription"
                  type="textarea"
                  :rows="5"
                  placeholder="输入描述后点击同步..."
                  maxlength="2000"
                />
              </div>
              <button class="cover-action-btn primary" @click="syncBatchToAll">
                <el-icon :size="15"><Promotion /></el-icon><span>同步到所有平台</span>
              </button>
            </div>
          </div>

          <!-- Quick tag buttons -->
          <div class="quick-tags">
            <button class="cover-action-btn" @click="topicDialogVisible = true">
              <span># 添加话题</span>
            </button>
            <button class="cover-action-btn">
              <span>$ 参加活动</span>
            </button>
            <button class="cover-action-btn">
              <span>@ 添加好友</span>
            </button>
          </div>
          <div v-if="commonConfig.topics.length" class="topics-row">
            <el-tag
              v-for="(t, i) in commonConfig.topics"
              :key="i"
              closable
              @close="commonConfig.topics.splice(i, 1)"
              size="small"
              class="cursor-pointer"
            >#{{ t }}</el-tag>
          </div>
        </div>

        <!-- Divider -->
        <div class="divider"></div>

        <!-- ===== PLATFORM-SPECIFIC SETTINGS ===== -->
        <div v-if="currentPlatformConfig" class="config-section">
          <div class="section-bar">
            <div class="bar" :style="{ background: currentPlatformConfig.color }"></div>
            <span class="section-label">
              {{ currentPlatformConfig.name }}
              {{ selectedAccountId ? '· ' + getAccountName(selectedAccountId) : '· 默认设置' }}
            </span>
            <span class="hint">{{ selectedAccountId ? '仅对该账号生效' : '对该分组所有未自定义的账号生效' }}</span>
          </div>

          <div v-if="selectedAccountId && hasAccountOverride(selectedAccountId)" style="margin-bottom: 12px;">
            <el-button size="small" @click="resetAccountOverride(selectedAccountId)">恢复为渠道默认</el-button>
          </div>

          <div v-if="selectedPlatform === 'xiaohongshu'" class="xhs-warning">
            <el-icon><WarningFilled /></el-icon>
            <span>由于小红书反检测机制比较恶心，如果出现被警告的情况！请立即停止使用小红书渠道！</span>
          </div>

          <div class="platform-title-desc">
            <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
              <div class="setting-label" :style="{ color: currentPlatformConfig.color }">标题</div>
              <el-input
                v-model="form.title"
                placeholder="请输入标题..."
                maxlength="100"
                show-word-limit
              />
            </div>
            <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
              <div class="setting-label" :style="{ color: currentPlatformConfig.color }">描述</div>
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="5"
                placeholder="请输入描述..."
                maxlength="2000"
                show-word-limit
              />
            </div>
          </div>

          <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a', marginBottom: '12px' }">
            <div class="setting-label" :style="{ color: currentPlatformConfig.color }">视频格式</div>
            <div class="radio-row">
              <label
                v-for="opt in videoFormatOptions"
                :key="opt.value"
                :class="['radio-item', 'cursor-pointer', { disabled: opt.disabled }]"
              >
                <input
                  type="radio"
                  :name="(selectedAccountId || selectedPlatform) + '-videoFormat'"
                  :value="opt.value"
                  v-model="form.videoFormat"
                  :disabled="opt.disabled"
                  class="cursor-pointer"
                />
                <span
                  :class="['radio-text', { on: form.videoFormat === opt.value, muted: opt.disabled }]"
                  :style="form.videoFormat === opt.value ? { borderColor: currentPlatformConfig.color, color: currentPlatformConfig.color } : {}"
                >{{ opt.label }}</span>
              </label>
            </div>
            <div v-if="!commonConfig.videoLandscape && !commonConfig.videoPortrait" class="setting-desc" style="font-size: 12px;">
              请先上传视频
            </div>
          </div>

          <div class="settings-grid">
            <template v-for="field in currentPlatformConfig.settingsFields" :key="field.key">
              <template v-if="field.key !== 'title' && field.key !== 'description' && field.key !== 'videoFormat'">
                <div
                  class="setting-card"
                  :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }"
                >
                  <div class="setting-label" :style="{ color: currentPlatformConfig.color }">{{ field.label }}</div>
                  <div v-if="field.description" class="setting-desc">{{ field.description }}</div>

                  <el-input
                    v-if="field.type === 'input'"
                    v-model="form[field.key]"
                    :placeholder="field.placeholder"
                    size="small"
                  />
                  <el-switch
                    v-else-if="field.type === 'switch'"
                    v-model="form[field.key]"
                  />
                  <div v-else-if="field.type === 'radio'" class="radio-row">
                    <label
                      v-for="opt in field.options"
                      :key="String(opt.value)"
                      class="radio-item cursor-pointer"
                    >
                      <input
                        type="radio"
                        :name="(selectedAccountId || selectedPlatform) + '-' + field.key"
                        :value="opt.value"
                        v-model="form[field.key]"
                        class="cursor-pointer"
                      />
                      <span
                        :class="['radio-text', { on: form[field.key] === opt.value }]"
                        :style="form[field.key] === opt.value ? { borderColor: currentPlatformConfig.color, color: currentPlatformConfig.color } : {}"
                      >{{ opt.label }}</span>
                    </label>
                  </div>
                  <el-select
                    v-else-if="field.type === 'select'"
                    v-model="form[field.key]"
                    :placeholder="field.placeholder"
                    size="small"
                    clearable
                    class="cursor-pointer"
                  >
                    <el-option
                      v-for="opt in (field.options || [])"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                    <el-option v-if="!field.options || field.options.length === 0" label="暂无可选项" :value="''" disabled />
                  </el-select>
                  <el-select
                    v-else-if="field.type === 'multiSelect'"
                    v-model="form[field.key]"
                    :placeholder="field.placeholder"
                    size="small"
                    multiple
                    collapse-tags
                    collapse-tags-tooltip
                    clearable
                    class="cursor-pointer"
                  >
                    <el-option
                      v-for="opt in (field.options || [])"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                    <el-option v-if="!field.options || field.options.length === 0" label="暂无可选项" :value="''" disabled />
                  </el-select>
                  <el-date-picker
                    v-else-if="field.type === 'datetime'"
                    v-model="form[field.key]"
                    type="datetime"
                    :placeholder="field.placeholder"
                    value-format="YYYY-MM-DD HH:mm:ss"
                    size="small"
                    class="cursor-pointer"
                  />
                </div>
              </template>
            </template>
          </div>
        </div>

        <!-- No platform selected hint -->
        <div v-else class="no-platform-hint">
          <div class="hint-icon">
            <el-icon :size="48"><VideoCameraFilled /></el-icon>
          </div>
          <p>请在左侧选择一个平台分组</p>
          <p class="hint-sub">选择后可配置该平台的个性化发布设置</p>
        </div>
      </div>
      </div><!-- /main-form-col -->

      <!-- Right: Phone preview panel -->
      <div class="phone-panel">
        <div class="phone-panel-header">
          <span class="phone-panel-title">视频预览</span>
        </div>
        <div class="phone-mode-tabs">
          <button :class="['mode-tab', { active: videoModeTab === 'portrait' }]" @click="videoModeTab = 'portrait'">
            <span class="mode-icon-portrait"></span> 竖版 {{ appStore.portraitRatio }}
          </button>
          <button :class="['mode-tab', { active: videoModeTab === 'landscape' }]" @click="videoModeTab = 'landscape'">
            <span class="mode-icon-landscape"></span> 横版 {{ appStore.landscapeRatio }}
          </button>
        </div>
        <div class="phone-preview-area">
          <div :class="['phone-mockup', videoModeTab]">
            <div class="phone-notch"></div>
            <div class="phone-screen">
              <template v-if="currentVideoData">
                <video
                  :src="currentVideoData.url"
                  controls
                  preload="metadata"
                  class="phone-video-player"
                ></video>
              </template>
              <template v-else>
                <div class="phone-empty" @click="triggerUploadVideo(videoModeTab)">
                  <el-icon :size="28"><Upload /></el-icon>
                  <span>上传{{ videoModeTab === 'portrait' ? '竖版' : '横版' }}视频</span>
                </div>
              </template>
            </div>
            <div class="phone-home-bar"></div>
          </div>
        </div>
        <div class="phone-panel-actions">
          <button class="cover-action-btn primary" @click="triggerUploadVideo(videoModeTab)">
            <el-icon :size="14"><Upload /></el-icon><span>本地上传</span>
          </button>
          <button class="cover-action-btn" @click="selectFromLibrary('video', videoModeTab)">
            <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
          </button>
        </div>
        <div v-if="currentVideoData" class="phone-panel-info">
          <span class="phone-info-name">{{ currentVideoData.name }}</span>
          <button class="phone-info-remove" @click="clearVideo(videoModeTab)">
            <el-icon :size="12"><Delete /></el-icon>
          </button>
        </div>
      </div>

      </div><!-- /main-body -->
    </main>

    <!-- ========== DIALOGS ========== -->

    <!-- Account Selection Dialog -->
    <AccountSelectDialog
      v-model="accountDialogVisible"
      :platforms="platformList"
      :publish-account-ids="publishAccountIds"
      @confirm="onAccountConfirm"
    />

    <!-- Topic Selection Dialog -->
    <el-dialog
      v-model="topicDialogVisible"
      title="添加话题"
      width="560px"
      class="topic-dialog"
    >
      <div class="topic-dialog-content">
        <div class="custom-topic-input">
          <el-input v-model="customTopic" placeholder="输入自定义话题" class="custom-input">
            <template #prepend>#</template>
          </el-input>
          <el-button type="primary" @click="addCustomTopic" class="cursor-pointer">添加</el-button>
        </div>

        <div class="recommended-topics">
          <h4>推荐话题</h4>
          <div class="topic-grid">
            <el-button
              v-for="topic in recommendedTopics"
              :key="topic"
              :type="commonConfig.topics.includes(topic) ? 'primary' : 'default'"
              @click="toggleRecommendedTopic(topic)"
              class="topic-btn cursor-pointer"
            >{{ topic }}</el-button>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer-right">
          <el-button @click="topicDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="topicDialogVisible = false">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Video Upload Dialog -->
    <el-dialog
      v-model="videoUploadDialogVisible"
      :title="'上传' + (videoUploadTarget === 'portrait' ? '竖版' : '横版') + '视频'"
      width="600px"
      class="video-upload-dialog"
    >
      <el-upload
        class="video-upload"
        drag
        :auto-upload="true"
        :http-request="handleVideoUpload"
        accept="video/*"
      >
        <el-icon class="el-icon--upload" :size="48"><Upload /></el-icon>
        <div class="el-upload__text">
          将视频文件拖到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">支持MP4、AVI等视频格式</div>
        </template>
      </el-upload>

      <template #footer>
        <div class="dialog-footer-right">
          <el-button @click="videoUploadDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Material Library Dialog -->
    <MaterialSelectDialog
      ref="materialSelectRef"
      :filter-type="materialLibraryMode === 'cover' ? 'image' : 'video'"
      @select="onMaterialSelect"
    />

    <!-- Batch Publish Progress Dialog -->
    <BatchPublishDialog
      v-model="batchPublishDialogVisible"
      :progress="publishProgress"
      :results="publishResults"
      :current-account="currentPublishingAccount"
      @cancel="cancelBatch"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch, onMounted } from 'vue'
import { Upload, ArrowDown, ArrowRight, Picture, VideoCameraFilled, Check, Close, InfoFilled, Promotion, StarFilled, Delete, Document, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
import { http } from '@/utils/request'
import { platformList, getPlatformByKey, platformKeyToId } from '@/config/platforms'

import AccountSidebar from '@/components/AccountSidebar.vue'
import AccountSelectDialog from '@/components/AccountSelectDialog.vue'
import BatchPublishDialog from '@/components/BatchPublishDialog.vue'
import CoverCard from '@/components/CoverCard.vue'
import CoverEditorDialog from '@/components/CoverEditorDialog.vue'
import MaterialSelectDialog from '@/components/MaterialSelectDialog.vue'
import { useAutoSave } from '@/composables/useAutoSave'
import { frameApi } from '@/api/frame'
import { draftApi } from '@/api/draft'
import { useRoute } from 'vue-router'

// ========== Stores & Config ==========
const accountStore = useAccountStore()
const appStore = useAppStore()
appStore.loadAutoFillTitle()
appStore.loadAutoSaveSettings()
appStore.loadCoverRatioSettings()
const route = useRoute()

// ========== Left Sidebar State ==========
const expandedGroups = ref(new Set())
const selectedPlatform = ref(null)
const selectedAccountId = ref(null)

const accountGroups = computed(() => {
  return platformList.map(p => ({
    key: p.key,
    id: p.id,
    name: p.name,
    letter: p.letter,
    color: p.color,
    bgColor: p.bgColor,
    cssClass: p.cssClass,
    logo: p.logo,
    accounts: accountStore.accounts.filter(a => a.platform === p.name),
    settingsFields: p.settingsFields || [],
    defaultSettings: p.defaultSettings || {},
  }))
})

const totalCount = computed(() => accountStore.accounts.length)

const currentVideoData = computed(() =>
  videoModeTab.value === 'portrait' ? commonConfig.videoPortrait : commonConfig.videoLandscape
)

const currentPlatformConfig = computed(() =>
  selectedPlatform.value ? getPlatformByKey(selectedPlatform.value) : null
)

// ========== Public Config ==========
const commonConfig = reactive({
  videoLandscape: null,
  videoPortrait: null,
  coverLandscape: null,
  coverPortrait: null,
  topics: [],
})

// Cover editor
const coverEditorRef = ref(null)
const landscapeFrames = ref([])
const portraitFrames = ref([])
const videoModeTab = ref('portrait')

const portraitCoverFrames = computed(() =>
  portraitFrames.value.length > 0 ? portraitFrames.value : landscapeFrames.value
)
const landscapeCoverFrames = computed(() =>
  landscapeFrames.value.length > 0 ? landscapeFrames.value : portraitFrames.value
)

// ========== Per-platform Config ==========
const platformConfigs = reactive({
  douyin: { title: '', description: '', productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true, videoFormat: '' },
  xiaohongshu: { title: '', description: '', collection: '', groupChat: '', location: '', aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  kuaishou: { title: '', description: '', productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  bilibili: { title: '', description: '', zone: '', tags: '', topic: '', creationDeclaration: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  channels: { title: '', description: '', isDraft: false, location: '', aiContent: false, isOriginal: false, videoFormat: '' },
  baijiahao: { title: '', description: '', aiContent: false, isOriginal: false, videoFormat: '' },
  tiktok: { title: '', description: '', aiContent: false, isOriginal: false, scheduleTime: '', videoFormat: '' },
  youtube: { title: '', description: '', audience: 'not_kids', alteredContent: false, scheduleTime: '', videoFormat: '' },
  iqiyi: { title: '', description: '', creationDeclaration: '', riskWarning: '', enableCashActivity: false, scheduleTime: '', videoFormat: '' },
  tencent_video: { title: '', description: '', creationDeclaration: [], scheduleTime: '', videoFormat: '' },
})

const accountOverrides = reactive({})

const currentSettings = computed(() =>
  selectedPlatform.value ? platformConfigs[selectedPlatform.value] || {} : {}
)

// ========== Video Format Helpers ==========
const videoFormatOptions = computed(() => {
  const hasLandscape = !!commonConfig.videoLandscape
  const hasPortrait = !!commonConfig.videoPortrait
  return [
    { label: '横版', value: 'landscape', disabled: !hasLandscape && hasPortrait },
    { label: '竖版', value: 'portrait', disabled: !hasPortrait && hasLandscape },
  ]
})

const effectiveVideoFormat = computed(() => {
  if (commonConfig.videoLandscape && !commonConfig.videoPortrait) return 'landscape'
  if (commonConfig.videoPortrait && !commonConfig.videoLandscape) return 'portrait'
  return ''
})

// ========== Account-level Settings Merging ==========
function getAccountSettings(accountId, platformKey) {
  const platform = platformConfigs[platformKey] || {}
  const override = accountOverrides[accountId] || {}
  const merged = { ...platform }
  for (const key of Object.keys(merged)) {
    if (override[key] !== undefined && override[key] !== '') {
      merged[key] = override[key]
    }
  }
  return merged
}

function hasAccountOverride(accountId) {
  const override = accountOverrides[accountId]
  if (!override) return false
  return Object.values(override).some(v => v !== undefined && v !== '' && v !== false)
}

const form = reactive({})

function getMergedSettings() {
  const platformKey = selectedPlatform.value
  if (!platformKey) return {}
  const platform = platformConfigs[platformKey] || {}
  if (selectedAccountId.value) {
    const override = accountOverrides[selectedAccountId.value]
    if (override && Object.keys(override).length > 0) {
      return {
        ...platform,
        ...Object.fromEntries(
          Object.entries(override).filter(([_, v]) => v !== undefined && v !== '' && v !== false)
        ),
      }
    }
  }
  return { ...platform }
}

watch([selectedPlatform, selectedAccountId], () => {
  const merged = getMergedSettings()
  for (const key of Object.keys(merged)) {
    form[key] = merged[key]
  }
  for (const key of Object.keys(form)) {
    if (!(key in merged)) {
      delete form[key]
    }
  }
  const platformKey = selectedPlatform.value
  if (platformKey) {
    const platform = platformConfigs[platformKey] || {}
    const fields = platform.settingsFields || []
    for (const field of fields) {
      if (field.type === 'multiSelect' && !Array.isArray(form[field.key])) {
        form[field.key] = []
      }
    }
  }
}, { immediate: true })

watch(form, (newVal) => {
  const platformKey = selectedPlatform.value
  if (!platformKey) return
  if (!platformConfigs[platformKey]) {
    platformConfigs[platformKey] = {}
  }
  const platform = platformConfigs[platformKey]

  if (selectedAccountId.value) {
    const diff = {}
    for (const key of Object.keys(newVal)) {
      if (newVal[key] !== platform[key]) {
        diff[key] = newVal[key]
      }
    }
    if (Object.keys(diff).length > 0) {
      accountOverrides[selectedAccountId.value] = { ...diff }
    } else {
      delete accountOverrides[selectedAccountId.value]
    }
  } else {
    for (const key of Object.keys(newVal)) {
      platform[key] = newVal[key]
    }
  }
}, { deep: true })

function getAccountName(accountId) {
  const account = accountStore.accounts.find(a => a.id === accountId)
  return account ? account.name : '未知'
}

function resetAccountOverride(accountId) {
  delete accountOverrides[accountId]
  ElMessage.success('已恢复为渠道默认设置')
}

// ========== Auto-save ==========
const currentDraftId = ref(null)
const { hasChanges, startAutoSaveTimer } = useAutoSave(() => saveDraft())

// ========== Batch sync ==========
const batchTitle = ref('')
const batchDescription = ref('')

function syncBatchToAll() {
  for (const key of Object.keys(platformConfigs)) {
    if (batchTitle.value) platformConfigs[key].title = batchTitle.value
    if (batchDescription.value) platformConfigs[key].description = batchDescription.value
  }
  ElMessage.success('已同步到所有平台')
}

const batchSyncExpanded = ref(false)

// ========== Init ==========
const firstGroup = accountGroups.value.find(g => g.accounts.length > 0)
if (firstGroup) {
  expandedGroups.value.add(firstGroup.key)
  selectedPlatform.value = firstGroup.key
}

// ========== Dialog State ==========
const accountDialogVisible = ref(false)
const topicDialogVisible = ref(false)
const videoUploadDialogVisible = ref(false)
const videoUploadTarget = ref('landscape')
const materialSelectRef = ref(null)
const materialLibraryMode = ref('video')
const materialLibraryCoverTarget = ref('landscape')
const materialLibraryVideoTarget = ref('landscape')
const batchPublishDialogVisible = ref(false)

// Batch publish state
const publishing = ref(false)
const publishProgress = ref(0)
const publishResults = ref([])
const currentPublishingAccount = ref('')
const isCancelled = ref(false)

// Selected accounts
const publishAccountIds = reactive(new Set())

// Topic dialog
const customTopic = ref('')
const recommendedTopics = [
  '游戏', '电影', '音乐', '美食', '旅行', '文化',
  '科技', '生活', '娱乐', '体育', '教育', '艺术',
  '健康', '时尚', '美妆', '摄影', '宠物', '汽车',
]

// ========== Sidebar Methods ==========

function toggleGroup(key) {
  if (expandedGroups.value.has(key)) {
    expandedGroups.value.delete(key)
  } else {
    expandedGroups.value.add(key)
  }
  selectedPlatform.value = key
  selectedAccountId.value = null
}

function removePublishAccount(id) {
  publishAccountIds.delete(id)
  hasChanges.value = true
}

function selectAccount(account, group) {
  selectedAccountId.value = account.id
  selectedPlatform.value = group.key
  expandedGroups.value.add(group.key)
}

// ========== Account Dialog ==========

function onAccountConfirm(ids) {
  ids.forEach(id => {
    publishAccountIds.add(id)
  })
  hasChanges.value = true
  ElMessage.success(`已选择 ${ids.length} 个账号`)
}

// ========== Upload Methods ==========

function triggerUploadVideo(target = 'landscape') {
  videoUploadTarget.value = target
  videoUploadDialogVisible.value = true
}

function clearVideo(type) {
  if (type === 'landscape') commonConfig.videoLandscape = null
  else commonConfig.videoPortrait = null
}

// ========== Cover Editor ==========

function openCoverEditor(tab = 'landscape') {
  coverEditorRef.value?.open(tab)
}

function triggerFrameExtraction(videoData, type) {
  if (!videoData?.id) return
  const doExtract = async () => {
    try {
      const resp = await frameApi.extractFrames(videoData.id)
      if (resp.data) {
        const allFrames = resp.data.frames || []
        const recommended = pickRecommendedFrames(allFrames, 6)
        if (type === 'landscape') landscapeFrames.value = recommended
        else portraitFrames.value = recommended
      }
    } catch (e) {
      console.error('Frame extraction failed:', e)
    }
  }
  doExtract()
}

function pickRecommendedFrames(frames, count) {
  if (frames.length <= count) return frames
  const result = [frames[0]]
  for (let i = 1; i < count - 1; i++) {
    const idx = Math.round((frames.length - 1) * i / (count - 1))
    result.push(frames[idx])
  }
  result.push(frames[frames.length - 1])
  return result
}

async function handleVideoUpload(options) {
  const file = options.file
  const formData = new FormData()
  formData.append('file', file)
  try {
    const resp = await materialsApi.upload(formData)
    if (resp.code === 200) {
      const d = resp.data
      const videoData = {
        id: d.id,
        name: d.original_filename,
        url: getFileUrl(d.stored_path),
        stored_path: d.stored_path,
        size: d.file_size,
        type: d.mime_type,
      }
      if (videoUploadTarget.value === 'portrait') {
        commonConfig.videoPortrait = videoData
      } else {
        commonConfig.videoLandscape = videoData
      }
      videoUploadDialogVisible.value = false
      ElMessage.success('视频上传成功')
      if (appStore.autoFillTitle) {
        const title = file.name.replace(/\.[^.]+$/, '')
        for (const key of Object.keys(platformConfigs)) {
          platformConfigs[key].title = title
        }
        for (const group of accountGroups.value) {
          for (const account of group.accounts) {
            if (accountOverrides[account.id]?.title) {
              accountOverrides[account.id].title = title
            }
          }
        }
        if (selectedPlatform.value) {
          const accountId = selectedAccountId.value
          if (accountId && accountOverrides[accountId]?.title) {
            form.title = accountOverrides[accountId].title
          } else if (platformConfigs[selectedPlatform.value]) {
            form.title = platformConfigs[selectedPlatform.value].title
          }
        }
      }
      triggerFrameExtraction(videoData, videoUploadTarget.value)
    } else {
      options.onError(new Error(resp.msg || '上传失败'))
    }
  } catch (error) {
    options.onError(error)
  }
}

// ========== Material Library ==========

async function selectFromLibrary(mode = 'video', videoOrCoverTarget = 'landscape') {
  materialLibraryMode.value = mode
  if (mode === 'video') {
    materialLibraryVideoTarget.value = videoOrCoverTarget
  } else {
    materialLibraryCoverTarget.value = videoOrCoverTarget
  }
  materialsApi.list({ page_size: 200 }).then((response) => {
    if (response.code === 200) {
      appStore.setMaterials(response.data.items || [])
    }
  }).catch((err) => console.error('预拉素材列表出错:', err))
  materialSelectRef.value?.open()
}

function onMaterialSelect(material) {
  if (materialLibraryMode.value === 'cover') {
    if (materialLibraryCoverTarget.value === 'portrait') {
      commonConfig.coverPortrait = material
    } else {
      commonConfig.coverLandscape = material
    }
    ElMessage.success('封面已设置')
  } else {
    if (materialLibraryVideoTarget.value === 'portrait') {
      commonConfig.videoPortrait = material
    } else {
      commonConfig.videoLandscape = material
    }
    ElMessage.success('视频已设置')
    if (appStore.autoFillTitle) {
      const title = material.name.replace(/\.[^.]+$/, '')
      for (const key of Object.keys(platformConfigs)) {
        platformConfigs[key].title = title
      }
      for (const group of accountGroups.value) {
        for (const account of group.accounts) {
          if (accountOverrides[account.id]?.title) {
            accountOverrides[account.id].title = title
          }
        }
      }
      if (selectedPlatform.value && platformConfigs[selectedPlatform.value]) {
        form.title = platformConfigs[selectedPlatform.value].title
      }
    }
    triggerFrameExtraction(material, materialLibraryVideoTarget.value)
  }
}

// ========== Topic Methods ==========

function addCustomTopic() {
  const topic = customTopic.value.trim()
  if (!topic) {
    ElMessage.warning('请输入话题内容')
    return
  }
  if (commonConfig.topics.includes(topic)) {
    ElMessage.warning('话题已存在')
    return
  }
  commonConfig.topics.push(topic)
  customTopic.value = ''
  ElMessage.success('话题添加成功')
}

function toggleRecommendedTopic(topic) {
  const idx = commonConfig.topics.indexOf(topic)
  if (idx > -1) {
    commonConfig.topics.splice(idx, 1)
  } else {
    commonConfig.topics.push(topic)
  }
}

// Auto-select video format
watch(effectiveVideoFormat, (format) => {
  if (format && selectedPlatform.value && !currentSettings.value?.videoFormat) {
    const platformKey = selectedPlatform.value
    if (platformConfigs[platformKey]) {
      platformConfigs[platformKey].videoFormat = format
    }
  }
})

// Watch content changes
watch(commonConfig, () => { hasChanges.value = true }, { deep: true })
watch(platformConfigs, () => { hasChanges.value = true }, { deep: true })
watch(accountOverrides, () => { hasChanges.value = true }, { deep: true })

// ========== Publish Methods ==========

async function saveDraft() {
  try {
    const draftData = {
      commonConfig: {
        topics: [...commonConfig.topics],
        videoLandscape: commonConfig.videoLandscape
          ? { id: commonConfig.videoLandscape.id, name: commonConfig.videoLandscape.name, stored_path: commonConfig.videoLandscape.stored_path, url: commonConfig.videoLandscape.url, size: commonConfig.videoLandscape.size, type: commonConfig.videoLandscape.type }
          : null,
        videoPortrait: commonConfig.videoPortrait
          ? { id: commonConfig.videoPortrait.id, name: commonConfig.videoPortrait.name, stored_path: commonConfig.videoPortrait.stored_path, url: commonConfig.videoPortrait.url, size: commonConfig.videoPortrait.size, type: commonConfig.videoPortrait.type }
          : null,
        coverLandscape: commonConfig.coverLandscape
          ? { name: commonConfig.coverLandscape.name, stored_path: commonConfig.coverLandscape.stored_path, url: commonConfig.coverLandscape.url, size: commonConfig.coverLandscape.size, type: commonConfig.coverLandscape.type, _fromFrame: commonConfig.coverLandscape._fromFrame }
          : null,
        coverPortrait: commonConfig.coverPortrait
          ? { name: commonConfig.coverPortrait.name, stored_path: commonConfig.coverPortrait.stored_path, url: commonConfig.coverPortrait.url, size: commonConfig.coverPortrait.size, type: commonConfig.coverPortrait.type, _fromFrame: commonConfig.coverPortrait._fromFrame }
          : null,
      },
      platformConfigs: JSON.parse(JSON.stringify(platformConfigs)),
      accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
      publishAccountIds: [...publishAccountIds],
      selectedPlatform: selectedPlatform.value,
      selectedAccountId: selectedAccountId.value,
      expandedGroups: [...expandedGroups.value],
      videoModeTab: videoModeTab.value,
    }

    if (currentDraftId.value) {
      await draftApi.updateDraft(currentDraftId.value, { draft_data: draftData })
      ElMessage.success('草稿已更新')
    } else {
      const resp = await draftApi.createDraft({ draft_data: draftData })
      currentDraftId.value = resp.data.id
      ElMessage.success('草稿已保存')
    }
  } catch (e) {
    ElMessage.error('草稿保存失败')
  }
}

async function restoreDraft(draftId) {
  try {
    const resp = await draftApi.getDraft(draftId)
    const data = resp.data
    const dd = data.draft_data
    if (!dd) {
      ElMessage.error('草稿数据为空')
      return
    }

    if (dd.commonConfig) {
      if (dd.commonConfig.topics) commonConfig.topics = dd.commonConfig.topics
      if (dd.commonConfig.videoLandscape) {
        const v = dd.commonConfig.videoLandscape
        if (v.stored_path) v.url = getFileUrl(v.stored_path)
        commonConfig.videoLandscape = v
      }
      if (dd.commonConfig.videoPortrait) {
        const v = dd.commonConfig.videoPortrait
        if (v.stored_path) v.url = getFileUrl(v.stored_path)
        commonConfig.videoPortrait = v
      }
      if (dd.commonConfig.coverLandscape) {
        const v = dd.commonConfig.coverLandscape
        if (v.stored_path) v.url = getFileUrl(v.stored_path)
        commonConfig.coverLandscape = v
      }
      if (dd.commonConfig.coverPortrait) {
        const v = dd.commonConfig.coverPortrait
        if (v.stored_path) v.url = getFileUrl(v.stored_path)
        commonConfig.coverPortrait = v
      }
    }

    if (dd.platformConfigs) {
      for (const [key, val] of Object.entries(dd.platformConfigs)) {
        if (platformConfigs[key]) {
          Object.assign(platformConfigs[key], val)
        }
      }
    }

    if (dd.accountOverrides) {
      Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
      Object.assign(accountOverrides, dd.accountOverrides)
    }

    if (dd.publishAccountIds) {
      publishAccountIds.clear()
      dd.publishAccountIds.forEach(id => publishAccountIds.add(id))
    }

    if (dd.expandedGroups) {
      expandedGroups.value = new Set(dd.expandedGroups)
    }

    if (dd.selectedPlatform) {
      selectedPlatform.value = dd.selectedPlatform
    }

    if (dd.videoModeTab) {
      videoModeTab.value = dd.videoModeTab
    }

    currentDraftId.value = draftId

    if (commonConfig.videoLandscape) {
      triggerFrameExtraction(commonConfig.videoLandscape, 'landscape')
    }
    if (commonConfig.videoPortrait) {
      triggerFrameExtraction(commonConfig.videoPortrait, 'portrait')
    }

    ElMessage.success('草稿已恢复')
  } catch (e) {
    ElMessage.error('草稿恢复失败')
  }
}

onMounted(() => {
  const draftId = route.query.draft
  if (draftId) {
    restoreDraft(Number(draftId))
  }
  startAutoSaveTimer()
})

async function publishAll() {
  if (!commonConfig.videoLandscape && !commonConfig.videoPortrait) {
    ElMessage.error('请先上传至少一个视频文件')
    return
  }

  if (!commonConfig.coverLandscape && !commonConfig.coverPortrait) {
    ElMessage.error('请先设置封面图片')
    return
  }

  const accountsWithoutDeclaration = []
  const DECLARATION_PLATFORMS = {
    xiaohongshu: 'aiContent',
    douyin: 'aiContent',
    kuaishou: 'aiContent',
    bilibili: 'creationDeclaration',
    baijiahao: 'creationDeclaration',
    tencent_video: 'creationDeclaration',
    iqiyi: 'creationDeclaration',
    youtube: ['audience', 'alteredContent'],
  }

  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    const pSettings = platformConfigs[group.key] || {}
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const accountOverride = accountOverrides[account.id]
      const mergedSettings = accountOverride && Object.keys(accountOverride).length > 0
        ? { ...pSettings, ...Object.fromEntries(
            Object.entries(accountOverride).filter(([_, v]) => v !== undefined && v !== '' && v !== false)
          )}
        : { ...pSettings }
      const platformKey = group.key
      const declFields = DECLARATION_PLATFORMS[platformKey]
      if (!declFields) continue
      const fields = Array.isArray(declFields) ? declFields : [declFields]
      for (const field of fields) {
        const value = mergedSettings[field]
        const isEmpty = Array.isArray(value)
          ? value.length === 0
          : (typeof value === 'boolean' ? value === null || value === undefined : (!value && value !== 0))
        if (isEmpty) {
          accountsWithoutDeclaration.push(`${account.name}(${group.name})`)
          break
        }
      }
    }
  }
  if (accountsWithoutDeclaration.length > 0) {
    ElMessage.error(`以下账号未设置作品声明：${accountsWithoutDeclaration.join('、')}`)
    return
  }

  const accountsWithoutTitle = []
  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    const pSettings = platformConfigs[group.key] || {}
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const accountOverride = accountOverrides[account.id]
      const mergedTitle = (accountOverride && accountOverride.title)
        || pSettings.title
      if (!mergedTitle || !mergedTitle.trim()) {
        accountsWithoutTitle.push(`${account.name}(${group.name})`)
      }
    }
  }
  if (accountsWithoutTitle.length > 0) {
    ElMessage.error(`以下账号未设置标题：${accountsWithoutTitle.join('、')}`)
    return
  }

  const accountsWithoutVideoFormat = []
  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    const pSettings = platformConfigs[group.key] || {}
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const accountOverride = accountOverrides[account.id]
      const mergedFormat = (accountOverride && accountOverride.videoFormat)
        || pSettings.videoFormat
      if (!mergedFormat) {
        accountsWithoutVideoFormat.push(`${account.name}(${group.name})`)
      }
    }
  }
  if (accountsWithoutVideoFormat.length > 0) {
    ElMessage.error(`以下账号未选择视频格式：${accountsWithoutVideoFormat.join('、')}`)
    return
  }

  publishing.value = true
  publishProgress.value = 0
  publishResults.value = []
  isCancelled.value = false
  currentPublishingAccount.value = ''
  batchPublishDialogVisible.value = true

  const allTasks = []
  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    const pSettings = platformConfigs[group.key] || {}
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const accountOverride = accountOverrides[account.id]
      const mergedSettings = accountOverride && Object.keys(accountOverride).length > 0
        ? { ...pSettings, ...Object.fromEntries(
            Object.entries(accountOverride).filter(([_, v]) => v !== undefined && v !== '' && v !== false)
          )}
        : { ...pSettings }
      allTasks.push({ account, group, platformSettings: mergedSettings })
    }
  }

  if (allTasks.length === 0) {
    ElMessage.warning('没有可发布的账号')
    publishing.value = false
    batchPublishDialogVisible.value = false
    return
  }

  for (let i = 0; i < allTasks.length; i++) {
    if (isCancelled.value) {
      publishResults.value.push({
        label: allTasks[i].account.name,
        status: 'cancelled',
        message: '已取消',
      })
      continue
    }

    const { account, group, platformSettings } = allTasks[i]
    currentPublishingAccount.value = account.name
    publishProgress.value = Math.floor((i / allTasks.length) * 100)

    const videoFormat = platformSettings.videoFormat || ''

    let selectedVideo
    if (videoFormat === 'portrait') {
      selectedVideo = commonConfig.videoPortrait
    } else if (videoFormat === 'landscape') {
      selectedVideo = commonConfig.videoLandscape
    } else {
      selectedVideo = commonConfig.videoLandscape || commonConfig.videoPortrait
    }

    if (!selectedVideo) {
        publishResults.value.push({
          label: account.name,
          status: 'error',
          message: '未找到匹配的视频（请检查视频格式设置）',
        })
        continue
      }

    try {
      const customTags = (platformSettings.tags || '').split(/[,，\s]+/).map(t => t.replace(/^#/, '').trim()).filter(Boolean)
      const allTags = [...commonConfig.topics, ...customTags]

      const publishData = {
        type: group.id,
        title: platformSettings.title,
        description: platformSettings.description || '',
        tags: allTags,
        fileList: [selectedVideo.stored_path],
        videoFormat: videoFormat,
        accountList: [account.filePath],
        thumbnailLandscape: commonConfig.coverLandscape ? commonConfig.coverLandscape.stored_path : '',
        thumbnailPortrait: commonConfig.coverPortrait ? commonConfig.coverPortrait.stored_path : '',
        enableTimer: platformSettings.scheduleTime ? 1 : 0,
        scheduleTime: platformSettings.scheduleTime || '',
        videosPerDay: 1,
        dailyTimes: ['10:00'],
        startDays: 0,
        category: platformSettings.zone || (platformSettings.isOriginal ? 1 : 0),
        productLink: platformSettings.productLink || '',
        productTitle: platformSettings.productTitle || '',
        isDraft: platformSettings.isDraft || false,
        aiContent: platformSettings.aiContent || '',
        creationDeclaration: Array.isArray(platformSettings.creationDeclaration)
          ? platformSettings.creationDeclaration.join(',')
          : platformSettings.creationDeclaration || '',
        riskWarning: platformSettings.riskWarning || '',
        enableCashActivity: platformSettings.enableCashActivity || false,
        audience: platformSettings.audience || 'not_kids',
        alteredContent: platformSettings.alteredContent || false,
      }

      await http.post('/postVideo', publishData)
      publishResults.value.push({
        label: account.name,
        status: 'success',
        message: '发布成功',
      })
    } catch (error) {
      publishResults.value.push({
        label: account.name,
        status: 'error',
        message: error.message || '发布失败',
      })
    }
  }

  publishProgress.value = 100
  currentPublishingAccount.value = ''
  publishing.value = false

  const successCount = publishResults.value.filter(r => r.status === 'success').length
  const failCount = publishResults.value.filter(r => r.status === 'error').length

  if (failCount > 0) {
    ElMessage.warning(`发布完成：${successCount}个成功，${failCount}个失败`)
  } else {
    ElMessage.success('全部发布成功')
    setTimeout(() => {
      batchPublishDialogVisible.value = false
    }, 1500)
  }
}

function cancelBatch() {
  isCancelled.value = true
  ElMessage.info('正在取消发布...')
}

// ========== Utility ==========
function formatSize(bytes) {
  if (!bytes) return '0B'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(2) + 'MB'
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.cursor-pointer {
  cursor: pointer;
}

.publish-center {
  display: flex;
  height: 100%;
  gap: 0;
  overflow: hidden;
}

// ========== RIGHT MAIN ==========
.publish-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: $bg-elevated;
  overflow: hidden;
}

.main-body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.main-form-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  border-bottom: 1px solid $border;
  flex-shrink: 0;

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;

    .page-title {
      font-size: 18px;
      font-weight: 700;
      color: $text-primary;
    }

    .platform-tag {
      font-size: 12px;
      font-weight: 500;
      padding: 4px 12px;
      border-radius: 20px;
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 16px;

    .text-btn {
      font-size: 14px;
      color: $text-secondary;
      transition: $transition-base;

      &:hover {
        color: $brand-start;
      }
    }

    .publish-btn {
      display: inline-flex;
      align-items: center;
      padding: 8px 24px;
      border: 1px solid transparent;
      border-radius: $radius-sm;
      background: $gradient-brand;
      color: #fff;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: $transition-base;
      outline: none;
      font-family: inherit;

      &:hover {
        opacity: 0.9;
      }

      &:active {
        transform: scale(0.97);
      }

      &:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }
    }

    .draft-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 0 16px;
      height: 36px;
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: $radius-base;
      background: rgba(255, 255, 255, 0.06);
      color: $text-secondary;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: $transition-base;

      &:hover {
        background: rgba(255, 255, 255, 0.1);
        border-color: rgba(255, 255, 255, 0.25);
        color: $text-primary;
      }
    }
  }
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;

  &::-webkit-scrollbar {
    width: 6px;
  }
  &::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
  }
}

// ========== Config Section ==========
.config-section {
  margin-bottom: 24px;
}

.xhs-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: rgba(#ff4d4f, 0.1);
  border: 2px solid #ff4d4f;
  border-radius: 8px;
  color: #ff4d4f;
  font-size: 14px;
  font-weight: 600;
  animation: xhs-pulse 2s ease-in-out infinite;

  .el-icon {
    font-size: 20px;
    flex-shrink: 0;
  }
}

@keyframes xhs-pulse {
  0%, 100% { border-color: #ff4d4f; }
  50% { border-color: #ff7875; box-shadow: 0 0 12px rgba(#ff4d4f, 0.3); }
}

.section-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;

  .bar {
    width: 3px;
    height: 18px;
    border-radius: 2px;
    flex-shrink: 0;

    &.purple {
      background: $brand-start;
    }
  }

  .section-label {
    font-size: 15px;
    font-weight: 600;
    color: $text-primary;
  }

  .hint {
    font-size: 12px;
    color: $text-muted;
  }
}

// ========== Media Section ==========
.media-section {
  margin-bottom: 20px;
  border: 1px solid $border;
  border-radius: $radius-card;
  padding: 16px;
  background: rgba(255, 255, 255, 0.02);
  transition: $transition-base;

  &:hover {
    border-color: $border-active;
  }

  > .section-label {
    font-size: 13px;
    font-weight: 600;
    color: $text-primary;
    margin-bottom: 12px;
    display: block;
  }
}

.btn-icon {
  margin-right: 4px;
}

// ----- Right Phone Panel -----
.phone-panel {
  width: 400px;
  flex-shrink: 0;
  background: $bg-base;
  border-left: 1px solid $border;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.08) transparent;
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 2px; }
}

.phone-panel-header {
  padding: 16px 16px 12px;
  border-bottom: 1px solid $border;
}

.phone-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
}

.phone-mode-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 16px 8px;
}

.mode-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: $text-muted;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: $transition-fast;
  font-family: inherit;
  outline: none;

  &:hover:not(.active) {
    color: $text-secondary;
    background: rgba(255, 255, 255, 0.03);
  }
  &.active {
    background: rgba($brand-start, 0.08);
    border-color: rgba($brand-start, 0.2);
    color: $brand-start;
  }
}

.mode-icon-portrait {
  display: inline-block;
  width: 10px;
  height: 14px;
  border: 2px solid currentColor;
  border-radius: 3px;
}
.mode-icon-landscape {
  display: inline-block;
  width: 14px;
  height: 10px;
  border: 2px solid currentColor;
  border-radius: 3px;
}

.phone-preview-area {
  display: flex;
  justify-content: center;
  padding: 16px 4px;
}

.phone-mockup {
  position: relative;
  background: #1a1a2e;
  border: 3px solid #2a2a40;
  border-radius: 28px;
  padding: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4), inset 0 0 0 1px rgba(255, 255, 255, 0.05);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: width 0.3s ease;

  width: 90%;
}

.phone-notch {
  width: 60px;
  height: 6px;
  background: #2a2a40;
  border-radius: 3px;
  margin-bottom: 6px;
}

.phone-screen {
  width: 100%;
  aspect-ratio: 9 / 16;
  background: $bg-base;
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.phone-video-player {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  outline: none;
}

.phone-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  color: $text-muted;
  font-size: 11px;
  cursor: pointer;
  transition: $transition-fast;

  &:hover {
    color: $brand-start;
    background: rgba($brand-start, 0.04);
  }
}

.phone-home-bar {
  width: 40px;
  height: 4px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
  margin-top: 6px;
}

.phone-panel-actions {
  display: flex;
  gap: 8px;
  padding: 0 16px 12px;
  .cover-action-btn { flex: 1; }
}

.phone-panel-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 16px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid $border;
  border-radius: $radius-base;
}

.phone-info-name {
  font-size: 12px;
  color: $text-secondary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.phone-info-remove {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: $text-muted;
  cursor: pointer;
  transition: $transition-fast;
  &:hover {
    background: rgba($danger-color, 0.1);
    color: $danger-color;
  }
}

// ----- Cover Section -----
.cover-section {
  background: rgba(255, 255, 255, 0.01);
  border-color: $border;
}

.cover-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: stretch;
}

.cover-action-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border: 1px solid $border;
  border-radius: $radius-sm;
  background: rgba(255, 255, 255, 0.03);
  color: $text-secondary;
  font-size: 12px;
  cursor: pointer;
  transition: $transition-base;
  outline: none;
  font-family: inherit;
  line-height: 1;

  .el-icon {
    flex-shrink: 0;
    color: $text-muted;
    transition: $transition-base;
  }

  &:hover {
    border-color: rgba($brand-start, 0.35);
    background: linear-gradient(135deg, rgba($brand-start, 0.08), rgba($brand-end, 0.06));
    color: $text-primary;

    .el-icon {
      color: $brand-start;
    }
  }

  &:active {
    transform: scale(0.97);
  }

  &.primary {
    border-color: rgba($brand-start, 0.25);
    background: linear-gradient(135deg, rgba($brand-start, 0.1), rgba($brand-end, 0.08));
    color: $text-primary;

    .el-icon {
      color: $brand-start;
    }

    &:hover {
      border-color: rgba($brand-start, 0.45);
      background: linear-gradient(135deg, rgba($brand-start, 0.18), rgba($brand-end, 0.14));
    }
  }

  &.danger {
    &:hover {
      border-color: rgba($danger-color, 0.35);
      background: rgba($danger-color, 0.08);
      color: $danger-color;

      .el-icon {
        color: $danger-color;
      }
    }
  }
}

// ========== Form Fields ==========
.form-field {
  margin-bottom: 20px;

  .field-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 500;
    color: $text-secondary;

    .field-counter {
      font-size: 12px;
      color: $text-muted;
    }
  }

  :deep(.el-input__wrapper),
  :deep(.el-textarea__inner) {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid $border;
    border-radius: $radius-base;
    box-shadow: none;
    color: $text-primary;
    transition: $transition-base;

    &:hover {
      border-color: $border-active;
    }

    &:focus,
    &.is-focus {
      border-color: $brand-start;
    }
  }

  :deep(.el-input__count) {
    color: $text-muted;
    background: transparent;
  }
}

// ========== Quick Tags ==========
.quick-tags {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.topics-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;

  .el-tag {
    background: $gradient-brand-subtle;
    border-color: $border-active;
    color: $text-primary;
  }
}

// ========== Divider ==========
.divider {
  height: 1px;
  background: $border;
  margin: 8px 0 24px;
  background-image: repeating-linear-gradient(
    90deg,
    $border,
    $border 6px,
    transparent 6px,
    transparent 12px
  );
}

// ========== Batch Sync Section ==========
.batch-sync-section {
  border: 1px solid $border;
  border-radius: $radius-card;
  overflow: hidden;
  margin-bottom: 4px;

  .batch-sync-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    color: $text-secondary;
    transition: $transition-base;

    &:hover {
      color: $text-primary;
      background: rgba(255, 255, 255, 0.02);
    }
  }

  .batch-sync-body {
    padding: 12px 16px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    border-top: 1px solid $border;
  }
}

// ========== Platform Title & Description ==========
.platform-title-desc {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 12px;
}

// ========== Settings Grid ==========
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.setting-card {
  padding: 14px 16px;
  border: 1px solid;
  border-radius: $radius-card;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: $transition-base;

  &:hover {
    filter: brightness(1.1);
  }

  .setting-label {
    font-size: 13px;
    font-weight: 600;
  }

  .setting-desc {
    font-size: 12px;
    color: $text-secondary;
    line-height: 1.6;
    white-space: pre-line;
  }

  :deep(.el-input__wrapper),
  :deep(.el-select .el-input__wrapper) {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid $border;
    border-radius: $radius-sm;
    box-shadow: none;
    transition: $transition-base;

    &:hover {
      border-color: $border-active;
    }
  }

  .radio-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .radio-item {
    display: flex;
    align-items: center;
    gap: 4px;

    input[type='radio'] {
      display: none;
    }

    .radio-text {
      padding: 4px 14px;
      border: 1px solid $border;
      border-radius: $radius-sm;
      font-size: 12px;
      color: $text-secondary;
      transition: $transition-base;

      &.on {
        border-color: $brand-start;
        color: $brand-start;
        background: rgba(139, 92, 246, 0.06);
      }
    }

    &.disabled {
      opacity: 0.4;
      cursor: not-allowed;
      .radio-text.muted { opacity: 0.5; }
    }
  }
}

// ========== No Platform Hint ==========
.no-platform-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: $text-muted;
  text-align: center;

  .hint-icon {
    opacity: 0.3;
    margin-bottom: 16px;
  }

  p {
    font-size: 15px;
    margin: 4px 0;
  }

  .hint-sub {
    font-size: 13px;
    color: $text-muted;
  }
}

// ========== Topic Dialog ==========
.topic-dialog {
  .topic-dialog-content {
    .custom-topic-input {
      display: flex;
      gap: 12px;
      margin-bottom: 24px;

      .custom-input {
        flex: 1;
      }
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

// ========== Upload Dialogs ==========
.video-upload-dialog,
.material-library-dialog {
  .material-library-content {
    .material-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      max-height: 400px;
      overflow-y: auto;

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
}

// ========== Shared ==========
.dialog-footer-right {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
