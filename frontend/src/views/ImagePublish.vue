<template>
  <div class="image-publish">
    <!-- ========== LEFT SIDEBAR ========== -->
    <AccountSidebar
      :account-groups="imageAccountGroups"
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
          <span class="page-title">图集发布</span>
          <span
            v-if="currentPlatformConfig"
            class="platform-tag"
            :style="{ background: currentPlatformConfig.bgColor, color: currentPlatformConfig.color }"
          >
            {{ currentPlatformConfig.name }} · 个性化设置
          </span>
        </div>
        <div class="header-right">
          <el-button :icon="Document" @click="saveDraft" class="header-btn">
            {{ currentDraftId ? '更新草稿' : '保存草稿' }}
          </el-button>
          <el-button :icon="MagicStick" @click="oneClickDialogOpen = true" :disabled="publishAccountIds.size === 0" class="header-btn">
            一键填写
          </el-button>
          <el-button :icon="Setting" @click="batchSetDialogOpen = true" :disabled="publishAccountIds.size === 0" class="header-btn">
            批量设置
          </el-button>
          <el-button type="primary" :icon="Promotion" @click="publishAll" :disabled="publishing" class="header-btn header-btn--primary">
            {{ publishing ? '发布中...' : '一键发布' }}
          </el-button>
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
            <template v-if="currentPlatformConfig && publishAccountIds.size > 0">
              <el-checkbox
                v-model="platformChecked[selectedPlatform]"
                @change="onPlatformCheckChange"
              >
                {{ currentPlatformConfig.name }} 渠道个性化
              </el-checkbox>
              <el-checkbox
                v-if="selectedAccountId"
                v-model="accountChecked[selectedAccountId]"
                :disabled="!platformChecked[selectedPlatform]"
                @change="onAccountCheckChange"
              >
                {{ getAccountDisplayName(selectedAccountId) }} 账号个性化
              </el-checkbox>
            </template>
          </div>

          <!-- 封面图片 -->
          <div class="cover-section">
            <ImageCoverUpload
              v-model="currentEditTarget.coverImage"
              label="封面图片"
              @open-library="openMaterialLibraryForCover"
            />
          </div>

          <!-- Image Upload Section -->
          <div class="media-section">
            <ImageUploader
              ref="imageUploaderRef"
              v-model="currentEditTarget.images"
              :max-count="35"
              :visible-rows="3"
              :columns="5"
              @open-material-library="openMaterialLibraryForImage"
            />
          </div>
        </div>

        <!-- Divider -->
        <div class="divider"></div>

        <!-- ===== PLATFORM-SPECIFIC SETTINGS ===== -->
        <div class="config-section" v-show="selectedPlatform && publishAccountIds.size > 0">
          <div class="section-bar">
            <div class="bar" :style="{ background: currentPlatformConfig?.color }"></div>
            <span class="section-label">
              {{ currentPlatformConfig?.name }}
              {{ selectedAccountId ? '· ' + getAccountDisplayName(selectedAccountId) : '· 默认设置' }}
            </span>
            <span class="hint">{{ selectedAccountId ? '仅对该账号生效' : '对该分组所有未自定义的账号生效' }}</span>
          </div>

          <DouyinImagePublishPanel
            ref="douyinPanelRef"
            :account-id="selectedPlatform === 'douyin' ? selectedAccountId : null"
            :disabled="publishing"
            v-show="selectedPlatform === 'douyin'"
            @config-changed="onChannelConfigChanged"
            @publish-result="onPublishResult"
          />
          <XiaohongshuImagePublishPanel
            ref="xiaohongshuPanelRef"
            :account-id="selectedPlatform === 'xiaohongshu' ? selectedAccountId : null"
            :disabled="publishing"
            v-show="selectedPlatform === 'xiaohongshu'"
            @config-changed="onChannelConfigChanged"
            @publish-result="onPublishResult"
          />
          <KuaishouImagePublishPanel
            ref="kuaishouPanelRef"
            :account-id="selectedPlatform === 'kuaishou' ? selectedAccountId : null"
            :disabled="publishing"
            v-show="selectedPlatform === 'kuaishou'"
            @config-changed="onChannelConfigChanged"
            @publish-result="onPublishResult"
          />
          <WeiboImagePublishPanel
            ref="weiboPanelRef"
            :account-id="selectedPlatform === 'weibo' ? selectedAccountId : null"
            :disabled="publishing"
            v-show="selectedPlatform === 'weibo'"
            @config-changed="onChannelConfigChanged"
            @publish-result="onPublishResult"
          />
          <AlipayImagePublishPanel
            ref="alipayPanelRef"
            :account-id="selectedPlatform === 'alipay' ? selectedAccountId : null"
            :disabled="publishing"
            v-show="selectedPlatform === 'alipay'"
            @config-changed="onChannelConfigChanged"
            @publish-result="onPublishResult"
          />
        </div>

        <!-- No account selected hint -->
        <div v-if="publishAccountIds.size === 0" class="no-platform-hint">
          <div class="hint-icon">
            <el-icon :size="48"><UserFilled /></el-icon>
          </div>
          <p>请先在左侧账号设置</p>
          <p class="hint-sub">选择账号后才能配置对应渠道的发布设置</p>
        </div>

        <!-- No platform selected hint -->
        <div v-else-if="!selectedPlatform" class="no-platform-hint">
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
            v-if="currentEditTarget.images.length > 0"
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
                v-if="currentEditTarget.images.length > 0"
                :images="currentEditTarget.images"
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

        <div v-if="currentEditTarget.images.length > 0" class="phone-panel-info">
          <span class="phone-info-name">{{ currentEditTarget.images[currentPreviewIndex]?.name || '未选择图片' }}</span>
          <span class="phone-info-count">{{ currentPreviewIndex + 1 }}/{{ currentEditTarget.images.length }}</span>
        </div>
      </div>

      </div><!-- /main-body -->
    </main>

    <!-- ========== DIALOGS ========== -->

    <!-- Account Selection Dialog -->
    <AccountSelectDialog
      v-model="accountDialogVisible"
      :platforms="IMAGE_PLATFORMS"
      :publish-account-ids="publishAccountIds"
      @confirm="onAccountConfirm"
    />

    <!-- Material Select Dialog -->
    <MaterialSelectDialog
      ref="materialSelectDialogRef"
      filter-type="image"
      @select="onMaterialSelected"
    />

    <!-- Image Preview Dialog -->
    <ImagePreviewDialog
      ref="imagePreviewDialogRef"
      :images="currentEditTarget.images"
      :initial-index="currentPreviewIndex"
    />

    <!-- Batch Publish Progress Dialog -->
    <BatchPublishDialog
      v-model="batchPublishDialogVisible"
      :progress="publishProgress"
      :results="publishResults"
      :current-account="currentPublishingAccount"
      @cancel="cancelBatch"
    />

    <!-- One-click Fill Dialog -->
    <OneClickFillDialog
      v-model="oneClickDialogOpen"
      type="image"
      @pick="handleOneClickFill"
    />

    <!-- Batch Set Dialog -->
    <BatchSetDialog
      v-model="batchSetDialogOpen"
      :platforms="batchSetPlatforms"
      @apply="onBatchSetApply"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted } from 'vue'
