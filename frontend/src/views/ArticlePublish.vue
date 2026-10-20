<template>
  <div class="article-publish">
    <!-- ========== LEFT SIDEBAR ========== -->
    <AccountSidebar
      :account-groups="articleAccountGroups"
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
        <div class="main-form-col">
          <!-- Top bar -->
          <div class="main-header">
            <div class="header-left">
              <span class="page-title">文章发布</span>
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
              <el-tooltip placement="top">
                <template #content>
                  <b>存草稿箱</b>:推送到公众号草稿箱,排版/封面/设置全部就位,<br />
                  不消耗群发次数,你在公众号后台确认后再群发;<br />
                  <b>直接发表</b>:立即群发,消耗当日群发次数(订阅号每天 1 次),<br />
                  需要用管理员/运营者微信扫码验证,粉丝会收到推送。
                </template>
                <el-icon class="mode-help"><QuestionFilled /></el-icon>
              </el-tooltip>
              <el-radio-group v-model="publishMode" size="small" :disabled="publishing" class="publish-mode-radio">
                <el-radio-button value="draft">存草稿箱</el-radio-button>
                <el-radio-button value="publish">直接发表</el-radio-button>
              </el-radio-group>
              <el-button type="primary" :icon="Promotion" @click="publishAll" :disabled="publishing" class="header-btn header-btn--primary">
                {{ publishing ? '发布中...' : (publishMode === 'publish' ? '一键发表' : '一键发布') }}
              </el-button>
            </div>
          </div>

          <!-- Scrollable content -->
          <div class="main-content">
            <!-- ===== 公共内容(标题 + 正文) ===== -->
            <div class="config-section">
              <div class="section-bar">
                <div class="bar purple"></div>
                <span class="section-label">文章内容</span>
                <span class="hint">所有账号共享</span>
              </div>

              <div class="title-row">
                <el-input
                  v-model="articleTitle"
                  placeholder="请输入文章标题(必填)"
                  maxlength="64"
                  show-word-limit
                  :disabled="publishing"
                  class="title-input"
                />
              </div>

              <div class="editor-row">
                <RichEditor
                  ref="richEditorRef"
                  v-model="articleHtml"
                  placeholder="请输入正文,支持图文混排..."
                  :min-height="380"
                  :disabled="publishing"
                  :uploading="imageUploading"
                  @insert-image="openMaterialLibraryForImage"
                  @upload-image="onUploadImageFiles"
                />
                <div class="editor-meta">
                  <span>正文字数: {{ textLength }}</span>
                  <span v-if="imageCount > 0">· 正文图片: {{ imageCount }} 张(发布时自动转存到平台)</span>
                </div>
              </div>
            </div>

            <!-- Divider -->
            <div class="divider"></div>

            <!-- ===== 封面(视频同款 4 尺寸,公众号自动裁 2.35:1/1:1) ===== -->
            <div class="config-section">
              <div class="section-bar">
                <div class="bar purple"></div>
                <span class="section-label">封面</span>
                <span class="hint">可选。设置了封面则发布时使用,否则自动抓取正文第一张图</span>
              </div>
              <div class="cover-grid">
                <CoverCard
                  label="横版封面"
                  :ratios="['4:3', '16:9']"
                  v-model:active-ratio="coverLandscapeActiveRatio"
                  :model-value="coverLandscapeActiveCover"
                  @update:modelValue="onLandscapeCoverChange"
                  @edit="openCoverEditor('landscape')"
                />
                <CoverCard
                  label="竖版封面"
                  :ratios="['3:4', '9:16']"
                  v-model:active-ratio="coverPortraitActiveRatio"
                  :model-value="coverPortraitActiveCover"
                  @update:modelValue="onPortraitCoverChange"
                  @edit="openCoverEditor('portrait')"
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

              <WeixinGzhArticlePanel
                ref="weixinGzhPanelRef"
                :account-id="selectedPlatform === 'weixin_gzh' ? selectedAccountId : null"
                :disabled="publishing"
                v-show="selectedPlatform === 'weixin_gzh'"
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
          </div>
        </div>

        <!-- Right: Article preview panel -->
        <div class="phone-panel">
          <div class="phone-panel-header">
            <span class="phone-panel-title">文章预览</span>
          </div>
          <div class="phone-preview-area">
            <div class="phone-mockup">
              <div class="phone-notch"></div>
              <div class="phone-screen article-screen">
                <div v-if="articleTitle || articleHtml" class="article-preview">
                  <h1 class="preview-title">{{ articleTitle || '无标题' }}</h1>
                  <div v-if="previewAuthor" class="preview-author">{{ previewAuthor }}</div>
                  <div class="preview-body" v-html="previewHtml"></div>
                </div>
                <div v-else class="phone-empty">
                  <el-icon :size="28"><Document /></el-icon>
                  <span>输入标题与正文后预览</span>
                </div>
              </div>
              <div class="phone-home-bar"></div>
            </div>
          </div>
        </div>
      </div><!-- /main-body -->
    </main>

    <!-- ========== DIALOGS ========== -->
    <AccountSelectDialog
      v-model="accountDialogVisible"
      :platforms="ARTICLE_PLATFORMS"
      :publish-account-ids="publishAccountIds"
      @confirm="onAccountConfirm"
    />

    <MaterialSelectDialog
      ref="materialSelectDialogRef"
      filter-type="image"
      @select="onMaterialSelected"
    />

    <BatchPublishDialog
      v-model="batchPublishDialogVisible"
      :progress="publishProgress"
      :results="publishResults"
      :current-account="currentPublishingAccount"
      @cancel="cancelBatch"
    />

    <PrePublishCheckDialog
      ref="prePublishCheckRef"
      v-model="prePublishCheckVisible"
    />

    <CoverEditorDialog
      ref="coverEditorRef"
      :cover-primary="editorSource.coverPrimary"
      :cover-secondary="editorSource.coverSecondary"
      @cover-saved="onCoverSaved"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import {
  Document, Promotion, UserFilled, QuestionFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { articlePublishApi } from '@/api/articlePublish'
import { accountApi } from '@/api/account'
import { getFileUrl } from '@/utils/storage'
import { platformList, getPlatformByKey } from '@/config/platforms'

import AccountSidebar from '@/components/AccountSidebar.vue'
import AccountSelectDialog from '@/components/AccountSelectDialog.vue'
import BatchPublishDialog from '@/components/BatchPublishDialog.vue'
import MaterialSelectDialog from '@/components/MaterialSelectDialog.vue'
import PrePublishCheckDialog from '@/components/PrePublishCheckDialog.vue'
import RichEditor from '@/components/article/RichEditor.vue'
import CoverCard from '@/components/CoverCard.vue'
import CoverEditorDialog from '@/components/CoverEditorDialog.vue'
import WeixinGzhArticlePanel from '@/components/weixin_gzh/ArticlePublishPanel.vue'
import { useAutoSave } from '@/composables/useAutoSave'

// ========== Stores & Config ==========
const accountStore = useAccountStore()
const appStore = useAppStore()
appStore.loadAccountCheckMode()
const route = useRoute()

const ARTICLE_PLATFORM_KEYS = ['weixin_gzh']
const ARTICLE_PLATFORMS = platformList.filter(p => ARTICLE_PLATFORM_KEYS.includes(p.key))

// ========== Left Sidebar State ==========
const expandedGroups = ref(new Set())
const selectedPlatform = ref(null)
const selectedAccountId = ref(null)

const articleAccountGroups = computed(() => {
  return ARTICLE_PLATFORMS.map(p => ({
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
  for (const group of articleAccountGroups.value) count += group.accounts.length
  return count
})

const currentPlatformConfig = computed(() =>
  selectedPlatform.value ? getPlatformByKey(selectedPlatform.value) : null
)

// ========== Article Content ==========
const articleTitle = ref('')
const articleHtml = ref('')
const richEditorRef = ref(null)

// 字数统计: 从 articleHtml 派生(去标签/实体/空白)。不能调 RichEditor 的
// DOM 方法 —— computed 无法追踪 DOM 变化,会永远停在初始值 0(2026-10-20 实测)
const textLength = computed(() => {
  const text = (articleHtml.value || '')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/gi, '')
    .replace(/&[a-z]+;/gi, ' ')
  return text.replace(/\s/g, '').length
})
const imageCount = computed(() => (articleHtml.value.match(/<img\s/g) || []).length)

// 预览:正文图片用 getFileUrl 兜底相对路径
const previewHtml = computed(() => {
  if (!articleHtml.value) return ''
  return articleHtml.value.replace(
    /src="((?!https?:|data:)[^"]+)"/g,
    (m, url) => `src="${getFileUrl(url)}"`
  )
})

const previewAuthor = computed(() => {
  const panel = weixinGzhPanelRef.value
  return panel?.form?.articleAuthor || ''
})

// ========== 封面(视频同款 4 尺寸: 横 4:3/16:9 + 竖 3:4/9:16) ==========
const coverLandscape = ref(null)      // 横版主 4:3
const coverPortrait = ref(null)       // 竖版主 3:4
const coverLandscape169 = ref(null)   // 横版次 16:9
const coverPortrait916 = ref(null)    // 竖版次 9:16
const coverLandscapeActiveRatio = ref('4:3')
const coverPortraitActiveRatio = ref('3:4')
const coverEditorRef = ref(null)
const coverEditOrientation = ref('landscape')

const coverLandscapeActiveCover = computed(() => {
  const t = { landscape: coverLandscape.value, landscape169: coverLandscape169.value }
  return coverLandscapeActiveRatio.value === '16:9' ? t.landscape169 : t.landscape
})
const coverPortraitActiveCover = computed(() => {
  const t = { portrait: coverPortrait.value, portrait916: coverPortrait916.value }
  return coverPortraitActiveRatio.value === '9:16' ? t.portrait916 : t.portrait
})

function onLandscapeCoverChange(v) {
  if (coverLandscapeActiveRatio.value === '16:9') coverLandscape169.value = v
  else coverLandscape.value = v
  hasChanges.value = true
}

function onPortraitCoverChange(v) {
  if (coverPortraitActiveRatio.value === '9:16') coverPortrait916.value = v
  else coverPortrait.value = v
  hasChanges.value = true
}

const editorSource = computed(() => {
  const isLandscape = coverEditOrientation.value === 'landscape'
  return isLandscape
    ? { coverPrimary: coverLandscape.value, coverSecondary: coverLandscape169.value }
    : { coverPrimary: coverPortrait.value, coverSecondary: coverPortrait916.value }
})

function openCoverEditor(orientation) {
  coverEditOrientation.value = orientation
  coverEditorRef.value?.open(orientation)
}

function onCoverSaved({ orientation, ratio, cover }) {
  const isLandscape = orientation === 'landscape'
  const t = {
    l: coverLandscape.value, l169: coverLandscape169.value,
    p: coverPortrait.value, p916: coverPortrait916.value,
  }
  if (isLandscape) {
    if (ratio === '4:3') coverLandscape.value = cover
    else if (ratio === '16:9') coverLandscape169.value = cover
  } else {
    if (ratio === '3:4') coverPortrait.value = cover
    else if (ratio === '9:16') coverPortrait916.value = cover
  }
  hasChanges.value = true
}

/** 发布用封面 stored_path: 横版 16:9 → 4:3 → 竖版 3:4 → 9:16,无则 null */
const publishCoverStoredPath = computed(() => {
  const first = (c) => c?.stored_path || c?.path || ''
  return (
    first(coverLandscape169.value)
    || first(coverLandscape.value)
    || first(coverPortrait.value)
    || first(coverPortrait916.value)
    || null
  )
})

// ========== Publish Mode ==========
// draft = 推送到公众号草稿箱(默认,安全,群发由用户在后台确认);
// publish = 直接群发(消耗当日群发次数,需管理员扫码验证)
const publishMode = ref('draft')

// ========== Auto-save ==========
const currentDraftId = ref(null)
const { hasChanges, startAutoSaveTimer } = useAutoSave(() => saveDraft())

// ========== Channel Panel Refs & Helpers ==========
const weixinGzhPanelRef = ref(null)

function getPanel(key) {
  const map = { weixin_gzh: weixinGzhPanelRef }
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
  const panel = getPanel('weixin_gzh')
  return !!(panel && panel.hasAccountOverride(accountId))
}

// ========== Sidebar Methods ==========
const publishAccountIds = reactive(new Set())

function toggleGroup(key) {
  if (expandedGroups.value.has(key)) {
    expandedGroups.value.delete(key)
  } else {
    expandedGroups.value.add(key)
  }
}

function removePublishAccount(id) {
  publishAccountIds.delete(id)
  hasChanges.value = true
}

function selectAccount(account, group) {
  selectedPlatform.value = group.key
  selectedAccountId.value = account.id
  if (publishAccountIds.has(account.id)) {
    publishAccountIds.delete(account.id)
  } else {
    publishAccountIds.add(account.id)
    expandedGroups.value.add(group.key)
  }
  hasChanges.value = true
}

// ========== Account Dialog ==========
const accountDialogVisible = ref(false)

function onAccountConfirm(ids) {
  ids.forEach(id => publishAccountIds.add(id))
  hasChanges.value = true
}

// ========== Image Insert(正文插图) ==========
const materialSelectDialogRef = ref(null)
const imageUploading = ref(false)

function openMaterialLibraryForImage() {
  materialSelectDialogRef.value?.open()
}

function onMaterialSelected(material) {
  const url = material.stored_path || material.path || ''
  if (!url) return
  richEditorRef.value?.insertImage(getFileUrl(url), material.original_filename || '配图')
  hasChanges.value = true
}

/** 本地上传: 选完自动传到素材库,再逐张插入正文光标处 */
async function onUploadImageFiles(files) {
  if (imageUploading.value) return
  imageUploading.value = true
  let okCount = 0
  for (const file of files) {
    try {
      const resp = await articlePublishApi.uploadImage(file)
      if (resp.code === 200 && resp.data?.stored_path) {
        richEditorRef.value?.insertImage(
          getFileUrl(resp.data.stored_path),
          resp.data.original_filename || file.name,
        )
        okCount++
      } else {
        ElMessage.error(`${file.name} 上传失败`)
      }
    } catch (e) {
      ElMessage.error(`${file.name} 上传失败：${e.message || e}`)
    }
  }
  imageUploading.value = false
  if (okCount > 0) {
    hasChanges.value = true
    ElMessage.success(`已插入 ${okCount} 张图片`)
  }
}

// ========== Publish Methods ==========
async function saveDraft() {
  if (!articleTitle.value.trim() && !articleHtml.value.trim()) {
    ElMessage.warning('标题和正文都为空,无需保存')
    return
  }
  try {
    const panel = getPanel('weixin_gzh')
    const allPlatformConfigs = {}
    const panelAccountOverrides = {}
    if (panel) {
      const configs = panel.getConfigs()
      allPlatformConfigs.weixin_gzh = configs.platformConfig
      Object.assign(panelAccountOverrides, configs.accountOverrides)
    }

    const draftData = {
      commonConfig: {
        articleTitle: articleTitle.value,
        articleHtml: articleHtml.value,
        coverLandscape: coverLandscape.value,
        coverPortrait: coverPortrait.value,
        coverLandscape169: coverLandscape169.value,
        coverPortrait916: coverPortrait916.value,
      },
      platformConfigs: allPlatformConfigs,
      panelAccountOverrides,
      publishAccountIds: [...publishAccountIds],
      selectedPlatform: selectedPlatform.value,
      selectedAccountId: selectedAccountId.value,
      expandedGroups: [...expandedGroups.value],
    }

    if (currentDraftId.value) {
      // 更新当前草稿(POST /drafts 会忽略 id 永远新建,必须走 PUT)
      await articlePublishApi.updateDraft(currentDraftId.value, draftData)
      ElMessage.success('草稿已更新')
    } else {
      const resp = await articlePublishApi.saveDraft({ draft_data: draftData })
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
  if (!articleTitle.value.trim()) {
    ElMessage.error('请填写文章标题')
    return
  }
  if (!articleHtml.value.trim() || richEditorRef.value?.isEmpty()) {
    ElMessage.error('请填写文章正文')
    return
  }
  if (publishAccountIds.size === 0) {
    ElMessage.error('请先添加发布账号')
    return
  }

  // panel 校验(摘要长度/链接格式)
  for (const group of articleAccountGroups.value) {
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

  // Cookie 预检(与图集一致)
  if (appStore.accountCheckMode === 'pre-publish' && publishAccountIds.size > 0 && prePublishCheckRef.value) {
    const accountsToCheck = accountStore.accounts.filter(a => publishAccountIds.has(a.id))
    if (accountsToCheck.length > 0) {
      const allValid = await prePublishCheckRef.value.open(accountsToCheck)
      if (!allValid) return
    }
  }

  // 直接发表 = 真实群发(不可逆),二次确认防误触
  if (publishMode.value === 'publish') {
    try {
      await ElMessageBox.confirm(
        `将向 ${publishAccountIds.size} 个公众号账号直接群发《${articleTitle.value.trim()}》，` +
        '消耗当日群发次数且不可撤回，发表过程中需用管理员/运营者微信扫码验证。确认发表？',
        '确认直接发表',
        { confirmButtonText: '确认发表', cancelButtonText: '取消', type: 'warning' },
      )
    } catch {
      return
    }
  }

  publishing.value = true
  publishProgress.value = 0
  publishResults.value = []
  isCancelled.value = false
  currentPublishingAccount.value = ''
  batchPublishDialogVisible.value = true

  const batchId = (crypto.randomUUID && crypto.randomUUID()) || (Date.now().toString(36) + '-' + Math.random().toString(36).slice(2))
  const publishExtra = {
    batchId,
    dryRun: false,
    // draft = 保存到公众号草稿箱;publish = 直接群发(需扫码验证)
    isDraft: publishMode.value !== 'publish',
    // 显式封面(横 16:9 → 横 4:3 → 竖 3:4 → 竖 9:16),空则自动抓正文首图
    coverStoredPath: publishCoverStoredPath.value,
  }

  const allTasks = []
  for (const group of articleAccountGroups.value) {
    if (group.accounts.length === 0) continue
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      allTasks.push({ account, groupKey: group.key })
    }
  }

  if (allTasks.length === 0) {
    ElMessage.warning('没有可发布的账号')
    publishing.value = false
    batchPublishDialogVisible.value = false
    return
  }

  // 文章内容为公共数据(标题/正文所有账号一致)
  const commonData = {
    articleTitle: articleTitle.value.trim(),
    articleHtml: articleHtml.value,
  }

  for (let i = 0; i < allTasks.length; i++) {
    if (isCancelled.value) {
      publishResults.value.push({ label: allTasks[i].account.name, status: 'cancelled', message: '已取消' })
      continue
    }
    const { account, groupKey } = allTasks[i]
    currentPublishingAccount.value = account.name
    publishProgress.value = Math.floor((i / allTasks.length) * 100)

    const panel = getPanel(groupKey)
    if (panel) {
      try {
        await panel.publish(account.id, account.name, commonData, publishExtra)
      } catch (e) {
        publishResults.value.push({ label: account.name, status: 'fail', message: e.message || '发布失败' })
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
    ElMessage.success(
      publishMode.value === 'publish'
        ? '全部发表成功（如平台要求扫码，已由你完成验证）'
        : '已保存到公众号草稿箱，可在公众号后台确认后群发'
    )
    setTimeout(() => { batchPublishDialogVisible.value = false }, 1500)
  }
}

const publishing = ref(false)
const publishProgress = ref(0)
const publishResults = ref([])
const currentPublishingAccount = ref('')
const isCancelled = ref(false)
const batchPublishDialogVisible = ref(false)
const prePublishCheckRef = ref(null)
const prePublishCheckVisible = ref(false)

function cancelBatch() {
  isCancelled.value = true
  ElMessage.info('正在取消发布...')
}

// ========== Load Draft ==========
async function loadDraft(draftId) {
  try {
    const resp = await articlePublishApi.getDraft(draftId)
    if (resp.code !== 200 || !resp.data) return
    // 后端 get_draft 已把 draft_data 解析成对象;兼容历史字符串形态
    const dd = typeof resp.data.draft_data === 'string'
      ? JSON.parse(resp.data.draft_data || '{}')
      : (resp.data.draft_data || {})
    const common = dd.commonConfig || {}
    articleTitle.value = common.articleTitle || ''
    articleHtml.value = common.articleHtml || ''
    coverLandscape.value = common.coverLandscape || null
    coverPortrait.value = common.coverPortrait || null
    coverLandscape169.value = common.coverLandscape169 || null
    coverPortrait916.value = common.coverPortrait916 || null
    currentDraftId.value = Number(draftId)

    const panel = getPanel('weixin_gzh')
    if (panel && dd.platformConfigs?.weixin_gzh) {
      panel.restoreConfigs(dd.platformConfigs.weixin_gzh, dd.panelAccountOverrides || {})
    }

    ;(dd.publishAccountIds || []).forEach(id => publishAccountIds.add(id))
    if (dd.selectedPlatform) selectedPlatform.value = dd.selectedPlatform
    if (dd.selectedAccountId) selectedAccountId.value = dd.selectedAccountId
    ;(dd.expandedGroups || []).forEach(k => expandedGroups.value.add(k))
    ElMessage.success('草稿已载入')
  } catch (e) {
    console.error('载入草稿失败:', e)
    ElMessage.error('载入草稿失败')
  }
}

// ========== Init ==========
onMounted(async () => {
  // 账号列表是 store 内存态: 从草稿箱直接跳转/刷新时为空,必须先拉取,
  // 否则左侧账号树为空、草稿的 publishAccountIds 无法回显(2026-10-20 实测)
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
  accountStore.loadTags()

  const firstGroup = articleAccountGroups.value.find(g => g.accounts.length > 0)
  if (firstGroup) {
    expandedGroups.value.add(firstGroup.key)
    if (!selectedPlatform.value) selectedPlatform.value = firstGroup.key
  }
  // 从草稿箱跳转载入(账号树就绪后再恢复,勾选状态才能匹配渲染)
  if (route.query.draft_id) {
    await loadDraft(route.query.draft_id)
  }
})

watch([articleTitle, articleHtml], () => {
  hasChanges.value = true
})
startAutoSaveTimer()
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.article-publish {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.publish-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-body {
  display: flex;
  gap: 16px;
  padding: 16px;
  overflow: hidden;
  flex: 1;
}

.main-form-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;

  .header-left {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .page-title {
    font-size: 18px;
    font-weight: 600;
    color: #303133;
  }

  .platform-tag {
    font-size: 12px;
    padding: 2px 10px;
    border-radius: 10px;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .publish-mode-radio {
    margin-right: 4px;

    :deep(.el-radio-button__inner) {
      padding: 5px 12px;
    }
  }

  .mode-help {
    color: #909399;
    cursor: help;
    margin-right: 6px;
  }
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.config-section {
  margin-bottom: 8px;
}

.section-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;

  .bar {
    width: 4px;
    height: 16px;
    border-radius: 2px;
    background: #409eff;

    &.purple {
      background: #7c6af2;
    }
  }

  .section-label {
    font-size: 14px;
    font-weight: 600;
    color: #303133;
  }

  .hint {
    font-size: 12px;
    color: #909399;
  }
}

.title-row {
  margin-bottom: 12px;

  .title-input {
    :deep(.el-input__inner) {
      font-size: 16px;
      font-weight: 600;
    }
  }
}

.editor-row {
  .editor-meta {
    margin-top: 8px;
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: #909399;
  }
}

// ----- Cover Section(视频发布同款两列封面网格) -----
.cover-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: stretch;
}

.divider {
  height: 1px;
  background: #ebeef5;
  margin: 16px 0;
}

.no-platform-hint {
  text-align: center;
  padding: 48px 0;
  color: #909399;

  .hint-icon {
    margin-bottom: 12px;
  }

  .hint-sub {
    font-size: 12px;
    margin-top: 4px;
  }
}

// ===== 右侧预览 =====
.phone-panel {
  width: 340px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fafbfc;
  overflow: hidden;
}

.phone-panel-header {
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;

  .phone-panel-title {
    font-size: 14px;
    font-weight: 600;
    color: #303133;
  }
}

.phone-preview-area {
  flex: 1;
  overflow: hidden;
  padding: 16px;
  display: flex;
  justify-content: center;
}

.phone-mockup {
  width: 300px;
  height: 100%;
  background: #fff;
  border-radius: 24px;
  border: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.phone-notch {
  height: 20px;
  background: #f5f7fa;
}

.phone-screen {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
}

.article-preview {
  .preview-title {
    font-size: 19px;
    font-weight: 700;
    line-height: 1.4;
    color: #1a1a1a;
    margin: 0 0 10px;
  }

  .preview-author {
    font-size: 12px;
    color: #909399;
    margin-bottom: 14px;
  }

  .preview-body {
    font-size: 15px;
    line-height: 1.85;
    color: #333;
    word-break: break-word;

    :deep(img) {
      max-width: 100%;
      border-radius: 4px;
    }

    :deep(blockquote) {
      margin: 8px 0;
      padding: 6px 12px;
      border-left: 3px solid #dcdfe6;
      background: #f7f8fa;
      color: #606266;
    }

    :deep(h2), :deep(h3) {
      font-weight: 700;
    }
  }
}

.phone-empty {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #c0c4cc;
  font-size: 13px;
}

.phone-home-bar {
  height: 16px;
  background: #f5f7fa;
}
</style>
