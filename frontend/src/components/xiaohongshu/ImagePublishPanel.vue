<template>
  <div class="xiaohongshu-image-publish-panel">
    <div class="xhs-warning">
      <el-icon><WarningFilled /></el-icon>
      <span>由于小红书反检测机制比较恶心，如果出现被警告的情况！请立即停止使用小红书渠道！</span>
    </div>

    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标题</div>
      <el-input v-model="form.title" placeholder="请输入标题..." maxlength="100" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入描述..." maxlength="2000" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认</div>
      <el-input v-model="tagInput" placeholder="输入标签内容，按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="settings-row">
      <div class="setting-card">
        <div class="setting-label">原创声明</div>
        <el-switch v-model="form.isOriginal" :disabled="disabled" />
      </div>

      <div class="setting-card">
        <div class="setting-label">内容类型声明</div>
        <el-select v-model="form.aiContent" placeholder="请选择" :disabled="disabled" style="width: 100%;">
          <el-option label="无" value="" />
          <el-option
            v-for="opt in aiContentOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>

      <div class="setting-card">
        <div class="setting-label">定时发布</div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <el-switch v-model="form.enableTimer" :disabled="disabled" />
          <el-date-picker
            v-if="form.enableTimer"
            v-model="form.scheduleTime"
            type="datetime"
            placeholder="选择发布时间"
            :disabled="disabled"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { WarningFilled } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { PLATFORMS } from '@/config/platforms'
import { useChannelForm } from '@/composables/useChannelForm'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

const aiContentField = PLATFORMS.XIAOHONGSHU.settingsFields.find(f => f.key === 'aiContent')
const aiContentOptions = computed(() => aiContentField?.options || [])

const XHS_DEFAULTS = { ...PLATFORMS.XIAOHONGSHU.defaultSettings, tags: [], enableTimer: false, isOriginal: false }

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  XHS_DEFAULTS,
  { props, emit },
  {
    publishFn: async (accountId, accountName, commonData, merged) => {
      const account = accountStore.accounts.find(a => a.id === accountId)
      if (!account) {
        emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
        return
      }
      try {
        await imagePublishApi.publishImage({
          image_ids: commonData.images.map(img => img.id),
          account_configs: [{
            account_id: accountId, platform: account.platform, filePath: account.filePath,
            title: merged.title, description: merged.description || '',
            tags: merged.tags || [], scheduleTime: merged.enableTimer ? merged.scheduleTime : '',
            aiContent: merged.aiContent || '', isOriginal: merged.isOriginal || false,
            cover_path: commonData.coverImage?.stored_path || '',
            dry_run: false,
          }],
        })
        emit('publish-result', { accountName, status: 'success', message: '发布成功' })
      } catch (e) {
        emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
      }
    },
    validateFn: (accountId, merged) => {
      const errors = []
      if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
      if (merged.enableTimer && !merged.scheduleTime) errors.push('请选择定时发布时间')
      return { valid: errors.length === 0, errors }
    },
  },
)

const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('标签已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

defineExpose(publicApi)
</script>

<style scoped>
.xiaohongshu-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.settings-row {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.settings-row .setting-card {
  min-width: 0;
}

.xhs-warning {
  grid-column: 1 / -1;
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
</style>
