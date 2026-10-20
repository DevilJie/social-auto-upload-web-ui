<template>
  <div class="weixin-gzh-article-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card">
      <div class="setting-label">作者</div>
      <div class="setting-hint">选填。显示在文章标题下方</div>
      <el-input v-model="form.articleAuthor" placeholder="请输入作者名(选填)" maxlength="30" :disabled="disabled" />
    </div>

    <div class="setting-card">
      <div class="setting-label">创作来源</div>
      <div class="setting-hint">可选。选择创作来源声明</div>
      <el-select v-model="form.gzhClaimSource" placeholder="请选择创作来源（可选）" :disabled="disabled" clearable style="width: 100%;">
        <el-option v-for="opt in claimSourceOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <div v-if="accountId" class="setting-card">
      <div class="setting-label">加入合集</div>
      <div class="setting-hint">可选。按名称匹配文章合集(无合集时自动跳过)</div>
      <RemoteSearchSelect
        v-model="form.gzhCollectionName"
        :data="form.gzhCollectionData"
        :fetcher="fetchGzhArticleCollections"
        :field-map="{ label: 'name' }"
        search-mode="frontend"
        empty-behavior="load-all"
        placeholder="选择合集"
        @change="handleCollectionChange"
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">原文链接</div>
      <div class="setting-hint">选填。显示在文章底部「阅读原文」</div>
      <el-input v-model="form.gzhOriginalUrl" placeholder="https://...(选填)" maxlength="200" :disabled="disabled" clearable />
    </div>

    <div class="setting-card">
      <div class="setting-label">定时发表</div>
      <div class="setting-hint">可选。最近 7 天,需大于当前时间至少 1 小时</div>
      <el-date-picker
        v-model="form.scheduleTime"
        type="datetime"
        placeholder="不选则按草稿模式执行"
        format="YYYY-MM-DD HH:mm"
        value-format="YYYY-MM-DD HH:mm:ss"
        :disabled="disabled"
        style="width: 100%;"
      />
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">摘要</div>
      <div class="setting-hint">选填。≤120 字,转发卡片和会话页展示;不填默认抓取正文开头</div>
      <el-input v-model="form.articleDigest" type="textarea" :rows="3" placeholder="请输入摘要(选填)" maxlength="120" show-word-limit :disabled="disabled" />
    </div>
  </div>
</template>

<script setup>
import { useAccountStore } from '@/stores/account'
import { articlePublishApi } from '@/api/articlePublish'
import { weixinGzhApi } from '@/api/weixin_gzh'
import { useChannelForm } from '@/composables/useChannelForm'
import RemoteSearchSelect from '@/components/common/RemoteSearchSelect.vue'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// 公众号文章平台字段(标题/正文在公共区,此处仅平台差异字段)
const WEIXIN_GZH_ARTICLE_DEFAULTS = {
  articleAuthor: '',
  articleDigest: '',
  gzhClaimSource: '',
  gzhCollectionName: '',
  gzhCollectionData: null,
  gzhOriginalUrl: '',
  scheduleTime: '',
}

// 创作来源选项(与图集/视频一致;不含「素材来源官方媒体/网络新闻」)
const claimSourceOptions = [
  { label: '内容由AI生成', value: '内容由AI生成' },
  { label: '内容剧情演绎，仅供娱乐', value: '内容剧情演绎，仅供娱乐' },
  { label: '个人观点，仅供参考', value: '个人观点，仅供参考' },
  { label: '健康医疗分享，仅供参考', value: '健康医疗分享，仅供参考' },
  { label: '投资观点，仅供参考', value: '投资观点，仅供参考' },
  { label: '无需声明', value: '无需声明' },
]

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  WEIXIN_GZH_ARTICLE_DEFAULTS,
  { props, emit },
  {
    publishFn: async (accountId, accountName, commonData, merged, extra) => {
      const account = accountStore.accounts.find(a => a.id === accountId)
      if (!account) {
        emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
        return
      }
      try {
        await articlePublishApi.publish({
          account_configs: {
            account_id: accountId,
            account_name: accountName,
            platform: 'weixin_gzh',
            filePath: account.filePath,
            articleTitle: commonData.articleTitle,
            articleHtml: commonData.articleHtml,
            articleAuthor: merged.articleAuthor || '',
            articleDigest: merged.articleDigest || '',
            gzhClaimSource: merged.gzhClaimSource || '',
            gzhCollectionName: merged.gzhCollectionName || '',
            gzhOriginalUrl: merged.gzhOriginalUrl || '',
            scheduleTime: merged.scheduleTime || '',
            // 显式封面(素材 stored_path,空则后端自动抓正文首图)
            coverStoredPath: extra?.coverStoredPath || '',
            // 一键发布安全默认:保存草稿(草稿箱可人工确认后群发,不消耗群发次数)
            dryRun: extra?.dryRun ?? true,
            isDraft: extra?.isDraft ?? true,
          },
          batchId: extra?.batchId || '',
        })
        emit('publish-result', { accountName, status: 'success', message: '发布成功' })
      } catch (e) {
        emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
      }
    },
    validateFn: (accountId, merged) => {
      const errors = []
      if (merged.articleDigest && merged.articleDigest.length > 120) {
        errors.push('摘要不能超过 120 字')
      }
      if (merged.gzhOriginalUrl && !/^https?:\/\//.test(merged.gzhOriginalUrl)) {
        errors.push('原文链接必须以 http(s):// 开头')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

// 文章合集数据源(合集管理页按 tab 文案查询;文章合集 tab 与视频/贴图不同,
// 后端找不到 tab 时返回空列表,下拉为空不影响发布)
async function fetchGzhArticleCollections(keyword) {
  const resp = await weixinGzhApi.getCollections(props.accountId, '图文合集')
  const all = resp.data?.list || []
  const kw = keyword?.trim().toLowerCase()
  return {
    list: kw ? all.filter(c => c.name?.toLowerCase().includes(kw)) : all,
  }
}

function handleCollectionChange(col) {
  form.gzhCollectionData = col || null
}

defineExpose(publicApi)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.weixin-gzh-article-panel {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba($info-color, 0.15);
  background: rgba($info-color, 0.04);
  border-radius: 8px;
  padding: 16px;
  min-width: 0; /* 防止长 URL/日期把列撑破 */
}

/* 长文本字段(摘要)占整行 */
.setting-card--full {
  grid-column: 1 / -1;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #07C160;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.5;
}
</style>
