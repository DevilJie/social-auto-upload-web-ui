<template>
  <div class="kuaishou-image-publish-panel">
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

    <!-- 3. Tags -->
    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认</div>
      <el-input v-model="tagInput" placeholder="输入标签内容，按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
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

function applyToForm(source) {
  Object.assign(form, source)
}

// ===== Watch accountId =====
watch(() => props.accountId, (newId) => {
  applyToForm(newId ? getMergedConfig(newId) : { ...platformConfig })
}, { immediate: true })

// ===== Watch form =====
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
    const hasValuesDiff = Object.entries(diff).some(([, v]) => hasValues(v))
    if (hasValuesDiff) {
      accountOverrides[props.accountId] = { ...diff }
    } else {
      delete accountOverrides[props.accountId]
    }
  }
  emit('config-changed')
}, { deep: true })

// ===== Tag operations =====
function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('标签已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

// ===== Reset override =====
function resetOverride() {
  if (props.accountId) {
    delete accountOverrides[props.accountId]
    applyToForm({ ...platformConfig })
    emit('config-changed')
    ElMessage.success('已恢复为渠道默认设置')
  }
}

// ===== Template helper =====
function hasAccountOverride(accountId) {
  return hasMeaningfulOverride(accountOverrides[accountId])
}

defineExpose({
  async publish(accountId, accountName, commonData) {
    const merged = getMergedConfig(accountId)
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
    return { valid: errors.length === 0, errors }
  },

  hasAccountOverride,
})
</script>

<style scoped>
.kuaishou-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
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
</style>
