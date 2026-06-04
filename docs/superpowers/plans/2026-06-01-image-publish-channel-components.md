# 图文发布渠道组件化重构 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `ImagePublish.vue`（2535 行）拆分为 1 个壳页面 + 3 个渠道独立组件，渠道组件封装自身布局、样式、脚本、校验、发布逻辑。

**Architecture:** 父页面通过 props 传 `accountId` + `disabled`，通过 emit `config-changed` 和 `publish-result` 接收通知，通过 `defineExpose` 提供的方法（publish / getConfigs / restoreConfigs / syncXXX / validate / hasAccountOverride）被父页面调度。

**Tech Stack:** Vue 3 + Element Plus + Pinia

**Files:**
- Create: `frontend/src/components/douyin/ImagePublishPanel.vue`
- Create: `frontend/src/components/xiaohongshu/ImagePublishPanel.vue`
- Create: `frontend/src/components/kuaishou/ImagePublishPanel.vue`
- Modify: `frontend/src/views/ImagePublish.vue`

---

### Task 1: 创建 `components/douyin/ImagePublishPanel.vue`

**Files:**
- Create: `frontend/src/components/douyin/ImagePublishPanel.vue`

- [ ] **Step 1: 创建组件目录并写入完整代码**

目标：将 `ImagePublish.vue` 中所有抖音特有逻辑移入此组件。复用已有 `components/douyin/` 下的子组件。

```bash
mkdir -p /home/czy/workspace/ai/social-auto-upload-web-ui/frontend/src/components/douyin
```

用 Write 创建 `frontend/src/components/douyin/ImagePublishPanel.vue`，完整内容：

