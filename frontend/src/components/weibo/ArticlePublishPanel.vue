<template>
  <div class="weibo-article-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="grid-column: 1 / -1; margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">导语</div>
      <div class="setting-hint">选填。微博头条文章编辑器「导语（选填）」，最多 44 字，展示在文章标题下方</div>
      <el-input
        v-model="form.articleDigest"
        type="textarea"
        :rows="2"
        placeholder="请输入导语（选填，≤44 字）"
        maxlength="44"
        show-word-limit
        :disabled="disabled"
      />
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">话题标签</div>
      <div class="setting-hint">可选。以 #话题# 形式追加到正文末尾并写入发布微博文案（最多 10 个）</div>
      <el-select
        v-model="form.weiboTopics"
        multiple
        filterable
        allow-create
        default-first-option
        :reserve-keyword="false"
        placeholder="输入话题名后回车,如: 千帆同步"
        :disabled="disabled"
        style="width: 100%;"
      >
        <el-option v-for="t in form.weiboTopics" :key="t" :label="t" :value="t" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">内容声明</div>
      <div class="setting-hint">
        可选。发布弹窗「内容声明」下拉，默认「无」。
        <span v-if="form.weiboRank === '粉丝'" class="linkage-tip">
          已选「粉丝」发布范围：平台限制内容声明与粉丝范围互斥，选择内容声明会自动改为公开
        </span>
      </div>
      <el-select
        v-model="form.weiboStatement"
        placeholder="无"
        :disabled="disabled || form.weiboRank === '粉丝'"
        clearable
        style="width: 100%;"
      >
        <el-option v-for="opt in statementOptions" :key="opt" :label="opt" :value="opt" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">发布范围</div>
      <div class="setting-hint">发布弹窗「公开 / 粉丝」下拉；粉丝范围文章仅粉丝可见</div>
      <el-select v-model="form.weiboRank" :disabled="disabled" style="width: 100%;">
        <el-option v-for="opt in rankOptions" :key="opt" :label="opt" :value="opt" />
      </el-select>
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">微博正文文案</div>
      <div class="setting-hint">
        可选。发布弹窗「微博正文」（必填，最多 2000 字）；留空自动生成
        「发布了头条文章：《文章标题》」并追加话题标签
      </div>
      <el-input
        v-model="form.weiboText"
        type="textarea"
        :rows="3"
        placeholder="留空则自动生成：发布了头条文章：《标题》 #话题#"
        maxlength="2000"
        show-word-limit
        :disabled="disabled"
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">原创声明</div>
      <div class="setting-hint">发布弹窗「我同意《微博签约媒体原创认证协议》，并声明本文是原创作品」；仅签约自媒体账号有此设置项，其他账号自动跳过</div>
      <el-switch v-model="form.weiboIsOriginal" :disabled="disabled" />
    </div>

    <div class="setting-card">
      <div class="setting-label">关注@头条文章</div>
      <div class="setting-hint">发布弹窗「关注@头条文章 第一时间获取官方通知」（平台默认勾选；已关注的账号不再显示）</div>
      <el-radio-group v-model="form.weiboFollowOfficial" :disabled="disabled" size="small">
        <el-radio-button value="关注">关注</el-radio-button>
        <el-radio-button value="不关注">不关注</el-radio-button>
      </el-radio-group>
    </div>

    <div class="setting-card">
      <div class="setting-label">仅粉丝阅读全文</div>
      <div class="setting-hint">编辑器「发布设置 → 其他设置」；开启后非粉丝仅可阅读全文的 50%（该账号平台默认开启，此处默认关闭=公开全文）</div>
      <el-switch v-model="form.weiboFollowToRead" :disabled="disabled" />
    </div>

    <div class="setting-card">
      <div class="setting-label">定时发布</div>
      <div class="setting-hint">可选。仅「直接发表」模式生效；微博允许今天 ~ 未来 7 天，提交走定时发表接口</div>
      <el-date-picker
        v-model="form.scheduleTime"
        type="datetime"
        placeholder="不选则立即发表"
        format="YYYY-MM-DD HH:mm"
        value-format="YYYY-MM-DD HH:mm:ss"
        :disabled-date="disabledScheduleDate"
        :disabled="disabled"
        style="width: 100%;"
      />
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">微博头条文章说明</div>
      <div class="setting-hint">
        标题（≤32 字）、正文图文、封面使用左侧公共配置：正文图片自动上传微博图床并替换为
        sinaimg CDN 地址，封面自动上传并裁剪为 16:9；导语写入编辑器「导语」字段；
        话题以 #话题# 追加到正文末尾。发表时若触发微博身份验证（风控 geetest），会在
        有头浏览器中等待人工完成验证，超时按发布失败记录。<br />
        <b>未纳入本系统的平台设置</b>：专栏设置、设置推荐文章、同步至新浪新闻、仅在移动端展示、
        付费阅读 / V+订阅 / 单篇付费 / 赞赏（后六项受账号能力位控制，本账号下不显示）。
      </div>
    </div>
    <div class="setting-card setting-card--full">
      <div class="setting-label">封面建议</div>
      <div class="setting-hint">
        平台推荐 16:9，建议 1000×563（或 1200×675）。
        发布时后端会自动按平台比例居中裁剪封面；未设置封面时按平台默认取正文首图。
      </div>
    </div>
  </div>
