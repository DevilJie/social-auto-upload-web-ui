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
            <span class="platform-badge" :style="{ background: group.color }">{{ group.letter }}</span>
            <span class="group-name">{{ group.name }}</span>
            <span class="group-count">{{ group.accounts.filter(a => publishAccountIds.has(a.id)).length }}</span>
          </div>

          <!-- Expandable account list -->
          <transition name="slide">
            <div v-show="expandedGroups.has(group.key)" class="group-accounts">
              <div
                v-for="account in group.accounts.filter(a => publishAccountIds.has(a.id))"
                :key="account.id"
                class="account-item cursor-pointer"
              >
                <div class="account-avatar" :style="{ borderColor: group.color }">
                  {{ account.name ? account.name.charAt(0) : '?' }}
                </div>
                <span class="account-name">{{ account.name }}</span>
                <span :class="['dot', account.status === '正常' ? 'on' : 'off']"></span>
                <el-icon class="account-remove" @click.stop="publishAccountIds.delete(account.id)"><Close /></el-icon>
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
          <span class="text-btn cursor-pointer" @click="saveDraft">保存草稿</span>
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

          <!-- Video Section -->
          <div class="media-section">
            <div class="section-label">视频</div>
            <div class="video-dual-grid">
              <!-- Landscape -->
              <div class="video-card">
                <div class="video-card-label">
                  <span>横版视频</span>
                  <span class="video-ratio">16:9</span>
                </div>
                <div v-if="!commonConfig.videoLandscape" class="video-card-empty" @click="triggerUploadVideo('landscape')">
                  <el-icon :size="28"><Upload /></el-icon>
                  <span class="video-card-empty-text">上传横版视频</span>
                </div>
                <div v-else class="video-card-preview">
                  <video :src="commonConfig.videoLandscape.url" controls preload="metadata" class="video-player"></video>
                  <div class="video-card-overlay">
                    <button class="overlay-btn" @click="triggerUploadVideo('landscape')">替换</button>
                    <button class="overlay-btn danger" @click="clearVideo('landscape')">移除</button>
                  </div>
                </div>
                <div class="video-card-actions">
                  <button class="cover-action-btn" @click="triggerUploadVideo('landscape')">
                    <el-icon :size="14"><Upload /></el-icon><span>本地上传</span>
                  </button>
                  <button class="cover-action-btn" @click="selectFromLibrary('video', 'landscape')">
                    <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
                  </button>
                </div>
              </div>
              <!-- Portrait -->
              <div class="video-card">
                <div class="video-card-label">
                  <span>竖版视频</span>
                  <span class="video-ratio">9:16</span>
                </div>
                <div v-if="!commonConfig.videoPortrait" class="video-card-empty" @click="triggerUploadVideo('portrait')">
                  <el-icon :size="28"><Upload /></el-icon>
                  <span class="video-card-empty-text">上传竖版视频</span>
                </div>
                <div v-else class="video-card-preview">
                  <video :src="commonConfig.videoPortrait.url" controls preload="metadata" class="video-player"></video>
                  <div class="video-card-overlay">
                    <button class="overlay-btn" @click="triggerUploadVideo('portrait')">替换</button>
                    <button class="overlay-btn danger" @click="clearVideo('portrait')">移除</button>
                  </div>
                </div>
                <div class="video-card-actions">
                  <button class="cover-action-btn" @click="triggerUploadVideo('portrait')">
                    <el-icon :size="14"><Upload /></el-icon><span>本地上传</span>
                  </button>
                  <button class="cover-action-btn" @click="selectFromLibrary('video', 'portrait')">
                    <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Cover Section -->
          <div class="media-section cover-section">
            <div class="section-label">封面</div>
            <div class="cover-grid">
              <!-- Landscape cover -->
              <div class="cover-card">
                <div class="cover-card-label">
                  <span>横版封面</span>
                  <span class="cover-ratio">16:9</span>
                </div>
                <div v-if="!commonConfig.coverLandscape" class="cover-empty" @click="triggerUploadCover('landscape')">
                  <el-icon :size="28"><Picture /></el-icon>
                  <span class="cover-empty-text">上传横版封面</span>
                </div>
                <div v-else class="cover-preview-wrap">
                  <img :src="commonConfig.coverLandscape.url" class="cover-preview" />
                  <div class="cover-preview-overlay">
                    <button class="overlay-btn" @click="openCropDialog('landscape')">裁剪</button>
                    <button class="overlay-btn" @click="triggerUploadCover('landscape')">更换</button>
                    <button class="overlay-btn danger" @click="commonConfig.coverLandscape = null">删除</button>
                  </div>
                </div>
                <div class="cover-card-actions">
                  <button class="cover-action-btn" @click="triggerUploadCover('landscape')">
                    <el-icon :size="14"><Upload /></el-icon><span>上传</span>
                  </button>
                  <button class="cover-action-btn" @click="selectFromLibrary('cover', 'landscape')">
                    <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
                  </button>
                </div>
              </div>
              <!-- Portrait cover -->
              <div class="cover-card">
                <div class="cover-card-label">
                  <span>竖版封面</span>
                  <span class="cover-ratio">3:4</span>
                </div>
                <div v-if="!commonConfig.coverPortrait" class="cover-empty" @click="triggerUploadCover('portrait')">
                  <el-icon :size="28"><Picture /></el-icon>
                  <span class="cover-empty-text">上传竖版封面</span>
                </div>
                <div v-else class="cover-preview-wrap">
                  <img :src="commonConfig.coverPortrait.url" class="cover-preview" />
                  <div class="cover-preview-overlay">
                    <button class="overlay-btn" @click="openCropDialog('portrait')">裁剪</button>
                    <button class="overlay-btn" @click="triggerUploadCover('portrait')">更换</button>
                    <button class="overlay-btn danger" @click="commonConfig.coverPortrait = null">删除</button>
                  </div>
                </div>
                <div class="cover-card-actions">
                  <button class="cover-action-btn" @click="triggerUploadCover('portrait')">
                    <el-icon :size="14"><Upload /></el-icon><span>上传</span>
                  </button>
                  <button class="cover-action-btn" @click="selectFromLibrary('cover', 'portrait')">
                    <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
                  </button>
                </div>
              </div>
            </div>
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
            <span class="section-label">{{ currentPlatformConfig.name }} 个性化设置</span>
            <span class="hint">仅对该分组账号生效</span>
          </div>

          <!-- Platform-specific title & description -->
          <div class="platform-title-desc">
            <div
              class="setting-card"
              :style="{
                borderColor: currentPlatformConfig.color + '26',
                background: currentPlatformConfig.color + '0a'
              }"
            >
              <div class="setting-label" :style="{ color: currentPlatformConfig.color }">标题</div>
              <el-input
                v-model="currentSettings.title"
                placeholder="请输入该平台的标题..."
                maxlength="100"
                show-word-limit
              />
            </div>
            <div
              class="setting-card"
              :style="{
                borderColor: currentPlatformConfig.color + '26',
                background: currentPlatformConfig.color + '0a'
              }"
            >
              <div class="setting-label" :style="{ color: currentPlatformConfig.color }">描述</div>
              <el-input
                v-model="currentSettings.description"
                type="textarea"
                :rows="5"
                placeholder="请输入该平台的描述..."
                maxlength="2000"
                show-word-limit
              />
            </div>
          </div>

          <div class="settings-grid">
            <div
              v-for="field in currentPlatformConfig.settingsFields"
              :key="field.key"
              class="setting-card"
              :style="{
                borderColor: currentPlatformConfig.color + '26',
                background: currentPlatformConfig.color + '0a'
              }"
            >
              <div class="setting-label" :style="{ color: currentPlatformConfig.color }">{{ field.label }}</div>
              <div v-if="field.description" class="setting-desc">{{ field.description }}</div>

              <!-- Input field -->
              <el-input
                v-if="field.type === 'input'"
                v-model="currentSettings[field.key]"
                :placeholder="field.placeholder"
                size="small"
              />

              <!-- Switch field -->
              <el-switch
                v-else-if="field.type === 'switch'"
                v-model="currentSettings[field.key]"
              />

              <!-- Radio field -->
              <div v-else-if="field.type === 'radio'" class="radio-row">
                <label
                  v-for="opt in field.options"
                  :key="String(opt.value)"
                  class="radio-item cursor-pointer"
                >
                  <input
                    type="radio"
                    :name="selectedPlatform + '-' + field.key"
                    :value="opt.value"
                    v-model="currentSettings[field.key]"
                    class="cursor-pointer"
                  />
                  <span
                    :class="['radio-text', { on: currentSettings[field.key] === opt.value }]"
                    :style="currentSettings[field.key] === opt.value ? { borderColor: currentPlatformConfig.color, color: currentPlatformConfig.color } : {}"
                  >{{ opt.label }}</span>
                </label>
              </div>

              <!-- Select field -->
              <el-select
                v-else-if="field.type === 'select'"
                v-model="currentSettings[field.key]"
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

              <!-- DateTime field -->
              <el-date-picker
                v-else-if="field.type === 'datetime'"
                v-model="currentSettings[field.key]"
                type="datetime"
                :placeholder="field.placeholder"
                value-format="YYYY-MM-DD HH:mm:ss"
                size="small"
                class="cursor-pointer"
              />
            </div>
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
        <div class="account-dialog-toolbar">
          <el-select
            v-model="accountFilterPlatform"
            placeholder="筛选平台"
            size="small"
            clearable
            class="cursor-pointer"
          >
            <el-option label="全部平台" :value="''" />
            <el-option
              v-for="p in platformList"
              :key="p.key"
              :label="p.name"
              :value="p.name"
            />
          </el-select>
          <el-input
            v-model="accountSearchQuery"
            placeholder="输入账号名称搜索..."
            size="small"
            clearable
            class="account-search-input"
          />
        </div>

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
              <span class="dialog-platform-badge" :style="{ background: p.color }">{{ p.letter }}</span>
              {{ p.name }}
            </div>
          </div>

          <!-- Right: account checkboxes -->
          <div class="dialog-account-list">
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

    <!-- Cover Upload Dialog -->
    <el-dialog
      v-model="coverUploadDialogVisible"
      :title="'上传' + (coverUploadTarget === 'portrait' ? '竖版' : '横版') + '封面'"
      width="500px"
      class="cover-upload-dialog"
    >
      <el-upload
        class="cover-upload"
        drag
        :auto-upload="true"
        :action="`${apiBaseUrl}/upload`"
        :on-success="handleCoverUploadSuccess"
        :on-error="handleUploadError"
        accept="image/*"
        :headers="authHeaders"
      >
        <el-icon class="el-icon--upload" :size="48"><Upload /></el-icon>
        <div class="el-upload__text">
          将封面图片拖到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            {{ coverUploadTarget === 'portrait' ? '竖版封面推荐比例 3:4' : '横版封面推荐比例 16:9' }}，支持JPG、PNG格式
          </div>
        </template>
      </el-upload>

      <template #footer>
        <div class="dialog-footer-right">
          <el-button @click="coverUploadDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Cover Crop Dialog -->
    <el-dialog
      v-model="cropDialogVisible"
      :title="'裁剪' + (cropTarget === 'portrait' ? '竖版' : '横版') + '封面'"
      width="600px"
      class="crop-dialog"
    >
      <div class="crop-container">
        <div class="crop-canvas-wrap">
          <canvas ref="cropCanvasRef" class="crop-canvas"></canvas>
          <div
            class="crop-selection"
            :style="cropSelectionStyle"
            @mousedown="startCropDrag"
          >
            <div class="crop-handle top-left" data-handle="tl"></div>
            <div class="crop-handle top-right" data-handle="tr"></div>
            <div class="crop-handle bottom-left" data-handle="bl"></div>
            <div class="crop-handle bottom-right" data-handle="br"></div>
          </div>
        </div>
        <div class="crop-info">
          <span>{{ cropTarget === 'portrait' ? '3:4' : '16:9' }}</span>
          <span class="crop-size">{{ Math.round(cropRect.w) }} x {{ Math.round(cropRect.h) }}</span>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer-right">
          <el-button @click="cropDialogVisible = false">取消</el-button>
          <el-button type="primary" @click="applyCrop">确认裁剪</el-button>
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
    <input
      ref="coverInputRef"
      type="file"
      accept="image/*"
      style="display: none"
      @change="handleCoverFileChange"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch } from 'vue'