import {
  Upload, Picture, PictureFilled,
  Document, FullScreen, MagicStick, Setting, Promotion, UserFilled
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { accountApi } from '@/api/account'
import { imagePublishApi } from '@/api/imagePublish'
import { draftApi } from '@/api/draft'
import { getFileUrl } from '@/utils/storage'
import { platformList, getPlatformByKey, platformNameToKey } from '@/config/platforms'
import { useRoute } from 'vue-router'

import AccountSidebar from '@/components/AccountSidebar.vue'
import AccountSelectDialog from '@/components/AccountSelectDialog.vue'
import BatchPublishDialog from '@/components/BatchPublishDialog.vue'
import ImageUploader from '@/components/ImageUploader.vue'
import ImageCarousel from '@/components/ImageCarousel.vue'
import ImagePreviewDialog from '@/components/ImagePreviewDialog.vue'
import MaterialSelectDialog from '@/components/MaterialSelectDialog.vue'
import ImageCoverUpload from '@/components/ImageCoverUpload.vue'
import OneClickFillDialog from '@/components/OneClickFillDialog.vue'
import BatchSetDialog from '@/components/BatchSetDialog.vue'
import { useImageBatchSetApply } from '@/composables/useImageBatchSetApply'
import { useAutoSave } from '@/composables/useAutoSave'

import DouyinImagePublishPanel from '@/components/douyin/ImagePublishPanel.vue'
import XiaohongshuImagePublishPanel from '@/components/xiaohongshu/ImagePublishPanel.vue'
import KuaishouImagePublishPanel from '@/components/kuaishou/ImagePublishPanel.vue'
import WeiboImagePublishPanel from '@/components/weibo/ImagePublishPanel.vue'
import AlipayImagePublishPanel from '@/components/alipay/ImagePublishPanel.vue'

// ========== Stores & Config ==========
const accountStore = useAccountStore()
const appStore = useAppStore()
appStore.loadAutoFillTitle()
appStore.loadAutoSaveSettings()
const route = useRoute()

const IMAGE_PLATFORM_KEYS = ['xiaohongshu', 'douyin', 'kuaishou', 'weibo', 'alipay']
const IMAGE_PLATFORMS = platformList.filter(p => IMAGE_PLATFORM_KEYS.includes(p.key))

// ========== Left Sidebar State ==========
const expandedGroups = ref(new Set())
const selectedPlatform = ref(null)
const selectedAccountId = ref(null)

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

// ========== Public Config ==========
const commonConfig = reactive({
  images: [],
  coverImage: null,
})

// ========== 平台/账号级覆写（spec §3.4）—— 公共区域的媒体字段覆写 ==========
const platformOverrides = reactive({})         // { [platformKey]: { images, coverImage } }
const platformChecked = reactive({})           // { [platformKey]: boolean }
const accountOverrides = reactive({})          // { [accountId]: { images, coverImage } }
const accountChecked = reactive({})            // { [accountId]: boolean }

// 当前编辑目标：公共区域 v-model 的实际绑定对象
// 勾选账号 → accountOverrides[id]；勾选平台 → platformOverrides[key]；默认 → commonConfig
const currentEditTarget = computed(() => {
  const aid = selectedAccountId.value
  if (aid && accountChecked[aid] && accountOverrides[aid]) return accountOverrides[aid]
  const pk = selectedPlatform.value
  if (pk && platformChecked[pk] && platformOverrides[pk]) return platformOverrides[pk]
  return commonConfig
})

function hasPlatformOverrideContent(platformKey) {
  const ov = platformOverrides[platformKey]
  if (!ov) return false
  return !!(
    (ov.images && ov.images.length > 0) ||
    ov.coverImage
  )
}

function hasAccountOverrideContent(accountId) {
  const ov = accountOverrides[accountId]
  if (!ov) return false
  return !!(
    (ov.images && ov.images.length > 0) ||
    ov.coverImage
  )
}

const currentPreviewIndex = ref(0)

// ========== Auto-save ==========
const currentDraftId = ref(null)

const { hasChanges, startAutoSaveTimer } = useAutoSave(() => saveDraft())

// ========== Channel Panel Refs & Helpers ==========
const douyinPanelRef = ref(null)
const xiaohongshuPanelRef = ref(null)
const kuaishouPanelRef = ref(null)
const weiboPanelRef = ref(null)
const alipayPanelRef = ref(null)

function getPanel(key) {
  const map = { douyin: douyinPanelRef, xiaohongshu: xiaohongshuPanelRef, kuaishou: kuaishouPanelRef, weibo: weiboPanelRef, alipay: alipayPanelRef }
  return map[key]?.value
}

function getAccountDisplayName(accountId) {
  const account = accountStore.accounts.find(a => a.id === accountId)
  return account ? account.name : '未知'
}

function onChannelConfigChanged() {
  hasChanges.value = true
}

function onPublishResult({ accountName, status, message }) {
  publishResults.value.push({ label: accountName, status, message })
}

function hasAccountOverride(accountId) {
  // Task 10：新增覆写层勾选 + panel 内部 accountOverrides 任一为真都算
  if (accountChecked[accountId] && hasAccountOverrideContent(accountId)) return true
  for (const key of ['douyin', 'xiaohongshu', 'kuaishou', 'weibo', 'alipay']) {
    const panel = getPanel(key)
    if (panel && panel.hasAccountOverride(accountId)) return true
  }
  return false
}

// ========== Override Section: Interaction ==========

function onPlatformCheckChange(checked) {
  if (!checked && hasPlatformOverrideContent(selectedPlatform.value)) {
    ElMessageBox.confirm(
      '取消个性化配置后，本渠道的覆写将丢失，恢复使用公共默认，是否继续？',
      '确认取消', { confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning' }
    ).then(() => {
      delete platformOverrides[selectedPlatform.value]
    }).catch(() => {
      platformChecked[selectedPlatform.value] = true
    })
  } else if (checked) {
    platformOverrides[selectedPlatform.value] = {
      images: [], coverImage: null,
    }
  }
}

function onAccountCheckChange(checked) {
  if (!checked && hasAccountOverrideContent(selectedAccountId.value)) {
    ElMessageBox.confirm(
      '取消个性化配置后，本账号的覆写将丢失，恢复使用渠道默认，是否继续？',
      '确认取消', { confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning' }
    ).then(() => {
      delete accountOverrides[selectedAccountId.value]
    }).catch(() => {
      accountChecked[selectedAccountId.value] = true
    })
  } else if (checked) {
    accountOverrides[selectedAccountId.value] = {
      images: [], coverImage: null,
    }
  }
}

// ========== 4 级优先级合并（spec §3.3 / §3.4） ==========
// accountOv > platformOv > platformDefault > common
function resolveAccountConfig(platformKey, accountId) {
  const accountOv = (accountChecked[accountId] && accountOverrides[accountId]) || null
  const platformOv = (platformChecked[platformKey] && platformOverrides[platformKey]) || null
  // 注意：plan 写的是 getConfig()，实际 panel 暴露的是 getConfigs() 返回 { platformConfig, accountOverrides }
  const platformDefault = getPanel(platformKey)?.getConfigs?.()?.platformConfig || null
  return mergeConfig(commonConfig, platformDefault, platformOv, accountOv)
}

function mergeConfig(common, platformDefault, platformOv, accountOv) {
  return {
    // 文本字段仅从 platformDefault 取（覆写区不再含 title/desc/tags）
    title: platformDefault?.title ?? '',
    description: platformDefault?.description ?? '',
    tags: platformDefault?.tags ?? [],
    // 媒体字段走 4 级合并 → commonConfig 兜底
    images: accountOv?.images ?? platformOv?.images ?? platformDefault?.images ?? common.images,
    coverImage: accountOv?.coverImage ?? platformOv?.coverImage ?? platformDefault?.coverImage ?? common.coverImage,
    enableTimer: accountOv?.enableTimer ?? platformOv?.enableTimer ?? platformDefault?.enableTimer ?? 0,
    scheduleTime: accountOv?.scheduleTime ?? platformOv?.scheduleTime ?? platformDefault?.scheduleTime ?? '',
    aiContent: accountOv?.aiContent ?? platformOv?.aiContent ?? platformDefault?.aiContent ?? '',
    isOriginal: accountOv?.isOriginal ?? platformOv?.isOriginal ?? platformDefault?.isOriginal ?? false,
    music: accountOv?.music ?? platformOv?.music ?? platformDefault?.music ?? null,
    authorStatement: accountOv?.authorStatement ?? platformOv?.authorStatement ?? platformDefault?.authorStatement ?? '',
  }
}

// ========== Init ==========
const firstGroup = imageAccountGroups.value.find(g => g.accounts.length > 0)
if (firstGroup) {
  expandedGroups.value.add(firstGroup.key)
  selectedPlatform.value = firstGroup.key
}

// ========== Dialog State ==========
const accountDialogVisible = ref(false)
const batchPublishDialogVisible = ref(false)
const oneClickDialogOpen = ref(false)
const batchSetDialogOpen = ref(false)

// 构造 panelKey → panel 引用值的映射,供 useImageBatchSetApply 按 key 索引;
// 传入 reactive proxy,使其属性访问时返回当前 panel 引用值 (component instance)
const panelsProxy = reactive({
  get douyin() { return douyinPanelRef.value },
  get xiaohongshu() { return xiaohongshuPanelRef.value },
  get kuaishou() { return kuaishouPanelRef.value },
  get weibo() { return weiboPanelRef.value },
  get alipay() { return alipayPanelRef.value },
})
const { applyImageBatchSet } = useImageBatchSetApply({ panels: panelsProxy })
// 渠道个性化可见平台列表：过滤掉被拉黑的平台
const visibleImagePlatformsForCustomize = computed(() =>
  IMAGE_PLATFORMS.filter(p => !appStore.isPlatformDisabled(p.key))
)
const batchSetPlatforms = computed(() => {
  return visibleImagePlatformsForCustomize.value.map(p => {
    const panelAccounts = accountStore.accounts.filter(a => a.platform === p.name)
    const selectedCount = panelAccounts.filter(a => publishAccountIds.has(a.id)).length
    return { key: p.key, name: p.name, logo: p.logo, count: selectedCount }
  })
})
function onBatchSetApply(checkedKeys, payload) {
  applyImageBatchSet(checkedKeys, payload)
  ElMessage.success(`已批量设置到 ${checkedKeys.length} 个渠道`)
}

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
  publishAccountIds.clear()
  ids.forEach(id => {
    publishAccountIds.add(id)
  })
  hasChanges.value = true
  ElMessage.success(`已选择 ${ids.length} 个账号`)
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
  materialSelectMode.value = 'image'
  materialSelectDialogRef.value?.open()
  materialTargetIndex.value = index
}

function openMaterialLibraryForCover() {
  materialSelectMode.value = 'cover'
  materialSelectDialogRef.value?.open()
}

const materialTargetIndex = ref(-1)
const materialSelectMode = ref('image')

function onMaterialSelected(material) {
  const imageData = {
    id: material.id,
    name: material.name,
    url: material.url,
    stored_path: material.stored_path,
    size: material.size,
    type: material.type,
    uploading: false,
    progress: 100,
  }

  if (materialSelectMode.value === 'cover') {
    currentEditTarget.value.coverImage = {
      id: material.id,
      name: material.name,
      url: material.url,
      stored_path: material.stored_path,
      size: material.size,
      type: material.type,
    }
    ElMessage.success('封面选择成功')
    return
  }

  const targetIdx = materialTargetIndex.value
  const targetImages = currentEditTarget.value.images
  if (targetIdx >= 0 && targetIdx < targetImages.length) {
    targetImages[targetIdx] = { ...targetImages[targetIdx], ...imageData }
  } else {
    if (targetImages.length < 35) {
      targetImages.push(imageData)
    } else {
      ElMessage.warning('最多只能上传 35 张图片')
    }
  }
}

// ========== Publish Methods ==========

async function saveDraft() {
  try {
    const allPlatformConfigs = {}
    const panelAccountOverrides = {}
    for (const key of ['douyin', 'xiaohongshu', 'kuaishou', 'weibo', 'alipay']) {
      const panel = getPanel(key)
      if (panel) {
        const configs = panel.getConfigs()
        allPlatformConfigs[key] = configs.platformConfig
        Object.assign(panelAccountOverrides, configs.accountOverrides)
      }
    }

    const draftData = {
      commonConfig: {
        images: commonConfig.images.map(img => ({ id: img.id, name: img.name, url: img.url, stored_path: img.stored_path, size: img.size, type: img.type })),
        coverImage: commonConfig.coverImage || null,
      },
      platformConfigs: allPlatformConfigs,
      // Task 10：保留 panel 内部 accountOverrides（旧草稿兼容），独立 key 避免与 spec §3.4 的 accountOverrides 冲突
      panelAccountOverrides,
      // Task 10：spec §3.4 新增 4 个键（覆写层）
      platformOverrides: JSON.parse(JSON.stringify(platformOverrides)),
      accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
      platformChecked: { ...platformChecked },
      accountChecked: { ...accountChecked },
      publishAccountIds: [...publishAccountIds],
      selectedPlatform: selectedPlatform.value,
      selectedAccountId: selectedAccountId.value,
      expandedGroups: [...expandedGroups.value],
    }

    if (currentDraftId.value) {
      await imagePublishApi.saveDraft({ id: currentDraftId.value, draft_data: draftData })
      ElMessage.success('草稿已更新')
    } else {
      const resp = await imagePublishApi.saveDraft({ draft_data: draftData })
      if (resp.code === 200) {
        currentDraftId.value = resp.data.id
        ElMessage.success('草稿已保存')
      }
    }
    hasChanges.value = false
  } catch (e) {
    console.error('保存草稿失败:', e)
    ElMessage.error('草稿保存失败')
  }
}

async function publishAll() {
  if (commonConfig.images.length === 0) {
    ElMessage.error('请先上传至少一张图片')
    return
  }
  if (publishAccountIds.size === 0) {
    ElMessage.error('请先添加发布账号')
    return
  }

  // Task 10：用 4 级合并后的数据校验（标题必须存在）
  const accountsWithoutTitle = []
  for (const group of imageAccountGroups.value) {
    if (group.accounts.length === 0) continue
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const merged = resolveAccountConfig(group.key, account.id)
      if (!merged.title || !merged.title.trim()) {
        accountsWithoutTitle.push(`${account.name}(${group.name})`)
      }
    }
  }
  if (accountsWithoutTitle.length > 0) {
    ElMessage.error(`以下账号未设置标题：${accountsWithoutTitle.join('、')}`)
    return
  }

  for (const group of imageAccountGroups.value) {
    if (group.accounts.length === 0) continue
    const panel = getPanel(group.key)
    if (!panel) continue
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const result = panel.validate(account.id)
      if (!result.valid) {
        ElMessage.error(`${account.name}(${group.name}): ${result.errors.join('; ')}`)
        return
      }
    }
  }

  publishing.value = true
  publishProgress.value = 0
  publishResults.value = []
  isCancelled.value = false
  currentPublishingAccount.value = ''
  batchPublishDialogVisible.value = true

  // Task 13：生成本次一键发布的 batchId + 封面素材 ID（一次发布，跨账号复用）
  const batchId = (crypto.randomUUID && crypto.randomUUID()) || (Date.now().toString(36) + '-' + Math.random().toString(36).slice(2))
  const coverMaterialId = commonConfig.coverImage?.id || ''
  const publishExtra = { batchId, landscapeCoverMaterialId: coverMaterialId, portraitCoverMaterialId: coverMaterialId }

  // Task 10：4 级合并为每个账号生成 merged commonData（images / coverImage 走合并后值）
  const allTasks = []
  for (const group of imageAccountGroups.value) {
    if (group.accounts.length === 0) continue
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const merged = resolveAccountConfig(group.key, account.id)
      allTasks.push({ account, groupKey: group.key, merged })
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
      publishResults.value.push({ label: allTasks[i].account.name, status: 'cancelled', message: '已取消' })
      continue
    }
    const { account, groupKey, merged } = allTasks[i]
    currentPublishingAccount.value = account.name
    publishProgress.value = Math.floor((i / allTasks.length) * 100)

    // merged 出的 images / coverImage 走 commonData（panel 默认使用 commonData）
    // title/description/tags/platformConfig（aiContent/isOriginal 等）走 panel 自身 merged（panel.getMergedConfig）
    const commonData = { images: merged.images, coverImage: merged.coverImage }

    const panel = getPanel(groupKey)
    if (panel) {
      // 备份 panel 原状态（含 platformConfig 中的平台特定字段如 selectedMusic / hotspotId / mini_link / activities 等）
      const originalConfigs = panel.getConfigs()
      const originalPlatformConfig = originalConfigs.platformConfig || {}
      const originalAccountOverrides = originalConfigs.accountOverrides || {}

      // 选择性更新 platformConfig 的 9 个标准字段，保留其他平台特定字段不被覆盖
      const STANDARD_FIELDS = [
        'title', 'description', 'tags', 'images', 'coverImage',
        'enableTimer', 'scheduleTime', 'aiContent', 'isOriginal'
      ]
      const updatedPlatformConfig = { ...originalPlatformConfig }
      for (const field of STANDARD_FIELDS) {
        if (field in merged) {
          updatedPlatformConfig[field] = Array.isArray(merged[field])
            ? [...merged[field]]
            : merged[field]
        }
      }

      // 注入 panel：platformConfig 保留所有平台特定字段 + 9 标准字段已更新；
      // accountOverrides[id] 在 panel 原有 override（含音乐等平台特定字段）基础上叠加 merged，
      // 否则 resolveAccountConfig 只产出 9 标准字段，会丢掉 selectedMusicId/musicTitle 等字段
      panel.restoreConfigs(
        updatedPlatformConfig,
        {
          ...originalAccountOverrides,
          [account.id]: { ...(originalAccountOverrides[account.id] || {}), ...merged },
        }
      )
      try {
        await panel.publish(account.id, account.name, commonData, publishExtra)
      } finally {
        // 恢复原 panel 状态（restoreConfigs 是整体重置，所以必须用完整备份）
        panel.restoreConfigs(
          originalPlatformConfig,
          originalAccountOverrides
        )
      }
    }
  }

  publishProgress.value = 100
  publishing.value = false

  const successCount = publishResults.value.filter(r => r.status === 'success').length
  const failCount = publishResults.value.filter(r => r.status === 'fail').length

  if (failCount > 0) {
    ElMessage.warning(`发布完成：${successCount}个成功，${failCount}个失败`)
  } else {
    ElMessage.success('全部发布成功')
    setTimeout(() => { batchPublishDialogVisible.value = false }, 1500)
  }
}

