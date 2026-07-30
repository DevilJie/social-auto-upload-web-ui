<template>
  <div class="weixin-gzh-image-publish-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标题 <span class="required">*</span></div>
      <el-input v-model="form.title" placeholder="请输入标题" maxlength="20" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入描述..." maxlength="1000" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入话题内容,按回车确认(发布时拼成 #话题1 #话题2)</div>
      <el-input v-model="tagInput" placeholder="输入话题内容,按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">创作来源</div>
      <div class="setting-hint">可选。选择创作来源声明</div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <el-select v-model="form.gzhClaimSource" placeholder="请选择创作来源（可选）" :disabled="disabled" clearable style="flex: 1;">
          <el-option v-for="opt in claimSourceOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-button v-if="form.gzhClaimSource" text size="small" @click="form.gzhClaimSource = ''" :disabled="disabled">清空</el-button>
      </div>
    </div>

    <div v-if="accountId" class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">加入合集</div>
      <div class="setting-hint">可选。从贴图合集选择(无合集时为空)</div>
      <RemoteSearchSelect
        v-model="form.gzhCollectionName"
        :data="form.gzhCollectionData"
        :fetcher="fetchGzhImageCollections"
        :field-map="{ label: 'name' }"
        search-mode="frontend"
        empty-behavior="load-all"
        placeholder="选择贴图合集"
        @change="handleCollectionChange"
      />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">定时发布</div>
      <div class="setting-hint">可选。最近7天,需大于当前时间至少1小时</div>
      <el-date-picker
        v-model="form.scheduleTime"
        type="datetime"
        placeholder="选择时间(不选则立即发布)"
        format="YYYY-MM-DD HH:mm"
        value-format="YYYY-MM-DD HH:mm:ss"
        :disabled="disabled"
        style="width: 100%;"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { weixinGzhApi } from '@/api/weixin_gzh'
import { useChannelForm } from '@/composables/useChannelForm'
import { useAutoExtractHashtags } from '@/utils/hashtag'
import RemoteSearchSelect from '@/components/common/RemoteSearchSelect.vue'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// 公众号图集默认字段(标题≤20, 描述≤1000)
const WEIXIN_GZH_DEFAULTS = {
  title: '',
  description: '',
  tags: [],
  gzhClaimSource: '',
  gzhCollectionName: '',
  gzhCollectionData: null,
  scheduleTime: '',
}

// 创作来源选项(与 platforms.js WEIXIN_GZH 一致;不含「素材来源官方媒体/网络新闻」)
const claimSourceOptions = [
  { label: '内容由AI生成', value: '内容由AI生成' },
  { label: '内容剧情演绎，仅供娱乐', value: '内容剧情演绎，仅供娱乐' },
  { label: '个人观点，仅供参考', value: '个人观点，仅供参考' },
  { label: '健康医疗分享，仅供参考', value: '健康医疗分享，仅供参考' },
  { label: '投资观点，仅供参考', value: '投资观点，仅供参考' },
  { label: '无需声明', value: '无需声明' },
]

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  WEIXIN_GZH_DEFAULTS,
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
            platform: '微信公众号',
            filePath: account.filePath,
            title: merged.title,
            description: merged.description,
            tags: merged.tags || [],
            gzhClaimSource: merged.gzhClaimSource || '',
            gzhCollectionName: merged.gzhCollectionName || '',
            scheduleTime: merged.scheduleTime || '',
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
    validateFn: (accountId, merged) => {
      const errors = []
      if (!merged.title || !merged.title.trim()) {
        errors.push('请填写标题(≤20 字)')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) return
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

// 贴图合集数据源(后端 type=贴图合集)
async function fetchGzhImageCollections(keyword) {
  const resp = await weixinGzhApi.getCollections(props.accountId, '贴图合集')
  const all = resp.data?.list || []
  const kw = keyword?.trim().toLowerCase()
  return {
    list: kw ? all.filter(c => c.name?.toLowerCase().includes(kw)) : all,
  }
}

function handleCollectionChange(col) {
  form.gzhCollectionData = col || null
}

// 自动提取描述中的 #xxx 到标签数组
useAutoExtractHashtags({
  form,
  descKey: 'description',
  tagKey: 'tags',
})

defineExpose(publicApi)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.weixin-gzh-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba($info-color, 0.15);
  background: rgba($info-color, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #07C160;
  margin-bottom: 8px;
}

.required {
  color: #f56c6c;
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