```vue
<template>
  <div class="douyin-image-publish-panel">
    <!-- 恢复默认按钮 -->
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <!-- ① 标题 -->
    <div class="setting-card">
      <div class="setting-label">标题</div>
      <input
        v-model="form.title"
        class="el-input"
        placeholder="请输入标题..."
        maxlength="100"
        :disabled="disabled"
      />
    </div>

    <!-- ② 描述 -->
    <div class="setting-card">
      <div class="setting-label">描述</div>
      <textarea
        v-model="form.description"
        class="el-textarea"
        :rows="5"
        placeholder="请输入描述..."
        maxlength="2000"
        :disabled="disabled"
      ></textarea>
    </div>

    <!-- ③ 标签（热点标签交互模式：回车添加 + Tag 芯片 + 可删除） -->
    <div class="setting-card">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认（官方活动 + 标签最多5个）</div>
      <input
        v-model="tagInput"
        class="el-input"
        placeholder="输入标签内容，按回车添加"
        @keyup.enter="addTag"
        :disabled="disabled"
      />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <span
          v-for="(tag, index) in form.tags"
          :key="index"
          class="tag-chip"
        >
          #{{ tag }}
          <button class="tag-close" @click="removeTag(index)">×</button>
        </span>
      </div>
    </div>

    <!-- ④ 官方活动 -->
    <div class="setting-card">
      <div class="setting-label">官方活动</div>
      <DouyinActivitySelect
        v-model="form.activityId"
        @change="handleActivityChange"
      />
    </div>

    <!-- ⑤ 选择音乐 -->
    <div class="setting-card">
      <div class="setting-label">选择音乐</div>
      <DouyinMusicSelect
        :account-id="accountId"
        v-model="form.selectedMusic"
        :data="form.selectedMusicData"
        @change="handleMusicSelect"
      />
    </div>

    <!-- ⑥ 关联热点 -->
    <div class="setting-card">
      <div class="setting-label">关联热点</div>
      <DouyinHotspotSelect
        v-model="form.hotspotId"
        :data="form.hotspotData"
        @change="handleHotspotChange"
      />
    </div>

    <!-- ⑦ 自主声明 -->
    <div class="setting-card">
      <div class="setting-label">自主声明</div>
      <el-select
        v-model="form.aiContent"
        placeholder="请选择自主声明"
        clearable
        style="width: 100%"
        :disabled="disabled"
      >
        <el-option
          v-for="opt in declarationOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </div>

    <!-- ⑧ 添加标签（地点/小程序/游戏/标记） -->
    <div class="setting-card">
      <div class="setting-label">添加标签</div>
      <DouyinTagSelect
        :account-id="accountId"
        v-model="form.selectedTag"
        @change="handleTagSelect"
      />
    </div>

    <!-- ⑨ 添加合集（仅账号级） -->
    <div v-if="accountId" class="setting-card">
      <div class="setting-label">添加合集</div>
      <DouyinMixSelect
        :account-id="accountId"
        v-model="form.mixId"
        :data="form.mixData"
        @change="handleMixChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { PLATFORMS } from '@/config/platforms'
import DouyinActivitySelect from './ActivitySelect.vue'
import DouyinMusicSelect from './MusicSelect.vue'
import DouyinHotspotSelect from './HotspotSelect.vue'
import DouyinTagSelect from './TagSelect.vue'
import DouyinMixSelect from './MixSelect.vue'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// ===== 渠道默认配置 =====
const DOUYIN_DEFAULTS = {
  ...PLATFORMS.DOUYIN.defaultSettings,
  tags: [],
}

// ===== 内部状态 =====
const platformConfig = reactive({ ...DOUYIN_DEFAULTS })
const accountOverrides = reactive({})
const form = reactive({ ...platformConfig })

// ===== 标签输入 =====
const tagInput = ref('')

// ===== 自主声明选项 =====
const declarationOptions = computed(() => {
  const field = PLATFORMS.DOUYIN.settingsFields.find(f => f.key === 'aiContent')
  return field?.options || []
})

// ===== 监听 accountId 切换表单 =====
watch(() => props.accountId, (newId) => {
  if (!newId) {
    // 切换到渠道默认
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, { ...platformConfig })
  } else {
    const override = accountOverrides[newId]
    const hasOverride = override && Object.keys(override).some(
      k => override[k] !== undefined && override[k] !== '' && override[k] !== false
        && !(Array.isArray(override[k]) && override[k].length === 0)
    )
    Object.keys(form).forEach(k => delete form[k])
    if (hasOverride) {
      const merged = { ...platformConfig }
      for (const [k, v] of Object.entries(override)) {
        if (v !== undefined && v !== '' && v !== false
            && !(Array.isArray(v) && v.length === 0)) {
          merged[k] = v
        }
      }
      Object.assign(form, merged)
    } else {
      Object.assign(form, { ...platformConfig })
    }
  }
}, { immediate: true })

// ===== 表单变更同步到 platformConfig / accountOverrides =====
watch(form, (newVal) => {
  if (!props.accountId) {
    // 渠道级：直接写入 platformConfig
    for (const key of Object.keys(newVal)) {
      if (Array.isArray(newVal[key])) {
        platformConfig[key] = [...newVal[key]]
      } else {
        platformConfig[key] = newVal[key]
      }
    }
  } else {
    // 账号级：计算与渠道默认的差异
    const diff = {}
    for (const key of Object.keys(newVal)) {
      const current = newVal[key]
      const fallback = platformConfig[key]
      // 复杂类型用 JSON 比较
      if (typeof current === 'object' && current !== null) {
        if (JSON.stringify(current) !== JSON.stringify(fallback)) {
          diff[key] = Array.isArray(current) ? [...current] : { ...current }
        }
      } else if (current !== fallback) {
        diff[key] = current
      }
    }
    const hasValues = Object.entries(diff).some(([, v]) => {
      if (Array.isArray(v)) return v.length > 0
      if (typeof v === 'object' && v !== null) return Object.keys(v).length > 0
      return v !== undefined && v !== '' && v !== false
    })
    if (hasValues) {
      accountOverrides[props.accountId] = { ...diff }
    } else {
      delete accountOverrides[props.accountId]
    }
  }
  emit('config-changed')
}, { deep: true })

// ===== 标签操作 =====
function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return

  const activityCount = form.activityId?.length || 0
  const tagCount = form.tags?.length || 0
  if (activityCount + tagCount >= 5) {
    ElMessage.warning('官方活动 + 标签最多 5 个')
    return
  }

  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) {
    ElMessage.warning('标签已存在')
    return
  }

  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) {
  form.tags.splice(index, 1)
}

// ===== 活动选择 =====
function handleActivityChange(activity) {
  if (activity && activity.challenge && activity.challenge.length > 0) {
    for (const topic of activity.challenge) {
      if (form.tags && !form.tags.includes(topic)) {
        // Check limit before adding
        const activityCount = form.activityId?.length || 0
        const tagCount = form.tags?.length || 0
        if (activityCount + tagCount >= 5) break
        form.tags.push(topic)
      }
    }
  }
}

// ===== 音乐选择 =====
function handleMusicSelect(music) {
  if (music) {
    form.selectedMusic = music.title || music.name || ''
    form.selectedMusicData = music
    ElMessage.success(`音乐已选择: ${form.selectedMusic}`)
  } else {
    form.selectedMusic = ''
    form.selectedMusicData = null
  }
}

// ===== 热点选择 =====
function handleHotspotChange(hotspot) {
  if (hotspot) {
    form.hotspotId = hotspot.word
    form.hotspotData = hotspot
  } else {
    form.hotspotId = ''
    form.hotspotData = null
  }
}

// ===== 标签选择（地点/小程序/游戏/标记） =====
function handleTagSelect(tag) {
  if (tag) {
    form.selectedTag = tag
    const typeMap = { 'poi': 'location', 'miniapp': 'miniapp', 'game': 'gamepad', 'mark': 'mark' }
    form.tagType = typeMap[tag.type] || ''
    form.tagValue = tag.name || tag.id || ''
    ElMessage.success(`标签已选择: ${tag.name}`)
  } else {
    form.selectedTag = null
    form.tagType = ''
    form.tagValue = ''
  }
}

// ===== 合集选择 =====
function handleMixChange(mix) {
  if (mix) {
    form.mixId = mix.mix_name
    form.mixData = mix
  } else {
    form.mixId = ''
    form.mixData = null
  }
}

// ===== 恢复默认 =====
function resetOverride() {
  if (props.accountId) {
    delete accountOverrides[props.accountId]
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, { ...platformConfig })
    emit('config-changed')
    ElMessage.success('已恢复为渠道默认设置')
  }
}

// ===== 图片加载失败备选 =====
function onMusicCoverError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjZjVmNWY1Ii8+PHRleHQgeD0iMjAiIHk9IjI0IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPvCflKQ8L3RleHQ+PC9zdmc+'
}

// ===== Exposed 方法 =====
defineExpose({
  // 发布单账号
  async publish(accountId, accountName, commonData) {
    const override = accountOverrides[accountId] || {}
    const merged = { ...platformConfig }
    for (const [k, v] of Object.entries(override)) {
      if (v !== undefined && v !== '' && v !== false
          && !(Array.isArray(v) && v.length === 0)) {
        merged[k] = v
      }
    }

    const account = accountStore.accounts.find(a => a.id === accountId)
    if (!account) {
      emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
      return
    }

    const imageIds = commonData.images.map(img => img.id)
    const selectedTag = merged.selectedTag || null
    const tagTypeMap = { 'poi': 'location', 'miniapp': 'miniapp', 'game': 'gamepad', 'mark': 'mark' }
    let tagValue = ''
    let miniLink = ''
    if (selectedTag) {
      tagValue = selectedTag.name || selectedTag.id || ''
      if (selectedTag.type === 'miniapp') {
        miniLink = selectedTag._searchKeyword || ''
      }
    }

    try {
      await imagePublishApi.publishImage({
        image_ids: imageIds,
        account_configs: [{
          account_id: accountId,
          platform: account.platform,
          filePath: account.filePath,
          title: merged.title,
          description: merged.description || '',
          tags: merged.tags || [],
          scheduleTime: merged.scheduleTime || '',
          aiContent: merged.aiContent || '',
          mix_id: merged.mixId || '',
          music_name: merged.selectedMusic || '',
          hotspot: merged.hotspotId || '',
          hotspot_tags: merged.hotspotTags || [],
          tag_type: selectedTag ? (tagTypeMap[selectedTag.type] || '') : '',
          tag_value: tagValue,
          mini_link: miniLink,
          activities: merged.activityId || [],
          cover_path: commonData.coverImage?.stored_path || '',
          dry_run: false,
        }],
      })
      emit('publish-result', { accountName, status: 'success', message: '发布成功' })
    } catch (e) {
      emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
    }
  },

  // 获取全部配置（草稿保存用）
  getConfigs() {
    return {
      platformConfig: JSON.parse(JSON.stringify(platformConfig)),
      accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
    }
  },

  // 恢复草稿配置
  restoreConfigs(config, overrides) {
    Object.keys(platformConfig).forEach(k => delete platformConfig[k])
    Object.assign(platformConfig, DOUYIN_DEFAULTS, config)
    Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
    if (overrides) Object.assign(accountOverrides, overrides)
    // 刷新表单
    Object.keys(form).forEach(k => delete form[k])
    if (props.accountId) {
      const override = accountOverrides[props.accountId]
      const hasOverride = override && Object.keys(override).some(
        k => override[k] !== undefined && override[k] !== '' && override[k] !== false
          && !(Array.isArray(override[k]) && override[k].length === 0)
      )
      Object.assign(form, hasOverride ? { ...platformConfig, ...override } : { ...platformConfig })
    } else {
      Object.assign(form, { ...platformConfig })
    }
  },

  // 批量同步标题
  syncTitle(title) {
    if (!props.accountId) {
      platformConfig.title = title
      form.title = title
    }
    emit('config-changed')
  },

  // 批量同步描述
  syncDescription(desc) {
    if (!props.accountId) {
      platformConfig.description = desc
      form.description = desc
    }
    emit('config-changed')
  },

  // 批量同步标签
  syncTags(tags) {
    if (!props.accountId) {
      platformConfig.tags = [...tags]
      form.tags = [...tags]
    }
    emit('config-changed')
  },

  // 发布前校验
  validate(accountId) {
    const errors = []
    const override = accountOverrides[accountId] || {}
    const hasOverride = Object.keys(override).some(
      k => override[k] !== undefined && override[k] !== '' && override[k] !== false
        && !(Array.isArray(override[k]) && override[k].length === 0)
    )
    const merged = hasOverride ? { ...platformConfig, ...override } : { ...platformConfig }

    if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
    if (!merged.aiContent) errors.push('请选择自主声明')

    const activityCount = merged.activityId?.length || 0
    const tagCount = merged.tags?.length || 0
    if (activityCount + tagCount > 5) {
      errors.push(`官方活动(${activityCount}) + 标签(${tagCount}) 超过 5 个`)
    }
    return { valid: errors.length === 0, errors }
  },

  // 检查账号是否有覆盖
  hasAccountOverride(accountId) {
    const override = accountOverrides[accountId]
    if (!override) return false
    return Object.values(override).some(
      v => v !== undefined && v !== '' && v !== false
        && !(Array.isArray(v) && v.length === 0)
    )
  },
})
</script>

<style scoped>
.douyin-image-publish-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba(244, 63, 94, 0.15);
  background: rgba(244, 63, 94, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #f43f5e;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.5;
}

.setting-desc {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.6;
}

.el-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.el-input:focus {
  border-color: #f43f5e;
}

.el-input:disabled {
  background: #f5f7fa;
  cursor: not-allowed;
}

.el-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.2s;
}

.el-textarea:focus {
  border-color: #f43f5e;
}

.el-textarea:disabled {
  background: #f5f7fa;
  cursor: not-allowed;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: rgba(244, 63, 94, 0.1);
  color: #f43f5e;
  border: 1px solid rgba(244, 63, 94, 0.2);
  border-radius: 4px;
  font-size: 12px;
}

.tag-close {
  background: none;
  border: none;
  color: #f43f5e;
  cursor: pointer;
  padding: 0;
  font-size: 14px;
  line-height: 1;
}

.tag-close:hover {
  color: #e11d48;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/components/douyin/ImagePublishPanel.vue
git commit -m "feat: 新建抖音图文发布渠道组件 DouyinImagePublishPanel

- 封装抖音渠道全部表单字段：标题/描述/标签/活动/音乐/热点/自主声明/合集
- 标签采用回车添加+Tag芯片+可删除的交互模式
- 自主维护 platformConfig 和 accountOverrides
- 通过 defineExpose 暴露 publish/getConfigs/restoreConfigs/syncXXX/validate/hasAccountOverride
- 活动选择自动添加 challenge 话题到 tags
- 校验规则：标题必填、自主声明必填、活动+标签最多5个

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: 创建 `components/xiaohongshu/ImagePublishPanel.vue`

**Files:**
- Create: `frontend/src/components/xiaohongshu/ImagePublishPanel.vue`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p /home/czy/workspace/ai/social-auto-upload-web-ui/frontend/src/components/xiaohongshu
```