function cancelBatch() {
  isCancelled.value = true
  ElMessage.info('正在取消发布...')
}

// ========== One-click fill ==========
function handleOneClickFill(record) {
  const histConfigs = record.account_configs || []
  if (histConfigs.length === 0) {
    ElMessage.warning('历史记录中没有账号配置')
    return
  }

  // 新逻辑：直接用历史的全部账号配置（覆盖或新增），不再做交集
  let filled = 0
  let skipped = 0

  for (const hist of histConfigs) {
    if (!hist || typeof hist !== 'object') continue

    const accountId = Number(hist.account_id)
    if (!accountId) continue

    const account = accountStore.accounts.find(a => a.id === accountId)
    if (!account) {
      // 历史里有但账号已被删除：跳过
      skipped++
      continue
    }

    const platformKey = getPlatformKeyByName(account.platform)
    const panel = getPanel(platformKey)
    if (!panel) {
      skipped++
      continue
    }

    // 把账号加入当前选择
    publishAccountIds.add(accountId)

    const configs = panel.getConfigs()
    const newOverrides = { ...configs.accountOverrides }
    const existing = newOverrides[accountId] || {}
    newOverrides[accountId] = {
      ...existing,
      title: hist.title ?? existing.title ?? '',
      description: hist.description ?? existing.description ?? '',
      tags: hist.tags ?? existing.tags ?? [],
      aiContent: hist.aiContent ?? existing.aiContent ?? '',
    }
    panel.restoreConfigs(configs.platformConfig, newOverrides)
    filled++
  }

  if (filled > 0) {
    const msg = skipped > 0
      ? `已从历史填充 ${filled} 个账号配置（${skipped} 个已删除账号跳过）`
      : `已从历史填充 ${filled} 个账号配置`
    ElMessage.success(msg)
  } else if (skipped > 0) {
    ElMessage.warning(`历史中 ${skipped} 个账号已不存在，无法填充`)
  } else {
    ElMessage.warning('历史记录没有可填充的账号配置')
  }
}