</template>

<script setup>
import { watch } from 'vue'
import { useAccountStore } from '@/stores/account'
import { articlePublishApi } from '@/api/articlePublish'
import { useChannelForm } from '@/composables/useChannelForm'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// 微博头条文章平台字段(标题/正文/封面在公共区,此处仅微博差异字段)
// 字段与微博头条文章编辑器「发布设置」区 + 发布弹窗 PublishModal 一一对应
const WEIBO_ARTICLE_DEFAULTS = {
  articleDigest: '',        // 导语(编辑器「导语（选填）」，≤44 字)
  weiboTopics: [],          // 话题标签(#话题# 追加正文 + 发布微博文案)
  weiboStatement: '',       // 内容声明(无/内容由AI生成/内容为虚构演绎)
  weiboRank: '公开',        // 发布范围(公开 / 粉丝)
  weiboText: '',            // 发布弹窗「微博正文」自定义文案(空=平台默认)
  weiboIsOriginal: false,   // 原创声明(仅签约自媒体有该设置项)
  weiboFollowOfficial: '关注', // 关注@头条文章(关注 / 不关注)
  weiboFollowToRead: false, // 仅粉丝阅读全文(编辑器发布设置)
  scheduleTime: '',         // 定时发布(仅直接发表模式生效)
}

// 内容声明选项(微博发布弹窗「内容声明」下拉实测 2026-10)
const statementOptions = ['无', '内容由AI生成', '内容为虚构演绎']
// 发布范围选项(发布弹窗 WbSetting: 公开 rank=0 / 粉丝 rank=10)
const rankOptions = ['公开', '粉丝']

// 定时发布: 平台日期选择器仅允许今天 ~ 今天+7 天
function disabledScheduleDate(date) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const max = new Date(today)
  max.setDate(max.getDate() + 7)
  return date.getTime() < today.getTime() || date.getTime() > max.getTime()
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  WEIBO_ARTICLE_DEFAULTS,
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
            platform: 'weibo',
            filePath: account.filePath,
            articleTitle: commonData.articleTitle,
            articleHtml: commonData.articleHtml,
            // 导语复用通用 articleDigest(bp 已透传为 digest → summary)
            articleDigest: merged.articleDigest || '',
            // 微博特有字段(bp 需透传 weibo_topics / weibo_statement /
            // weibo_text / weibo_rank / weibo_is_original /
            // weibo_follow_official / weibo_follow_to_read)
            weiboTopics: merged.weiboTopics || [],
            weiboStatement: merged.weiboStatement || '',
            weiboText: merged.weiboText || '',
            weiboRank: merged.weiboRank || '公开',
            weiboIsOriginal: !!merged.weiboIsOriginal,
            weiboFollowOfficial: (merged.weiboFollowOfficial || '关注') !== '不关注',
            weiboFollowToRead: !!merged.weiboFollowToRead,
            scheduleTime: merged.scheduleTime || '',
            // 显式封面(素材 stored_path,空则取正文首图)
            coverStoredPath: extra?.coverStoredPath || '',
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
    validateFn: (accountId, merged) => {
      // 标题在公共区(commonData)不回传本面板,超 32 字由后端自动截断,
      // 这里只校验微博面板自己的字段
      const errors = []
      const digest = (merged.articleDigest || '').trim()
      if (digest.length > 44) errors.push('导语不能超过 44 字')
      const topics = merged.weiboTopics || []
      if (topics.length > 10) errors.push('话题标签最多 10 个')
      const weiboText = (merged.weiboText || '').trim()
      if (weiboText.length > 2000) errors.push('微博正文文案不能超过 2000 字')
      if (merged.weiboRank === '粉丝' && merged.weiboStatement) {
        errors.push('平台限制：发布范围「粉丝」与内容声明互斥，请清空内容声明')
      }
      // 定时发布: 今天 ~ 未来 7 天, 且不能早于当前时间
      const sched = (merged.scheduleTime || '').trim()
      if (sched) {
        const t = new Date(sched.replace(/-/g, '/')).getTime()
        const max = Date.now() + 7 * 24 * 3600 * 1000
        if (Number.isNaN(t)) errors.push('定时时间格式无效')
        else if (t < Date.now()) errors.push('定时时间不能早于当前时间')
        else if (t > max) errors.push('定时时间不能超过 7 天（微博平台限制）')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

defineExpose(publicApi)

// 联动 1: 发布范围切到「粉丝」时, 平台会把内容声明重置为「无」→ 同步清空
watch(() => form.weiboRank, (v) => {
  if (v === '粉丝' && form.weiboStatement) form.weiboStatement = ''
})

// 联动 2: 选择内容声明时, 平台(内容声明在「公开」项子菜单)会强制发布范围=公开
watch(() => form.weiboStatement, (v) => {
  if (v && form.weiboRank === '粉丝') form.weiboRank = '公开'
})
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.weibo-article-panel {
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
  color: #ff8200;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.6;
}

.linkage-tip {
  color: #e6a23c;
}
</style>