- [ ] **Step 2: 创建组件文件**

用 Write 创建 `frontend/src/components/xiaohongshu/ImagePublishPanel.vue`，完整内容：

```vue
<template>
  <div class="xiaohongshu-image-publish-panel">
    <!-- 小红书反检测警告 -->
    <div class="xhs-warning">
      <el-icon><WarningFilled /></el-icon>
      <span>由于小红书反检测机制比较恶心，如果出现被警告的情况！请立即停止使用小红书渠道！</span>
    </div>

    <!-- 恢复默认按钮 -->
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <!-- ① 标题 -->
    <div class="setting-card">
      <div class="setting-label">标题</div>
      <input
        v-model="form.title"
        class="el-input"
        placeholder="请输入标题..."
        maxlength="100"
        :disabled="disabled"
      />
    </div>

    <!-- ② 描述 -->
    <div class="setting-card">
      <div class="setting-label">描述</div>
      <textarea
        v-model="form.description"
        class="el-textarea"
        :rows="5"
        placeholder="请输入描述..."
        maxlength="2000"
        :disabled="disabled"
      ></textarea>
    </div>

    <!-- ③ 标签 -->
    <div class="setting-card">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认</div>
      <input
        v-model="tagInput"
        class="el-input"
        placeholder="输入标签内容，按回车添加"
        @keyup.enter="addTag"
        :disabled="disabled"
      />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <span
          v-for="(tag, index) in form.tags"
          :key="index"
          class="tag-chip"
        >
          #{{ tag }}
          <button class="tag-close" @click="removeTag(index)">×</button>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { PLATFORMS } from '@/config/platforms'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

const XHS_DEFAULTS = {
  ...PLATFORMS.XIAOHONGSHU.defaultSettings,
  tags: [],
}

const platformConfig = reactive({ ...XHS_DEFAULTS })
const accountOverrides = reactive({})
const form = reactive({ ...platformConfig })
const tagInput = ref('')

// 自主声明选项
const declarationOptions = computed(() => {
  const field = PLATFORMS.XIAOHONGSHU.settingsFields.find(f => f.key === 'aiContent')
  return field?.options || []
})

// 监听 accountId 切换
watch(() => props.accountId, (newId) => {
  Object.keys(form).forEach(k => delete form[k])
  if (!newId) {
    Object.assign(form, { ...platformConfig })
  } else {
    const override = accountOverrides[newId]
    const hasOverride = override && Object.keys(override).some(
      k => override[k] !== undefined && override[k] !== '' && override[k] !== false
        && !(Array.isArray(override[k]) && override[k].length === 0)
    )
    if (hasOverride) {
      const merged = { ...platformConfig }
      for (const [k, v] of Object.entries(override)) {
        if (v !== undefined && v !== '' && v !== false
            && !(Array.isArray(v) && v.length === 0)) merged[k] = v
      }
      Object.assign(form, merged)
    } else {
      Object.assign(form, { ...platformConfig })
    }
  }
}, { immediate: true })

// 表单变更同步
watch(form, (newVal) => {
  if (!props.accountId) {
    for (const key of Object.keys(newVal)) {
      if (Array.isArray(newVal[key])) {
        platformConfig[key] = [...newVal[key]]
      } else {
        platformConfig[key] = newVal[key]
      }
    }
  } else {
    const diff = {}
    for (const key of Object.keys(newVal)) {
      const current = newVal[key]
      const fallback = platformConfig[key]
      if (typeof current === 'object' && current !== null) {
        if (JSON.stringify(current) !== JSON.stringify(fallback)) {
          diff[key] = Array.isArray(current) ? [...current] : { ...current }
        }
      } else if (current !== fallback) {
        diff[key] = current
      }
    }
    const hasValues = Object.entries(diff).some(([, v]) => {
      if (Array.isArray(v)) return v.length > 0
      if (typeof v === 'object' && v !== null) return Object.keys(v).length > 0
      return v !== undefined && v !== '' && v !== false
    })
    if (hasValues) {
      accountOverrides[props.accountId] = { ...diff }
    } else {
      delete accountOverrides[props.accountId]
    }
  }
  emit('config-changed')
}, { deep: true })

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('标签已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) {
  form.tags.splice(index, 1)
}

function resetOverride() {
  if (props.accountId) {
    delete accountOverrides[props.accountId]
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, { ...platformConfig })
    emit('config-changed')
    ElMessage.success('已恢复为渠道默认设置')
  }
}

defineExpose({
  async publish(accountId, accountName, commonData) {
    const override = accountOverrides[accountId] || {}
    const hasOverride = Object.keys(override).some(
      k => override[k] !== undefined && override[k] !== '' && override[k] !== false
        && !(Array.isArray(override[k]) && override[k].length === 0)
    )
    const merged = hasOverride ? { ...platformConfig, ...override } : { ...platformConfig }
    const account = accountStore.accounts.find(a => a.id === accountId)
    if (!account) {
      emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
      return
    }
    const imageIds = commonData.images.map(img => img.id)
    try {
      await imagePublishApi.publishImage({
        image_ids: imageIds,
        account_configs: [{
          account_id: accountId,
          platform: account.platform,
          filePath: account.filePath,
          title: merged.title,
          description: merged.description || '',
          tags: merged.tags || [],
          scheduleTime: merged.scheduleTime || '',
          aiContent: merged.aiContent || '',
          cover_path: commonData.coverImage?.stored_path || '',
          dry_run: false,
        }],
      })
      emit('publish-result', { accountName, status: 'success', message: '发布成功' })
    } catch (e) {
      emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
    }
  },

  getConfigs() {
    return {
      platformConfig: JSON.parse(JSON.stringify(platformConfig)),
      accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
    }
  },

  restoreConfigs(config, overrides) {
    Object.keys(platformConfig).forEach(k => delete platformConfig[k])
    Object.assign(platformConfig, XHS_DEFAULTS, config)
    Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
    if (overrides) Object.assign(accountOverrides, overrides)
    Object.keys(form).forEach(k => delete form[k])
    if (props.accountId) {
      const override = accountOverrides[props.accountId]
      const hasOverride = override && Object.keys(override).some(
        k => override[k] !== undefined && override[k] !== '' && override[k] !== false
          && !(Array.isArray(override[k]) && override[k].length === 0)
      )
      Object.assign(form, hasOverride ? { ...platformConfig, ...override } : { ...platformConfig })
    } else {
      Object.assign(form, { ...platformConfig })
    }
  },

  syncTitle(title) {
    if (!props.accountId) { platformConfig.title = title; form.title = title }
    emit('config-changed')
  },

  syncDescription(desc) {
    if (!props.accountId) { platformConfig.description = desc; form.description = desc }
    emit('config-changed')
  },

  syncTags(tags) {
    if (!props.accountId) { platformConfig.tags = [...tags]; form.tags = [...tags] }
    emit('config-changed')
  },

  validate(accountId) {
    const errors = []
    const override = accountOverrides[accountId] || {}
    const hasOverride = Object.keys(override).some(
      k => override[k] !== undefined && override[k] !== '' && override[k] !== false
        && !(Array.isArray(override[k]) && override[k].length === 0)
    )
    const merged = hasOverride ? { ...platformConfig, ...override } : { ...platformConfig }
    if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
    // 小红书暂不强制声明
    return { valid: errors.length === 0, errors }
  },

  hasAccountOverride(accountId) {
    const override = accountOverrides[accountId]
    if (!override) return false
    return Object.values(override).some(
      v => v !== undefined && v !== '' && v !== false
        && !(Array.isArray(v) && v.length === 0)
    )
  },
})
</script>

<style scoped>
.xiaohongshu-image-publish-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.xhs-warning {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px;
  background: #fef0f0;
  border: 1px solid #fde2e2;
  border-radius: 8px;
  color: #f56c6c;
  font-size: 13px;
  line-height: 1.6;
}

.xhs-warning .el-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.setting-card {
  border: 1px solid rgba(139, 92, 246, 0.15);
  background: rgba(139, 92, 246, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #8b5cf6;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.5;
}

.el-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.el-input:focus { border-color: #8b5cf6; }
.el-input:disabled { background: #f5f7fa; cursor: not-allowed; }

.el-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.2s;
}

.el-textarea:focus { border-color: #8b5cf6; }
.el-textarea:disabled { background: #f5f7fa; cursor: not-allowed; }

.tags-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: rgba(139, 92, 246, 0.1);
  color: #8b5cf6;
  border: 1px solid rgba(139, 92, 246, 0.2);
  border-radius: 4px;
  font-size: 12px;
}

.tag-close {
  background: none; border: none; color: #8b5cf6;
  cursor: pointer; padding: 0; font-size: 14px; line-height: 1;
}

.tag-close:hover { color: #7c3aed; }
</style>
```

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/components/xiaohongshu/ImagePublishPanel.vue
git commit -m "feat: 新建小红书图文发布渠道组件 XiaohongshuImagePublishPanel

