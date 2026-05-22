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

    <!-- 关于系统 -->
    <div class="settings-card">
      <h3 class="card-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
        技术栈
      </h3>
      <div class="tech-grid">
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
import { ElMessage } from 'element-plus'
import { settingsApi } from '@/api/v2'
import { platformList } from '@/config/platforms'

const loading = ref(false)
const saving = ref(false)

const settings = reactive({
  proxyUrl: '',
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
    grid-template-columns: repeat(3, 1fr);
    gap: $spacing-lg;

    @media (max-width: 768px) {
      grid-template-columns: 1fr;
    }

    .tech-section {
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
    justify-content: flex-end;
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
