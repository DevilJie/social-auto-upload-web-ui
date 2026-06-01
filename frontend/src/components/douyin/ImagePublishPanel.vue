<template>
  <div class="douyin-image-publish-panel">
    <!-- Reset override button -->
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <!-- 1. Title -->
    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标题</div>
      <el-input v-model="form.title" placeholder="请输入标题..." maxlength="100" show-word-limit :disabled="disabled" />
    </div>

    <!-- 2. Description -->
    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入描述..." maxlength="2000" show-word-limit :disabled="disabled" />
    </div>

    <!-- 3. Tags (hotspot-style interaction: enter to add + chip display + removable) -->
    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认（官方活动 + 标签最多5个）</div>
      <el-input v-model="tagInput" placeholder="输入标签内容，按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <!-- 4. Activity -->
    <div class="setting-card">
      <div class="setting-label">官方活动</div>
      <DouyinActivitySelect v-model="form.activityId" @change="handleActivityChange" />
    </div>

    <!-- 5. Music -->
    <div class="setting-card">
      <div class="setting-label">选择音乐</div>
      <DouyinMusicSelect :account-id="accountId" v-model="form.selectedMusic" :data="form.selectedMusicData" @change="handleMusicSelect" />
    </div>

    <!-- 6. Hotspot -->
    <div class="setting-card">
      <div class="setting-label">关联热点</div>
      <DouyinHotspotSelect v-model="form.hotspotId" :data="form.hotspotData" @change="handleHotspotChange" />
    </div>

    <!-- 7. AI Content Declaration -->
    <div class="setting-card">
      <div class="setting-label">自主声明</div>
      <el-select v-model="form.aiContent" placeholder="请选择自主声明" clearable style="width: 100%" :disabled="disabled">
        <el-option v-for="opt in declarationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <!-- 8. Tag Select (location/miniapp/game/mark) -->
    <div class="setting-card">
      <div class="setting-label">添加标签</div>
      <DouyinTagSelect :account-id="accountId" v-model="form.selectedTag" @change="handleTagSelect" />
    </div>

    <!-- 9. Mix Select (account only) -->
    <div v-if="accountId" class="setting-card">
      <div class="setting-label">添加合集</div>
      <DouyinMixSelect :account-id="accountId" v-model="form.mixId" :data="form.mixData" @change="handleMixChange" />
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

// ===== Channel defaults =====
const DOUYIN_DEFAULTS = {
  ...PLATFORMS.DOUYIN.defaultSettings,
  tags: [],
}

// ===== Internal state =====
const platformConfig = reactive({ ...DOUYIN_DEFAULTS })
const accountOverrides = reactive({})
const form = reactive({ ...platformConfig })

// ===== Tag input =====
const tagInput = ref('')

// ===== Declaration options =====
const declarationOptions = computed(() => {
  const field = PLATFORMS.DOUYIN.settingsFields.find(f => f.key === 'aiContent')
  return field?.options || []
})

// ===== Helpers =====
function hasValues(v) {
  if (v === undefined || v === '' || v === false) return false
  if (Array.isArray(v)) return v.length > 0
  return true
}

function hasMeaningfulOverride(override) {
  return override && Object.values(override).some(hasValues)
}

function getMergedConfig(accountId) {
  const override = accountOverrides[accountId] || {}
  const merged = { ...platformConfig }
  for (const [k, v] of Object.entries(override)) {
    if (hasValues(v)) merged[k] = Array.isArray(v) ? [...v] : v
  }
  return merged
}

// ===== Helpers to reset form =====
function applyToForm(source) {
  Object.assign(form, source)
}

// ===== Watch accountId to switch form =====
watch(() => props.accountId, (newId) => {
  applyToForm(newId ? getMergedConfig(newId) : { ...platformConfig })
}, { immediate: true })

// ===== Watch form changes to sync to platformConfig / accountOverrides =====
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
    const hasDiff = Object.entries(diff).some(([, v]) => hasValues(v))
    if (hasDiff) {
      accountOverrides[props.accountId] = { ...diff }
    } else {
      delete accountOverrides[props.accountId]
    }
  }
  emit('config-changed')
}, { deep: true, flush: 'post' })

// ===== Tag operations =====
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

// ===== Activity selection handler =====
function handleActivityChange(activity) {
  if (activity && activity.challenge && activity.challenge.length > 0) {
    for (const topic of activity.challenge) {
      if (form.tags && !form.tags.includes(topic)) {
        const activityCount = form.activityId?.length || 0
        const tagCount = form.tags?.length || 0
        if (activityCount + tagCount >= 5) break
        form.tags.push(topic)
      }
    }
  }
}

// ===== Music selection handler =====
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

// ===== Hotspot selection handler =====
function handleHotspotChange(hotspot) {
  if (hotspot) {
    form.hotspotId = hotspot.word
    form.hotspotData = hotspot
  } else {
    form.hotspotId = ''
    form.hotspotData = null
  }
}

// ===== Tag selection handler (location/miniapp/game/mark) =====
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

// ===== Mix selection handler =====
function handleMixChange(mix) {
  if (mix) {
    form.mixId = mix.mix_name
    form.mixData = mix
  } else {
    form.mixId = ''
    form.mixData = null
  }
}

// ===== Reset override =====
function resetOverride() {
  if (props.accountId) {
    delete accountOverrides[props.accountId]
    applyToForm({ ...platformConfig })
    emit('config-changed')
    ElMessage.success('已恢复为渠道默认设置')
  }
}

// ===== Template helper (used in v-if) =====
function hasAccountOverride(accountId) {
  return hasMeaningfulOverride(accountOverrides[accountId])
}

// ===== Exposed methods =====
defineExpose({
  // Publish single account
  async publish(accountId, accountName, commonData) {
    const merged = getMergedConfig(accountId)
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

  getConfigs() {
    return {
      platformConfig: JSON.parse(JSON.stringify(platformConfig)),
      accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
    }
  },

  restoreConfigs(config, overrides) {
    Object.keys(platformConfig).forEach(k => delete platformConfig[k])
    Object.assign(platformConfig, DOUYIN_DEFAULTS, config)
    Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
    if (overrides) Object.assign(accountOverrides, overrides)
    applyToForm(props.accountId ? getMergedConfig(props.accountId) : { ...platformConfig })
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
    const merged = getMergedConfig(accountId)
    if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
    if (!merged.aiContent) errors.push('请选择自主声明')
    const activityCount = merged.activityId?.length || 0
    const tagCount = merged.tags?.length || 0
    if (activityCount + tagCount > 5) {
      errors.push(`官方活动(${activityCount}) + 标签(${tagCount}) 超过 5 个`)
    }
    return { valid: errors.length === 0, errors }
  },

  hasAccountOverride,
})
</script>

<style scoped>
.douyin-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
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
</style>