- 封装小红书渠道表单字段：标题/描述/标签
- 包含反检测警告横幅
- 完整实现统一接口：publish/getConfigs/restoreConfigs/syncXXX/validate/hasAccountOverride

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3: 创建 `components/kuaishou/ImagePublishPanel.vue`

**Files:**
- Create: `frontend/src/components/kuaishou/ImagePublishPanel.vue`

- [ ] **Step 1: 创建目录并写入组件**

```bash
mkdir -p /home/czy/workspace/ai/social-auto-upload-web-ui/frontend/src/components/kuaishou
```

用 Write 创建 `frontend/src/components/kuaishou/ImagePublishPanel.vue`，内容与 XiaohongshuImagePublishPanel 相同框架结构，差异：

1. 不需要反检测警告横幅
2. 主题色使用快手色 `#f59e0b`
3. `KUAISHOU_DEFAULTS` 使用 `PLATFORMS.KUAISHOU.defaultSettings`
4. `validate()` 校验标题必填 + 声明必填

```vue
<template>
  <div class="kuaishou-image-publish-panel">
    <!-- 恢复默认按钮 -->
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <!-- ① 标题 -->
    <div class="setting-card">
      <div class="setting-label">标题</div>
      <input
        v-model="form.title"
        class="el-input"
        placeholder="请输入标题..."
        maxlength="100"
        :disabled="disabled"
      />
    </div>

    <!-- ② 描述 -->
    <div class="setting-card">
      <div class="setting-label">描述</div>
      <textarea
        v-model="form.description"
        class="el-textarea"
        :rows="5"
        placeholder="请输入描述..."
        maxlength="2000"
        :disabled="disabled"
      ></textarea>
    </div>

    <!-- ③ 标签 -->
    <div class="setting-card">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认</div>
      <input
        v-model="tagInput"
        class="el-input"
        placeholder="输入标签内容，按回车添加"
        @keyup.enter="addTag"
        :disabled="disabled"
      />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <span
          v-for="(tag, index) in form.tags"
          :key="index"
          class="tag-chip"
        >
          #{{ tag }}
          <button class="tag-close" @click="removeTag(index)">×</button>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { PLATFORMS } from '@/config/platforms'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

const KS_DEFAULTS = {
  ...PLATFORMS.KUAISHOU.defaultSettings,
  tags: [],
}

const platformConfig = reactive({ ...KS_DEFAULTS })
const accountOverrides = reactive({})
const form = reactive({ ...platformConfig })
const tagInput = ref('')

watch(() => props.accountId, (newId) => {
  Object.keys(form).forEach(k => delete form[k])
  if (!newId) {
    Object.assign(form, { ...platformConfig })
  } else {
    const override = accountOverrides[newId]
    const hasOverride = override && Object.keys(override).some(
      k => override[k] !== undefined && override[k] !== '' && override[k] !== false
        && !(Array.isArray(override[k]) && override[k].length === 0)
    )
    if (hasOverride) {
      const merged = { ...platformConfig }
      for (const [k, v] of Object.entries(override)) {
        if (v !== undefined && v !== '' && v !== false
            && !(Array.isArray(v) && v.length === 0)) merged[k] = v
      }
      Object.assign(form, merged)
    } else {
      Object.assign(form, { ...platformConfig })
    }
  }
}, { immediate: true })

watch(form, (newVal) => {
  if (!props.accountId) {
    for (const key of Object.keys(newVal)) {
      if (Array.isArray(newVal[key])) {
        platformConfig[key] = [...newVal[key]]
      } else {
        platformConfig[key] = newVal[key]
      }
    }
  } else {
    const diff = {}
    for (const key of Object.keys(newVal)) {
      const current = newVal[key]
      const fallback = platformConfig[key]
      if (typeof current === 'object' && current !== null) {
        if (JSON.stringify(current) !== JSON.stringify(fallback)) {
          diff[key] = Array.isArray(current) ? [...current] : { ...current }
        }
      } else if (current !== fallback) {
        diff[key] = current
      }
    }
    const hasValues = Object.entries(diff).some(([, v]) => {
      if (Array.isArray(v)) return v.length > 0
      if (typeof v === 'object' && v !== null) return Object.keys(v).length > 0
      return v !== undefined && v !== '' && v !== false
    })
    if (hasValues) {
      accountOverrides[props.accountId] = { ...diff }
    } else {
      delete accountOverrides[props.accountId]
    }
  }
  emit('config-changed')
}, { deep: true })

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('标签已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

function resetOverride() {
  if (props.accountId) {
    delete accountOverrides[props.accountId]
    Object.keys(form).forEach(k => delete form[k])
    Object.assign(form, { ...platformConfig })
    emit('config-changed')
    ElMessage.success('已恢复为渠道默认设置')
  }
}

defineExpose({
  async publish(accountId, accountName, commonData) {
    const override = accountOverrides[accountId] || {}
    const hasOverride = Object.keys(override).some(
      k => override[k] !== undefined && override[k] !== '' && override[k] !== false
        && !(Array.isArray(override[k]) && override[k].length === 0)
    )
    const merged = hasOverride ? { ...platformConfig, ...override } : { ...platformConfig }
    const account = accountStore.accounts.find(a => a.id === accountId)
    if (!account) {
      emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
      return
    }
    const imageIds = commonData.images.map(img => img.id)
    try {
      await imagePublishApi.publishImage({
        image_ids: imageIds,
        account_configs: [{
          account_id: accountId,
          platform: account.platform,
          filePath: account.filePath,
          title: merged.title,
          description: merged.description || '',
          tags: merged.tags || [],
          scheduleTime: merged.scheduleTime || '',
          aiContent: merged.aiContent || '',
          cover_path: commonData.coverImage?.stored_path || '',
          dry_run: false,
        }],
      })
      emit('publish-result', { accountName, status: 'success', message: '发布成功' })
    } catch (e) {
      emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
    }
  },

  getConfigs() {
    return {
      platformConfig: JSON.parse(JSON.stringify(platformConfig)),
      accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
    }
  },

  restoreConfigs(config, overrides) {
    Object.keys(platformConfig).forEach(k => delete platformConfig[k])
    Object.assign(platformConfig, KS_DEFAULTS, config)
    Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
    if (overrides) Object.assign(accountOverrides, overrides)
    Object.keys(form).forEach(k => delete form[k])
    if (props.accountId) {
      const override = accountOverrides[props.accountId]
      const hasOverride = override && Object.keys(override).some(
        k => override[k] !== undefined && override[k] !== '' && override[k] !== false
          && !(Array.isArray(override[k]) && override[k].length === 0)
      )
      Object.assign(form, hasOverride ? { ...platformConfig, ...override } : { ...platformConfig })
    } else {
      Object.assign(form, { ...platformConfig })
    }
  },

  syncTitle(title) {
    if (!props.accountId) { platformConfig.title = title; form.title = title }
    emit('config-changed')
  },

  syncDescription(desc) {
    if (!props.accountId) { platformConfig.description = desc; form.description = desc }
    emit('config-changed')
  },

  syncTags(tags) {
    if (!props.accountId) { platformConfig.tags = [...tags]; form.tags = [...tags] }
    emit('config-changed')
  },

  validate(accountId) {
    const errors = []
    const override = accountOverrides[accountId] || {}
    const hasOverride = Object.keys(override).some(
      k => override[k] !== undefined && override[k] !== '' && override[k] !== false
        && !(Array.isArray(override[k]) && override[k].length === 0)
    )
    const merged = hasOverride ? { ...platformConfig, ...override } : { ...platformConfig }
    if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
    if (!merged.aiContent) errors.push('请选择自主声明')
    return { valid: errors.length === 0, errors }
  },

  hasAccountOverride(accountId) {
    const override = accountOverrides[accountId]
    if (!override) return false
    return Object.values(override).some(
      v => v !== undefined && v !== '' && v !== false
        && !(Array.isArray(v) && v.length === 0)
    )
  },
})
</script>

<style scoped>
.kuaishou-image-publish-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba(245, 158, 11, 0.15);
  background: rgba(245, 158, 11, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #f59e0b;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.5;
}

.el-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}

.el-input:focus { border-color: #f59e0b; }
.el-input:disabled { background: #f5f7fa; cursor: not-allowed; }

.el-textarea {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  resize: vertical;
  font-family: inherit;
  transition: border-color 0.2s;
}

.el-textarea:focus { border-color: #f59e0b; }
.el-textarea:disabled { background: #f5f7fa; cursor: not-allowed; }

.tags-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }

.tag-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: 4px;
  font-size: 12px;
}

.tag-close {
  background: none; border: none; color: #d97706;
  cursor: pointer; padding: 0; font-size: 14px; line-height: 1;
}

.tag-close:hover { color: #b45309; }
</style>
```

