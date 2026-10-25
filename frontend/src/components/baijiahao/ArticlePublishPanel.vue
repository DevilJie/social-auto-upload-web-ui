<template>
  <div class="baijiahao-article-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="grid-column: 1 / -1; margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card">
      <div class="setting-label">封面对布</div>
      <div class="setting-hint">
        平台「设置封面」为必填。三图模式按「公共封面 → 正文图片」顺序取 3 张上传，
        不足 3 张自动退回单图。推荐封面比例 4:3（800×600），发布时自动裁切
      </div>
      <el-radio-group v-model="form.coverMode" :disabled="disabled">
        <el-radio value="single">单图</el-radio>
        <el-radio value="three">三图</el-radio>
      </el-radio-group>
    </div>

    <div class="setting-card">
      <div class="setting-label">智能创作</div>
      <div class="setting-hint">平台默认勾选「自动生成播客」；不勾选则发布时取消该开关</div>
      <el-checkbox v-model="form.podcast" :disabled="disabled">
        自动生成播客
      </el-checkbox>
    </div>

    <div class="setting-card">
      <div class="setting-label">创作声明</div>
      <div class="setting-hint">可选。勾选后发布时同步勾选「采用AI生成内容」</div>
      <el-checkbox v-model="form.aiContent" :disabled="disabled">
        采用AI生成内容
      </el-checkbox>
    </div>

    <div class="setting-card">
      <div class="setting-label">来源说明</div>
      <div class="setting-hint">
        可选。勾选后发布时同步勾选「来源说明」，并联动填写平台必填的
        来源时间与来源地点
      </div>
      <el-checkbox v-model="form.sourceNote" :disabled="disabled">
        添加来源说明
      </el-checkbox>
      <template v-if="form.sourceNote">
        <el-date-picker
          v-model="form.sourceTime"
          type="date"
          placeholder="来源时间(不选默认今天)"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          :disabled="disabled"
          style="width: 100%; margin-top: 10px;"
        />
        <el-input
          v-model="form.sourceLocation"
          placeholder="来源地点，如：北京市/北京市"
          maxlength="40"
          :disabled="disabled"
          clearable
          style="margin-top: 8px;"
        />
      </template>
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">定时发布</div>
      <div class="setting-hint">可选。仅「直接发表」模式生效，需当前时间后 1 小时 ~ 7 天内</div>
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
      <div class="setting-label">百家号图文说明</div>
      <div class="setting-hint">
        标题(2~64 字)、正文图文使用左侧公共配置。正文图片自动上传百家号图床;
        封面优先使用公共封面(三图模式取公共封面+正文图片共 3 张)。
        活动投稿：平台「活动投稿」当前账号暂无可参与活动，未纳入自动化。
      </div>
    </div>
    <div class="setting-card setting-card--full">
      <div class="setting-label">封面建议</div>
      <div class="setting-hint">
        平台推荐 4:3，建议 800×600（或 1200×900）；三图模式三张同比例。
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

// 百家号文章平台字段(对应编辑器「发文设置」区)
const BAJIAHAO_ARTICLE_DEFAULTS = {
  scheduleTime: '',
  aiContent: false,
  sourceNote: false,
  sourceTime: '',
  sourceLocation: '',
  coverMode: 'single',
  podcast: true,
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  BAJIAHAO_ARTICLE_DEFAULTS,
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
            platform: 'baijiahao',
            filePath: account.filePath,
            articleTitle: commonData.articleTitle,
            articleHtml: commonData.articleHtml,
            coverStoredPath: extra?.coverStoredPath || '',
            creationStatement: merged.aiContent ? '采用AI生成内容' : '',
            sourceDeclaration: !!merged.sourceNote,
            sourceTime: merged.sourceTime || '',
            sourceLocation: merged.sourceLocation || '',
            coverMode: merged.coverMode || 'single',
            podcast: merged.podcast !== false,
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
    // 标题/正文在公共区校验,面板覆盖默认校验
    validateFn: (accountId, merged) => {
      const errors = []
      // 来源说明联动: 勾选后平台会出现「来源时间/来源地点」必填项
      if (merged.sourceNote) {
        if (!merged.sourceTime && !merged.sourceLocation) {
          errors.push('勾选「来源说明」后需填写来源时间或来源地点,否则声明不会生效')
        }
        const loc = String(merged.sourceLocation || '').trim()
        if (loc && !loc.includes('/') && !loc.includes(',')) {
          errors.push('来源地点格式应为「省/市」,如 北京市/北京市')
        }
      }
      if (merged.scheduleTime) {
        const t = new Date(merged.scheduleTime.replace(/-/g, '/')).getTime()
        const diffMin = (t - Date.now()) / 60000
        if (Number.isNaN(diffMin)) errors.push('定时时间格式无效')
        else if (diffMin < 60) errors.push('定时时间需晚于当前 1 小时')
        else if (diffMin > 7 * 24 * 60) errors.push('定时时间不能超过 7 天')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

defineExpose(publicApi)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.baijiahao-article-panel {
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
  color: #3385ff;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.6;
}
</style>
