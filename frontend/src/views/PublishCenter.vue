<template>
  <div class="publish-center">
    <!-- ========== LEFT SIDEBAR ========== -->
    <AccountSidebar
      :mode="'edit'"
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
          <el-button :icon="Document" @click="saveDraft" class="header-btn">
            {{ currentDraftId ? '更新草稿' : '保存草稿' }}
          </el-button>
          <el-button :icon="MagicStick" @click="oneClickDialogOpen = true" class="header-btn">
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
                {{ getAccountName(selectedAccountId) }} 账号个性化
              </el-checkbox>
            </template>
          </div>

          <!-- Cover Section -->
          <div class="media-section cover-section">
            <div class="section-label">封面</div>
            <div class="cover-grid">
              <CoverCard
                label="竖版封面"
                :ratio-label="appStore.portraitRatio"
                v-model="currentEditTarget.coverPortrait"
                :has-video="!!(currentEditTarget.videoPortrait || currentEditTarget.videoLandscape)"
                @edit="openCoverEditor('portrait')"
                @open-library="selectFromLibrary('cover', 'portrait')"
              />
              <CoverCard
                label="横版封面"
                :ratio-label="appStore.landscapeRatio"
                v-model="currentEditTarget.coverLandscape"
                :has-video="!!(currentEditTarget.videoPortrait || currentEditTarget.videoLandscape)"
                @edit="openCoverEditor('landscape')"
                @open-library="selectFromLibrary('cover', 'landscape')"
              />
            </div>
          </div>

          <CoverEditorDialog
            ref="coverEditorRef"
            :video-landscape="editorSource.videoLandscape"
            :video-portrait="editorSource.videoPortrait"
            :cover-landscape="editorSource.coverLandscape"
            :cover-portrait="editorSource.coverPortrait"
            :portrait-ratio="appStore.portraitRatio"
            :landscape-ratio="appStore.landscapeRatio"
            @update:cover-landscape="onEditorUpdate({coverLandscape: $event})"
            @update:cover-portrait="onEditorUpdate({coverPortrait: $event})"
          />
        </div>

        <!-- Divider -->
        <div class="divider"></div>

        <!-- ===== PLATFORM-SPECIFIC SETTINGS ===== -->
        <div v-if="currentPlatformConfig && publishAccountIds.size > 0" class="config-section">
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

          <!-- 视频格式 + 标签 各占50% -->
          <div class="settings-grid" style="grid-template-columns: 1fr 1fr;">
            <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
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
                    :style="form.videoFormat === opt.value ? { borderColor: currentPlatformConfig.color, background: currentPlatformConfig.color, color: '#fff' } : {}"
                  >{{ opt.label }}</span>
                </label>
              </div>
              <div v-if="!commonConfig.videoLandscape && !commonConfig.videoPortrait" class="setting-desc" style="font-size: 12px;">
                请先上传视频
              </div>
            </div>

            <!-- 通用标签输入 -->
            <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
              <div class="setting-label" :style="{ color: currentPlatformConfig.color }">标签</div>
              <div class="setting-hint">{{ selectedPlatform === 'douyin' ? '官方活动 + 标签最多 5 个，按回车确认' : '输入标签内容，按回车确认' }}</div>
              <el-input
                v-model="tagInput"
                placeholder="输入标签内容，按回车添加"
                @keyup.enter="addTag"
                clearable
              />
              <div v-if="form.tags && form.tags.length > 0" class="tags-list">
                <el-tag
                  v-for="(tag, index) in form.tags"
                  :key="index"
                  closable
                  @close="removeTag(index)"
                  size="small"
                  :disable-transitions="false"
                >#{{ tag }}</el-tag>
              </div>
            </div>
          </div>

          <!-- 平台特有配置（抖音专属卡片 + settingsFields 合并到同一网格） -->
          <div class="settings-grid">
            <!-- 抖音专属卡片 -->
            <template v-if="selectedPlatform === 'douyin'">
              <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
                <div class="setting-label" :style="{ color: currentPlatformConfig.color }">官方活动</div>
                <DouyinActivitySelect :account-id="selectedAccountId" v-model="form.activityId" @change="handleDouyinActivityChange" />
              </div>

              <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
                <div class="setting-label" :style="{ color: currentPlatformConfig.color }">关联热点</div>
                <DouyinHotspotSelect v-model="form.hotspotId" :data="form.hotspotData" @change="handleDouyinHotspotChange" />
              </div>

              <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
                <div class="setting-label" :style="{ color: currentPlatformConfig.color }">添加标签</div>
                <DouyinTagSelect :account-id="selectedAccountId" v-model="form.selectedTag" @change="handleDouyinTagSelect" />
              </div>

              <div v-if="selectedAccountId" class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
                <div class="setting-label" :style="{ color: currentPlatformConfig.color }">添加合集</div>
                <DouyinMixSelect :account-id="selectedAccountId" v-model="form.mixId" :data="form.mixData" @change="handleDouyinMixChange" />
              </div>
            </template>

            <!-- settingsFields（排除已在通用字段渲染的） -->
            <template v-for="field in currentPlatformConfig.settingsFields" :key="field.key">
              <template v-if="field.key !== 'title' && field.key !== 'description' && field.key !== 'videoFormat'">
                <div
                  v-if="!field.visibleWhen || form[field.visibleWhen.key] === field.visibleWhen.value"
                  class="setting-card"
                  :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }"
                >
                  <div class="setting-label" :style="{ color: currentPlatformConfig.color }">
                    <span v-if="field.required" style="color: #f56c6c; margin-right: 2px;">*</span>
                    {{ field.label }}
                  </div>
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
                    :disabled-date="field.disabledDate"
                    :disabled-hours="field.disabledHours"
                    :disabled-minutes="field.disabledMinutes"
                    value-format="YYYY-MM-DD HH:mm:ss"
                    size="small"
                    class="cursor-pointer"
                  />
                  <el-cascader
                    v-else-if="field.type === 'cascader'"
                    v-model="form[field.key]"
                    :options="field.options || []"
                    :placeholder="field.placeholder"
                    :props="field.props || { expandTrigger: 'hover' }"
                    size="small"
                    clearable
                    filterable
                    class="cursor-pointer weibo-cascader"
                  />
                  <AlipayCompilationSelect
                    v-else-if="field.type === 'compilationSelect'"
                    :account-id="selectedAccountId"
                    :platform="selectedPlatform === 'toutiao' ? 'toutiao' : 'alipay'"
                    v-model="form[field.key]"
                    @change="(val) => handleAlipayCompilationChange(field.key, val)"
                  />
                </div>
              </template>
            </template>
          </div>
        </div>

        <!-- No account selected hint -->
        <div v-else-if="publishAccountIds.size === 0" class="no-platform-hint">
          <div class="hint-icon">
            <el-icon :size="48"><UserFilled /></el-icon>
          </div>
          <p>请先在左侧账号设置</p>
          <p class="hint-sub">选择账号后才能配置对应渠道的发布设置</p>
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

    <!-- Video Upload Dialog -->
    <MaterialUploader
      v-model="videoUploadDialogVisible"
      accept="video/*"
      :max-size="null"
      :multiple="false"
      :title="'上传' + (videoUploadTarget === 'portrait' ? '竖版' : '横版') + '视频'"
      tip="支持 MP4、AVI、MKV 等视频格式，不限大小"
      @uploaded="onVideoUploaded"
    />

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

    <!-- Pre-publish Cookie Check Dialog -->
    <PrePublishCheckDialog
      ref="prePublishCheckRef"
      v-model="prePublishCheckVisible"
    />

    <OneClickFillDialog
      v-model="oneClickDialogOpen"
      type="video"
      @pick="handleOneClickFill"
    />

    <BatchSetDialog
      v-model="batchSetDialogOpen"
      :platforms="batchSetPlatforms"
      @apply="onBatchSetApply"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch, onMounted } from 'vue'