// ========== Old Draft Migration ==========
function migrateOldDraftFormat(dd) {
  if (dd.commonConfig?.topics && Array.isArray(dd.commonConfig.topics)) {
    for (const key of ['douyin', 'xiaohongshu', 'kuaishou', 'weibo', 'alipay']) {
      if (dd.platformConfigs?.[key]) {
        dd.platformConfigs[key].tags = [...dd.commonConfig.topics]
      }
    }
    delete dd.commonConfig.topics
  }

  if (dd.douyinSelections) {
    const sel = dd.douyinSelections
    const douyinCfg = dd.platformConfigs?.douyin || {}
    if (sel.selectedMusic !== undefined) douyinCfg.selectedMusic = sel.selectedMusic
    if (sel.selectedMusicData !== undefined) douyinCfg.selectedMusicData = sel.selectedMusicData
    if (sel.hotspotId !== undefined) douyinCfg.hotspotId = sel.hotspotId
    if (sel.hotspotData !== undefined) douyinCfg.hotspotData = sel.hotspotData
    if (sel.mixId !== undefined) douyinCfg.mixId = sel.mixId
    if (sel.mixData !== undefined) douyinCfg.mixData = sel.mixData
    if (sel.selectedTag !== undefined) douyinCfg.selectedTag = sel.selectedTag
    if (sel.tagType !== undefined) douyinCfg.tagType = sel.tagType
    if (sel.tagValue !== undefined) douyinCfg.tagValue = sel.tagValue
    if (!dd.platformConfigs) dd.platformConfigs = {}
    dd.platformConfigs.douyin = douyinCfg
    delete dd.douyinSelections
  }

  // 旧草稿 accountOverrides 实际是 panel 的；新草稿拆成 panelAccountOverrides + accountOverrides
  const oldOverrideSource = dd.panelAccountOverrides || dd.accountOverrides
  if (oldOverrideSource) {
    for (const override of Object.values(oldOverrideSource)) {
      delete override.coverImage
    }
  }
}

