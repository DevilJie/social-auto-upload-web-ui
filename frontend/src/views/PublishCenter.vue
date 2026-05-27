<template>
  <div class="publish-center">
    <!-- ========== LEFT SIDEBAR ========== -->
    <aside class="account-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">账号管理</span>
        <span class="sidebar-count">{{ totalCount }}</span>
      </div>

      <div class="group-list">
        <div
          v-for="group in accountGroups"
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
            :materials="materials"
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

          <!-- 视频格式选择 -->
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
              <!-- 其他字段通用渲染（排除 title, description, videoFormat） -->
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
    <el-dialog
      v-model="accountDialogVisible"
      title="选择账号"
      width="680px"
      :close-on-click-modal="false"
      class="account-select-dialog"
    >
      <div class="account-dialog-body">
        <div class="account-dialog-content">
          <!-- Left: platform list -->
          <div class="dialog-platform-list">
            <div
              :class="['dialog-platform-item', 'cursor-pointer', { active: !accountFilterPlatform }]"
              @click="accountFilterPlatform = ''"
            >全部平台</div>
            <div
              v-for="p in platformList"
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
        :action="`${apiBaseUrl}/uploadSave`"
        :on-success="handleVideoUploadSuccess"
        :on-error="handleUploadError"
        accept="video/*"
        :headers="authHeaders"
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
    <el-dialog
      v-model="materialLibraryVisible"
      :title="materialLibraryMode === 'cover' ? '选择封面图片' : '选择视频素材'"
      width="800px"
      class="material-library-dialog"
    >
      <div class="material-library-content">
        <el-checkbox-group v-model="selectedMaterials">
          <div class="material-list">
            <div
              v-for="material in filteredMaterials"
              :key="material.id"
              class="material-item"
            >
              <el-checkbox :label="material.id" class="material-checkbox cursor-pointer">
                <div class="material-info">
                  <div class="material-name">{{ material.filename }}</div>
                  <div class="material-details">
                    <span class="mat-size">{{ material.filesize }}MB</span>
                    <span class="mat-time">{{ material.upload_time }}</span>
                  </div>
                </div>
              </el-checkbox>
            </div>
          </div>
        </el-checkbox-group>
        <div v-if="filteredMaterials.length === 0" class="dialog-empty">素材库暂无{{ materialLibraryMode === 'cover' ? '图片' : '视频' }}素材</div>
      </div>

      <template #footer>
        <div class="dialog-footer-right">
          <el-button @click="materialLibraryVisible = false">取消</el-button>
          <el-button type="primary" @click="confirmMaterialSelect">确定</el-button>
        </div>
      </template>
    </el-dialog>

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

    <!-- Hidden file inputs -->
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch, onMounted, onBeforeUnmount } from 'vue'
import { Upload, ArrowDown, ArrowRight, Picture, VideoCameraFilled, Check, Close, InfoFilled, Promotion, StarFilled, Delete, Document, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { materialApi } from '@/api/material'
import { accountApi } from '@/api/account'
import { http } from '@/utils/request'
import { platformList, getPlatformByKey, platformKeyToId } from '@/config/platforms'
import CoverCard from '@/components/CoverCard.vue'
import CoverEditorDialog from '@/components/CoverEditorDialog.vue'
import { frameApi } from '@/api/frame'
import { draftApi } from '@/api/draft'
import { useRoute } from 'vue-router'

// ========== Stores & Config ==========
const accountStore = useAccountStore()
const appStore = useAppStore()
appStore.loadAutoFillTitle()  // 加载自动填充标题开关状态
appStore.loadAutoSaveSettings()  // 加载自动保存草稿设置
appStore.loadCoverRatioSettings()  // 加载封面比例设置
const route = useRoute()
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
const authHeaders = computed(() => ({ 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` }))

// ========== Left Sidebar State ==========
const expandedGroups = ref(new Set())
const selectedPlatform = ref(null)
const selectedAccountId = ref(null)

// Account groups computed from store
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

// ========== Public Config (shared across all accounts) ==========
const commonConfig = reactive({
  videoLandscape: null,  // { name, url, path, size, type }
  videoPortrait: null,   // { name, url, path, size, type }
  coverLandscape: null, // 横版封面 16:9
  coverPortrait: null,  // 竖版封面 9:16
  topics: [],
})

// Cover editor
const coverEditorRef = ref(null)
const landscapeFrames = ref([])
const portraitFrames = ref([])
const videoModeTab = ref('portrait')  // 'portrait' | 'landscape'

// Smart frame fallback: if only one video exists, both covers share its frames
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
  bilibili: { title: '', description: '', zone: '', tags: '', topic: '', aiContent: '', creationDeclaration: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  channels: { title: '', description: '', isDraft: false, location: '', aiContent: false, isOriginal: false, videoFormat: '' },
  baijiahao: { title: '', description: '', aiContent: false, isOriginal: false, videoFormat: '' },
  tiktok: { title: '', description: '', aiContent: false, isOriginal: false, scheduleTime: '', videoFormat: '' },
  youtube: { title: '', description: '', audience: 'not_kids', alteredContent: false, scheduleTime: '', videoFormat: '' },
  iqiyi: { title: '', description: '', creationDeclaration: '', riskWarning: '', enableCashActivity: false, scheduleTime: '', videoFormat: '' },
  tencent_video: { title: '', description: '', creationDeclaration: [], scheduleTime: '', videoFormat: '' },
})

// ========== Account-level Overrides (账号级覆盖, 优先级高于渠道默认) ==========
const accountOverrides = reactive({})

const currentSettings = computed(() =>
  selectedPlatform.value ? platformConfigs[selectedPlatform.value] || {} : {}
)

// ========== Video Format Helpers ==========
const videoFormatOptions = computed(() => {
  const hasLandscape = !!commonConfig.videoLandscape
  const hasPortrait = !!commonConfig.videoPortrait
  const options = [
    { label: '横版', value: 'landscape', disabled: !hasLandscape && hasPortrait },
    { label: '竖版', value: 'portrait', disabled: !hasPortrait && hasLandscape },
  ]
  return options
})

const effectiveVideoFormat = computed(() => {
  if (commonConfig.videoLandscape && !commonConfig.videoPortrait) return 'landscape'
  if (commonConfig.videoPortrait && !commonConfig.videoLandscape) return 'portrait'
  return ''
})

// ========== Account-level Settings Merging ==========
/**
 * 获取合并后的账号设置：账号级覆盖优先，其次渠道默认
 * @param {string} accountId
 * @param {string} platformKey
 */
function getAccountSettings(accountId, platformKey) {
  const platform = platformConfigs[platformKey] || {}
  const override = accountOverrides[accountId] || {}
  // 账号级覆盖优先，其次渠道默认
  const merged = { ...platform }
  for (const key of Object.keys(merged)) {
    if (override[key] !== undefined && override[key] !== '') {
      merged[key] = override[key]
    }
  }
  return merged
}

/**
 * 检查账号是否有自定义覆盖配置
 */
function hasAccountOverride(accountId) {
  const override = accountOverrides[accountId]
  if (!override) return false
  return Object.values(override).some(v => v !== undefined && v !== '' && v !== false)
}

// 表单数据（reactive 对象，支持 v-model 绑定到属性）
const form = reactive({})

// 获取当前合并后的设置
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
  // 多选字段初始化为数组
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

// 表单变更时同步到 store
watch(form, (newVal) => {
  const platformKey = selectedPlatform.value
  if (!platformKey) return
  if (!platformConfigs[platformKey]) {
    platformConfigs[platformKey] = {}
  }
  const platform = platformConfigs[platformKey]

  if (selectedAccountId.value) {
    // 账号级：计算与渠道默认的差异，存入 accountOverrides
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
    // 渠道级：直接写入 platformConfigs
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

// ========== Batch title/description sync ==========
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

// ========== Init: expand first group with accounts ==========
const firstGroup = accountGroups.value.find(g => g.accounts.length > 0)
if (firstGroup) {
  expandedGroups.value.add(firstGroup.key)
  selectedPlatform.value = firstGroup.key
}

// ========== Dialog State ==========
const accountDialogVisible = ref(false)
const topicDialogVisible = ref(false)
const videoUploadDialogVisible = ref(false)
const videoUploadTarget = ref('landscape') // 'landscape' | 'portrait'
const materialLibraryVisible = ref(false)
const materialLibraryMode = ref('video') // 'video' | 'cover'
const materialLibraryCoverTarget = ref('landscape') // 'landscape' | 'portrait'
const materialLibraryVideoTarget = ref('landscape') // 'landscape' | 'portrait'
const batchPublishDialogVisible = ref(false)

// Account dialog state
const accountFilterPlatform = ref('')
const accountSearchQuery = ref('')
const tempSelectedAccounts = ref([])

// 账号弹窗打开时，从 publishAccountIds 恢复 tempSelectedAccounts
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

// 自动选择视频格式（当只有一种格式可用时）
watch(effectiveVideoFormat, (format) => {
  if (format && selectedPlatform.value && !currentSettings.value?.videoFormat) {
    const platformKey = selectedPlatform.value
    if (platformConfigs[platformKey]) {
      platformConfigs[platformKey].videoFormat = format
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

// Material library state
const selectedMaterials = ref([])
const materials = computed(() => appStore.materials)

const imageExts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
const videoExts = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']

const filteredMaterials = computed(() => {
  const list = materials.value
  if (materialLibraryMode.value === 'cover') {
    return list.filter(m => imageExts.some(ext => (m.filename || '').toLowerCase().endsWith(ext)))
  }
  return list.filter(m => videoExts.some(ext => (m.filename || '').toLowerCase().endsWith(ext)))
})

// Batch publish state
const publishing = ref(false)
const publishProgress = ref(0)
const publishResults = ref([])
const currentPublishingAccount = ref('')
const isCancelled = ref(false)

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

// Selected accounts for publishing (default empty)
const publishAccountIds = reactive(new Set())
const currentDraftId = ref(null) // null = 新草稿, number = 编辑已有草稿
const autoSaveTimer = ref(null)
const hasChanges = ref(false) // 是否有过修改

function removePublishAccount(id) {
  publishAccountIds.delete(id)
  hasChanges.value = true
}

function togglePublishAccount(account, group) {
  selectedPlatform.value = group.key
  expandedGroups.value.add(group.key)
  if (publishAccountIds.has(account.id)) {
    publishAccountIds.delete(account.id)
  } else {
    publishAccountIds.add(account.id)
  }
  hasChanges.value = true
}

function selectAccount(account, group) {
  selectedAccountId.value = account.id
  selectedPlatform.value = group.key
  expandedGroups.value.add(group.key)
}

// ========== Upload Methods ==========

function triggerUploadVideo(target = 'landscape') {
  videoUploadTarget.value = target
  videoUploadDialogVisible.value = true
}

function clearVideo(type) {
  // type: 'landscape' | 'portrait'
  if (type === 'landscape') commonConfig.videoLandscape = null
  else commonConfig.videoPortrait = null
}

// ========== Cover Editor ==========

function openCoverEditor(tab = 'landscape') {
  coverEditorRef.value?.open(tab)
}

function triggerFrameExtraction(videoData, type) {
  if (!videoData?.path) return
  const doExtract = async () => {
    try {
      const resp = await frameApi.extractFrames(videoData.path)
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

function handleVideoUploadSuccess(response, file) {
  if (response.code === 200) {
    const filePath = response.data.filepath || response.data
    const filename = filePath.split('/').pop()
    const videoData = {
      name: file.name,
      url: materialApi.getMaterialPreviewUrl(filename),
      path: filePath,
      size: file.size,
      type: file.type,
    }
    if (videoUploadTarget.value === 'portrait') {
      commonConfig.videoPortrait = videoData
    } else {
      commonConfig.videoLandscape = videoData
    }
    videoUploadDialogVisible.value = false
    ElMessage.success('视频上传成功')
    // Auto-fill title from video filename
    if (appStore.autoFillTitle) {
      const title = file.name.replace(/\.[^.]+$/, '')
      // 1. 更新所有渠道级标题
      for (const key of Object.keys(platformConfigs)) {
        platformConfigs[key].title = title
      }
      // 2. 对已有账号级标题的账号，也一并更新
      for (const group of accountGroups.value) {
        for (const account of group.accounts) {
          if (accountOverrides[account.id]?.title) {
            accountOverrides[account.id].title = title
          }
        }
      }
      // 3. 同步到当前表单显示
      if (selectedPlatform.value) {
        const accountId = selectedAccountId.value
        if (accountId && accountOverrides[accountId]?.title) {
          form.title = accountOverrides[accountId].title
        } else if (platformConfigs[selectedPlatform.value]) {
          form.title = platformConfigs[selectedPlatform.value].title
        }
      }
    }
    // Extract frames for the uploaded type; the other cover falls back via computed
    triggerFrameExtraction(videoData, videoUploadTarget.value)
  } else {
    ElMessage.error(response.msg || '上传失败')
  }
}

function handleUploadError() {
  ElMessage.error('文件上传失败')
}

// ========== Material Library ==========

async function selectFromLibrary(mode = 'video', videoOrCoverTarget = 'landscape') {
  materialLibraryMode.value = mode
  if (mode === 'video') {
    materialLibraryVideoTarget.value = videoOrCoverTarget
  } else {
    materialLibraryCoverTarget.value = videoOrCoverTarget
  }
  // 每次打开素材库都重新加载，确保看到最新上传的文件
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
  selectedMaterials.value = []
  materialLibraryVisible.value = true
}

function confirmMaterialSelect() {
  if (selectedMaterials.value.length === 0) {
    ElMessage.warning('请选择至少一个素材')
    return
  }
  if (materialLibraryMode.value === 'cover') {
    // 封面模式：只用第一张图片素材
    const material = materials.value.find(m => m.id === selectedMaterials.value[0])
    if (material) {
      const coverData = {
        name: material.filename,
        url: materialApi.getMaterialPreviewUrl(material.file_path.split('/').pop()),
        path: material.file_path,
        size: material.filesize * 1024 * 1024,
        type: 'image/jpeg',
      }
      if (materialLibraryCoverTarget.value === 'portrait') {
        commonConfig.coverPortrait = coverData
      } else {
        commonConfig.coverLandscape = coverData
      }
      ElMessage.success('封面已设置')
    }
  } else {
    // 素材库选择视频模式，只用第一个
    const material = materials.value.find(m => m.id === selectedMaterials.value[0])
    if (material) {
      const videoData = {
        name: material.filename,
        url: materialApi.getMaterialPreviewUrl(material.file_path.split('/').pop()),
        path: material.file_path,
        size: material.filesize * 1024 * 1024,
        type: 'video/mp4',
      }
      if (materialLibraryVideoTarget.value === 'portrait') {
        commonConfig.videoPortrait = videoData
      } else {
        commonConfig.videoLandscape = videoData
      }
      ElMessage.success('视频已设置')
      if (appStore.autoFillTitle) {
        const title = material.filename.replace(/\.[^.]+$/, '')
        // 1. 更新所有渠道级标题
        for (const key of Object.keys(platformConfigs)) {
          platformConfigs[key].title = title
        }
        // 2. 对已有账号级标题的账号，也一并更新
        for (const group of accountGroups.value) {
          for (const account of group.accounts) {
            if (accountOverrides[account.id]?.title) {
              accountOverrides[account.id].title = title
            }
          }
        }
        // 3. 同步到当前表单显示
        if (selectedPlatform.value && platformConfigs[selectedPlatform.value]) {
          form.title = platformConfigs[selectedPlatform.value].title
        }
      }
      triggerFrameExtraction(videoData, materialLibraryVideoTarget.value)
    }
  }
  materialLibraryVisible.value = false
  selectedMaterials.value = []
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
  if (accountFilterPlatform.value) {
    list = list.filter(a => a.platform === accountFilterPlatform.value)
  }
  if (accountSearchQuery.value.trim()) {
    const query = accountSearchQuery.value.trim().toLowerCase()
    list = list.filter(a => a.name.toLowerCase().includes(query))
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
    const draftData = {
      commonConfig: {
        topics: [...commonConfig.topics],
        videoLandscape: commonConfig.videoLandscape
          ? { name: commonConfig.videoLandscape.name, path: commonConfig.videoLandscape.path, url: commonConfig.videoLandscape.url, size: commonConfig.videoLandscape.size, type: commonConfig.videoLandscape.type }
          : null,
        videoPortrait: commonConfig.videoPortrait
          ? { name: commonConfig.videoPortrait.name, path: commonConfig.videoPortrait.path, url: commonConfig.videoPortrait.url, size: commonConfig.videoPortrait.size, type: commonConfig.videoPortrait.type }
          : null,
        coverLandscape: commonConfig.coverLandscape
          ? { name: commonConfig.coverLandscape.name, path: commonConfig.coverLandscape.path, url: commonConfig.coverLandscape.url, size: commonConfig.coverLandscape.size, type: commonConfig.coverLandscape.type, _fromFrame: commonConfig.coverLandscape._fromFrame }
          : null,
        coverPortrait: commonConfig.coverPortrait
          ? { name: commonConfig.coverPortrait.name, path: commonConfig.coverPortrait.path, url: commonConfig.coverPortrait.url, size: commonConfig.coverPortrait.size, type: commonConfig.coverPortrait.type, _fromFrame: commonConfig.coverPortrait._fromFrame }
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

    // 恢复 commonConfig
    if (dd.commonConfig) {
      if (dd.commonConfig.topics) commonConfig.topics = dd.commonConfig.topics
      if (dd.commonConfig.videoLandscape) commonConfig.videoLandscape = dd.commonConfig.videoLandscape
      if (dd.commonConfig.videoPortrait) commonConfig.videoPortrait = dd.commonConfig.videoPortrait
      if (dd.commonConfig.coverLandscape) commonConfig.coverLandscape = dd.commonConfig.coverLandscape
      if (dd.commonConfig.coverPortrait) commonConfig.coverPortrait = dd.commonConfig.coverPortrait
    }

    // 恢复 platformConfigs（深度合并以保留可能新增的字段）
    if (dd.platformConfigs) {
      for (const [key, val] of Object.entries(dd.platformConfigs)) {
        if (platformConfigs[key]) {
          Object.assign(platformConfigs[key], val)
        }
      }
    }

    // 恢复 accountOverrides
    if (dd.accountOverrides) {
      Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
      Object.assign(accountOverrides, dd.accountOverrides)
    }

    // 恢复 publishAccountIds
    if (dd.publishAccountIds) {
      publishAccountIds.clear()
      dd.publishAccountIds.forEach(id => publishAccountIds.add(id))
    }

    // 恢复 tempSelectedAccounts（账号选择弹窗的选中状态）
    if (dd.publishAccountIds) {
      tempSelectedAccounts.value = [...dd.publishAccountIds]
    }

    // 恢复 expandedGroups
    if (dd.expandedGroups) {
      expandedGroups.value = new Set(dd.expandedGroups)
    }

    // 恢复 selectedPlatform
    if (dd.selectedPlatform) {
      selectedPlatform.value = dd.selectedPlatform
    }

    // 恢复 videoModeTab
    if (dd.videoModeTab) {
      videoModeTab.value = dd.videoModeTab
    }

    // 设置草稿编辑模式
    currentDraftId.value = draftId

    // 重新提取视频抽帧（异步，不阻塞）
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
  // 启动自动保存定时器
  startAutoSaveTimer()
})

onBeforeUnmount(() => {
  if (autoSaveTimer.value) {
    clearInterval(autoSaveTimer.value)
    autoSaveTimer.value = null
  }
})

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

// 监听自动保存设置变化，重新启动定时器
watch(() => appStore.autoSaveDraft, (val) => {
  if (val) {
    startAutoSaveTimer()
  } else {
    stopAutoSaveTimer()
  }
})

watch(() => appStore.autoSaveInterval, () => {
  if (appStore.autoSaveDraft) {
    startAutoSaveTimer()
  }
})

// 监听需要保存的内容变化
watch(commonConfig, () => { hasChanges.value = true }, { deep: true })
watch(platformConfigs, () => { hasChanges.value = true }, { deep: true })
watch(accountOverrides, () => { hasChanges.value = true }, { deep: true })

async function publishAll() {
  // Validate
  if (!commonConfig.videoLandscape && !commonConfig.videoPortrait) {
    ElMessage.error('请先上传至少一个视频文件')
    return
  }

  // 封面必填
  if (!commonConfig.coverLandscape && !commonConfig.coverPortrait) {
    ElMessage.error('请先设置封面图片')
    return
  }

  // 各平台声明必填检查
  const accountsWithoutDeclaration = []
  const DECLARATION_PLATFORMS = {
    xiaohongshu: 'aiContent',
    douyin: 'aiContent',
    kuaishou: 'aiContent',
    bilibili: ['aiContent', 'creationDeclaration'],
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
        // 数组类型检查长度；字符串检查空；布尔只看是否为 null/undefined（false 是有效值）
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

  // Check each selected account has a title (platform-level or account-level)
  const accountsWithoutTitle = []
  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    const pSettings = platformConfigs[group.key] || {}
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      // 合并账号级覆盖后检查标题
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

  // 视频格式必填检查
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

  // Collect selected accounts only
  const allTasks = []
  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    const pSettings = platformConfigs[group.key] || {}
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      // 合并账号级覆盖
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

    // 获取视频格式（已包含账号级覆盖）
    const videoFormat = platformSettings.videoFormat || ''

    // 根据格式选择视频
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
      // 解析平台自定义标签：支持 "#xx #xx" 和 "xx,xx" 两种格式
      const customTags = (platformSettings.tags || '').split(/[,，\s]+/).map(t => t.replace(/^#/, '').trim()).filter(Boolean)
      const allTags = [...commonConfig.topics, ...customTags]

      const publishData = {
        type: group.id,
        title: platformSettings.title,
        description: platformSettings.description || '',
        tags: allTags,
        fileList: [selectedVideo.path],
        videoFormat: videoFormat,
        accountList: [account.filePath],
        thumbnailLandscape: commonConfig.coverLandscape ? commonConfig.coverLandscape.path : '',
        thumbnailPortrait: commonConfig.coverPortrait ? commonConfig.coverPortrait.path : '',
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

// ========== Utility Classes ==========
.cursor-pointer {
  cursor: pointer;
}

// ========== Layout ==========
.publish-center {
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

      &.ring {
        border-color: $brand-start;
      }
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

// ========== Media Section (Video & Cover) ==========
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

        &:hover {
          background: rgba(255, 255, 255, 0.03);
        }

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

        &:hover {
          background: rgba(255, 255, 255, 0.03);
        }

        &.disabled {
          opacity: 0.5;
        }
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

          &.ok {
            color: $success-color;
          }
          &.err {
            color: $danger-color;
          }
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
// ========== Material Library Dialog ==========
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

        .el-icon {
          margin-right: 8px;
        }

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
          .el-icon,
          .result-label {
            color: $success-color;
          }
        }

        &.error {
          .el-icon,
          .result-label {
            color: $danger-color;
          }
        }

        &.cancelled {
          color: $text-muted;

          .result-label {
            color: $text-muted;
          }
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
