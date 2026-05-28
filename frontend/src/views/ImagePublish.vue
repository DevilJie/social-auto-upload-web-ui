<template>
  <div class="image-publish">
    <!-- ========== LEFT SIDEBAR ========== -->
    <aside class="account-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">账号管理</span>
        <span class="sidebar-count">{{ totalCount }}</span>
      </div>

      <div class="group-list">
        <div
          v-for="group in imageAccountGroups"
          :key="group.key"
          :class="['group-wrap', { 'is-selected': selectedPlatform === group.key }]"
        >
          <!-- Group header -->
          <div
            class="group-header cursor-pointer"
            @click="toggleGroup(group.key)"
          >
            <el-icon class="expand-icon" :style="{ color: selectedPlatform === group.key ? group.color : '' }">
              <component :is="expandedGroups.has(group.key) ? ArrowDown : ArrowRight" />
            </el-icon>
            <span class="platform-badge">
              <img v-if="group.logo" :src="group.logo" :alt="group.name" class="platform-badge-img">
              <template v-else>{{ group.letter }}</template>
            </span>
            <span class="group-name">{{ group.name }}</span>
            <span class="group-count">{{ group.accounts.filter(a => publishAccountIds.has(a.id)).length }}</span>
          </div>

          <!-- Expandable account list -->
          <transition name="slide">
            <div v-show="expandedGroups.has(group.key)" class="group-accounts">
              <div
                v-for="account in group.accounts.filter(a => publishAccountIds.has(a.id))"
                :key="account.id"
                :class="['account-item cursor-pointer', {
                  active: selectedAccountId === account.id,
                  'has-override': hasAccountOverride(account.id)
                }]"
                @click="selectAccount(account, group)"
              >
                <div class="account-avatar" :style="{ borderColor: group.color }">
                  {{ account.name ? account.name.charAt(0) : '?' }}
                </div>
                <span class="account-name">{{ account.name }}</span>
                <span :class="['dot', account.status === '正常' ? 'on' : 'off']"></span>
                <el-icon v-if="hasAccountOverride(account.id)" class="override-icon" title="已自定义配置"><StarFilled /></el-icon>
                <el-icon class="account-remove" @click.stop="removePublishAccount(account.id)"><Close /></el-icon>
              </div>
              <div v-if="group.accounts.filter(a => publishAccountIds.has(a.id)).length === 0" class="no-accounts">暂无账号</div>
            </div>
          </transition>
        </div>
      </div>

      <div class="sidebar-footer">
        <div class="add-btn cursor-pointer" @click="accountDialogVisible = true">+ 添加账号</div>
      </div>
    </aside>

    <!-- ========== RIGHT MAIN AREA ========== -->
    <main class="publish-main">
      <div class="main-body">
      <!-- Left: form + content -->
      <div class="main-form-col">
      <!-- Top bar -->
      <div class="main-header">
        <div class="header-left">
          <span class="page-title">图文发布</span>
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

          <!-- Image Upload Section -->
          <div class="media-section">
            <ImageUploader
              ref="imageUploaderRef"
              v-model="commonConfig.images"
              :max-count="35"
              :visible-rows="3"
              :columns="5"
              @open-material-library="openMaterialLibraryForImage"
            />
          </div>

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

          <!-- 如果选中了账号且有自定义配置，显示"恢复默认"按钮 -->
          <div v-if="selectedAccountId && hasAccountOverride(selectedAccountId)" style="margin-bottom: 12px;">
            <el-button size="small" @click="resetAccountOverride(selectedAccountId)">恢复为渠道默认</el-button>
          </div>

          <!-- 小红书反检测警告 -->
          <div v-if="selectedPlatform === 'xiaohongshu'" class="xhs-warning">
            <el-icon><WarningFilled /></el-icon>
            <span>由于小红书反检测机制比较恶心，如果出现被警告的情况！请立即停止使用小红书渠道！</span>
          </div>

          <!-- 账号级 or 渠道级标题描述 -->
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

          <div class="settings-grid">
            <template v-for="field in imagePlatformSettingsFields" :key="field.key">
              <template v-if="field.key !== 'title' && field.key !== 'description'">
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
            <el-icon :size="48"><PictureFilled /></el-icon>
          </div>
          <p>请在左侧选择一个平台分组</p>
          <p class="hint-sub">选择后可配置该平台的个性化发布设置</p>
        </div>
      </div>
      </div><!-- /main-form-col -->

      <!-- Right: Image preview panel -->
      <div class="phone-panel">
        <div class="phone-panel-header">
          <span class="phone-panel-title">图片预览</span>
          <button
            v-if="commonConfig.images.length > 0"
            class="cover-action-btn"
            @click="openPreviewDialog"
          >
            <el-icon :size="14"><FullScreen /></el-icon><span>放大预览</span>
          </button>
        </div>

        <div class="phone-preview-area">
          <div class="phone-mockup">
            <div class="phone-notch"></div>
            <div class="phone-screen">
              <ImageCarousel
                v-if="commonConfig.images.length > 0"
                :images="commonConfig.images"
                @change="onCarouselChange"
              />
              <div v-else class="phone-empty" @click="triggerUpload">
                <el-icon :size="28"><Upload /></el-icon>
                <span>上传图片</span>
              </div>
            </div>
            <div class="phone-home-bar"></div>
          </div>
        </div>

        <div class="phone-panel-actions">
          <button class="cover-action-btn primary" @click="triggerUpload">
            <el-icon :size="14"><Upload /></el-icon><span>本地上传</span>
          </button>
          <button class="cover-action-btn" @click="openMaterialLibraryForImage(-1)">
            <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
          </button>
        </div>

        <div v-if="commonConfig.images.length > 0" class="phone-panel-info">
          <span class="phone-info-name">{{ commonConfig.images[currentPreviewIndex]?.name || '未选择图片' }}</span>
          <span class="phone-info-count">{{ currentPreviewIndex + 1 }}/{{ commonConfig.images.length }}</span>
        </div>
      </div>

      </div><!-- /main-body -->
    </main>

    <!-- ========== DIALOGS ========== -->

    <!-- Account Selection Dialog -->
    <el-dialog
      v-model="accountDialogVisible"
      title="选择账号"
      width="680px"
      :close-on-click-modal="false"
      class="account-select-dialog"
    >
      <div class="account-dialog-body">
        <div class="account-dialog-content">
          <!-- Left: platform list (only image-capable platforms) -->
          <div class="dialog-platform-list">
            <div
              :class="['dialog-platform-item', 'cursor-pointer', { active: !accountFilterPlatform }]"
              @click="accountFilterPlatform = ''"
            >全部平台</div>
            <div
              v-for="p in IMAGE_PLATFORMS"
              :key="p.key"
              :class="['dialog-platform-item', 'cursor-pointer', { active: accountFilterPlatform === p.name }]"
              @click="accountFilterPlatform = p.name"
            >
              <span class="dialog-platform-badge">
                <img v-if="p.logo" :src="p.logo" :alt="p.name" class="dialog-platform-badge-img">
                <template v-else>{{ p.letter }}</template>
              </span>
              {{ p.name }}
            </div>
          </div>

          <!-- Right: account checkboxes -->
          <div class="dialog-account-list">
            <div class="dialog-select-all">
              <el-button size="small" @click="toggleSelectAll">
                {{ isAllSelected ? '取消全选' : '一键全选' }}
              </el-button>
            </div>
            <el-checkbox-group v-model="tempSelectedAccounts">
              <div
                v-for="account in filteredAccounts"
                :key="account.id"
                :class="['dialog-account-item', { disabled: account.status !== '正常' }]"
              >
                <el-checkbox :label="account.id" class="cursor-pointer">
                  <div class="dialog-account-info">
                    <div class="dialog-account-avatar">{{ account.name ? account.name.charAt(0) : '?' }}</div>
                    <span class="dialog-account-name">{{ account.name }}</span>
                    <span class="dialog-account-platform">{{ account.platform }}</span>
                    <span :class="['dialog-account-status', account.status === '正常' ? 'ok' : 'err']">
                      {{ account.status === '正常' ? '正常' : '已失效' }}
                    </span>
                  </div>
                </el-checkbox>
              </div>
            </el-checkbox-group>
            <div v-if="filteredAccounts.length === 0" class="dialog-empty">暂无可选账号</div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <span class="selected-count">已选择 {{ tempSelectedAccounts.length }} 个账号</span>
          <div class="dialog-footer-btns">
            <el-button @click="accountDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="confirmAccountSelection">确认添加</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

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

    <!-- Material Select Dialog -->
    <MaterialSelectDialog
      ref="materialSelectDialogRef"
      filter-type="image"
      @select="onMaterialSelected"
    />

    <!-- Image Preview Dialog -->
    <ImagePreviewDialog
      ref="imagePreviewDialogRef"
      :images="commonConfig.images"
      :initial-index="currentPreviewIndex"
    />

    <!-- Batch Publish Progress Dialog -->
    <el-dialog
      v-model="batchPublishDialogVisible"
      title="批量发布进度"
      width="500px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
      class="batch-progress-dialog"
    >
      <div class="publish-progress">
        <el-progress
          :percentage="publishProgress"
          :status="publishProgress === 100 ? 'success' : ''"
        />
        <div v-if="currentPublishingAccount" class="current-publishing">
          正在发布：{{ currentPublishingAccount }}
        </div>

        <div class="publish-results" v-if="publishResults.length > 0">
          <div
            v-for="(result, index) in publishResults"
            :key="index"
            :class="['result-item', result.status]"
          >
            <el-icon v-if="result.status === 'success'"><Check /></el-icon>
            <el-icon v-else-if="result.status === 'error'"><Close /></el-icon>
            <el-icon v-else><InfoFilled /></el-icon>
            <span class="result-label">{{ result.label }}</span>
            <span class="result-message">{{ result.message }}</span>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer-right">
          <el-button @click="cancelBatch" :disabled="publishProgress === 100">取消发布</el-button>
          <el-button type="primary" @click="batchPublishDialogVisible = false" v-if="publishProgress === 100">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import {
  Upload, ArrowDown, ArrowRight, Picture, PictureFilled,
  Check, Close, InfoFilled, Promotion, StarFilled,
  Document, WarningFilled, FullScreen
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { accountApi } from '@/api/account'
import { imagePublishApi } from '@/api/imagePublish'
import { platformList, getPlatformByKey, PLATFORMS } from '@/config/platforms'
import { useRoute } from 'vue-router'

import ImageUploader from '@/components/ImageUploader.vue'
import ImageCarousel from '@/components/ImageCarousel.vue'
import ImagePreviewDialog from '@/components/ImagePreviewDialog.vue'
import MaterialSelectDialog from '@/components/MaterialSelectDialog.vue'

// ========== Stores & Config ==========
const accountStore = useAccountStore()
const appStore = useAppStore()
appStore.loadAutoFillTitle()
appStore.loadAutoSaveSettings()
const route = useRoute()

// Only image-capable platforms: 小红书(1), 抖音(3), 快手(4)
const IMAGE_PLATFORM_KEYS = ['xiaohongshu', 'douyin', 'kuaishou']
const IMAGE_PLATFORMS = platformList.filter(p => IMAGE_PLATFORM_KEYS.includes(p.key))

// ========== Left Sidebar State ==========
const expandedGroups = ref(new Set())
const selectedPlatform = ref(null)
const selectedAccountId = ref(null)

// Account groups - only image-capable platforms
const imageAccountGroups = computed(() => {
  return IMAGE_PLATFORMS.map(p => ({
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

const totalCount = computed(() => {
  let count = 0
  for (const group of imageAccountGroups.value) {
    count += group.accounts.length
  }
  return count
})

const currentPlatformConfig = computed(() =>
  selectedPlatform.value ? getPlatformByKey(selectedPlatform.value) : null
)

// Image platform settings fields (exclude videoFormat)
const imagePlatformSettingsFields = computed(() => {
  if (!currentPlatformConfig.value) return []
  return (currentPlatformConfig.value.settingsFields || []).filter(f => f.key !== 'videoFormat')
})

// ========== Public Config (shared across all accounts) ==========
const commonConfig = reactive({
  images: [],      // Array of { id, name, url, path, size, type }
  topics: [],
})

const currentPreviewIndex = ref(0)

// ========== Per-platform Config ==========
const platformConfigs = reactive({
  douyin: { title: '', description: '', productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true },
  xiaohongshu: { title: '', description: '', collection: '', groupChat: '', location: '', aiContent: '', isOriginal: false, scheduleTime: '' },
  kuaishou: { title: '', description: '', productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '' },
})

// ========== Account-level Overrides ==========
const accountOverrides = reactive({})

// 表单数据
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

// 切换平台/账号时重新填充表单
watch([selectedPlatform, selectedAccountId], () => {
  const merged = getMergedSettings()
  for (const key of Object.keys(merged)) {
    form[key] = merged[key]
  }
  // 清理不存在的字段
  for (const key of Object.keys(form)) {
    if (!(key in merged)) {
      delete form[key]
    }
  }
}, { immediate: true })

// 表单变更时同步到 store
watch(form, (newVal) => {
  const platformKey = selectedPlatform.value
  if (!platformKey) return
  if (!platformConfigs[platformKey]) {
    platformConfigs[platformKey] = {}
  }
  const platform = platformConfigs[platformKey]

  if (selectedAccountId.value) {
    // 账号级：计算与渠道默认的差异
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
    // 渠道级：直接写入
    for (const key of Object.keys(newVal)) {
      platform[key] = newVal[key]
    }
  }
}, { deep: true })

function getAccountName(accountId) {
  const account = accountStore.accounts.find(a => a.id === accountId)
  return account ? account.name : '未知'
}

function hasAccountOverride(accountId) {
  const override = accountOverrides[accountId]
  if (!override) return false
  return Object.values(override).some(v => v !== undefined && v !== '' && v !== false)
}

function resetAccountOverride(accountId) {
  delete accountOverrides[accountId]
  ElMessage.success('已恢复为渠道默认设置')
}

// ========== Batch title/description sync ==========
const batchTitle = ref('')
const batchDescription = ref('')
const batchSyncExpanded = ref(false)

function syncBatchToAll() {
  for (const key of Object.keys(platformConfigs)) {
    if (batchTitle.value) platformConfigs[key].title = batchTitle.value
    if (batchDescription.value) platformConfigs[key].description = batchDescription.value
  }
  ElMessage.success('已同步到所有平台')
}

// ========== Init: expand first group with accounts ==========
const firstGroup = imageAccountGroups.value.find(g => g.accounts.length > 0)
if (firstGroup) {
  expandedGroups.value.add(firstGroup.key)
  selectedPlatform.value = firstGroup.key
}

// ========== Dialog State ==========
const accountDialogVisible = ref(false)
const topicDialogVisible = ref(false)
const batchPublishDialogVisible = ref(false)

// Account dialog state
const accountFilterPlatform = ref('')
const tempSelectedAccounts = ref([])

// 账号弹窗打开时恢复状态
watch(accountDialogVisible, async (visible) => {
  if (visible) {
    tempSelectedAccounts.value = [...publishAccountIds]
    if (accountStore.accounts.length === 0) {
      try {
        const res = await accountApi.getAccounts()
        if (res.code === 200 && res.data) {
          accountStore.setAccounts(res.data)
        }
      } catch (e) {
        console.error('加载账号失败:', e)
      }
    }
  }
})

// Topic dialog state
const customTopic = ref('')
const recommendedTopics = [
  '游戏', '电影', '音乐', '美食', '旅行', '文化',
  '科技', '生活', '娱乐', '体育', '教育', '艺术',
  '健康', '时尚', '美妆', '摄影', '宠物', '汽车',
]

// Refs
const imageUploaderRef = ref(null)
const materialSelectDialogRef = ref(null)
const imagePreviewDialogRef = ref(null)

// Batch publish state
const publishing = ref(false)
const publishProgress = ref(0)
const publishResults = ref([])
const currentPublishingAccount = ref('')
const isCancelled = ref(false)

// Selected accounts for publishing
const publishAccountIds = reactive(new Set())
const currentDraftId = ref(null)
const autoSaveTimer = ref(null)
const hasChanges = ref(false)

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

// ========== Image Methods ==========

function triggerUpload() {
  imageUploaderRef.value?.triggerUpload?.()
}

function onCarouselChange(index) {
  currentPreviewIndex.value = index
}

function openPreviewDialog() {
  imagePreviewDialogRef.value?.open(currentPreviewIndex.value)
}

function openMaterialLibraryForImage(index) {
  materialSelectDialogRef.value?.open()
  // Store the target index for when material is selected
  materialTargetIndex.value = index
}

const materialTargetIndex = ref(-1)

function onMaterialSelected(material) {
  const imageData = {
    id: `img-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
    name: material.name,
    url: material.url,
    path: material.path,
    size: material.size,
    type: material.type,
    uploading: false,
    progress: 100,
  }

  const targetIdx = materialTargetIndex.value
  if (targetIdx >= 0 && targetIdx < commonConfig.images.length) {
    // Replace existing image
    commonConfig.images[targetIdx] = { ...commonConfig.images[targetIdx], ...imageData }
  } else {
    // Add new image
    if (commonConfig.images.length < 35) {
      commonConfig.images.push(imageData)
    } else {
      ElMessage.warning('最多只能上传 35 张图片')
    }
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

// ========== Account Dialog Methods ==========

const filteredAccounts = computed(() => {
  let list = accountStore.accounts
  // Only show image-capable platform accounts
  const imagePlatformNames = IMAGE_PLATFORMS.map(p => p.name)
  list = list.filter(a => imagePlatformNames.includes(a.platform))
  if (accountFilterPlatform.value) {
    list = list.filter(a => a.platform === accountFilterPlatform.value)
  }
  return list
})

const validFilteredAccounts = computed(() =>
  filteredAccounts.value.filter(a => a.status === '正常')
)

const isAllSelected = computed(() =>
  validFilteredAccounts.value.length > 0 &&
  validFilteredAccounts.value.every(a => tempSelectedAccounts.value.includes(a.id))
)

function toggleSelectAll() {
  if (isAllSelected.value) {
    const validIds = new Set(validFilteredAccounts.value.map(a => a.id))
    tempSelectedAccounts.value = tempSelectedAccounts.value.filter(id => !validIds.has(id))
  } else {
    const validIds = validFilteredAccounts.value.map(a => a.id)
    const merged = new Set([...tempSelectedAccounts.value, ...validIds])
    tempSelectedAccounts.value = [...merged]
  }
}

function confirmAccountSelection() {
  tempSelectedAccounts.value.forEach(id => {
    publishAccountIds.add(id)
  })
  hasChanges.value = true
  accountDialogVisible.value = false
  ElMessage.success(`已选择 ${tempSelectedAccounts.value.length} 个账号`)
  tempSelectedAccounts.value = []
}

// ========== Publish Methods ==========

async function saveDraft() {
  try {
    const imageIds = commonConfig.images.map(img => img.id)
    const accountConfigs = [...publishAccountIds].map(id => {
      const account = accountStore.accounts.find(a => a.id === id)
      const group = imageAccountGroups.value.find(g => g.accounts.some(a => a.id === id))
      const pSettings = platformConfigs[group?.key] || {}
      const accountOverride = accountOverrides[id]
      const mergedSettings = accountOverride && Object.keys(accountOverride).length > 0
        ? { ...pSettings, ...Object.fromEntries(
            Object.entries(accountOverride).filter(([_, v]) => v !== undefined && v !== '' && v !== false)
          )}
        : { ...pSettings }
      return {
        account_id: id,
        platform: account?.platform || '',
        title: mergedSettings.title || '',
        description: mergedSettings.description || '',
        ...mergedSettings,
      }
    })

    if (currentDraftId.value) {
      await imagePublishApi.saveDraft({ id: currentDraftId.value, image_ids: imageIds, account_configs: accountConfigs })
      ElMessage.success('草稿已更新')
    } else {
      const resp = await imagePublishApi.saveDraft({ image_ids: imageIds, account_configs: accountConfigs })
      if (resp?.data?.id) {
        currentDraftId.value = resp.data.id
      }
      ElMessage.success('草稿已保存')
    }
  } catch (e) {
    ElMessage.error('草稿保存失败')
  }
}

async function publishAll() {
  // Validate
  if (commonConfig.images.length === 0) {
    ElMessage.error('请先上传至少一张图片')
    return
  }

  // Check selected accounts
  if (publishAccountIds.size === 0) {
    ElMessage.error('请先添加发布账号')
    return
  }

  // Check each selected account has a title
  const accountsWithoutTitle = []
  for (const group of imageAccountGroups.value) {
    if (group.accounts.length === 0) continue
    const pSettings = platformConfigs[group.key] || {}
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const accountOverride = accountOverrides[account.id]
      const mergedTitle = (accountOverride && accountOverride.title) || pSettings.title
      if (!mergedTitle || !mergedTitle.trim()) {
        accountsWithoutTitle.push(`${account.name}(${group.name})`)
      }
    }
  }
  if (accountsWithoutTitle.length > 0) {
    ElMessage.error(`以下账号未设置标题：${accountsWithoutTitle.join('、')}`)
    return
  }

  // 声明必填检查
  const accountsWithoutDeclaration = []
  const DECLARATION_PLATFORMS = {
    xiaohongshu: 'aiContent',
    douyin: 'aiContent',
    kuaishou: 'aiContent',
  }

  for (const group of imageAccountGroups.value) {
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
      const declField = DECLARATION_PLATFORMS[platformKey]
      if (!declField) continue
      const value = mergedSettings[declField]
      const isEmpty = typeof value === 'boolean' ? value === null || value === undefined : (!value && value !== 0)
      if (isEmpty) {
        accountsWithoutDeclaration.push(`${account.name}(${group.name})`)
        break
      }
    }
  }
  if (accountsWithoutDeclaration.length > 0) {
    ElMessage.error(`以下账号未设置内容声明：${accountsWithoutDeclaration.join('、')}`)
    return
  }

  publishing.value = true
  publishProgress.value = 0
  publishResults.value = []
  isCancelled.value = false
  currentPublishingAccount.value = ''
  batchPublishDialogVisible.value = true

  // Collect tasks
  const allTasks = []
  for (const group of imageAccountGroups.value) {
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

  // Build account_configs for the backend
  const imageIds = commonConfig.images.map(img => img.id)
  const accountConfigs = allTasks.map(({ account, group, platformSettings }) => {
    const customTags = (platformSettings.tags || '').split(/[,，\s]+/).map(t => t.replace(/^#/, '').trim()).filter(Boolean)
    const allTags = [...commonConfig.topics, ...customTags]
    return {
      account_id: account.id,
      platform: account.platform,
      title: platformSettings.title,
      description: platformSettings.description || '',
      tags: allTags,
      scheduleTime: platformSettings.scheduleTime || '',
      aiContent: platformSettings.aiContent || '',
      productLink: platformSettings.productLink || '',
      productTitle: platformSettings.productTitle || '',
      visibility: platformSettings.visibility || 'public',
      allowDownload: platformSettings.allowDownload !== false,
    }
  })

  for (let i = 0; i < allTasks.length; i++) {
    if (isCancelled.value) {
      publishResults.value.push({
        label: allTasks[i].account.name,
        status: 'cancelled',
        message: '已取消',
      })
      continue
    }

    const { account } = allTasks[i]
    currentPublishingAccount.value = account.name
    publishProgress.value = Math.floor((i / allTasks.length) * 100)

    try {
      // Call the backend publish API with the full task data
      await imagePublishApi.publishImage({
        image_ids: imageIds,
        account_configs: [accountConfigs[i]],
      })
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

// ========== Auto-save ==========

function startAutoSaveTimer() {
  if (autoSaveTimer.value) {
    clearInterval(autoSaveTimer.value)
    autoSaveTimer.value = null
  }
  if (!appStore.autoSaveDraft) return
  autoSaveTimer.value = setInterval(() => {
    if (hasChanges.value) {
      saveDraft()
      hasChanges.value = false
    }
  }, appStore.autoSaveInterval * 1000)
}

function stopAutoSaveTimer() {
  if (autoSaveTimer.value) {
    clearInterval(autoSaveTimer.value)
    autoSaveTimer.value = null
  }
}

watch(() => appStore.autoSaveDraft, (val) => {
  if (val) startAutoSaveTimer()
  else stopAutoSaveTimer()
})

watch(() => appStore.autoSaveInterval, () => {
  if (appStore.autoSaveDraft) startAutoSaveTimer()
})

// 监听内容变化
watch(commonConfig, () => { hasChanges.value = true }, { deep: true })
watch(platformConfigs, () => { hasChanges.value = true }, { deep: true })
watch(accountOverrides, () => { hasChanges.value = true }, { deep: true })

// ========== Load Draft ==========
async function loadDraft(draftId) {
  try {
    const resp = await imagePublishApi.getDrafts()
    if (resp.code === 200) {
      const draft = resp.data.find(d => d.id === draftId)
      if (draft) {
        // 恢复草稿 ID
        currentDraftId.value = draft.id

        // 恢复图片列表
        if (draft.image_urls && draft.image_urls.length > 0) {
          const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
          commonConfig.images = draft.image_ids.map((id, index) => ({
            id: id,
            name: `图片 ${index + 1}`,
            url: draft.image_urls[index] ? `${baseUrl}${draft.image_urls[index]}` : '',
            path: '',
            size: 0,
            type: 'image/jpeg',
            uploading: false,
            progress: 100,
          }))
        }

        // 恢复账号配置
        if (draft.account_configs && draft.account_configs.length > 0) {
          // 恢复选中的账号
          publishAccountIds.clear()
          draft.account_configs.forEach(config => {
            publishAccountIds.add(config.account_id)

            // 恢复平台配置
            const account = accountStore.accounts.find(a => a.id === config.account_id)
            if (account) {
              const group = imageAccountGroups.value.find(g => g.key === getPlatformKeyByName(account.platform))
              if (group) {
                platformConfigs[group.key] = {
                  ...platformConfigs[group.key],
                  title: config.title || '',
                  description: config.description || '',
                  ...config,
                }
              }
            }
          })
        }

        ElMessage.success('草稿已加载')
      }
    }
  } catch (e) {
    console.error('加载草稿失败:', e)
    ElMessage.error('加载草稿失败')
  }
}

function getPlatformKeyByName(platformName) {
  const platform = IMAGE_PLATFORMS.find(p => p.name === platformName)
  return platform?.key || ''
}

onMounted(() => {
  startAutoSaveTimer()

  // 检查是否有 draft 参数
  const draftId = route.query.draft
  if (draftId) {
    loadDraft(draftId)
  }
})

onBeforeUnmount(() => {
  stopAutoSaveTimer()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

// ========== Utility Classes ==========
.cursor-pointer {
  cursor: pointer;
}

// ========== Layout ==========
.image-publish {
  display: flex;
  height: 100%;
  gap: 0;
  overflow: hidden;
}

// ========== LEFT SIDEBAR ==========
.account-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: $bg-base;
  border-right: 1px solid $border;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 16px 14px;
    border-bottom: 1px solid $border;

    .sidebar-title {
      font-size: 15px;
      font-weight: 600;
      color: $text-primary;
    }

    .sidebar-count {
      font-size: 12px;
      color: $text-muted;
      background: $bg-surface;
      padding: 2px 8px;
      border-radius: 10px;
    }
  }

  .group-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px 0;

    &::-webkit-scrollbar {
      width: 4px;
    }
    &::-webkit-scrollbar-thumb {
      background: rgba(255, 255, 255, 0.1);
      border-radius: 2px;
    }
  }

  .group-wrap {
    margin: 2px 8px;
    border-radius: $radius-base;
    transition: $transition-base;

    &.is-selected {
      background: rgba(139, 92, 246, 0.06);
      border: 1px solid rgba(139, 92, 246, 0.12);
      margin: 2px 7px;
    }
  }

  .group-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: $radius-base;
    transition: $transition-base;
    user-select: none;

    &:hover {
      background: rgba(255, 255, 255, 0.03);
    }

    .expand-icon {
      font-size: 12px;
      color: $text-muted;
      transition: $transition-base;
    }

    .platform-badge {
      width: 32px;
      height: 32px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-size: 13px;
      font-weight: 700;
      flex-shrink: 0;
      overflow: hidden;

      .platform-badge-img {
        width: 24px;
        height: 24px;
        object-fit: contain;
      }
    }

    .group-name {
      flex: 1;
      font-size: 15px;
      color: $text-secondary;
      font-weight: 500;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .group-count {
      font-size: 11px;
      color: $text-muted;
      background: rgba(255, 255, 255, 0.06);
      padding: 1px 6px;
      border-radius: 8px;
    }
  }

  .group-accounts {
    padding: 0 12px 8px 42px;

    .no-accounts {
      font-size: 12px;
      color: $text-muted;
      padding: 4px 0;
    }
  }

  // Slide transition
  .slide-enter-active,
  .slide-leave-active {
    transition: all 200ms ease;
    overflow: hidden;
  }
  .slide-enter-from,
  .slide-leave-to {
    opacity: 0;
    max-height: 0;
  }
  .slide-enter-to,
  .slide-leave-from {
    opacity: 1;
    max-height: 500px;
  }

  .account-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 8px;
    transition: $transition-base;

    &:hover {
      background: rgba(255, 255, 255, 0.04);
    }

    &.active {
      background: rgba(139, 92, 246, 0.08);
    }

    .account-avatar {
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.08);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      color: $text-secondary;
      font-weight: 600;
      flex-shrink: 0;
      border: 2px solid transparent;
      transition: $transition-base;
    }

    .account-name {
      flex: 1;
      font-size: 12px;
      color: $text-secondary;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      flex-shrink: 0;

      &.on {
        background: $success-color;
      }
      &.off {
        background: $danger-color;
      }
    }

    .account-remove {
      font-size: 16px;
      color: $text-muted;
      opacity: 0.6;
      transition: $transition-fast;
      flex-shrink: 0;
      margin-left: 4px;
      cursor: pointer;

      &:hover {
        color: $danger-color;
        opacity: 1;
      }
    }

    &.has-override {
      background: rgba(255, 215, 0, 0.06);
      .account-name { font-weight: 600; }
    }

    .override-icon {
      font-size: 12px;
      color: #f59e0b;
      flex-shrink: 0;
    }
  }

  .sidebar-footer {
    padding: 12px;
    border-top: 1px solid $border;

    .add-btn {
      border: 1px dashed $border;
      border-radius: $radius-base;
      padding: 8px;
      text-align: center;
      font-size: 13px;
      color: $text-muted;
      transition: $transition-base;

      &:hover {
        border-color: $border-active;
        color: $brand-start;
        background: rgba(139, 92, 246, 0.06);
      }
    }
  }
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

      &:hover { opacity: 0.9; }
      &:active { transform: scale(0.97); }
      &:disabled { opacity: 0.6; cursor: not-allowed; }
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

  &::-webkit-scrollbar { width: 6px; }
  &::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 3px; }
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
  }

  :deep(.el-input__wrapper),
  :deep(.el-textarea__inner) {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid $border;
    border-radius: $radius-base;
    box-shadow: none;
    color: $text-primary;
    transition: $transition-base;

    &:hover { border-color: $border-active; }
    &:focus, &.is-focus { border-color: $brand-start; }
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

  &:hover { filter: brightness(1.1); }

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

    &:hover { border-color: $border-active; }
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

    input[type='radio'] { display: none; }

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
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.phone-panel-title {
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
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

.phone-info-count {
  font-size: 11px;
  color: $text-muted;
  flex-shrink: 0;
  margin-left: 8px;
}

// ========== Cover Action Button ==========
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

    .el-icon { color: $brand-start; }
  }

  &:active { transform: scale(0.97); }

  &.primary {
    border-color: rgba($brand-start, 0.25);
    background: linear-gradient(135deg, rgba($brand-start, 0.1), rgba($brand-end, 0.08));
    color: $text-primary;

    .el-icon { color: $brand-start; }

    &:hover {
      border-color: rgba($brand-start, 0.45);
      background: linear-gradient(135deg, rgba($brand-start, 0.18), rgba($brand-end, 0.14));
    }
  }
}

// ========== Account Dialog ==========
.account-select-dialog {
  .account-dialog-body {
    .account-dialog-content {
      display: flex;
      gap: 0;
      border: 1px solid $border;
      border-radius: $radius-base;
      overflow: hidden;
      height: 420px;
    }

    .dialog-platform-list {
      width: 160px;
      flex-shrink: 0;
      border-right: 1px solid $border;
      background: rgba(0, 0, 0, 0.2);
      overflow-y: auto;

      .dialog-platform-item {
        padding: 14px 16px;
        font-size: 15px;
        color: $text-secondary;
        display: flex;
        align-items: center;
        gap: 12px;
        transition: $transition-base;

        &:hover { background: rgba(255, 255, 255, 0.03); }

        &.active {
          background: rgba(139, 92, 246, 0.08);
          color: $text-primary;
          font-weight: 500;
        }

        .dialog-platform-badge {
          width: 28px;
          height: 28px;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #fff;
          font-size: 11px;
          font-weight: 700;
          flex-shrink: 0;
          overflow: hidden;

          .dialog-platform-badge-img {
            width: 22px;
            height: 22px;
            object-fit: contain;
          }
        }
      }
    }

    .dialog-account-list {
      flex: 1;
      padding: 12px;
      overflow-y: auto;

      .dialog-select-all {
        display: flex;
        justify-content: flex-end;
        margin-bottom: 8px;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      }

      .dialog-account-item {
        padding: 8px 10px;
        border-radius: $radius-sm;
        transition: $transition-base;
        margin-bottom: 4px;

        &:hover { background: rgba(255, 255, 255, 0.03); }
        &.disabled { opacity: 0.5; }
      }

      .dialog-account-info {
        display: flex;
        align-items: center;
        gap: 8px;

        .dialog-account-avatar {
          width: 26px;
          height: 26px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.08);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 11px;
          color: $text-secondary;
          font-weight: 600;
          flex-shrink: 0;
        }

        .dialog-account-name {
          font-size: 13px;
          color: $text-primary;
          font-weight: 500;
        }

        .dialog-account-platform {
          font-size: 11px;
          color: $text-muted;
        }

        .dialog-account-status {
          font-size: 11px;
          margin-left: auto;

          &.ok { color: $success-color; }
          &.err { color: $danger-color; }
        }
      }
    }
  }

  .dialog-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .selected-count {
      font-size: 13px;
      color: $text-muted;
    }

    .dialog-footer-btns {
      display: flex;
      gap: 8px;
    }
  }
}

// ========== Topic Dialog ==========
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

// ========== Batch Progress Dialog ==========
.batch-progress-dialog {
  .publish-progress {
    padding: 12px 0;

    .current-publishing {
      margin: 16px 0;
      text-align: center;
      color: $text-secondary;
      font-size: 14px;
    }

    .publish-results {
      margin-top: 20px;
      border-top: 1px solid $border;
      padding-top: 16px;
      max-height: 300px;
      overflow-y: auto;

      .result-item {
        display: flex;
        align-items: center;
        padding: 8px 0;
        color: $text-secondary;

        .el-icon { margin-right: 8px; }

        .result-label {
          margin-right: 10px;
          font-weight: 500;
          color: $text-primary;
        }

        .result-message {
          color: $text-muted;
          font-size: 13px;
        }

        &.success {
          .el-icon, .result-label { color: $success-color; }
        }

        &.error {
          .el-icon, .result-label { color: $danger-color; }
        }

        &.cancelled {
          color: $text-muted;
          .result-label { color: $text-muted; }
        }
      }
    }
  }
}

// ========== Shared Dialog Styles ==========
.dialog-footer-right {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.dialog-empty {
  text-align: center;
  padding: 40px 0;
  color: $text-muted;
  font-size: 14px;
}
</style>