import { Upload, Picture, VideoCameraFilled, Delete, Document, WarningFilled, MagicStick, Setting, Promotion, UserFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
import { http } from '@/utils/request'
import { accountApi } from '@/api/account'
import { platformList, getPlatformByKey, platformKeyToId, platformNameToKey } from '@/config/platforms'
import { validateVideoForPlatform } from '@/config/videoLimits'

import AccountSidebar from '@/components/AccountSidebar.vue'
import AccountSelectDialog from '@/components/AccountSelectDialog.vue'
import BatchPublishDialog from '@/components/BatchPublishDialog.vue'
import BatchSetDialog from '@/components/BatchSetDialog.vue'
import CoverCard from '@/components/CoverCard.vue'
import CoverEditorDialog from '@/components/CoverEditorDialog.vue'
import MaterialSelectDialog from '@/components/MaterialSelectDialog.vue'
import MaterialUploader from '@/components/MaterialUploader.vue'
import OneClickFillDialog from '@/components/OneClickFillDialog.vue'
import DouyinActivitySelect from '@/components/douyin/ActivitySelect.vue'
import DouyinHotspotSelect from '@/components/douyin/HotspotSelect.vue'
import DouyinTagSelect from '@/components/douyin/TagSelect.vue'
import DouyinMixSelect from '@/components/douyin/MixSelect.vue'
import AlipayCompilationSelect from '@/components/alipay/CompilationSelect.vue'
import PrePublishCheckDialog from '@/components/PrePublishCheckDialog.vue'
import { useAutoSave } from '@/composables/useAutoSave'
import { useBatchSetApply } from '@/composables/useBatchSetApply'
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
  videoModeTab.value === 'portrait' ? currentEditTarget.value.videoPortrait : currentEditTarget.value.videoLandscape
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
})

// 平台级覆写（spec §3.3）—— 公共区域的媒体字段覆写
const platformOverrides = reactive({})         // { [platformKey]: { coverPortrait, coverLandscape, videoPortrait, videoLandscape } }
const platformChecked = reactive({})           // { [platformKey]: boolean }

// 账号级覆写（accountOverrides 已在下方 line 631 声明）
const accountChecked = reactive({})            // { [accountId]: boolean }

// 当前编辑目标：公共区域 v-model / 编辑器 source/target 的实际绑定对象
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
    ov.coverPortrait || ov.coverLandscape ||
    ov.videoPortrait  || ov.videoLandscape
  )
}

function hasAccountOverrideContent(accountId) {
  const ov = accountOverrides[accountId]
  if (!ov) return false
  return !!(
    ov.coverPortrait || ov.coverLandscape ||
    ov.videoPortrait  || ov.videoLandscape
  )
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
      coverPortrait: null, coverLandscape: null,
      videoPortrait: null, videoLandscape: null,
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
      coverPortrait: null, coverLandscape: null,
      videoPortrait: null, videoLandscape: null,
    }
  }
}

// ========== 4 级优先级合并（spec §3.3） ==========
// accountOv > platformOv > platformDefault > common
function resolveAccountConfig(platformKey, accountId) {
  const accountOv = accountOverrides[accountId] || null
  const platformOv = platformOverrides[platformKey] || null
  const platformDefault = platformConfigs[platformKey] || null
  return mergeConfig(commonConfig, platformDefault, platformOv, accountOv)
}