- [ ] **Step 2: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/components/kuaishou/ImagePublishPanel.vue
git commit -m "feat: 新建快手图文发布渠道组件 KuaishouImagePublishPanel

- 封装快手渠道表单字段：标题/描述/标签
- 完整实现统一接口：publish/getConfigs/restoreConfigs/syncXXX/validate/hasAccountOverride
- 校验规则：标题必填、自主声明必填

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: 重构 `views/ImagePublish.vue` — 第一部分：删除旧代码

**Files:**
- Modify: `frontend/src/views/ImagePublish.vue`

这是最大的一步。将 2535 行的 `ImagePublish.vue` 逐步简化。

- [ ] **Step 1: 删除模板中"快速标签按钮"区域（第 174-195 行）**

编辑删除以下内容：
```html
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
```

- [ ] **Step 2: 删除模板中话题选择对话框（第 503-538 行）**

编辑删除以下内容：
```html
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
```

- [ ] **Step 3: 删除模板中"平台特有设置区域"（第 163-303 行），替换为渠道面板占位**

当前第 163-304 行是巨大的平台设置区域。删除从 `<!-- ===== PLATFORM-SPECIFIC SETTINGS ===== -->` 到 `<!-- No platform selected hint -->` 之间的所有内容（包括小红书警告、标题描述卡、抖音特有配置模板），替换为：

