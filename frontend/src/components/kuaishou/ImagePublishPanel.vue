<template>
  <div class="kuaishou-image-publish-panel">
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

    <div class="setting-card">
      <div class="setting-label">作者声明</div>
      <el-select v-model="form.aiContent" placeholder="请选择作者声明" clearable style="width: 100%" :disabled="disabled">
        <el-option v-for="opt in declarationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">定时发布</div>
      <el-date-picker
        v-model="form.scheduleTime"
        type="datetime"
        placeholder="选择日期时间"
        format="YYYY-MM-DD HH:mm:ss"
        value-format="YYYY-MM-DD HH:mm:ss"
        style="width: 100%"
        :disabled="disabled"
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">选择音乐</div>
      <KuaishouMusicSelect :account-id="accountId" v-model="form.selectedMusicId" :data="form.selectedMusicData" @change="handleMusicChange" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { PLATFORMS } from '@/config/platforms'
import { useChannelForm } from '@/composables/useChannelForm'
import KuaishouMusicSelect from './MusicSelect.vue'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

const KS_DEFAULTS = { ...PLATFORMS.KUAISHOU.defaultSettings, tags: [] }

const declarationOptions = computed(() => {
  const field = PLATFORMS.KUAISHOU.settingsFields.find(f => f.key === 'aiContent')
  return field?.options || []
})

function handleMusicChange(music) {
  if (music) {
    form.selectedMusicId = music.musicId
    form.selectedMusicData = music
    form.musicTitle = music.title
  } else {
    form.selectedMusicId = ''
    form.selectedMusicData = null
    form.musicTitle = ''
  }
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  KS_DEFAULTS,
  { props, emit },
  {
    publishFn: async (accountId, accountName, commonData, merged, extra) => {
      const account = accountStore.accounts.find(a => a.id === accountId)
      if (!account) {
        emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
        return
      }
      try {
        await imagePublishApi.publishImage({
          image_ids: commonData.images.map(img => img.id),
          account_configs: {
            account_id: accountId, platform: account.platform, filePath: account.filePath,
            title: merged.title, description: merged.description || '',
            tags: merged.tags || [], scheduleTime: merged.scheduleTime || '',
            aiContent: merged.aiContent || '',
            cover_path: commonData.coverImage?.stored_path || '',
            music_id: merged.selectedMusicId || '',
            music_title: merged.musicTitle || '',
            dry_run: true,  // 测试期固定 true；正式发布时改 false
          },
          batchId: extra?.batchId || '',
          landscapeCoverMaterialId: extra?.landscapeCoverMaterialId || '',
          portraitCoverMaterialId: extra?.portraitCoverMaterialId || '',
        })
        emit('publish-result', { accountName, status: 'success', message: '发布成功' })
      } catch (e) {
        emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
      }
    },
    validateFn: (accountId, merged) => {
      const errors = []
      if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
      if (!merged.aiContent) errors.push('请选择自主声明')
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
