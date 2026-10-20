<template>
  <div class="zhihu-article-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">知乎文章说明</div>
      <div class="setting-hint">
        标题(≤100 字)、正文图文、封面使用左侧公共配置。封面会自动上传并经
        知乎裁剪(2.35:1 / 1:1)设置;正文图片自动上传知乎图床。
      </div>
      <div class="setting-hint">
        当前账号的知乎编辑器为精简版发布设置(仅封面/定时发布),
        投稿至问题/创作声明/文章话题/内容来源等内容设置该账号不可用;
        「定时发布」的日历时间控件暂未支持自动化,如需定时请发表后在
        知乎文章管理中调整。
      </div>
    </div>
  </div>
</template>

<script setup>
import { useAccountStore } from '@/stores/account'
import { articlePublishApi } from '@/api/articlePublish'
import { useChannelForm } from '@/composables/useChannelForm'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// 知乎文章平台字段
const ZHIHU_ARTICLE_DEFAULTS = {
  scheduleTime: '',
}

const { hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  ZHIHU_ARTICLE_DEFAULTS,
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
            platform: 'zhihu',
            filePath: account.filePath,
            articleTitle: commonData.articleTitle,
            articleHtml: commonData.articleHtml,
            coverStoredPath: extra?.coverStoredPath || '',
            scheduleTime: merged.scheduleTime || '',
            dryRun: extra?.dryRun ?? true,
            isDraft: extra?.isDraft ?? true,
          },
          batchId: extra?.batchId || '',
        })
        emit('publish-result', {
          accountName,
          status: 'success',
          message: extra?.isDraft === false ? '发表成功' : '已存草稿',
        })
      } catch (e) {
        emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
      }
    },
    // 文章标题/正文在公共区校验;面板无 title 字段,
    // 必须覆盖默认校验(否则必报「标题不能为空」)
    validateFn: (accountId, merged) => {
      const errors = []
      if (merged.scheduleTime) {
        const t = new Date(merged.scheduleTime.replace(/-/g, '/')).getTime()
        const diffMin = (t - Date.now()) / 60000
        if (Number.isNaN(diffMin)) errors.push('定时时间格式无效')
        else if (diffMin < 30) errors.push('定时时间需晚于当前 30 分钟以上')
        else if (diffMin > 48 * 60) errors.push('定时时间不能超过 48 小时')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

defineExpose(publicApi)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.zhihu-article-panel {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba($info-color, 0.15);
  background: rgba($info-color, 0.04);
  border-radius: 8px;
  padding: 16px;
  min-width: 0;
}

.setting-card--full {
  grid-column: 1 / -1;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #0084ff;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.6;
}
</style>