// ========== Load Draft ==========
async function loadDraft(draftId) {
  try {
    const resp = await draftApi.getDraft(draftId)
    if (resp.code !== 200) return
    const draft = resp.data
    const dd = draft.draft_data
    if (!dd) { ElMessage.error('草稿数据为空'); return }

    currentDraftId.value = draft.id

    if (dd.commonConfig) {
      if (dd.commonConfig.images) {
        commonConfig.images = dd.commonConfig.images.map((img, i) => ({
          id: img.id,
          name: img.name || `图片 ${i + 1}`,
          url: img.stored_path ? getFileUrl(img.stored_path) : (img.url || ''),
          stored_path: img.stored_path || '',
          size: img.size || 0,
          type: img.type || 'image/jpeg',
          uploading: false,
          progress: 100,
        }))
      }
      if (dd.commonConfig.coverImage) {
        const ci = dd.commonConfig.coverImage
        commonConfig.coverImage = { ...ci, url: ci.stored_path ? getFileUrl(ci.stored_path) : (ci.url || '') }
      }
    }

    migrateOldDraftFormat(dd)

    if (dd.selectedPlatform) selectedPlatform.value = dd.selectedPlatform
    if (dd.selectedAccountId) {
      selectedAccountId.value = dd.selectedAccountId
    } else if (dd.publishAccountIds?.length > 0) {
      selectedAccountId.value = dd.publishAccountIds[0]
    }
    if (dd.expandedGroups) expandedGroups.value = new Set(dd.expandedGroups)
    if (dd.publishAccountIds) {
      publishAccountIds.clear()
      dd.publishAccountIds.forEach(id => publishAccountIds.add(id))
    }

    await nextTick()

    // Task 10：恢复 spec §3.4 的 4 个新键（先恢复 override 层，再恢复 panel 状态）
    if (dd.platformOverrides) {
      Object.keys(platformOverrides).forEach(k => delete platformOverrides[k])
      Object.assign(platformOverrides, dd.platformOverrides)
    }
    if (dd.accountOverrides) {
      Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
      Object.assign(accountOverrides, dd.accountOverrides)
    }
    if (dd.platformChecked) {
      Object.keys(platformChecked).forEach(k => delete platformChecked[k])
      Object.assign(platformChecked, dd.platformChecked)
    }
    if (dd.accountChecked) {
      Object.keys(accountChecked).forEach(k => delete accountChecked[k])
      Object.assign(accountChecked, dd.accountChecked)
    }

    if (dd.platformConfigs) {
      // 兼容：旧草稿的 accountOverrides 是 panel 的；新草稿改名为 panelAccountOverrides
      const panelOverridesSource = dd.panelAccountOverrides || dd.accountOverrides
      for (const [key, val] of Object.entries(dd.platformConfigs)) {
        const panel = getPanel(key)
        if (panel && val) {
          const ownOverrides = {}
          if (panelOverridesSource) {
            const ownAccountIds = new Set(
              accountStore.accounts
                .filter(a => getPlatformKeyByName(a.platform) === key)
                .map(a => a.id)
            )
            for (const [accId, accOverride] of Object.entries(panelOverridesSource)) {
              if (ownAccountIds.has(Number(accId))) {
                ownOverrides[accId] = accOverride
              }
            }
          }
          panel.restoreConfigs(val, ownOverrides)
        }
      }
    }

    ElMessage.success('草稿已加载')
  } catch (e) {
    console.error('加载草稿失败:', e)
    ElMessage.error('加载草稿失败')
  }
}