```html
        <!-- ===== PLATFORM-SPECIFIC SETTINGS ===== -->
        <div class="config-section" v-show="selectedPlatform">
          <div class="section-bar">
            <div class="bar" :style="{ background: currentPlatformConfig?.color }"></div>
            <span class="section-label">
              {{ currentPlatformConfig?.name }}
              {{ selectedAccountId ? '· ' + getAccountDisplayName(selectedAccountId) : '· 默认设置' }}
            </span>
            <span class="hint">{{ selectedAccountId ? '仅对该账号生效' : '对该分组所有未自定义的账号生效' }}</span>
          </div>

          <DouyinImagePublishPanel
            ref="el => panelRefs.douyin = el"
            :account-id="selectedPlatform === 'douyin' ? selectedAccountId : null"
            :disabled="publishing"
            v-show="selectedPlatform === 'douyin'"
            @config-changed="onChannelConfigChanged"
            @publish-result="onPublishResult"
          />
          <XiaohongshuImagePublishPanel
            ref="el => panelRefs.xiaohongshu = el"
            :account-id="selectedPlatform === 'xiaohongshu' ? selectedAccountId : null"
            :disabled="publishing"
            v-show="selectedPlatform === 'xiaohongshu'"
            @config-changed="onChannelConfigChanged"
            @publish-result="onPublishResult"
          />
          <KuaishouImagePublishPanel
            ref="el => panelRefs.kuaishou = el"
            :account-id="selectedPlatform === 'kuaishou' ? selectedAccountId : null"
            :disabled="publishing"
            v-show="selectedPlatform === 'kuaishou'"
            @config-changed="onChannelConfigChanged"
            @publish-result="onPublishResult"
          />
        </div>

        <!-- No platform selected hint -->
        <div v-show="!selectedPlatform" class="no-platform-hint">
          <div class="hint-icon">
            <el-icon :size="48"><PictureFilled /></el-icon>
          </div>
          <p>请在左侧选择一个平台分组</p>
          <p class="hint-sub">选择后可配置该平台的个性化发布设置</p>
        </div>
```

- [ ] **Step 4: 修改批量同步区—增加标签输入**

将第 122-157 行的批量同步区替换为含标签的新版：

```html
          <!-- Batch title/description/tags sync -->
          <div class="batch-sync-section">
            <div class="batch-sync-header" @click="batchSyncExpanded = !batchSyncExpanded">
              <span>批量设置标题、描述和标签</span>
              <el-icon class="cursor-pointer">
                <component :is="batchSyncExpanded ? ArrowDown : ArrowRight" />
              </el-icon>
            </div>
            <div v-show="batchSyncExpanded" class="batch-sync-body">
              <div class="form-field">
                <div class="field-head">
                  <span>标题</span>
                </div>
                <el-input
                  v-model="batchTitle"
                  placeholder="输入标题后点击同步..."
                  maxlength="100"
                />
              </div>
              <div class="form-field">
                <div class="field-head">
                  <span>描述</span>
                </div>
                <el-input
                  v-model="batchDescription"
                  type="textarea"
                  :rows="5"
                  placeholder="输入描述后点击同步..."
                  maxlength="2000"
                />
              </div>
              <div class="form-field">
                <div class="field-head">
                  <span>标签</span>
                </div>
                <el-input
                  v-model="batchTagInput"
                  placeholder="输入标签，回车添加"
                  @keyup.enter="addBatchTag"
                  clearable
                />
                <div v-if="batchTags.length > 0" style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;">
                  <el-tag
                    v-for="(t, i) in batchTags"
                    :key="i"
                    closable
                    @close="batchTags.splice(i, 1)"
                    size="small"
                  >#{{ t }}</el-tag>
                </div>
              </div>
              <button class="cover-action-btn primary" @click="syncBatchToAll">
                <el-icon :size="15"><Promotion /></el-icon><span>同步到所有平台</span>
              </button>
            </div>
          </div>
```

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/views/ImagePublish.vue
git commit -m "refactor: ImagePublish 模板初步简化 — 删除话题/平台特有区域，接入渠道组件

