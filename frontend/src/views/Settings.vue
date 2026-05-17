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

    <!-- 关于作者 -->
    <div class="settings-card author-card">
      <h3 class="card-title">
        <svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        关于作者
      </h3>
      <div class="author-layout">
        <div class="author-avatar-wrap">
          <img
            class="author-avatar"
            :src="authorInfo.avatar"
            :alt="authorInfo.name"
          />
          <h4 class="author-name">{{ authorInfo.name }}</h4>
          <p class="author-title">{{ authorInfo.title }}</p>
        </div>
        <div class="author-details">
          <p class="author-bio">{{ authorInfo.bio }}</p>
          <div class="author-links">
            <a
              v-for="link in authorInfo.links"
              :key="link.label"
              :href="link.url"
              target="_blank"
              rel="noopener"
              class="author-link"
            >
              <component :is="link.icon" class="link-icon" />
              <span>{{ link.label }}</span>
            </a>
          </div>
        </div>
        <div class="author-qr-section">
          <img
            v-if="authorInfo.wechatQr"
            :src="authorInfo.wechatQr"
            alt="微信名片"
            class="author-qr"
          />
          <span class="qr-label">微信扫码添加</span>
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
import { ref, reactive, onMounted, h } from 'vue'
import { ElMessage } from 'element-plus'
import { settingsApi } from '@/api/v2'
import { platformList } from '@/config/platforms'

// SVG icon components
const GithubIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'currentColor', class: 'link-icon' }, [
      h('path', { d: 'M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z' })
    ])
  }
}

const BlogIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', class: 'link-icon' }, [
      h('path', { d: 'M12 20h9' }),
      h('path', { d: 'M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z' })
    ])
  }
}

const WechatIcon = {
  render() {
    return h('svg', { viewBox: '0 0 24 24', fill: 'currentColor', class: 'link-icon' }, [
      h('path', { d: 'M8.691 2.188C3.891 2.188 0 5.476 0 9.53c0 2.212 1.17 4.203 3.002 5.55a.59.59 0 0 1 .213.665l-.39 1.48c-.019.07-.048.141-.048.213 0 .163.13.295.295.295a.326.326 0 0 0 .167-.054l1.903-1.114a.864.864 0 0 1 .717-.098 10.16 10.16 0 0 0 2.837.403c.276 0 .543-.027.811-.05-.857-2.578.157-4.972 1.932-6.446 1.703-1.415 3.882-1.98 5.853-1.838-.576-3.583-4.196-6.348-8.596-6.348zM5.785 5.991c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178A1.17 1.17 0 0 1 4.623 7.17c0-.651.52-1.18 1.162-1.18zm5.813 0c.642 0 1.162.529 1.162 1.18a1.17 1.17 0 0 1-1.162 1.178 1.17 1.17 0 0 1-1.162-1.178c0-.651.52-1.18 1.162-1.18zm3.164 4.508c-3.71 0-7.48 2.57-7.48 5.852 0 3.352 3.247 5.852 7.48 5.852a9.036 9.036 0 0 0 2.45-.34.727.727 0 0 1 .596.083l1.525.89a.262.262 0 0 0 .134.045c.132 0 .24-.108.24-.24 0-.058-.023-.115-.038-.17l-.312-1.186a.486.486 0 0 1 .174-.546C21.717 19.969 24 18.193 24 16.35c0-3.283-3.77-5.852-7.238-5.852zm-2.505 2.456c.537 0 .972.442.972.988a.98.98 0 0 1-.972.988.98.98 0 0 1-.973-.988c0-.546.436-.988.973-.988zm5.01 0c.537 0 .973.442.973.988a.98.98 0 0 1-.973.988.98.98 0 0 1-.972-.988c0-.546.435-.988.972-.988z' })
    ])
  }
}

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
  { name: 'Patchright', version: '1.58.x' },
  { name: 'Chromium', version: 'latest' },
]

// 作者信息（后续由用户填充具体内容）
const authorInfo = reactive({
  name: '程序员老蔡',
  title: '全栈开发者 / 开源爱好者',
  avatar: 'https://avatars.githubusercontent.com/u/0?v=4',
  bio: '专注自动化工具开发，热爱开源，致力于提升内容创作者的效率。',
  wechatQr: '',
  links: [
    { label: 'GitHub', url: 'https://github.com/', icon: GithubIcon },
    { label: '个人博客', url: 'https://', icon: BlogIcon },
    { label: '微信公众号', url: '#', icon: WechatIcon },
  ],
})

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
    const res = await settingsApi.updateSettings({ proxyUrl: settings.proxyUrl })
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

  // ── Author section ──
  .author-card {
    .author-layout {
      display: flex;
      gap: $spacing-xl;
      align-items: flex-start;

      @media (max-width: 768px) {
        flex-direction: column;
        align-items: center;
      }
    }

    .author-avatar-wrap {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: $spacing-sm;
      flex-shrink: 0;

      .author-avatar {
        width: 80px;
        height: 80px;
        border-radius: 50%;
        border: 2px solid $border;
        object-fit: cover;
      }

      .author-name {
        font-size: 16px;
        font-weight: 600;
        color: $text-primary;
        margin: 0;
      }

      .author-title {
        font-size: 12px;
        color: $text-muted;
        margin: 0;
      }
    }

    .author-details {
      flex: 1;
      min-width: 0;

      .author-bio {
        font-size: 14px;
        color: $text-secondary;
        line-height: 1.6;
        margin: 0 0 $spacing-md 0;
      }

      .author-links {
        display: flex;
        flex-wrap: wrap;
        gap: $spacing-sm;

        .author-link {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 14px;
          border-radius: $radius-base;
          background: $bg-surface;
          border: 1px solid $border;
          color: $text-secondary;
          font-size: 13px;
          text-decoration: none;
          cursor: pointer;
          transition: all $transition-base;

          &:hover {
            border-color: $brand-start;
            color: $text-primary;
            background: $gradient-brand-subtle;
          }

          .link-icon {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
          }
        }
      }
    }

    .author-qr-section {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: $spacing-xs;
      flex-shrink: 0;

      .author-qr {
        width: 100px;
        height: 100px;
        border-radius: $radius-sm;
        border: 1px solid $border;
        object-fit: cover;
        background: #fff;
      }

      .qr-label {
        font-size: 11px;
        color: $text-muted;
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