function getPlatformKeyByName(platformName) {
  const platform = IMAGE_PLATFORMS.find(p => p.name === platformName)
  return platform?.key || ''
}

// Watch content changes
watch(commonConfig, () => { hasChanges.value = true }, { deep: true })

onMounted(async () => {
  startAutoSaveTimer()

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

  // 加载标签列表(确保「选择账号」弹窗内的标签筛选可用)
  accountStore.loadTags()

  // 清理 publishAccountIds 中属于黑名单平台的账号（本地清理，不写后端）
  // publishAccountIds 是 reactive Set，用 clear + add 模式重建
  const filteredIds = new Set()
  for (const id of publishAccountIds) {
    const acc = accountStore.accounts.find(a => a.id === id)
    if (!acc) continue
    const key = platformNameToKey[acc.platform]
    if (key && !appStore.isPlatformDisabled(key)) {
      filteredIds.add(id)
    }
  }
  publishAccountIds.clear()
  filteredIds.forEach(id => publishAccountIds.add(id))

  const draftId = route.query.draft
  if (draftId) {
    await loadDraft(Number(draftId))
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

// ========== Utility Classes ==========
.cursor-pointer { cursor: pointer; }

// ========== Layout ==========
.image-publish {
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

// ========== HEADER BAR ==========
.main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 28px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
  background: linear-gradient(90deg, rgba(139, 92, 246, 0.04) 0%, transparent 40%, transparent 60%, rgba(59, 130, 246, 0.03) 100%);

  .header-left {
    display: flex;
    align-items: center;
    gap: 14px;

    .page-title {
      font-size: 20px;
      font-weight: 800;
      color: #f8fafc;
      letter-spacing: -0.02em;
    }

    .platform-tag {
      font-size: 12px;
      font-weight: 600;
      padding: 5px 16px;
      border-radius: 20px;
      letter-spacing: 0.02em;
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    justify-content: flex-end;

    .header-btn {
      // el-button 默认 padding 8px 15px / font-size 14px / height 32px
      // 想要更紧凑一点,小分辨率下自动缩
      @media (max-width: 1280px) {
        padding: 6px 12px !important;
        font-size: 12px !important;
      }
    }

    .header-btn--primary {
      // 一键发布: 保留项目渐变 + 阴影
      background: linear-gradient(135deg, #8b5cf6, #6366f1) !important;
      border: none !important;
      box-shadow: 0 4px 20px rgba(139, 92, 246, 0.35) !important;
      font-weight: 700;
      letter-spacing: 0.04em;
      padding: 10px 24px !important;

      &:hover {
        box-shadow: 0 6px 28px rgba(139, 92, 246, 0.5) !important;
        transform: translateY(-1px);
        opacity: 1 !important;
      }
      &:active { transform: translateY(0) scale(0.98); }
      &:disabled { opacity: 0.5 !important; cursor: not-allowed; transform: none; box-shadow: none !important; }
    }
  }
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 28px;

  &::-webkit-scrollbar { width: 5px; }
  &::-webkit-scrollbar-thumb { background: rgba(139, 92, 246, 0.12); border-radius: 3px; }
}

// ========== Config Section ==========
.config-section {
  margin-bottom: 28px;
}

.xhs-warning {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  margin-bottom: 16px;
  background: rgba(255, 77, 79, 0.1);
  border: 1px solid rgba(255, 77, 79, 0.3);
  border-radius: 12px;
  color: #ff7875;
  font-size: 13px;
  font-weight: 600;
  animation: xhs-pulse 3s ease-in-out infinite;

  .el-icon { font-size: 18px; flex-shrink: 0; }
}

@keyframes xhs-pulse {
  0%, 100% { border-color: rgba(255, 77, 79, 0.3); }
  50% { border-color: rgba(255, 120, 117, 0.5); box-shadow: 0 0 20px rgba(255, 77, 79, 0.12); }
}

.section-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 22px;

  .bar {
    width: 4px;
    height: 22px;
    border-radius: 2px;
    flex-shrink: 0;

    &.purple {
      background: linear-gradient(180deg, #8b5cf6, #6366f1);
      box-shadow: 0 0 10px rgba(139, 92, 246, 0.4);
    }
  }

  .section-label {
    font-size: 16px;
    font-weight: 700;
    color: #f8fafc;
  }

  .hint {
    font-size: 12px;
    color: $text-muted;
    padding: 3px 12px;
    background: rgba(255, 255, 255, 0.04);
    border-radius: 12px;
  }
}

.cover-section {
  margin-bottom: 16px;
}

.media-section {
  margin-bottom: 20px;
  border: 1px solid rgba(139, 92, 246, 0.12);
  border-radius: 14px;
  padding: 18px;
  background: rgba(139, 92, 246, 0.03);
  transition: all 0.2s ease;

  &:hover {
    border-color: rgba(139, 92, 246, 0.22);
  }
}

.form-field {
  margin-bottom: 20px;

  .field-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 600;
    color: $text-secondary;
  }

  :deep(.el-input__wrapper),
  :deep(.el-textarea__inner) {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    box-shadow: none;
    color: $text-primary;
    transition: all 0.2s ease;

    &:hover { border-color: rgba(139, 92, 246, 0.3); }
    &:focus, &.is-focus {
      border-color: rgba(139, 92, 246, 0.5);
      box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.08);
    }
  }

  :deep(.el-input__count) {
    color: $text-muted;
    background: transparent;
  }
}

.divider {
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(139, 92, 246, 0.15) 30%, rgba(139, 92, 246, 0.15) 70%, transparent);
  margin: 8px 0 28px;
}

.batch-sync-section {
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 14px;
  overflow: hidden;
  margin-bottom: 4px;
  background: rgba(255, 255, 255, 0.015);
  transition: all 0.2s ease;

  &:hover { border-color: rgba(139, 92, 246, 0.12); }

  .batch-sync-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 18px;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    color: $text-secondary;
    transition: all 0.2s ease;

    &:hover { color: $text-primary; background: rgba(255, 255, 255, 0.02); }
  }

  .batch-sync-body {
    padding: 14px 18px 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.04);
  }
}