import { Upload, ArrowDown, ArrowRight, Picture, VideoCameraFilled, Check, Close, InfoFilled, Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { materialApi } from '@/api/material'
import { accountApi } from '@/api/account'
import { http } from '@/utils/request'
import { platformList, getPlatformByKey, platformKeyToId } from '@/config/platforms'

// ========== Stores & Config ==========
const accountStore = useAccountStore()
const appStore = useAppStore()
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

const currentPlatformConfig = computed(() =>
  selectedPlatform.value ? getPlatformByKey(selectedPlatform.value) : null
)

// ========== Public Config (shared across all accounts) ==========
const commonConfig = reactive({
  videoLandscape: null,  // { name, url, path, size, type }
  videoPortrait: null,   // { name, url, path, size, type }
  coverLandscape: null, // 横版封面 16:9
  coverPortrait: null,  // 竖版封面 3:4
  topics: [],
})

// Active video index for player
const activeVideoIdx = ref(0)

// Cover upload target: 'landscape' or 'portrait'
const coverUploadTarget = ref('landscape')

// Crop dialog state
const cropDialogVisible = ref(false)
const cropTarget = ref('landscape') // 'landscape' or 'portrait'
const cropCanvasRef = ref(null)
const cropImage = ref(null) // Image element for cropping
const cropRect = reactive({ x: 0, y: 0, w: 0, h: 0 })
const cropDragState = ref(null) // null | { type, startX, startY, origRect }
const cropDisplayScale = ref(1) // canvas display scale vs actual image

const cropSelectionStyle = computed(() => ({
  left: cropRect.x * cropDisplayScale.value + 'px',
  top: cropRect.y * cropDisplayScale.value + 'px',
  width: cropRect.w * cropDisplayScale.value + 'px',
  height: cropRect.h * cropDisplayScale.value + 'px',
}))

// ========== Per-platform Config ==========
const platformConfigs = reactive({
  douyin: { title: '', description: '', productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true },
  xiaohongshu: { title: '', description: '', collection: '', groupChat: '', location: '', aiContent: '', isOriginal: false, scheduleTime: '' },
  kuaishou: { title: '', description: '', productTitle: '', productLink: '', aiContent: false, isOriginal: false, scheduleTime: '' },
  bilibili: { title: '', description: '', zone: '', tags: '', topic: '', aiContent: '', creationDeclaration: '', isOriginal: false, scheduleTime: '' },
  channels: { title: '', description: '', isDraft: false, location: '', aiContent: false, isOriginal: false },
  baijiahao: { title: '', description: '', aiContent: false, isOriginal: false },
  tiktok: { title: '', description: '', aiContent: false, isOriginal: false, scheduleTime: '' },
  youtube: { title: '', description: '', audience: 'not_kids', alteredContent: false, scheduleTime: '' },
})

// ========== Account-level Overrides (账号级覆盖, 优先级高于渠道默认) ==========
const accountOverrides = reactive({})

const currentSettings = computed(() =>
  selectedPlatform.value ? platformConfigs[selectedPlatform.value] || {} : {}
)

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
const coverUploadDialogVisible = ref(false)
const materialLibraryVisible = ref(false)
const materialLibraryMode = ref('video') // 'video' | 'cover'
const materialLibraryCoverTarget = ref('landscape') // 'landscape' | 'portrait'
const batchPublishDialogVisible = ref(false)

// Account dialog state
const accountFilterPlatform = ref('')
const accountSearchQuery = ref('')
const tempSelectedAccounts = ref([])

// 弹窗打开时加载账号数据
watch(accountDialogVisible, async (visible) => {
  if (visible && accountStore.accounts.length === 0) {
    try {
      const res = await accountApi.getAccounts()
      if (res.code === 200 && res.data) {
        accountStore.setAccounts(res.data)
      }
    } catch (e) {
      console.error('加载账号失败:', e)
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

const coverInputRef = ref(null)

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

function togglePublishAccount(account, group) {
  selectedPlatform.value = group.key
  expandedGroups.value.add(group.key)
  if (publishAccountIds.has(account.id)) {
    publishAccountIds.delete(account.id)
  } else {
    publishAccountIds.add(account.id)
  }
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

function triggerUploadCover(target = 'landscape') {
  coverUploadTarget.value = target
  coverUploadDialogVisible.value = true
}

function captureFromVideo() {
  if (commonConfig.fileList.length === 0) {
    ElMessage.warning('请先上传视频')
    return
  }
  ElMessage.info('视频截取功能开发中')
}

function clearVideo(type) {
  // type: 'landscape' | 'portrait'
  if (type === 'landscape') commonConfig.videoLandscape = null
  else commonConfig.videoPortrait = null
}

function openCropDialog(target) {
  cropTarget.value = target
  const coverData = target === 'portrait' ? commonConfig.coverPortrait : commonConfig.coverLandscape
  if (!coverData) return

  // Load image and init canvas
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    cropImage.value = img
    nextTick(() => initCropCanvas(img))
  }
  img.src = coverData.url
  cropDialogVisible.value = true
}

function initCropCanvas(img) {
  const canvas = cropCanvasRef.value
  if (!canvas) return

  const maxW = 540
  const maxH = 400
  const scale = Math.min(maxW / img.width, maxH / img.height, 1)
  cropDisplayScale.value = scale

  canvas.width = img.width * scale
  canvas.height = img.height * scale
  canvas.style.width = canvas.width + 'px'
  canvas.style.height = canvas.height + 'px'

  const ctx = canvas.getContext('2d')
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)

  // Init crop rect: centered with target aspect ratio
  const ratio = cropTarget.value === 'portrait' ? 3 / 4 : 16 / 9
  let rw = canvas.width / scale * 0.8
  let rh = rw / ratio
  if (rh > img.height * 0.8) {
    rh = img.height * 0.8
    rw = rh * ratio
  }
  cropRect.x = (img.width - rw) / 2
  cropRect.y = (img.height - rh) / 2
  cropRect.w = rw
  cropRect.h = rh
}

function startCropDrag(e) {
  e.preventDefault()
  const target = e.target.dataset.handle
  cropDragState.value = {
    type: target || 'move',
    startX: e.clientX,
    startY: e.clientY,
    origRect: { ...cropRect },
  }

  const onMove = (ev) => {
    if (!cropDragState.value) return
    const dx = (ev.clientX - cropDragState.value.startX) / cropDisplayScale.value
    const dy = (ev.clientY - cropDragState.value.startY) / cropDisplayScale.value
    const orig = cropDragState.value.origRect
    const img = cropImage.value
    const ratio = cropTarget.value === 'portrait' ? 3 / 4 : 16 / 9
    const type = cropDragState.value.type

    if (type === 'move') {
      cropRect.x = Math.max(0, Math.min(img.width - orig.w, orig.x + dx))
      cropRect.y = Math.max(0, Math.min(img.height - orig.h, orig.y + dy))
    } else {
      // Resize from corner, maintaining aspect ratio
      let newW = orig.w
      let newH = orig.h
      if (type === 'br') { newW = orig.w + dx; newH = newW / ratio }
      else if (type === 'bl') { newW = orig.w - dx; newH = newW / ratio }
      else if (type === 'tr') { newW = orig.w + dx; newH = newW / ratio }
      else if (type === 'tl') { newW = orig.w - dx; newH = newW / ratio }

      newW = Math.max(60, newW)
      newH = newW / ratio

      if (type === 'tl' || type === 'bl') {
        cropRect.x = orig.x + orig.w - newW
      }
      if (type === 'tl' || type === 'tr') {
        cropRect.y = orig.y + orig.h - newH
      }

      // Clamp
      cropRect.x = Math.max(0, cropRect.x)
      cropRect.y = Math.max(0, cropRect.y)
      if (cropRect.x + newW > img.width) newW = img.width - cropRect.x
      if (cropRect.y + newH > img.height) newH = img.height - cropRect.y
      newH = newW / ratio

      cropRect.w = newW
      cropRect.h = newH
    }

    // Redraw canvas
    redrawCropCanvas()
  }

  const onUp = () => {
    cropDragState.value = null
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}

function redrawCropCanvas() {
  // No need to redraw canvas - CSS box-shadow on .crop-selection handles the dim overlay,
  // and the crop-selection div position updates via Vue reactivity.
}

function applyCrop() {
  const img = cropImage.value
  if (!img) return

  const offscreen = document.createElement('canvas')
  offscreen.width = Math.round(cropRect.w)
  offscreen.height = Math.round(cropRect.h)
  const ctx = offscreen.getContext('2d')
  ctx.drawImage(img, cropRect.x, cropRect.y, cropRect.w, cropRect.h, 0, 0, offscreen.width, offscreen.height)

  offscreen.toBlob((blob) => {
    if (!blob) {
      ElMessage.error('裁剪失败')
      return
    }

    // Upload cropped image
    const formData = new FormData()
    formData.append('file', blob, `cover_${cropTarget.value}_${Date.now()}.png`)

    http.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((resp) => {
      if (resp.code === 200) {
        const filePath = resp.data.path || resp.data
        const filename = filePath.split('/').pop()
        const coverData = {
          name: `裁剪_${cropTarget.value === 'portrait' ? '竖版' : '横版'}_封面.png`,
          url: materialApi.getMaterialPreviewUrl(filename),
          path: filePath,
          size: blob.size,
          type: 'image/png',
        }
        if (cropTarget.value === 'portrait') {
          commonConfig.coverPortrait = coverData
        } else {
          commonConfig.coverLandscape = coverData
        }
        cropDialogVisible.value = false
        ElMessage.success('封面裁剪完成')
      } else {
        ElMessage.error(resp.msg || '裁剪上传失败')
      }
    }).catch(() => {
      ElMessage.error('裁剪上传失败')
    })
  }, 'image/png')
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
  } else {
    ElMessage.error(response.msg || '上传失败')
  }
}

function handleCoverUploadSuccess(response, file) {
  if (response.code === 200) {
    const filePath = response.data.path || response.data
    const filename = filePath.split('/').pop()
    const coverData = {
      name: file.name,
      url: materialApi.getMaterialPreviewUrl(filename),
      path: filePath,
      size: file.size,
      type: file.type,
    }
    if (coverUploadTarget.value === 'portrait') {
      commonConfig.coverPortrait = coverData
    } else {
      commonConfig.coverLandscape = coverData
    }
    coverUploadDialogVisible.value = false
    ElMessage.success('封面上传成功')
  } else {
    ElMessage.error(response.msg || '上传失败')
  }
}

function handleUploadError() {
  ElMessage.error('文件上传失败')
}

function handleCoverFileChange(e) {
  // handled by el-upload dialog
}

// ========== Material Library ==========

async function selectFromLibrary(mode = 'video', coverTarget = 'landscape') {
  materialLibraryMode.value = mode
  materialLibraryCoverTarget.value = coverTarget
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
    // 视频模式：取第一个素材放入对应格式位
    const material = materials.value.find(m => m.id === selectedMaterials.value[0])
    if (material) {
      const videoData = {
        name: material.filename,
        url: materialApi.getMaterialPreviewUrl(material.file_path.split('/').pop()),
        path: material.file_path,
        size: material.filesize * 1024 * 1024,
        type: 'video/mp4',
      }
      if (materialLibraryCoverTarget.value === 'portrait') {
        commonConfig.videoPortrait = videoData
      } else {
        commonConfig.videoLandscape = videoData
      }
    }
    ElMessage.success('素材已添加')
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

function confirmAccountSelection() {
  tempSelectedAccounts.value.forEach(id => {
    publishAccountIds.add(id)
  })
  accountDialogVisible.value = false
  ElMessage.success(`已选择 ${tempSelectedAccounts.value.length} 个账号`)
  tempSelectedAccounts.value = []
}

// ========== Publish Methods ==========

function saveDraft() {
  try {
    const draftData = {
      commonConfig: {
        topics: [...commonConfig.topics],
        fileList: commonConfig.fileList.map(f => ({ name: f.name, path: f.path, url: f.url, size: f.size, type: f.type })),
        coverLandscape: commonConfig.coverLandscape ? { name: commonConfig.coverLandscape.name, path: commonConfig.coverLandscape.path, url: commonConfig.coverLandscape.url, size: commonConfig.coverLandscape.size, type: commonConfig.coverLandscape.type } : null,
        coverPortrait: commonConfig.coverPortrait ? { name: commonConfig.coverPortrait.name, path: commonConfig.coverPortrait.path, url: commonConfig.coverPortrait.url, size: commonConfig.coverPortrait.size, type: commonConfig.coverPortrait.type } : null,
      },
      platformConfigs: JSON.parse(JSON.stringify(platformConfigs)),
      savedAt: new Date().toISOString(),
    }
    localStorage.setItem('publishDraft', JSON.stringify(draftData))
    ElMessage.success('草稿已保存')
  } catch (e) {
    ElMessage.error('草稿保存失败')
  }
}

async function publishAll() {
  // Validate
  if (commonConfig.fileList.length === 0) {
    ElMessage.error('请先上传视频文件')
    return
  }

  // Check each platform with selected accounts has a title
  const platformsWithoutTitle = []
  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    if (!group.accounts.some(a => publishAccountIds.has(a.id))) continue
    const pSettings = platformConfigs[group.key]
    if (!pSettings || !pSettings.title.trim()) {
      platformsWithoutTitle.push(group.name)
    }
  }
  if (platformsWithoutTitle.length > 0) {
    ElMessage.error(`以下平台未设置标题：${platformsWithoutTitle.join('、')}`)
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
      allTasks.push({ account, group, platformSettings: { ...pSettings } })
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

    try {
      // 解析平台自定义标签：支持 "#xx #xx" 和 "xx,xx" 两种格式
      const customTags = (platformSettings.tags || '').split(/[,，\s]+/).map(t => t.replace(/^#/, '').trim()).filter(Boolean)
      const allTags = [...commonConfig.topics, ...customTags]

      const publishData = {
        type: group.id,
        title: platformSettings.title,
        description: platformSettings.description || '',
        tags: allTags,
        fileList: commonConfig.fileList.map(f => f.path),
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
        creationDeclaration: platformSettings.creationDeclaration || '',
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
      width: 22px;
      height: 22px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      flex-shrink: 0;
    }

    .group-name {
      flex: 1;
      font-size: 13px;
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
      font-size: 12px;
      color: $text-muted;
      opacity: 0;
      transition: $transition-fast;
      flex-shrink: 0;
      margin-left: 2px;

      &:hover {
        color: $danger-color;
      }
    }

    &:hover .account-remove {
      opacity: 1;
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
}

// ========== Config Section ==========
.config-section {
  margin-bottom: 24px;
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

// ----- Video Empty -----
.video-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 0;
  gap: 10px;

  .empty-icon {
    color: $text-muted;
    opacity: 0.4;
  }

  .empty-text {
    font-size: 13px;
    color: $text-muted;
  }

  .empty-actions {
    display: flex;
    gap: 8px;
    margin-top: 6px;
  }
}

// ----- Video Filled (player + sidebar) -----
.video-filled {
  display: flex;
  gap: 16px;
  min-height: 220px;

  .video-player-wrap {
    flex: 1;
    min-width: 0;
    border-radius: $radius-base;
    overflow: hidden;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;

    .video-player {
      width: 100%;
      max-height: 300px;
      display: block;
      outline: none;
    }
  }

  .video-sidebar {
    width: 200px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;

    .video-file-list {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .video-file-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 8px;
      border-radius: $radius-sm;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid transparent;
      cursor: pointer;
      transition: $transition-base;
      font-size: 12px;

      &:hover {
        background: rgba(255, 255, 255, 0.06);
      }

      &.active {
        border-color: $brand-start;
        background: rgba(139, 92, 246, 0.08);
      }

      .file-name {
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: $text-primary;
      }

      .file-size {
        font-size: 10px;
        color: $text-muted;
        flex-shrink: 0;
      }

      .remove-icon {
        color: $text-muted;
        opacity: 0;
        transition: $transition-fast;
        font-size: 12px;

        &:hover {
          color: $danger-color;
        }
      }

      &:hover .remove-icon {
        opacity: 1;
      }
    }

    .video-actions {
      display: flex;
      flex-direction: column;
      gap: 6px;

      .cover-action-btn {
        justify-content: center;
      }
    }
  }
}

// ----- Video Dual Card Grid -----
.video-dual-grid {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.video-card {
  flex: 1;
  border: 1px dashed $border;
  border-radius: $radius-base;
  overflow: hidden;
  transition: $transition-base;

  &:hover {
    border-color: $border-active;
  }

  .video-card-label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: rgba(255, 255, 255, 0.03);
    font-size: 12px;
    font-weight: 500;
    color: $text-secondary;

    .video-ratio {
      font-size: 10px;
      color: $text-muted;
      background: rgba(255, 255, 255, 0.06);
      padding: 2px 6px;
      border-radius: 4px;
    }
  }

  .video-card-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 40px 0;
    color: $text-muted;
    cursor: pointer;
    transition: $transition-base;

    &:hover {
      background: rgba(255, 255, 255, 0.03);
      color: $brand-start;
      .video-card-empty-text { color: $brand-start; }
    }

    .video-card-empty-text { font-size: 12px; transition: $transition-fast; }
  }

  .video-card-preview {
    position: relative;
    video {
      width: 100%;
      display: block;
      max-height: 200px;
      outline: none;
    }
    .video-card-overlay {
      position: absolute;
      bottom: 0; left: 0; right: 0;
      display: flex;
      justify-content: center;
      gap: 12px;
      padding: 8px 0;
      background: linear-gradient(transparent, rgba(0,0,0,0.7));
      opacity: 0;
      transition: $transition-base;
      .overlay-btn {
        padding: 3px 10px;
        border: none; border-radius: 4px;
        background: rgba(255,255,255,0.15);
        color: #fff; font-size: 12px;
        cursor: pointer; transition: $transition-fast;
        outline: none; font-family: inherit;
        &:hover { background: rgba(255,255,255,0.25); }
        &.danger:hover { background: rgba($danger-color,0.6); }
      }
    }
    &:hover .video-card-overlay { opacity: 1; }
  }

  .video-card-actions {
    display: flex;
    gap: 8px;
    padding: 8px 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
    .cover-action-btn { flex: 1; }
  }
}

// ----- Cover Section -----
.cover-section {
  // overrides if needed
}

.cover-grid {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.cover-card {
  flex: 1;
  border: 1px dashed $border;
  border-radius: $radius-base;
  overflow: hidden;
  transition: $transition-base;

  &:hover {
    border-color: $border-active;
  }

  .cover-card-label {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    background: rgba(255, 255, 255, 0.03);
    font-size: 12px;
    font-weight: 500;
    color: $text-secondary;

    .cover-ratio {
      font-size: 10px;
      color: $text-muted;
      background: rgba(255, 255, 255, 0.06);
      padding: 2px 6px;
      border-radius: 4px;
    }
  }

  .cover-empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 24px 0;
    color: $text-muted;
    cursor: pointer;
    transition: $transition-base;

    &:hover {
      background: rgba(255, 255, 255, 0.03);
      color: $brand-start;

      .cover-empty-text {
        color: $brand-start;
      }
    }

    .cover-empty-text {
      font-size: 12px;
      transition: $transition-fast;
    }
  }

  .cover-card-actions {
    display: flex;
    gap: 8px;
    padding: 8px 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);

    .cover-action-btn {
      flex: 1;
    }
  }

  .cover-preview-wrap {
    position: relative;
    display: flex;
    justify-content: center;

    .cover-preview {
      display: block;
      height: 360px;
      width: auto;
      max-width: 100%;
      object-fit: contain;
    }

    .cover-preview-overlay {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      display: flex;
      justify-content: center;
      gap: 12px;
      padding: 8px 0;
      background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
      opacity: 0;
      transition: $transition-base;

      .overlay-btn {
        padding: 3px 10px;
        border: none;
        border-radius: 4px;
        background: rgba(255, 255, 255, 0.15);
        color: #fff;
        font-size: 12px;
        cursor: pointer;
        transition: $transition-fast;
        outline: none;
        font-family: inherit;

        &:hover {
          background: rgba(255, 255, 255, 0.25);
        }

        &.danger:hover {
          background: rgba($danger-color, 0.6);
        }
      }
    }

    &:hover .cover-preview-overlay {
      opacity: 1;
    }
  }
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
    .account-dialog-toolbar {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;

      .account-search-input {
        flex: 1;
      }
    }

    .account-dialog-content {
      display: flex;
      gap: 0;
      border: 1px solid $border;
      border-radius: $radius-base;
      overflow: hidden;
      min-height: 320px;
    }

    .dialog-platform-list {
      width: 140px;
      flex-shrink: 0;
      border-right: 1px solid $border;
      background: rgba(0, 0, 0, 0.2);
      overflow-y: auto;

      .dialog-platform-item {
        padding: 10px 12px;
        font-size: 13px;
        color: $text-secondary;
        display: flex;
        align-items: center;
        gap: 8px;
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
          width: 18px;
          height: 18px;
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #fff;
          font-size: 9px;
          font-weight: 700;
          flex-shrink: 0;
        }
      }
    }

    .dialog-account-list {
      flex: 1;
      padding: 12px;
      overflow-y: auto;

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
.cover-upload-dialog {
  .video-upload,
  .cover-upload {
    width: 100%;

    :deep(.el-upload-dragger) {
      width: 100%;
      height: 180px;
      background: rgba(255, 255, 255, 0.02);
      border-color: $border;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      transition: $transition-base;

      &:hover {
        border-color: $border-active;
      }

      .el-icon--upload {
        color: $text-muted;
        margin-bottom: 8px;
      }
    }

    .el-upload__text {
      color: $text-secondary;
      font-size: 14px;

      em {
        color: $brand-start;
      }
    }

    .el-upload__tip {
      color: $text-muted;
      font-size: 12px;
      margin-top: 8px;
    }
  }
}

// ========== Crop Dialog ==========
.crop-dialog {
  .crop-container {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .crop-canvas-wrap {
    position: relative;
    width: fit-content;
    margin: 0 auto;
    background: #000;
    border-radius: $radius-base;
    overflow: hidden;
  }

  .crop-canvas {
    display: block;
  }

  .crop-selection {
    position: absolute;
    border: 2px solid $brand-start;
    cursor: move;
    box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.5);
  }

  .crop-handle {
    position: absolute;
    width: 10px;
    height: 10px;
    background: $brand-start;
    border: 1px solid #fff;
    border-radius: 2px;

    &.top-left { top: -5px; left: -5px; cursor: nw-resize; }
    &.top-right { top: -5px; right: -5px; cursor: ne-resize; }
    &.bottom-left { bottom: -5px; left: -5px; cursor: sw-resize; }
    &.bottom-right { bottom: -5px; right: -5px; cursor: se-resize; }
  }

  .crop-info {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 12px;
    color: $text-muted;

    .crop-size {
      color: $text-secondary;
    }
  }
}

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
