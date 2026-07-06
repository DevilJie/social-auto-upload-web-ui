<template>
  <div class="weibo-image-publish-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入微博正文..." maxlength="2000" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入话题内容,按回车确认(微博图集会拼成 #话题1 #话题2)</div>
      <el-input v-model="tagInput" placeholder="输入话题内容,按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="settings-row">
      <div class="setting-card" style="grid-column: 1 / -1">
        <div class="setting-label">内容声明</div>
        <el-select v-model="form.aiContent" placeholder="请选择" :disabled="disabled" style="width: 100%;">
          <el-option
            v-for="opt in statementOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { PLATFORMS } from '@/config/platforms'
import { useChannelForm } from '@/composables/useChannelForm'
import { useAutoExtractHashtags } from '@/utils/hashtag'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// 内容声明 options 来自 settingsFields.contentStatement(不是 aiContent!)
const statementField = PLATFORMS.WEIBO.settingsFields.find(f => f.key === 'contentStatement')
const statementOptions = computed(() => statementField?.options || [])

// 9 STANDARD_FIELDS 全部齐备(必含 aiContent,即使 PLATFORMS.WEIBO.defaultSettings 没这个 key)
// 7 文本字段(panel 内部状态);images/coverImage 不显式声明,4 级合并时
// undefined ?? common.images → 走公共区兜底(避免空数组阻挡 fallback)
const WEIBO_DEFAULTS = {
  title: '',
  description: '',
  tags: [],
  enableTimer: false,
  scheduleTime: '',
  aiContent: '',
  isOriginal: false,
  // 微博视频版残留字段(冗余但无害):
  videoType: '',
  weiboCategory: [],
  contentStatement: '',
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  WEIBO_DEFAULTS,
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
            account_id: accountId,
            platform: account.platform,
            filePath: account.filePath,
            title: merged.title,           // = description (watch 同步)
            description: merged.description,
            tags: merged.tags || [],
            aiContent: merged.aiContent || '',
            isOriginal: false,
            cover_path: '',
            dry_run: false,
          },
          batchId: extra?.batchId || '',
          landscapeCoverMaterialId: '',
          portraitCoverMaterialId: '',
        })
        emit('publish-result', { accountName, status: 'success', message: '发布成功' })
      } catch (e) {
        emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
      }
    },
    // 微博 panel 无独立必填项,所有校验已在 publishAll 完成
    validateFn: (accountId, merged) => ({ valid: true, errors: [] }),
  },
)

// 关键:form.title 始终 = form.description(让 publishAll 的 !merged.title 校验通过)
watch(() => form.description, (v) => { form.title = v || '' })

const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('话题已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

// 自动提取描述中的 #xxx 到标签数组(微博发布时会拼成 #话题1 #话题2)
useAutoExtractHashtags({
  form,
  descKey: 'description',
  tagKey: 'tags',
})

defineExpose(publicApi)
</script>

<style scoped>
.weibo-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.settings-row {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.settings-row .setting-card {
  min-width: 0;
}

.setting-card {
  border: 1px solid rgba(230, 22, 45, 0.15);
  background: rgba(230, 22, 45, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #E6162D;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.5;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
</style>