.platform-title-desc {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 12px;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.setting-card {
  padding: 16px 18px;
  border: 1px solid;
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.2s ease;

  &:hover { filter: brightness(1.1); }

  .setting-label {
    font-size: 13px;
    font-weight: 700;
  }

  .setting-desc {
    font-size: 12px;
    color: $text-secondary;
    line-height: 1.6;
    white-space: pre-line;
  }

  :deep(.el-input__wrapper),
  :deep(.el-select .el-input__wrapper) {
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(51, 65, 85, 0.5);
    border-radius: 8px;
    box-shadow: none;
    transition: all 0.2s ease;

    &:hover { border-color: rgba(99, 102, 241, 0.4); background: rgba(30, 41, 59, 0.7); }
    &.is-focus { border-color: rgba(99, 102, 241, 0.6); background: rgba(30, 41, 59, 0.7); box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08); }
  }

  :deep(.el-input__inner) {
    color: #f8fafc;
    &::placeholder { color: #94a3b8; }
  }

  :deep(.el-select__caret) { color: #94a3b8; }

  :deep(.el-textarea__inner) {
    background: rgba(30, 41, 59, 0.5);
    border: 1px solid rgba(51, 65, 85, 0.5);
    color: #f8fafc;
    border-radius: 8px;
    transition: all 0.2s ease;

    &:hover { border-color: rgba(99, 102, 241, 0.4); }
    &:focus { border-color: rgba(99, 102, 241, 0.6); box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08); }
  }

  .radio-row { display: flex; gap: 8px; flex-wrap: wrap; }

  .radio-item {
    display: flex;
    align-items: center;
    gap: 4px;

    input[type='radio'] { display: none; }

    .radio-text {
      padding: 5px 16px;
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      font-size: 12px;
      color: $text-secondary;
      transition: all 0.2s ease;
      cursor: pointer;

      &.on {
        border-color: $brand-start;
        color: $brand-start;
        background: rgba(139, 92, 246, 0.1);
      }
    }

    &.disabled {
      opacity: 0.4;
      cursor: not-allowed;
      .radio-text.muted { opacity: 0.5; }
    }
  }
}

.hotspot-tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;

  .el-tag {
    background: rgba(139, 92, 246, 0.12);
    border-color: rgba(139, 92, 246, 0.2);
    color: #c4b5fd;
    border-radius: 16px;
    padding: 0 14px;
    font-weight: 500;
  }
}

