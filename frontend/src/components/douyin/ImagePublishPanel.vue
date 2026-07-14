<template>
  <div class="douyin-image-publish-panel">
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
      <div class="setting-hint">输入标签内容，按回车确认（官方活动 + 标签最多5个）</div>
      <el-input v-model="tagInput" placeholder="输入标签内容，按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="setting-card">
      <div class="setting-label">官方活动</div>
      <DouyinActivitySelect :account-id="accountId" v-model="form.activityId" @change="handleActivityChange" />
    </div>

    <div class="setting-card">
      <div class="setting-label">选择音乐</div>
      <DouyinMusicSelect :account-id="accountId" v-model="form.selectedMusic" :data="form.selectedMusicData" @change="handleMusicSelect" />
    </div>

    <div class="setting-card">
      <div class="setting-label">关联热点</div>
      <DouyinHotspotSelect v-model="form.hotspotId" :data="form.hotspotData" @change="handleHotspotChange" />
    </div>

    <div class="setting-card">
      <div class="setting-label">自主声明</div>
      <el-select v-model="form.aiContent" placeholder="请选择自主声明" clearable style="width: 100%" :disabled="disabled">
        <el-option v-for="opt in declarationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">添加标签</div>
      <DouyinTagSelect :account-id="accountId" v-model="form.selectedTag" @change="handleTagSelect" />
    </div>

    <div v-if="accountId" class="setting-card">
      <div class="setting-label">添加合集</div>
      <DouyinMixSelect :account-id="accountId" v-model="form.mixId" :data="form.mixData" @change="handleMixChange" />
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
import DouyinActivitySelect from './ActivitySelect.vue'
import DouyinMusicSelect from './MusicSelect.vue'
import DouyinHotspotSelect from './HotspotSelect.vue'
import DouyinTagSelect from './TagSelect.vue'
import DouyinMixSelect from './MixSelect.vue'
import { useAutoExtractHashtags } from '@/utils/hashtag'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

const DOUYIN_DEFAULTS = { ...PLATFORMS.DOUYIN.defaultSettings, tags: [] }

const declarationOptions = computed(() => {
  const field = PLATFORMS.DOUYIN.settingsFields.find(f => f.key === 'aiContent')
  return field?.options || []
})

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  DOUYIN_DEFAULTS,
  { props, emit },
  {
    publishFn: async (accountId, accountName, commonData, merged, extra) => {
      const account = accountStore.accounts.find(a => a.id === accountId)
      if (!account) {
        emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
        return
      }
      const selectedTag = merged.selectedTag || null
      const tagTypeMap = { poi: 'location', miniapp: 'miniapp', game: 'gamepad', mark: 'mark' }
      let tagValue = '', miniLink = ''
      if (selectedTag) {
        tagValue = selectedTag.name || selectedTag.id || ''
        if (selectedTag.type === 'miniapp') miniLink = selectedTag._searchKeyword || ''
      }
      try {
        await imagePublishApi.publishImage({
          image_ids: commonData.images.map(img => img.id),
          account_configs: {
            account_id: accountId, platform: account.platform, filePath: account.filePath,
            title: merged.title, description: merged.description || '',
            tags: merged.tags || [], scheduleTime: merged.scheduleTime || '',
            aiContent: merged.aiContent || '', mix_id: merged.mixId || '',
            music_name: merged.selectedMusic || '', hotspot: merged.hotspotId || '',
            tag_type: selectedTag ? (tagTypeMap[selectedTag.type] || '') : '',
            tag_value: tagValue, mini_link: miniLink,
            activities: merged.activityId || [],
            cover_path: commonData.coverImage?.stored_path || '',
            dry_run: false,
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
      const ac = merged.activityId?.length || 0
      const tc = merged.tags?.length || 0
      if (ac + tc > 5) errors.push(`官方活动(${ac}) + 标签(${tc}) 超过 5 个`)
      return { valid: errors.length === 0, errors }
    },
  },
)

// ===== Tag input =====
const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if ((form.activityId?.length || 0) + (form.tags?.length || 0) >= 5) {
    ElMessage.warning('官方活动 + 标签最多 5 个')
    return
  }
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('标签已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

// 自动提取描述中的 #xxx 到标签数组,抖音活动+标签上限 5
useAutoExtractHashtags({
  form,
  descKey: 'description',
  tagKey: 'tags',
  maxTags: 5,
  getReservedTagCount: () => (form.activityId?.length || 0),
})

// ===== Douyin-specific handlers =====
function handleActivityChange(activity) {
  if (activity?.challenge?.length > 0) {
    for (const topic of activity.challenge) {
      if (form.tags && !form.tags.includes(topic)) {
        if ((form.activityId?.length || 0) + (form.tags?.length || 0) >= 5) break
        form.tags.push(topic)
      }
    }
  }
}

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

function handleHotspotChange(hotspot) {
  if (hotspot) { form.hotspotId = hotspot.word; form.hotspotData = hotspot }
  else { form.hotspotId = ''; form.hotspotData = null }
}

function handleTagSelect(tag) {
  if (tag) {
    form.selectedTag = tag
    const m = { poi: 'location', miniapp: 'miniapp', game: 'gamepad', mark: 'mark' }
    form.tagType = m[tag.type] || ''
    form.tagValue = tag.name || tag.id || ''
    ElMessage.success(`标签已选择: ${tag.name}`)
  } else {
    form.selectedTag = null; form.tagType = ''; form.tagValue = ''
  }
}

function handleMixChange(mix) {
  if (mix) { form.mixId = mix.mix_name; form.mixData = mix }
  else { form.mixId = ''; form.mixData = null }
}

defineExpose(publicApi)
</script>

<style scoped>
.douyin-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba($accent-rose, 0.15);
  background: rgba($accent-rose, 0.04);
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
