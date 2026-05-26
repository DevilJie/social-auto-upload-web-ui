<template>
  <div class="settings-page" v-loading="loading">
    <h1 class="page-title">系统设置</h1>
    <p class="page-subtitle">配置应用偏好</p>

    <!-- 代理设置 -->
    <div class="settings-card">
      <h3 class="card-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        网络代理
      </h3>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">HTTP 代理地址</span>
          <span class="setting-desc">用于 YouTube、TikTok 等海外平台的浏览器连接，国内平台无需代理</span>
        </div>
        <div class="setting-control">
          <el-input
            v-model="settings.proxyUrl"
            placeholder="http://127.0.0.1:7897"
            style="width: 300px"
            clearable
          />
        </div>
      </div>
      <div class="proxy-platforms">
        <span class="proxy-tag" v-for="p in overseasPlatforms" :key="p.key">
          <img :src="p.logo" :alt="p.name" class="proxy-tag-logo" />
          {{ p.name }}
        </span>
      </div>
    </div>

    <!-- 发布设置 -->
    <div class="settings-card">
      <h3 class="card-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
        发布设置
      </h3>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">上传视频后自动填充标题</span>
          <span class="setting-desc">上传视频成功后，自动将文件名填入所有渠道的标题字段</span>
        </div>
        <div class="setting-control">
          <el-switch v-model="settings.autoFillTitle" />
        </div>
      </div>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">自动保存草稿</span>
          <span class="setting-desc">发布界面内容（视频、封面、标题、描述等）发生变更时，自动定时将当前内容保存为草稿，避免意外丢失</span>
        </div>
        <div class="setting-control">
          <el-switch v-model="settings.autoSaveDraft" />
        </div>
      </div>
      <div class="setting-row" v-if="settings.autoSaveDraft">
        <div class="setting-info">
          <span class="setting-label">自动保存间隔（秒）</span>
          <span class="setting-desc">检测到内容变更后，等待指定时间再执行保存。间隔过短可能频繁触发请求，建议设置为 10-30 秒</span>
        </div>
        <div class="setting-control">
          <el-input-number v-model="settings.autoSaveInterval" :min="10" :max="300" controls-position="right" style="width: 120px" />
        </div>
      </div>
    </div>

    <!-- 缓存管理 -->
    <div class="settings-card">
      <h3 class="card-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        缓存管理
      </h3>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">清理抽帧缓存</span>
          <span class="setting-desc">清除 data/frames/ 目录下所有已提取的视频帧画面，释放磁盘空间</span>
        </div>
        <div class="setting-control">
          <span v-if="cacheInfo.frames.count > 0" class="cache-size">{{ cacheInfo.frames.count }} 个文件 · {{ formatSize(cacheInfo.frames.size) }}</span>
          <span v-else class="cache-size empty">无缓存</span>
          <button class="cache-btn" :disabled="clearingCache || cacheInfo.frames.count === 0" @click="handleClearCache('frames')">
            {{ clearingCache ? '清理中...' : '清理缓存' }}
          </button>
        </div>
      </div>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">清理日志文件</span>
          <span class="setting-desc">清除 7 天前的日志文件，保留最近一周的日志</span>
        </div>
        <div class="setting-control">
          <span v-if="cacheInfo.logs.oldCount > 0" class="cache-size">{{ cacheInfo.logs.oldCount }} 个过期文件 · {{ formatSize(cacheInfo.logs.size) }}</span>
          <span v-else class="cache-size empty">无过期日志</span>
          <button class="cache-btn" :disabled="clearingCache || cacheInfo.logs.oldCount === 0" @click="handleClearCache('logs')">
            {{ clearingCache ? '清理中...' : '清理日志' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 关于系统 -->
    <div class="settings-card">
      <h3 class="card-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        技术栈
      </h3>
      <div class="tech-grid">
        <div class="tech-section">
          <h4 class="tech-section-title">版本</h4>
          <div class="version-badge">v{{ appVersion }}</div>
        </div>
        <div class="tech-section">
          <h4 class="tech-section-title">前端</h4>
          <div class="tech-item" v-for="item in frontendStack" :key="item.name">
            <span class="tech-name">{{ item.name }}</span>
            <span class="tech-version">{{ item.version }}</span>
          </div>
        </div>
        <div class="tech-section">
          <h4 class="tech-section-title">后端</h4>
          <div class="tech-item" v-for="item in backendStack" :key="item.name">
            <span class="tech-name">{{ item.name }}</span>
            <span class="tech-version">{{ item.version }}</span>
          </div>
        </div>
        <div class="tech-section">
          <h4 class="tech-section-title">浏览器引擎</h4>
          <div class="tech-item" v-for="item in browserStack" :key="item.name">
            <span class="tech-name">{{ item.name }}</span>
            <span class="tech-version">{{ item.version }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Save button -->
    <div class="save-bar">
      <button class="save-btn" :disabled="saving" @click="handleSave">
        {{ saving ? '保存中...' : '保存设置' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingsApi } from '@/api/v2'
import { platformList } from '@/config/platforms'
import { http } from '@/utils/request'

const loading = ref(false)
const saving = ref(false)
const clearingCache = ref(false)
const appVersion = ref('--')
const cacheInfo = reactive({
  frames: { count: 0, size: 0 },
  logs: { count: 0, size: 0, oldCount: 0 },
})

const fetchSystemInfo = async () => {
  try {
    const res = await http.get('/api/system-info')
    if (res.code === 200 && res.data) {
      appVersion.value = res.data.version || '--'
      if (res.data.cache) {
        cacheInfo.frames = res.data.cache.frames || { count: 0, size: 0 }
        cacheInfo.logs = res.data.cache.logs || { count: 0, size: 0, oldCount: 0 }
      }
    }
  } catch {}
}

const formatSize = (bytes) => {
  if (!bytes) return '0B'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}

const handleClearCache = async (target) => {
  const messages = { frames: '抽帧缓存', logs: '日志文件' }
  const confirmMessages = { frames: '确定要清理所有抽帧缓存数据吗？清理后下次使用封面功能时会重新提取视频帧。', logs: '确定要清理所有过期日志文件吗？' }
  try {
    await ElMessageBox.confirm(
      confirmMessages[target],
      '确认清理',
      { confirmButtonText: '确定清理', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  clearingCache.value = true
  try {
    const res = await http.post('/api/clear-cache', { targets: [target] })
    if (res.code === 200) {
      const info = res.data?.[target]
      ElMessage.success(info ? `已清理 ${info.cleared} 个${messages[target]}` : `${messages[target]}已清理`)
      fetchSystemInfo()
    } else {
      ElMessage.error(res.msg || '清理失败')
    }
  } catch {
    ElMessage.error('清理失败')
  } finally {
    clearingCache.value = false
  }
}

const settings = reactive({
  proxyUrl: '',
  autoFillTitle: true,
  autoSaveDraft: true,
  autoSaveInterval: 10,
})

// 海外平台列表
const overseasPlatforms = platformList.filter(p => ['youtube', 'tiktok'].includes(p.key))

// 技术栈版本
const frontendStack = [
  { name: 'Vue', version: '3.5.x' },
  { name: 'Element Plus', version: '2.9.x' },
  { name: 'Vite', version: '6.3.x' },
  { name: 'Pinia', version: '3.0.x' },
  { name: 'Axios', version: '1.9.x' },
]

const backendStack = [
  { name: 'Python', version: '3.14' },
  { name: 'Flask', version: '3.1.x' },
  { name: 'SQLite', version: '3.x' },
]

const browserStack = [
  { name: 'CloakBrowser', version: 'latest' },
  { name: 'Chromium', version: 'latest' },
]

const fetchSettings = async () => {
  loading.value = true
  try {
    const res = await settingsApi.getSettings()
    if (res.code === 200 && res.data) {
      if (res.data.proxyUrl !== undefined) settings.proxyUrl = res.data.proxyUrl
      if (res.data.autoFillTitle !== undefined) settings.autoFillTitle = res.data.autoFillTitle
      if (res.data.autoSaveDraft !== undefined) settings.autoSaveDraft = res.data.autoSaveDraft
      if (res.data.autoSaveInterval !== undefined) settings.autoSaveInterval = res.data.autoSaveInterval
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  saving.value = true
  try {
    const res = await settingsApi.updateSettings({
      proxyUrl: settings.proxyUrl,
      autoFillTitle: settings.autoFillTitle,
      autoSaveDraft: settings.autoSaveDraft,
      autoSaveInterval: settings.autoSaveInterval,
    })
    if (res.code === 200) {
      ElMessage.success('设置已保存')
    } else {
      ElMessage.error(res.msg || '保存失败')
    }
  } catch (e) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  fetchSettings()
  fetchSystemInfo()
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.settings-page {
  padding: 0 28px;

  .page-title {
    font-size: 24px;
    font-weight: 600;
    color: $text-primary;
    margin: 0 0 8px 0;
  }

  .page-subtitle {
    font-size: 14px;
    color: $text-secondary;
    margin: 0 0 $spacing-lg 0;
  }

  .settings-card {
    background: $bg-elevated;
    border: 1px solid $border;
    border-radius: $radius-card;
    padding: $spacing-lg;
    margin-bottom: $spacing-md;

    .card-title {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 16px;
      font-weight: 600;
      color: $text-primary;
      margin: 0 0 $spacing-lg 0;
      padding-bottom: $spacing-sm;
      border-bottom: 1px solid $border;

      .title-icon {
        width: 20px;
        height: 20px;
        color: $text-secondary;
      }
    }

    .setting-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 0;

      &:not(:last-child) {
        border-bottom: 1px solid $border-light;
      }

      .setting-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
        flex: 1;

        .setting-label {
          font-size: 14px;
          color: $text-primary;
          font-weight: 500;
        }

        .setting-desc {
          font-size: 12px;
          color: $text-muted;
          line-height: 1.5;
        }
      }

      .setting-control {
        flex-shrink: 0;
        margin-left: $spacing-lg;
        display: flex;
        align-items: center;
        gap: 12px;
      }

      .cache-size {
        font-size: 12px;
        color: $text-muted;
        font-family: 'Fira Code', monospace;
        white-space: nowrap;

        &.empty {
          opacity: 0.5;
        }
      }

      .cache-btn {
        padding: 8px 20px;
        border: 1px solid rgba($danger-color, 0.3);
        border-radius: $radius-base;
        background: rgba($danger-color, 0.06);
        color: $danger-color;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: $transition-base;
        font-family: inherit;
        outline: none;

        &:hover:not(:disabled) {
          background: rgba($danger-color, 0.12);
          border-color: rgba($danger-color, 0.5);
        }

        &:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      }
    }

    .proxy-platforms {
      display: flex;
      gap: $spacing-sm;
      margin-top: $spacing-sm;
      padding-left: 4px;

      .proxy-tag {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 14px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
        background: $bg-surface;
        border: 1px solid $border;
        color: $text-secondary;

        .proxy-tag-logo {
          width: 16px;
          height: 16px;
          border-radius: 3px;
        }
      }
    }
  }

  // ── Tech stack section ──
  .tech-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: $spacing-lg;

    @media (max-width: 768px) {
      grid-template-columns: 1fr;
    }

    .tech-section {
      .version-badge {
        display: inline-flex;
        align-items: center;
        padding: 8px 20px;
        border-radius: 8px;
        background: $gradient-brand;
        color: #fff;
        font-size: 18px;
        font-weight: 700;
        font-family: 'Fira Code', monospace;
        letter-spacing: 0.5px;
      }

      .tech-section-title {
        font-size: 12px;
        font-weight: 600;
        color: $text-muted;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin: 0 0 $spacing-sm 0;
      }

      .tech-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0;
        border-bottom: 1px solid $border-light;

        &:last-child {
          border-bottom: none;
        }

        .tech-name {
          font-size: 14px;
          color: $text-primary;
        }

        .tech-version {
          font-size: 13px;
          color: $text-muted;
          font-family: 'Fira Code', monospace;
        }
      }
    }
  }

  .save-bar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 16px;
    padding: $spacing-lg 0;

    .save-btn {
      padding: 10px 32px;
      border: none;
      border-radius: $radius-base;
      font-size: 14px;
      font-weight: 500;
      color: #fff;
      background: $gradient-brand;
      cursor: pointer;
      transition: opacity $transition-base;

      &:hover:not(:disabled) {
        opacity: 0.9;
      }

      &:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
    }
  }

  // Element Plus overrides for dark theme consistency
  :deep(.el-input__wrapper),
  :deep(.el-select__wrapper),
  :deep(.el-input-number) {
    background-color: $bg-surface;
    box-shadow: 0 0 0 1px $border inset;
  }

  :deep(.el-input__inner),
  :deep(.el-select__placeholder),
  :deep(.el-input-number .el-input__inner) {
    color: $text-primary;
  }
}
</style>
