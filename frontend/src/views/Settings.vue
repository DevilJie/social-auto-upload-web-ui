<template>
  <div class="settings-page" v-loading="loading">
    <h1 class="page-title">系统设置</h1>
    <p class="page-subtitle">配置应用偏好</p>

    <!-- 基本设置 -->
    <div class="settings-card">
      <h3 class="card-title">基本设置</h3>
      <div class="setting-row">
        <span class="setting-label">后端地址</span>
        <el-input
          v-model="settings.apiBaseUrl"
          placeholder="http://localhost:8080"
          style="width: 320px"
        />
      </div>
      <div class="setting-row">
        <span class="setting-label">最大并发任务数</span>
        <el-select v-model="settings.maxConcurrent" style="width: 200px">
          <el-option v-for="n in 5" :key="n" :label="n" :value="n" />
        </el-select>
      </div>
      <div class="setting-row">
        <span class="setting-label">默认重试次数</span>
        <el-select v-model="settings.defaultRetry" style="width: 200px">
          <el-option v-for="n in 5" :key="n" :label="n" :value="n" />
        </el-select>
      </div>
    </div>

    <!-- 发布设置 -->
    <div class="settings-card">
      <h3 class="card-title">发布设置</h3>
      <div class="setting-row">
        <span class="setting-label">默认发布平台</span>
        <el-select v-model="settings.defaultPlatform" placeholder="请选择平台" style="width: 200px">
          <el-option label="抖音" value="douyin" />
          <el-option label="快手" value="kuaishou" />
          <el-option label="视频号" value="channels" />
          <el-option label="小红书" value="xiaohongshu" />
        </el-select>
      </div>
      <div class="setting-row">
        <span class="setting-label">默认声明原创</span>
        <el-switch v-model="settings.defaultOriginal" />
      </div>
      <div class="setting-row">
        <span class="setting-label">视频号默认存草稿</span>
        <el-switch v-model="settings.defaultDraft" />
      </div>
    </div>

    <!-- 账号设置 -->
    <div class="settings-card">
      <h3 class="card-title">账号设置</h3>
      <div class="setting-row">
        <span class="setting-label">Cookie过期提醒天数</span>
        <el-input-number v-model="settings.cookieWarningDays" :min="1" :max="30" style="width: 200px" />
      </div>
      <div class="setting-row">
        <span class="setting-label">自动验证账号状态</span>
        <el-switch v-model="settings.autoVerify" />
      </div>
    </div>

    <!-- 关于系统 -->
    <div class="settings-card">
      <h3 class="card-title">关于系统</h3>
      <div class="setting-row">
        <span class="setting-label">版本号</span>
        <span class="setting-value">1.0.0</span>
      </div>
      <div class="setting-row">
        <span class="setting-label">技术栈</span>
        <span class="setting-value">Vue 3 + Element Plus + Vite + Flask</span>
      </div>
      <div class="setting-row">
        <span class="setting-label">支持平台</span>
        <div class="platform-tags">
          <span class="platform-tag douyin">抖音</span>
          <span class="platform-tag kuaishou">快手</span>
          <span class="platform-tag channels">视频号</span>
          <span class="platform-tag xiaohongshu">小红书</span>
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

const loading = ref(false)
const saving = ref(false)

const settings = reactive({
  apiBaseUrl: '',
  maxConcurrent: 2,
  defaultRetry: 3,
  defaultPlatform: '',
  defaultOriginal: false,
  defaultDraft: false,
  cookieWarningDays: 7,
  autoVerify: false,
})

const fetchSettings = async () => {
  loading.value = true
  try {
    const res = await settingsApi.getSettings()
    if (res.code === 200 && res.data) {
      Object.keys(res.data).forEach(key => {
        if (key in settings) settings[key] = res.data[key]
      })
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
    const res = await settingsApi.updateSettings({ ...settings })
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
      font-size: 16px;
      font-weight: 600;
      color: $text-primary;
      margin: 0 0 $spacing-lg 0;
      padding-bottom: $spacing-sm;
      border-bottom: 1px solid $border;
    }

    .setting-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 0;

      &:not(:last-child) {
        border-bottom: 1px solid $border-light;
      }

      .setting-label {
        font-size: 14px;
        color: $text-secondary;
        flex-shrink: 0;
      }

      .setting-value {
        font-size: 14px;
        color: $text-primary;
      }

      .platform-tags {
        display: flex;
        gap: $spacing-sm;

        .platform-tag {
          display: inline-block;
          padding: 2px 12px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 500;

          &.douyin {
            color: $platform-douyin;
            background: $platform-douyin-bg;
          }

          &.kuaishou {
            color: $platform-kuaishou;
            background: $platform-kuaishou-bg;
          }

          &.channels {
            color: $platform-channels;
            background: $platform-channels-bg;
          }

          &.xiaohongshu {
            color: $platform-xiaohongshu;
            background: $platform-xiaohongshu-bg;
          }
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

  :deep(.el-switch) {
    --el-switch-on-color: #{$brand-start};
  }
}
</style>