function mergeConfig(common, platformDefault, platformOv, accountOv) {
  return {
    // 文本字段 4 级合并（账号 > 渠道 > 平台默认），与视频/封面/平台特有字段一致
    title: accountOv?.title ?? platformOv?.title ?? platformDefault?.title ?? '',
    description: accountOv?.description ?? platformOv?.description ?? platformDefault?.description ?? '',
    tags: accountOv?.tags ?? platformOv?.tags ?? platformDefault?.tags ?? [],
    // 视频/封面走 4 级合并 → commonConfig 兜底
    coverLandscape: accountOv?.coverLandscape ?? platformOv?.coverLandscape ?? common.coverLandscape,
    coverPortrait:  accountOv?.coverPortrait  ?? platformOv?.coverPortrait  ?? common.coverPortrait,
    videoLandscape: accountOv?.videoLandscape ?? platformOv?.videoLandscape ?? common.videoLandscape,
    videoPortrait:  accountOv?.videoPortrait  ?? platformOv?.videoPortrait  ?? common.videoPortrait,
    // 平台特有字段走 platformDefault 兜底
    videoFormat: accountOv?.videoFormat ?? platformOv?.videoFormat ?? platformDefault?.videoFormat ?? '',
    enableTimer: accountOv?.enableTimer ?? platformOv?.enableTimer ?? platformDefault?.enableTimer ?? 0,
    scheduleTime: accountOv?.scheduleTime ?? platformOv?.scheduleTime ?? platformDefault?.scheduleTime ?? '',
    aiContent: accountOv?.aiContent ?? platformOv?.aiContent ?? platformDefault?.aiContent ?? '',
    isOriginal: accountOv?.isOriginal ?? platformOv?.isOriginal ?? platformDefault?.isOriginal ?? false,
    // 平台特有字段：4 级合并（账号 > 渠道 > 平台默认），与视频/封面一致
    creationDeclaration: accountOv?.creationDeclaration ?? platformOv?.creationDeclaration ?? platformDefault?.creationDeclaration,
    riskWarning: accountOv?.riskWarning ?? platformOv?.riskWarning ?? platformDefault?.riskWarning,
    enableCashActivity: accountOv?.enableCashActivity ?? platformOv?.enableCashActivity ?? platformDefault?.enableCashActivity,
    supplementaryDeclaration: accountOv?.supplementaryDeclaration ?? platformOv?.supplementaryDeclaration ?? platformDefault?.supplementaryDeclaration,
    audience: accountOv?.audience ?? platformOv?.audience ?? platformDefault?.audience,
    alteredContent: accountOv?.alteredContent ?? platformOv?.alteredContent ?? platformDefault?.alteredContent,
    // 修：zone 字段也走 4 级合并（B 站分区），账号级填的 zone 才能进 publishData
    zone: accountOv?.zone ?? platformOv?.zone ?? platformDefault?.zone ?? '',
    // 平台特有字段 4 级合并（账号 > 渠道 > 平台默认）—— 补回漏的
    // 抖音
    activityId: accountOv?.activityId ?? platformOv?.activityId ?? platformDefault?.activityId ?? [],
    hotspotId: accountOv?.hotspotId ?? platformOv?.hotspotId ?? platformDefault?.hotspotId ?? '',
    hotspotData: accountOv?.hotspotData ?? platformOv?.hotspotData ?? platformDefault?.hotspotData ?? null,
    selectedTag: accountOv?.selectedTag ?? platformOv?.selectedTag ?? platformDefault?.selectedTag ?? null,
    tagType: accountOv?.tagType ?? platformOv?.tagType ?? platformDefault?.tagType ?? '',
    tagValue: accountOv?.tagValue ?? platformOv?.tagValue ?? platformDefault?.tagValue ?? '',
    mixId: accountOv?.mixId ?? platformOv?.mixId ?? platformDefault?.mixId ?? '',
    mixData: accountOv?.mixData ?? platformOv?.mixData ?? platformDefault?.mixData ?? null,
    // B 站
    topic: accountOv?.topic ?? platformOv?.topic ?? platformDefault?.topic ?? '',
    // 视频号
    isDraft: accountOv?.isDraft ?? platformOv?.isDraft ?? platformDefault?.isDraft ?? false,
    location: accountOv?.location ?? platformOv?.location ?? platformDefault?.location ?? '',
    // 平台特有字段 4 级合并（账号 > 渠道 > 平台默认）—— 补回 xiaohongshu 漏的
    collection: accountOv?.collection ?? platformOv?.collection ?? platformDefault?.collection ?? '',
    groupChat: accountOv?.groupChat ?? platformOv?.groupChat ?? platformDefault?.groupChat ?? '',
    // 微博
    videoType: accountOv?.videoType ?? platformOv?.videoType ?? platformDefault?.videoType ?? '',
    weiboCategory: accountOv?.weiboCategory ?? platformOv?.weiboCategory ?? platformDefault?.weiboCategory ?? [],
    contentStatement: accountOv?.contentStatement ?? platformOv?.contentStatement ?? platformDefault?.contentStatement ?? '',
    // 支付宝
    authorStatement: accountOv?.authorStatement ?? platformOv?.authorStatement ?? platformDefault?.authorStatement ?? '',
    compilation: accountOv?.compilation ?? platformOv?.compilation ?? platformDefault?.compilation ?? '',
    compilationData: accountOv?.compilationData ?? platformOv?.compilationData ?? platformDefault?.compilationData ?? null,
    // 今日头条
    enableGenerateImage: accountOv?.enableGenerateImage ?? platformOv?.enableGenerateImage ?? platformDefault?.enableGenerateImage ?? true,
    collection: accountOv?.collection ?? platformOv?.collection ?? platformDefault?.collection ?? '',
    extendLink: accountOv?.extendLink ?? platformOv?.extendLink ?? platformDefault?.extendLink ?? false,
    extendLinkUrl: accountOv?.extendLinkUrl ?? platformOv?.extendLinkUrl ?? platformDefault?.extendLinkUrl ?? '',
  }
}

// ========== Override Section: CoverEditor source/target ==========
// 公共区域的 CoverEditor 永远跟随 currentEditTarget（默认=commonConfig, 勾选时=覆写对象）
const editorSource = computed(() => {
  const t = currentEditTarget.value
  return {
    videoLandscape: t?.videoLandscape,
    videoPortrait:  t?.videoPortrait,
    coverLandscape: t?.coverLandscape,
    coverPortrait:  t?.coverPortrait,
  }
})