- 删除快速标签按钮和话题对话框 (commonConfig.topics 已废弃)
- 删除平台特有设置区域 (v-if=selectedPlatform===douyin 等)
- 替换为 3 个渠道信息面板组件 (v-show 切换)
- 批量同步区增加标签输入

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: 重构 `views/ImagePublish.vue` — 第二部分：改造脚本

**Files:**
- Modify: `frontend/src/views/ImagePublish.vue`

- [ ] **Step 1: 替换 import 语句**

删除第 522-526 行的旧 douyin 子组件 import：
```js
// 抖音图文发布组件
import DouyinMixSelect from '@/components/douyin/MixSelect.vue'
import DouyinActivitySelect from '@/components/douyin/ActivitySelect.vue'
import DouyinHotspotSelect from '@/components/douyin/HotspotSelect.vue'
import DouyinMusicSelect from '@/components/douyin/MusicSelect.vue'
import DouyinTagSelect from '@/components/douyin/TagSelect.vue'
```

替换为新的渠道面板组件 import：
```js
// 渠道图文发布面板
import DouyinImagePublishPanel from '@/components/douyin/ImagePublishPanel.vue'
import XiaohongshuImagePublishPanel from '@/components/xiaohongshu/ImagePublishPanel.vue'
import KuaishouImagePublishPanel from '@/components/kuaishou/ImagePublishPanel.vue'
```

- [ ] **Step 2: 删除旧 reactive 状态和 computed**

删除以下所有代码块（从 `commonConfig` 移除 `topics` 开始）：

**删除 `commonConfig.topics`**（第 588 行）：
```js
// 将
const commonConfig = reactive({
  images: [],
  topics: [],
  coverImage: null,
})
// 改为
const commonConfig = reactive({
  images: [],
  coverImage: null,
})
```

**删除整个 `platformConfigs` reactive 对象**（第 595-611 行）

**删除 `accountOverrides` reactive 对象**（第 615 行 `const accountOverrides = reactive({})`）

**删除 `form` reactive 对象**（第 618 行 `const form = reactive({})`）

**删除 `declarationOptions` computed**（第 574-578 行）

**删除 `imagePlatformSettingsFields` computed**（第 581-583 行）

- [ ] **Step 3: 删除旧 watcher 和处理函数**

删除 第 639-679 行的 `watch([selectedPlatform, selectedAccountId])` 和 `watch(form, ...)`

删除 第 620-636 行的 `getMergedSettings()` 函数

删除 第 687-728 行的 `hasAccountOverride()` / `resetAccountOverride()` / `hotspotTagInput` / `addHotspotTag()` / `removeHotspotTag()`

删除 第 888-959 行的 `handleActivityChange()` / `handleMusicSelect()` / `handleHotspotChange()` / `handleMixChange()` / `handleTagSelect()`

删除 第 961-963 行的 `onMusicCoverError()`

删除话题相关：`topicDialogVisible` / `customTopic` / `recommendedTopics` / `addCustomTopic()` / `toggleRecommendedTopic()` — 搜索 `topic` 定位

- [ ] **Step 4: 新增 panelRefs 和事件回调**

在脚本的 `// ========== Stores & Config ==========` 区块后（约第 533 行后）添加：

```js
// ========== Channel Panel Refs ==========
const panelRefs = reactive({
  douyin: null,
  xiaohongshu: null,
  kuaishou: null,
})

function getAccountDisplayName(accountId) {
  const account = accountStore.accounts.find(a => a.id === accountId)
  return account ? account.name : '未知'
}

// ========== Channel Panel Event Handlers ==========
function onChannelConfigChanged() {
  hasChanges.value = true
}

function onPublishResult({ accountName, status, message }) {
  publishResults.value.push({ label: accountName, status, message })
}
```

- [ ] **Step 5: 重写 `hasAccountOverride()` 为委托**

```js
function hasAccountOverride(accountId) {
  for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
    const panel = panelRefs[key]
    if (panel && panel.hasAccountOverride(accountId)) return true
  }
  return false
}
```

- [ ] **Step 6: 重写 `syncBatchToAll()`**

```js
function syncBatchToAll() {
  const platforms = ['douyin', 'xiaohongshu', 'kuaishou']
  for (const key of platforms) {
    const panel = panelRefs[key]
    if (!panel) continue
    if (batchTitle.value) panel.syncTitle(batchTitle.value)
    if (batchDescription.value) panel.syncDescription(batchDescription.value)
    if (batchTags.value.length) panel.syncTags([...batchTags.value])
  }
  ElMessage.success('已同步到所有平台')
}
```

新增批量标签状态（放在 `batchSyncExpanded` 附近）：
```js
const batchTags = ref([])
const batchTagInput = ref('')

function addBatchTag() {
  const tag = batchTagInput.value.trim()
  if (!tag) return
  if (batchTags.value.includes(tag)) return
  batchTags.value.push(tag)
  batchTagInput.value = ''
}
```

- [ ] **Step 7: 重写 `saveDraft()`**

用以下内容完全替换当前 `saveDraft()` 函数（第 1010-1052 行）：

```js
async function saveDraft() {
  try {
    // 从各渠道组件收集配置
    const allPlatformConfigs = {}
    const allAccountOverrides = {}
    for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
      const panel = panelRefs[key]
      if (panel) {
        const configs = panel.getConfigs()
        allPlatformConfigs[key] = configs.platformConfig
        Object.assign(allAccountOverrides, configs.accountOverrides)
      }
    }

    const draftData = {
      commonConfig: {
        images: commonConfig.images.map(img => ({
          id: img.id, name: img.name, url: img.url,
          stored_path: img.stored_path, size: img.size, type: img.type,
        })),
        coverImage: commonConfig.coverImage || null,
      },
      platformConfigs: allPlatformConfigs,
      accountOverrides: allAccountOverrides,
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
```

- [ ] **Step 8: 重写 `publishAll()`**

用以下内容完全替换当前 `publishAll()` 函数（第 1054-1278 行）：