.setting-hint {
  font-size: 12px;
  color: $text-muted;
  margin-bottom: 8px;
}

.no-platform-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: $text-muted;
  text-align: center;
  border: 2px dashed rgba(139, 92, 246, 0.12);
  border-radius: 16px;
  margin: 24px 0;

  .hint-icon { opacity: 0.2; margin-bottom: 16px; }

  p { font-size: 15px; margin: 4px 0; font-weight: 500; }

  .hint-sub { font-size: 13px; color: $text-muted; font-weight: 400; }
}

// ========== PHONE PREVIEW PANEL ==========
.phone-panel {
  width: 380px;
  flex-shrink: 0;
  background: linear-gradient(180deg, #0c0c20 0%, #0a0a1a 100%);
  border-left: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(139, 92, 246, 0.1) transparent;
  &::-webkit-scrollbar { width: 4px; }
  &::-webkit-scrollbar-thumb { background: rgba(139, 92, 246, 0.1); border-radius: 2px; }
}

.phone-panel-header {
  padding: 16px 20px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.phone-panel-title {
  font-size: 15px;
  font-weight: 700;
  color: #f8fafc;
}

.phone-preview-area {
  display: flex;
  justify-content: center;
  padding: 20px 4px;
}

.phone-mockup {
  position: relative;
  background: linear-gradient(145deg, #1e1e3a, #14142a);
  border: 2px solid rgba(139, 92, 246, 0.12);
  border-radius: 36px;
  padding: 10px;
  box-shadow:
    0 16px 48px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(139, 92, 246, 0.06),
    0 0 60px rgba(139, 92, 246, 0.06);
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: all 0.3s ease;
  width: 88%;

  &:hover {
    box-shadow:
      0 20px 56px rgba(0, 0, 0, 0.55),
      0 0 0 1px rgba(139, 92, 246, 0.1),
      0 0 80px rgba(139, 92, 246, 0.1);
    transform: translateY(-2px);
  }
}

.phone-notch {
  width: 80px;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  margin-bottom: 8px;
}

.phone-screen {
  width: 100%;
  aspect-ratio: 9 / 16;
  background: #0a0a1a;
  border-radius: 20px;
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
  gap: 10px;
  width: 100%;
  height: 100%;
  color: $text-muted;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 500;

  &:hover {
    color: $brand-start;
    background: rgba($brand-start, 0.03);
    .el-icon { transform: scale(1.1); }
  }

  .el-icon { transition: transform 0.2s ease; }
}

.phone-home-bar {
  width: 48px;
  height: 4px;
  background: linear-gradient(90deg, #8b5cf6, #3b82f6);
  border-radius: 2px;
  margin-top: 8px;
  opacity: 0.5;
}

.phone-panel-actions {
  display: flex;
  gap: 10px;
  padding: 4px 20px 16px;
  .cover-action-btn { flex: 1; }
}

.phone-panel-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 20px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
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
  color: #a78bfa;
  font-weight: 600;
  flex-shrink: 0;
  margin-left: 8px;
}

.cover-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  color: $text-secondary;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
  font-family: inherit;
  line-height: 1;

  .el-icon { flex-shrink: 0; color: $text-muted; transition: all 0.2s ease; }

  &:hover {
    border-color: rgba(139, 92, 246, 0.25);
    background: rgba(139, 92, 246, 0.06);
    color: $text-primary;
    .el-icon { color: $brand-start; }
  }

  &:active { transform: scale(0.97); }

  &.primary {
    border-color: rgba(139, 92, 246, 0.2);
    background: rgba(139, 92, 246, 0.08);
    color: #c4b5fd;
    .el-icon { color: $brand-start; }

    &:hover {
      border-color: rgba(139, 92, 246, 0.35);
      background: rgba(139, 92, 246, 0.14);
    }
  }
}

.setting-hint {
  font-size: 12px;
  color: $text-muted;
  font-style: italic;
}

.selected-music {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;

  .music-info { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }

  .music-cover {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    object-fit: cover;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }

  .music-name { font-size: 14px; color: #f8fafc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
  .music-author { font-size: 12px; color: $text-secondary; }
}

// ========== Entry Animation ==========
.config-section {
  animation: fadeUp 0.35s ease both;
  &:nth-child(2) { animation-delay: 0.06s; }
  &:nth-child(3) { animation-delay: 0.12s; }
}

@keyframes fadeUp {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