function onEditorUpdate({ coverLandscape, coverPortrait }) {
  const t = currentEditTarget.value
  if (coverLandscape) t.coverLandscape = coverLandscape
  if (coverPortrait)  t.coverPortrait  = coverPortrait
}

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
  douyin: { title: '', description: '', tags: [], aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '', activityId: [], hotspotId: '', hotspotData: null, selectedTag: null, tagType: '', tagValue: '', mixId: '', mixData: null },
  xiaohongshu: { title: '', description: '', aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '', tags: [] },
  kuaishou: { title: '', description: '', aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '', tags: [] },
  bilibili: { title: '', description: '', zone: '', tags: [], creationDeclaration: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  channels: { title: '', description: '', isOriginal: false, scheduleTime: '', videoFormat: '', tags: [] },
  baijiahao: { title: '', description: '', isOriginal: false, scheduleTime: '', videoFormat: '', tags: [] },
  tiktok: { title: '', description: '', aiContent: false, isOriginal: false, scheduleTime: '', videoFormat: '', tags: [] },
  youtube: { title: '', description: '', audience: 'not_kids', alteredContent: false, scheduleTime: '', videoFormat: '', tags: [] },
  iqiyi: { title: '', description: '', creationDeclaration: '', riskWarning: '', enableCashActivity: false, scheduleTime: '', videoFormat: '', tags: [] },
  tencent_video: { title: '', description: '', creationDeclaration: [], scheduleTime: '', videoFormat: '', tags: [] },
  weibo: { title: '', description: '', videoType: '', weiboCategory: [], contentStatement: '', tags: [] },
  alipay: { title: '', description: '', authorStatement: '', compilation: '', scheduleTime: '', videoFormat: '', tags: [] },
  toutiao: { title: '', description: '', creationDeclaration: [], enableGenerateImage: true, collection: '', extendLink: false, extendLinkUrl: '', scheduleTime: '', videoFormat: '', tags: [] },
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
      if (field.type === 'cascader' && !Array.isArray(form[field.key])) {
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
    // 用 merge 而不是 replace：保留已上传的视频/封面/图片等媒体字段
    // （这些字段不在 form 里，diff 不会包含它们）
    const existing = accountOverrides[selectedAccountId.value]
    if (Object.keys(diff).length > 0) {
      accountOverrides[selectedAccountId.value] = existing
        ? { ...existing, ...diff }
        : { ...diff }
    }
    // diff 为空时不要 delete！媒体字段可能还在
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

// ========== Tag Input ==========
const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) {
    ElMessage.warning('标签已存在')
    return
  }
  if (selectedPlatform.value === 'douyin') {
    const ac = form.activityId?.length || 0
    const tc = form.tags?.length || 0
    if (ac + tc >= 5) {
      ElMessage.warning('官方活动 + 标签最多 5 个')
      return
    }
  }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) {
  form.tags.splice(index, 1)
}

// ========== Douyin-specific Methods ==========
function handleDouyinActivityChange(activity) {
  if (activity?.challenge?.length > 0) {
    for (const topic of activity.challenge) {
      if (form.tags && !form.tags.includes(topic)) {
        if ((form.activityId?.length || 0) + (form.tags?.length || 0) >= 5) break
        form.tags.push(topic)
      }
    }
  }
}

function handleDouyinHotspotChange(hotspot) {
  if (hotspot) {
    form.hotspotId = hotspot.word
    form.hotspotData = hotspot
  } else {
    form.hotspotId = ''
    form.hotspotData = null
  }
}

function handleDouyinTagSelect(tag) {
  if (tag) {
    form.selectedTag = tag
    const m = { poi: 'location', miniapp: 'miniapp', game: 'gamepad', mark: 'mark', film: 'film' }
    form.tagType = m[tag.type] || ''
    form.tagValue = tag.name || tag.id || ''
    ElMessage.success(`标签已选择: ${tag.name}`)
  } else {
    form.selectedTag = null
    form.tagType = ''
    form.tagValue = ''
  }
}

function handleDouyinMixChange(mix) {
  if (mix) {
    form.mixId = mix.mix_name
    form.mixData = mix
  } else {
    form.mixId = ''
    form.mixData = null
  }
}

// 支付宝合集选择回调:把选中的完整对象存到 form.compilationData 便于回显,
// v-model 已把 compilationId 绑定到 form.compilation
function handleAlipayCompilationChange(fieldKey, comp) {
  if (comp) {
    form.compilationData = comp
  } else {
    form.compilationData = null
  }
}

// ========== Init ==========
const firstGroup = accountGroups.value.find(g => g.accounts.length > 0)
if (firstGroup) {
  expandedGroups.value.add(firstGroup.key)
  selectedPlatform.value = firstGroup.key
}

// ========== Dialog State ==========
const accountDialogVisible = ref(false)
const videoUploadDialogVisible = ref(false)
const videoUploadTarget = ref('landscape')
const materialSelectRef = ref(null)
const materialLibraryMode = ref('video')
const materialLibraryCoverTarget = ref('landscape')
const oneClickDialogOpen = ref(false)
const materialLibraryVideoTarget = ref('landscape')
const batchPublishDialogVisible = ref(false)

// ========== 发布前 Cookie 预检 ==========
const prePublishCheckRef = ref(null)
const prePublishCheckVisible = ref(false)

// ========== 批量设 (Batch Set) ==========
const batchSetDialogOpen = ref(false)
const { applyBatchSet } = useBatchSetApply({
  platformConfigs,
  accountOverrides,
  accountChecked,
  accountStore,
})
// 渠道个性化可见平台列表：过滤掉被拉黑的平台
const visiblePlatformsForCustomize = computed(() =>
  platformList.filter(p => !appStore.isPlatformDisabled(p.key))
)

const batchSetPlatforms = computed(() => {
  return visiblePlatformsForCustomize.value.map(p => {
    const platformAccounts = accountStore.accounts.filter(a => a.platform === p.name)
    const selectedCount = platformAccounts.filter(a => publishAccountIds.has(a.id)).length
    return { key: p.key, name: p.name, logo: p.logo, count: selectedCount }
  })
})
function onBatchSetApply(checkedKeys, payload) {
  applyBatchSet(checkedKeys, payload)
  // 如果当前查看的渠道在批量设范围内,强制刷新 form (watch [selectedPlatform,...] 不会自动触发)
  if (selectedPlatform.value && checkedKeys.includes(selectedPlatform.value)) {
    const merged = getMergedSettings()
    for (const key of Object.keys(merged)) {
      form[key] = merged[key]
    }
    for (const key of Object.keys(form)) {
      if (!(key in merged)) {
        delete form[key]
      }
    }
  }
  ElMessage.success(`已批量设置到 ${checkedKeys.length} 个渠道`)
}