```js
async function publishAll() {
  // 1. 公共校验
  if (commonConfig.images.length === 0) {
    ElMessage.error('请先上传至少一张图片')
    return
  }
  if (publishAccountIds.size === 0) {
    ElMessage.error('请先添加发布账号')
    return
  }

  // 2. 渠道校验（委托给各渠道组件）
  for (const group of imageAccountGroups.value) {
    if (group.accounts.length === 0) continue
    const panel = panelRefs[group.key]
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

  // 3. 启动发布
  publishing.value = true
  publishProgress.value = 0
  publishResults.value = []
  isCancelled.value = false
  currentPublishingAccount.value = ''
  batchPublishDialogVisible.value = true

  const commonData = {
    images: commonConfig.images,
    coverImage: commonConfig.coverImage,
  }

  const allTasks = []
  for (const group of imageAccountGroups.value) {
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

  // 4. 逐个调用渠道组件发布
  for (let i = 0; i < allTasks.length; i++) {
    if (isCancelled.value) {
      publishResults.value.push({
        label: allTasks[i].account.name,
        status: 'cancelled',
        message: '已取消',
      })
      continue
    }
    const { account, groupKey } = allTasks[i]
    currentPublishingAccount.value = account.name
    publishProgress.value = Math.floor((i / allTasks.length) * 100)

    const panel = panelRefs[groupKey]
    if (panel) {
      await panel.publish(account.id, account.name, commonData)
    }
  }

  publishProgress.value = 100
  publishing.value = false

  // 发布结果统计
  const successCount = publishResults.value.filter(r => r.status === 'success').length
  const failCount = publishResults.value.filter(r => r.status === 'fail').length

  if (failCount > 0) {
    ElMessage.warning(`发布完成：${successCount}个成功，${failCount}个失败`)
  } else {
    ElMessage.success('全部发布成功')
    setTimeout(() => { batchPublishDialogVisible.value = false }, 1500)
  }
}
```

- [ ] **Step 9: 重写 `loadDraft()` 和添加 `migrateOldDraftFormat()`**

用以下内容完全替换当前 `loadDraft()` 函数（第 1323-1443 行）：

```js
// ========== 旧草稿兼容迁移 ==========
function migrateOldDraftFormat(dd) {
  // 7.1 commonConfig.topics → 各渠道 tags
  if (dd.commonConfig?.topics && Array.isArray(dd.commonConfig.topics)) {
    for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
      if (dd.platformConfigs?.[key]) {
        dd.platformConfigs[key].tags = [...dd.commonConfig.topics]
      }
    }
    delete dd.commonConfig.topics
  }

  // 7.2 douyinSelections → platformConfigs.douyin
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

  // 7.3 accountOverrides 中的 coverImage 清理
  if (dd.accountOverrides) {
    for (const override of Object.values(dd.accountOverrides)) {
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

    // 恢复公共配置
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
        commonConfig.coverImage = {
          ...ci,
          url: ci.stored_path ? getFileUrl(ci.stored_path) : (ci.url || ''),
        }
      }
    }

    // 兼容迁移旧草稿格式
    migrateOldDraftFormat(dd)

    // 恢复各渠道配置
    if (dd.platformConfigs) {
      for (const [key, val] of Object.entries(dd.platformConfigs)) {
        const panel = panelRefs[key]
        if (panel && val) {
          panel.restoreConfigs(val, dd.accountOverrides || {})
        }
      }
    }

    // 恢复发布账号
    if (dd.publishAccountIds) {
      publishAccountIds.clear()
      dd.publishAccountIds.forEach(id => publishAccountIds.add(id))
    }

    // 恢复 UI 状态
    if (dd.expandedGroups) expandedGroups.value = new Set(dd.expandedGroups)
    if (dd.selectedPlatform) selectedPlatform.value = dd.selectedPlatform
    if (dd.selectedAccountId) {
      selectedAccountId.value = dd.selectedAccountId
    } else if (dd.publishAccountIds?.length > 0) {
      selectedAccountId.value = dd.publishAccountIds[0]
    }

    ElMessage.success('草稿已加载')
  } catch (e) {
    console.error('加载草稿失败:', e)
    ElMessage.error('加载草稿失败')
  }
}
```

- [ ] **Step 10: 更新 auto-save watcher — 删除对 platformConfigs/accountOverrides 的 watch**

第 1317-1320 行，当前为：
```js
watch(commonConfig, () => { hasChanges.value = true }, { deep: true })
watch(platformConfigs, () => { hasChanges.value = true }, { deep: true })
watch(accountOverrides, () => { hasChanges.value = true }, { deep: true })
```

删除后两行，保留 commonConfig watch 即可：
```js
watch(commonConfig, () => { hasChanges.value = true }, { deep: true })
```

（`config-changed` 事件从子组件 emit 上来处理渠道配置的 dirty 跟踪）

- [ ] **Step 11: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/views/ImagePublish.vue
git commit -m "refactor: ImagePublish 脚本重构 — 数据所有权移入渠道组件

- 删除 platformConfigs/accountOverrides/form reactive 对象
- 删除所有抖音特有处理函数和 watcher
- 新增 panelRefs 管理和事件回调 (config-changed/publish-result)
- 重写 saveDraft/publishAll/loadDraft 为委托模式
- 新增 migrateOldDraftFormat 兼容旧草稿格式
- 批量同步增加标签支持 (batchTags/batchTagInput/addBatchTag)
- hasAccountOverride 改为委托渠道组件查询
- auto-save 改为监听 commonConfig + config-changed 事件

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: 验证

**Files:** 无

- [ ] **Step 1: 验证前端构建**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend
npm run build
```

Expected: 无构建错误。

- [ ] **Step 2: 检查构建输出中的 Vue 组件引用**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
grep -r "DouyinImagePublishPanel\|XiaohongshuImagePublishPanel\|KuaishouImagePublishPanel" frontend/src/views/ImagePublish.vue
```

Expected: 能找到 import 和模板中的引用。

- [ ] **Step 3: 检查 ImagePublish.vue 行数是否大幅减少**

```bash
wc -l /home/czy/workspace/ai/social-auto-upload-web-ui/frontend/src/views/ImagePublish.vue
```

Expected: < 900 行（原 2535 行）

- [ ] **Step 4: 检查无死引用**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend
grep -rn "platformConfigs\|accountOverrides\|declarationOptions\|handleActivityChange\|handleMusicSelect\|handleHotspotChange\|handleMixChange\|handleTagSelect\|onMusicCoverError\|hotspotTagInput\|addHotspotTag\|removeHotspotTag\|topicDialogVisible\|customTopic\|recommendedTopics\|addCustomTopic" src/views/ImagePublish.vue
```

Expected: 无输出（全部清理干净）

- [ ] **Step 5: Commit（如有未提交变更）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git status
```

---

### 改造流程总览

```
Task 1 → Commit    新建 DouyinImagePublishPanel.vue     (~450 lines)
Task 2 → Commit    新建 XiaohongshuImagePublishPanel.vue (~200 lines)
Task 3 → Commit    新建 KuaishouImagePublishPanel.vue    (~200 lines)
Task 4 → Commit    ImagePublish.vue 模板改造
Task 5 → Commit    ImagePublish.vue 脚本改造
Task 6             构建验证
```

每个 Task 完成后必须 commit，确保每一步是独立可回滚的。
