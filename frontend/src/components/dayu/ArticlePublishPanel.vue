<template>
  <div class="dayu-article-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="grid-column: 1 / -1; margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card">
      <div class="setting-label">作者名称</div>
      <div class="setting-hint">可选。编辑器「作者名称」0/10 字,留空用平台默认作者</div>
      <el-input
        v-model="form.dayuAuthor"
        placeholder="留空使用平台默认作者"
        maxlength="10"
        show-word-limit
        :disabled="disabled"
        clearable
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">信息来源（必选）</div>
      <div class="setting-hint">大鱼号发表必选「信息来源」，默认「无需标注」；平台 7 个单选项全集</div>
      <el-radio-group v-model="form.dayuSourceRemark" :disabled="disabled">
        <el-radio
          v-for="opt in sourceRemarkOptions"
          :key="opt"
          :value="opt"
        >{{ opt }}</el-radio>
      </el-radio-group>
    </div>

    <div v-if="form.dayuSourceRemark === '转载'" class="setting-card setting-card--full">
      <div class="setting-label">转载原文链接（必填）</div>
      <div class="setting-hint">选「转载」时平台才显示该输入框,且必须填写原文链接</div>
      <el-input
        v-model="form.dayuOriginalUrl"
        placeholder="请输入原文链接 https://..."
        maxlength="200"
        :disabled="disabled"
        clearable
      />
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">定时发布</div>
      <div class="setting-hint">可选。仅「直接发表」模式生效，当前时间后 2 小时 ~ 7 天内（平台仅支持 5 分钟粒度，自动向上取整）</div>
      <el-date-picker
        v-model="form.scheduleTime"
        type="datetime"
        placeholder="不选则立即发表"
        format="YYYY-MM-DD HH:mm"
        value-format="YYYY-MM-DD HH:mm:ss"
        :disabled="disabled"
        style="width: 100%;"
      />
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">大鱼号图文说明</div>
      <div class="setting-hint">
        标题（5~50 字）、正文图文、封面图使用左侧公共配置。正文图片自动上传大鱼号
        图床（mp.dayu.com/dayu/image）并替换 CDN URL；封面图会上传图床后作为
        「正文首图」插入（大鱼号封面只能从正文图片中选择），再自动完成裁剪保存。
        横版封面平台默认「三封面」，自动化统一切「单封面」以保证可保存发表；竖版封面
        为平台可选设置，暂未接入自动设置。作者名称 / 信息来源 / 转载原文链接 / 定时
        发表由本面板透传；「原创声明」「分类」「广告」「首发」「评论权限」在当前账号
        图文编辑器无对应控件（平台按账号资质默认处理，formData 中仅隐藏字段）。
        发表成功判定为监听 /dashboard/submit-article 响应（含 data.content_id），
        不使用 URL 判定。
      </div>
    </div>
    <div class="setting-card setting-card--full">
      <div class="setting-label">封面建议</div>
      <div class="setting-hint">
        平台推荐 横版 16:9，建议 1280×720（或更高）；竖版封面 9:16。
        发布时后端会自动按平台比例居中裁剪封面；未设置封面时按平台默认取正文首图。
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

// 大鱼号图文平台字段（对应编辑器「作者名称 / 信息来源 / 其他设置」区）
const DAYU_ARTICLE_DEFAULTS = {
  dayuAuthor: '',
  dayuSourceRemark: '无需标注',
  dayuOriginalUrl: '',
  scheduleTime: '',
}

// 信息来源选项（2026-10 编辑器 radio 实测）
const sourceRemarkOptions = [
  '无需标注',
  'AI生成',
  '虚构演绎',
  '营销信息',
  '转载',
  '个人观点',
  '不适宜未成年人',
]

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  DAYU_ARTICLE_DEFAULTS,
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
            platform: 'dayu',
            filePath: account.filePath,
            articleTitle: commonData.articleTitle,
            articleHtml: commonData.articleHtml,
            coverStoredPath: extra?.coverStoredPath || '',
            // bp 已把 articleAuthor 透传为平台 author kwarg
            articleAuthor: merged.dayuAuthor || '',
            dayuSourceRemark: merged.dayuSourceRemark || '无需标注',
            dayuOriginalUrl: merged.dayuOriginalUrl || '',
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
    // 标题/正文在公共区校验；大鱼号特有校验：转载链接/定时窗口(2h~7d)
    validateFn: (accountId, merged) => {
      const errors = []
      if ((merged.dayuAuthor || '').length > 10) {
        errors.push('作者名称不能超过 10 字')
      }
      if (merged.dayuSourceRemark === '转载' && !(merged.dayuOriginalUrl || '').trim()) {
        errors.push('信息来源选择「转载」时必须填写原文链接')
      }
      if (merged.scheduleTime) {
        const t = new Date(merged.scheduleTime.replace(/-/g, '/')).getTime()
        const diffMin = (t - Date.now()) / 60000
        if (Number.isNaN(diffMin)) errors.push('定时时间格式无效')
        else if (diffMin < 2 * 60) errors.push('大鱼号定时发布需晚于当前 2 小时')
        else if (diffMin > 7 * 24 * 60) errors.push('大鱼号定时发布仅支持 7 天内')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

defineExpose(publicApi)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.dayu-article-panel {
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
  color: #ff6a00;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.6;
}
</style>