// Batch publish state
const publishing = ref(false)
const publishProgress = ref(0)
const publishResults = ref([])
const currentPublishingAccount = ref('')
const isCancelled = ref(false)

// Selected accounts
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

// ========== Upload Methods ==========

function triggerUploadVideo(target = 'landscape') {
  videoUploadTarget.value = target
  videoUploadDialogVisible.value = true
}

function clearVideo(type) {
  if (type === 'landscape') currentEditTarget.value.videoLandscape = null
  else currentEditTarget.value.videoPortrait = null
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

async function onVideoUploaded(d) {
  const videoData = {
    id: d.id,
    name: d.original_filename,
    url: getFileUrl(d.stored_path),
    stored_path: d.stored_path,
    size: d.file_size,
    type: d.mime_type,
    duration: d.duration ?? 0,
  }
  if (videoUploadTarget.value === 'portrait') {
    currentEditTarget.value.videoPortrait = videoData
  } else {
    currentEditTarget.value.videoLandscape = videoData
  }
  videoUploadDialogVisible.value = false
  ElMessage.success('视频上传成功')
  if (appStore.autoFillTitle) {
    const title = videoData.name.replace(/\.[^.]+$/, '')
    if (selectedAccountId.value && accountChecked[selectedAccountId.value]) {
      // 账号级别：只更新 form.title（form watcher 会把 diff 写到 accountOverrides）
      form.title = title
    } else if (selectedPlatform.value && platformChecked[selectedPlatform.value]) {
      // 渠道级别：只更新当前渠道的 title
      if (platformConfigs[selectedPlatform.value]) {
        platformConfigs[selectedPlatform.value].title = title
        form.title = title
      }
    } else {
      // 公共：同步所有渠道（原逻辑）
      for (const key of Object.keys(platformConfigs)) {
        platformConfigs[key].title = title
      }
      if (selectedPlatform.value && platformConfigs[selectedPlatform.value]) {
        form.title = platformConfigs[selectedPlatform.value].title
      }
    }
  }
  triggerFrameExtraction(videoData, videoUploadTarget.value)
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
  // 公共区域选素材：写入 currentEditTarget（默认=commonConfig, 勾选=覆写对象）
  if (materialLibraryMode.value === 'cover') {
    if (materialLibraryCoverTarget.value === 'portrait') {
      currentEditTarget.value.coverPortrait = material
    } else {
      currentEditTarget.value.coverLandscape = material
    }
    ElMessage.success('封面已设置')
  } else {
    if (materialLibraryVideoTarget.value === 'portrait') {
      currentEditTarget.value.videoPortrait = material
    } else {
      currentEditTarget.value.videoLandscape = material
    }
    ElMessage.success('视频已设置')
    if (appStore.autoFillTitle) {
      const title = material.name.replace(/\.[^.]+$/, '')
      if (selectedAccountId.value && accountChecked[selectedAccountId.value]) {
        // 账号级别：只更新 form.title（form watcher 会写到 accountOverrides）
        form.title = title
      } else if (selectedPlatform.value && platformChecked[selectedPlatform.value]) {
        // 渠道级别：只更新当前渠道
        if (platformConfigs[selectedPlatform.value]) {
          platformConfigs[selectedPlatform.value].title = title
          form.title = title
        }
      } else {
        // 公共：同步所有渠道
        for (const key of Object.keys(platformConfigs)) {
          platformConfigs[key].title = title
        }
        if (selectedPlatform.value && platformConfigs[selectedPlatform.value]) {
          form.title = platformConfigs[selectedPlatform.value].title
        }
      }
    }
    triggerFrameExtraction(material, materialLibraryVideoTarget.value)
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
        videoLandscape: commonConfig.videoLandscape
          ? { id: commonConfig.videoLandscape.id, name: commonConfig.videoLandscape.name, stored_path: commonConfig.videoLandscape.stored_path, url: commonConfig.videoLandscape.url, size: commonConfig.videoLandscape.size, type: commonConfig.videoLandscape.type }
          : null,
        videoPortrait: commonConfig.videoPortrait
          ? { id: commonConfig.videoPortrait.id, name: commonConfig.videoPortrait.name, stored_path: commonConfig.videoPortrait.stored_path, url: commonConfig.videoPortrait.url, size: commonConfig.videoPortrait.size, type: commonConfig.videoPortrait.type }
          : null,
        coverLandscape: commonConfig.coverLandscape
          ? { id: commonConfig.coverLandscape.id, name: commonConfig.coverLandscape.name, stored_path: commonConfig.coverLandscape.stored_path, url: commonConfig.coverLandscape.url, size: commonConfig.coverLandscape.size, type: commonConfig.coverLandscape.type, _fromFrame: commonConfig.coverLandscape._fromFrame }
          : null,
        coverPortrait: commonConfig.coverPortrait
          ? { id: commonConfig.coverPortrait.id, name: commonConfig.coverPortrait.name, stored_path: commonConfig.coverPortrait.stored_path, url: commonConfig.coverPortrait.url, size: commonConfig.coverPortrait.size, type: commonConfig.coverPortrait.type, _fromFrame: commonConfig.coverPortrait._fromFrame }
          : null,
      },
      platformConfigs: JSON.parse(JSON.stringify(platformConfigs)),
      platformOverrides: JSON.parse(JSON.stringify(platformOverrides)),
      accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
      platformChecked: { ...platformChecked },
      accountChecked: { ...accountChecked },
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

    // 兼容旧草稿格式：将 commonConfig.topics 迁移到各平台的 tags
    if (dd.commonConfig?.topics && dd.commonConfig.topics.length > 0) {
      for (const key of Object.keys(platformConfigs)) {
        if (!platformConfigs[key].tags || platformConfigs[key].tags.length === 0) {
          platformConfigs[key].tags = [...dd.commonConfig.topics]
        }
      }
    }

    // 兼容旧草稿格式：bilibili 的 tags 从字符串转数组
    if (dd.platformConfigs?.bilibili && typeof dd.platformConfigs.bilibili.tags === 'string') {
      const str = dd.platformConfigs.bilibili.tags
      platformConfigs.bilibili.tags = str.split(/[,，\s]+/).map(t => t.replace(/^#/, '').trim()).filter(Boolean)
    }

    // 兼容旧草稿格式：为缺少 tags 的平台补充空数组
    for (const key of Object.keys(platformConfigs)) {
      if (!Array.isArray(platformConfigs[key].tags)) {
        platformConfigs[key].tags = []
      }
    }

    // 兼容旧草稿格式：为抖音补充新增字段
    if (dd.platformConfigs?.douyin) {
      const dy = platformConfigs.douyin
      if (!Array.isArray(dy.activityId)) dy.activityId = []
      if (dy.hotspotId === undefined) dy.hotspotId = ''
      if (dy.hotspotData === undefined) dy.hotspotData = null
      if (dy.selectedTag === undefined) dy.selectedTag = null
      if (dy.tagType === undefined) dy.tagType = ''
      if (dy.tagValue === undefined) dy.tagValue = ''
      if (dy.mixId === undefined) dy.mixId = ''
      if (dy.mixData === undefined) dy.mixData = null
    }

    if (dd.accountOverrides) {
      Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
      Object.assign(accountOverrides, dd.accountOverrides)
    }

    if (dd.platformOverrides) {
      Object.keys(platformOverrides).forEach(k => delete platformOverrides[k])
      Object.assign(platformOverrides, dd.platformOverrides)
    }

    if (dd.platformChecked) {
      Object.keys(platformChecked).forEach(k => delete platformChecked[k])
      Object.assign(platformChecked, dd.platformChecked)
    }

    if (dd.accountChecked) {
      Object.keys(accountChecked).forEach(k => delete accountChecked[k])
      Object.assign(accountChecked, dd.accountChecked)
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

    if (dd.selectedAccountId) {
      selectedAccountId.value = dd.selectedAccountId
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

onMounted(async () => {
  // 加载账号列表
  try {
    const res = await accountApi.getAccounts()
    accountStore.setAccounts(res.data)
  } catch (e) {
    console.error('加载账号列表失败:', e)
  }

  // 加载标签列表(确保「选择账号」弹窗内的标签筛选可用)
  accountStore.loadTags()

  // 清理 publishAccountIds 中属于黑名单平台的账号（本地清理，不写后端）
  // Set 是发布页内存状态，重建一个新的 Set 来剔除被拉黑平台的账号
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
    restoreDraft(Number(draftId))
  }
  startAutoSaveTimer()
})

async function publishAll() {
  // 视频校验：扫全部 3 个源（commonConfig / platformOverrides / accountOverrides）
  // 个性化模式下视频可能在 platformOverrides 里，commonConfig 为空是正常的，
  // 只看 commonConfig 会误判为「未上传视频」。
  const hasAnyVideo = (() => {
    if (commonConfig.videoLandscape || commonConfig.videoPortrait) return true
    for (const aid of publishAccountIds) {
      const ov = accountOverrides[aid]
      if (ov && (ov.videoLandscape || ov.videoPortrait)) return true
    }
    for (const pkey of Object.keys(platformOverrides)) {
      const pov = platformOverrides[pkey]
      if (pov && (pov.videoLandscape || pov.videoPortrait)) return true
    }
    return false
  })()
  if (!hasAnyVideo) {
    ElMessage.error('请先上传至少一个视频文件')
    return
  }

  // ===== Collect ALL errors first (collect-all-then-show-one) =====
  const errors = []  // [{ type: '作品声明', accounts: ['账号A(B站)', ...] }, ...]

  // 1. 封面校验（扫 3 个源）
  const hasAnyCover = (() => {
    if (commonConfig.coverLandscape || commonConfig.coverPortrait) return true
    for (const aid of publishAccountIds) {
      const ov = accountOverrides[aid]
      if (ov && (ov.coverLandscape || ov.coverPortrait)) return true
    }
    for (const pkey of Object.keys(platformOverrides)) {
      const pov = platformOverrides[pkey]
      if (pov && (pov.coverLandscape || pov.coverPortrait)) return true
    }
    return false
  })()
  if (!hasAnyCover) {
    errors.push({ type: '封面', accounts: ['所有账号都缺封面，请上传至少一张'] })
  }

  // 2. 作品声明 + 标题 + 视频格式 + 封面 per-account
  const accountsWithoutDeclaration = []
  const accountsWithoutTitle = []
  const accountsWithoutCover = []  // 格式: '账号X(平台Y)' 或 '账号X(平台Y) 缺竖版封面'
  const accountsWithoutVideoFormat = []
  const DECLARATION_PLATFORMS = {
    xiaohongshu: 'aiContent',
    douyin: 'aiContent',
    kuaishou: 'aiContent',
    bilibili: 'creationDeclaration',
    baijiahao: 'creationDeclaration',
    tencent_video: 'creationDeclaration',
    iqiyi: 'creationDeclaration',
    youtube: ['audience', 'alteredContent'],
    tiktok: 'aiContent',
    weibo: 'contentStatement',
    alipay: 'authorStatement',
    // channels 不必填
  }

  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const merged = resolveAccountConfig(group.key, account.id)
      const platformKey = group.key

      // 2a. 作品声明
      const declFields = DECLARATION_PLATFORMS[platformKey]
      if (declFields) {
        const fields = Array.isArray(declFields) ? declFields : [declFields]
        for (const field of fields) {
          const value = merged[field]
          const isEmpty = Array.isArray(value)
            ? value.length === 0
            : (typeof value === 'boolean' ? value === null || value === undefined : (!value && value !== 0))
          if (isEmpty) {
            accountsWithoutDeclaration.push(`${account.name}(${group.name})`)
            break
          }
        }
      }

      // 2b. 标题
      if (!merged.title || !merged.title.trim()) {
        accountsWithoutTitle.push(`${account.name}(${group.name})`)
      }

      // 2c. 视频格式
      if (!merged.videoFormat) {
        accountsWithoutVideoFormat.push(`${account.name}(${group.name})`)
      }

      // 2d. 封面 per-account
      const videoFormat = merged.videoFormat || ''
      if (!merged.coverLandscape && !merged.coverPortrait) {
        accountsWithoutCover.push(`${account.name}(${group.name})`)
      } else if (videoFormat === 'portrait' && !merged.coverPortrait) {
        accountsWithoutCover.push(`${account.name}(${group.name}) 缺竖版封面`)
      } else if (videoFormat === 'landscape' && !merged.coverLandscape) {
        accountsWithoutCover.push(`${account.name}(${group.name}) 缺横版封面`)
      }
    }
  }

  if (accountsWithoutDeclaration.length > 0) errors.push({ type: '作品声明', accounts: accountsWithoutDeclaration })
  if (accountsWithoutTitle.length > 0) errors.push({ type: '标题', accounts: accountsWithoutTitle })
  if (accountsWithoutVideoFormat.length > 0) errors.push({ type: '视频格式', accounts: accountsWithoutVideoFormat })
  if (accountsWithoutCover.length > 0) errors.push({ type: '封面', accounts: accountsWithoutCover })

  // 3. 视频时长/大小校验
  const accountsVideoInvalid = []
  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const merged = resolveAccountConfig(group.key, account.id)
      const platformKey = group.key

      // 取有效视频（按 videoFormat 或兜底）
      const fmt = merged.videoFormat
      let video = null
      if (fmt === 'landscape') video = merged.videoLandscape
      else if (fmt === 'portrait') video = merged.videoPortrait
      else video = merged.videoLandscape || merged.videoPortrait

      if (!video || !video.duration || video.duration === 0) {
        // 未上传视频的账号：跳过（必填标题会先拦住）
        continue
      }

      const result = validateVideoForPlatform(platformKey, video.duration, video.size || 0)
      if (!result.ok) {
        accountsVideoInvalid.push(`${account.name}(${group.name}): ${result.error}`)
      }
    }
  }
  if (accountsVideoInvalid.length > 0) {
    errors.push({ type: '视频校验', accounts: accountsVideoInvalid })
  }

  if (errors.length > 0) {
    const maxShow = 3
    const body = errors.map(e => {
      const list = e.accounts
      const shown = list.length > maxShow
        ? list.slice(0, maxShow).join('、') + ` 等 ${list.length} 个账号`
        : list.join('、')
      return `<div style="margin-bottom:6px;"><b style="color:#f56c6c">未设置${e.type}：</b>${shown}</div>`
    }).join('')
    ElNotification({
      title: '发布前检查未通过',
      message: body,
      type: 'error',
      dangerouslyUseHTMLString: true,
      duration: 5000,
    })
    return
  }

  // 校验抖音平台官方活动 + 标签数量
  if (selectedPlatform.value === 'douyin') {
    const ac = form.activityId?.length || 0
    const tc = form.tags?.length || 0
    if (ac + tc > 5) {
      ElMessage.error(`官方活动(${ac}) + 标签(${tc}) 超过 5 个`)
      return
    }
  }

  // ===== 表单校验全部通过后，进行 Cookie 预检 =====
  if (publishAccountIds.size > 0 && prePublishCheckRef.value) {
    const accountsToCheck = accountStore.accounts.filter(a => publishAccountIds.has(a.id))
    if (accountsToCheck.length > 0) {
      const allValid = await prePublishCheckRef.value.open(accountsToCheck)
      if (!allValid) return  // 用户取消或未全部修复
    }
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
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      // 4 级优先级合并：accountOv > platformOv > platformDefault > common
      const merged = resolveAccountConfig(group.key, account.id)
      // 修：平台特有字段都从 merged.xxx 取（mergeConfig 已 4 级合并）。
      // 之前用 platformSettings.xxx（只读渠道默认），账号级填的值进不来。
      const pSettings = platformConfigs[group.key] || {}
      allTasks.push({ account, group, merged, platformSettings: pSettings })
    }
  }

  // 生成本次一键发布的 batchId 与素材 ID（一次发布，跨账号复用）
  const batchId = (crypto.randomUUID && crypto.randomUUID()) || (Date.now().toString(36) + '-' + Math.random().toString(36).slice(2))
  const videoMaterialId = commonConfig.videoLandscape?.id || commonConfig.videoPortrait?.id || ''
  const landscapeCoverMaterialId = commonConfig.coverLandscape?.id || ''
  const portraitCoverMaterialId = commonConfig.coverPortrait?.id || ''

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

    const { account, group, merged, platformSettings } = allTasks[i]
    currentPublishingAccount.value = account.name
    publishProgress.value = Math.floor((i / allTasks.length) * 100)

    const videoFormat = merged.videoFormat || ''

    let selectedVideo
    if (videoFormat === 'portrait') {
      selectedVideo = merged.videoPortrait || commonConfig.videoPortrait
    } else if (videoFormat === 'landscape') {
      selectedVideo = merged.videoLandscape || commonConfig.videoLandscape
    } else {
      selectedVideo = merged.videoLandscape || commonConfig.videoLandscape || merged.videoPortrait || commonConfig.videoPortrait
    }

    // [DEBUG 2026-06-10] 详细日志：把 4 级合并后的视频相关字段都打出来
    console.log('[PublishCenter.publish.account] account=' + account.name + ' platform=' + group.key + ' videoFormat=' + videoFormat + ' merged.videoLandscape.id=' + (merged.videoLandscape && merged.videoLandscape.id) + ' merged.videoPortrait.id=' + (merged.videoPortrait && merged.videoPortrait.id) + ' commonConfig.videoLandscape.id=' + (commonConfig.videoLandscape && commonConfig.videoLandscape.id) + ' commonConfig.videoPortrait.id=' + (commonConfig.videoPortrait && commonConfig.videoPortrait.id) + ' selectedVideo.id=' + (selectedVideo && selectedVideo.id))

    if (!selectedVideo) {
        publishResults.value.push({
          label: account.name,
          status: 'error',
          message: '未找到匹配的视频（请检查视频格式设置）',
        })
        continue
      }

    // 封面走 4 级合并（merged.coverLandscape/Portrait），common 兜底
    // 封面缺失校验已在 publishAll 顶部 collect-all 阶段完成，这里不再重复
    const thumbnailLandscapeMaterial = merged.coverLandscape || commonConfig.coverLandscape
    const thumbnailPortraitMaterial = merged.coverPortrait || commonConfig.coverPortrait

    try {
      const tags = merged.tags || []

      const publishData = {
        type: group.id,
        title: merged.title,
        description: merged.description || '',
        tags: tags,
        activities: merged.activityId || [],
        fileList: [selectedVideo.stored_path],
        videoFormat: videoFormat,
        accountList: [account.filePath],
        thumbnailLandscape: thumbnailLandscapeMaterial ? thumbnailLandscapeMaterial.stored_path : '',
        thumbnailPortrait: thumbnailPortraitMaterial ? thumbnailPortraitMaterial.stored_path : '',
        enableTimer: merged.scheduleTime ? 1 : 0,
        scheduleTime: merged.scheduleTime || '',
        videosPerDay: 1,
        dailyTimes: ['10:00'],
        startDays: 0,
        // 修：账号级填的 zone 才能进 publishData
        // 微博分类走 cascader(数组 [channel_name, sub_name]);其他平台用 zone 或数值
        category: group.key === 'weibo'
          ? (Array.isArray(merged.weiboCategory) ? merged.weiboCategory : [])
          : (merged.zone || (merged.isOriginal ? 1 : 0)),
        // 微博的「类型」(原创/二创/转载)走 aiContent 字段透传给后端
        aiContent: group.key === 'weibo'
          ? (merged.videoType || '')
          : (merged.aiContent || ''),
        // 微博「内容声明」单独透传
        contentStatement: group.key === 'weibo' ? (merged.contentStatement || '') : '',
        // 支付宝「作者声明」+「合集」单独透传(其他平台忽略)
        authorStatement: merged.authorStatement || '',
        compilation: merged.compilation || '',
        // 今日头条特有字段
        enableGenerateImage: merged.enableGenerateImage ?? true,
        collection: merged.collection || '',
        extendLink: merged.extendLink || false,
        extendLinkUrl: merged.extendLinkUrl || '',
        hotspot: merged.hotspotId || '',
        tag_type: merged.tagType || '',
        tag_value: merged.tagValue || '',
        mini_link: merged.selectedTag?.type === 'miniapp' ? (merged.selectedTag._searchKeyword || '') : '',
        mix_id: merged.mixId || '',
        // Other platform fields (修：channels isDraft 同)
        isDraft: merged.isDraft || false,
        // creationDeclaration 走 merged（已含 platformDefault 兜底）
        creationDeclaration: Array.isArray(merged.creationDeclaration)
          ? merged.creationDeclaration.join(',')
          : merged.creationDeclaration || '',
        riskWarning: merged.riskWarning || '',
        // 百家号补充声明
        supplementaryDeclaration: merged.supplementaryDeclaration || '',
        enableCashActivity: merged.enableCashActivity || false,
        audience: merged.audience || 'not_kids',
        alteredContent: merged.alteredContent || false,
        // Task 12：本次一键发布的批次与素材 ID
        batchId,
        videoMaterialId,
        landscapeCoverMaterialId,
        portraitCoverMaterialId,
        accountId: account.id,
        // Task 7：透传 4 级合并后的素材对象（供后端持久化到 account_configs JSON，符合 spec §3.3）
        coverLandscape: thumbnailLandscapeMaterial,
        coverPortrait: thumbnailPortraitMaterial,
        videoLandscape: merged.videoLandscape,
        videoPortrait: merged.videoPortrait,
      }

      // [DEBUG 2026-06-10] 详细日志：把要发的 publishData 关键字段打印
      console.log('[PublishCenter.publish] account=' + account.name + ' platform=' + group.key + ' fileList=' + JSON.stringify(publishData.fileList) + ' videoLandscape.id=' + (publishData.videoLandscape && publishData.videoLandscape.id) + ' videoPortrait.id=' + (publishData.videoPortrait && publishData.videoPortrait.id) + ' coverLandscape.id=' + (publishData.coverLandscape && publishData.coverLandscape.id) + ' coverPortrait.id=' + (publishData.coverPortrait && publishData.coverPortrait.id) + ' creationDeclaration=' + publishData.creationDeclaration + ' aiContent=' + publishData.aiContent)
      // 今日头条特有参数日志
      if (group.key === 'toutiao') {
        console.log('[PublishCenter.publish] 今日头条参数: extendLink=' + publishData.extendLink + ' extendLinkUrl=' + publishData.extendLinkUrl + ' enableGenerateImage=' + publishData.enableGenerateImage + ' collection=' + publishData.collection)
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

function handleOneClickFill(record) {
  const histConfig = record.account_configs || {}
  const channels = record.channels || []
  // 1. 复原账号选择：清空当前选中，按历史 channels 自动勾选对应平台下的所有账号
  publishAccountIds.clear()
  let selectedAccounts = 0
  for (const ch of channels) {
    const group = accountGroups.value.find(g => g.name === ch.platform)
    if (!group) continue
    for (const acc of group.accounts) {
      if (acc.id != null) {
        publishAccountIds.add(acc.id)
        selectedAccounts++
      }
    }
  }
  // 2. 把历史的单份配置应用到所有涉及的平台（覆盖现有平台配置）
  // 注意：channels[].platform 是中文名（如 "抖音"），platformConfigs 的 key 是英文（如 "douyin"）
  let filled = 0
  for (const ch of channels) {
    const key = platformNameToKey[ch.platform]
    if (!key) continue
    platformConfigs[key] = {
      ...platformConfigs[key],
      ...histConfig,
    }
    filled++
  }
  if (filled > 0) {
    ElMessage.success(`已从历史填充 ${filled} 个平台配置${selectedAccounts > 0 ? `，已选中 ${selectedAccounts} 个账号` : ''}`)
  } else {
    if (selectedAccounts > 0) {
      ElMessage.success(`已选中 ${selectedAccounts} 个账号`)
    } else {
      ElMessage.warning('历史记录没有可填充的平台配置')
    }
  }
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
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
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
        font-weight: 600;
        box-shadow: 0 0 0 1px rgba(139, 92, 246, 0.3);
      }
    }

    &.disabled {
      opacity: 0.4;
      cursor: not-allowed;
      .radio-text.muted { opacity: 0.5; }
    }
  }
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.5;
}

.tags-list {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
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
