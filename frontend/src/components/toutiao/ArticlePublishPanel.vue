<template>
  <div class="toutiao-article-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="grid-column: 1 / -1; margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card">
      <div class="setting-label">作品声明</div>
      <div class="setting-hint">可选。头条实测为单选 7 个选项(勾选新项会自动取消旧项),本系统按单选下发</div>
      <el-select v-model="form.creationDeclaration" placeholder="不声明" :disabled="disabled" clearable style="width: 100%;">
        <el-option v-for="opt in declarationOptions" :key="opt" :label="opt" :value="opt" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">封面模式</div>
      <div class="setting-hint">平台必填。单图由公共封面/正文首图自动填充;三图由正文前 3 张图自动填充,不足 3 张时自动降级单图;无封面也可定时/发表。推荐封面比例 16:9（1200×675），发布时自动裁切</div>
      <el-select v-model="form.coverMode" :disabled="disabled" style="width: 100%;">
        <el-option label="单图(推荐)" value="单图" />
        <el-option label="三图(正文前 3 图)" value="三图" />
        <el-option label="无封面" value="无封面" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">头条首发</div>
      <div class="setting-hint">可选。平台编辑器会记忆上次状态,自动化按本开关双向同步(勾选/取消);正文需不少于 100 字,校验不通过时平台会拦截</div>
      <el-checkbox v-model="form.firstPublish" :disabled="disabled">声明头条首发</el-checkbox>
    </div>

    <div class="setting-card">
      <div class="setting-label">授权平台自动维权</div>
      <div class="setting-hint">仅勾选「头条首发」时平台才显示该开关;需账号已开通全网维权</div>
      <el-checkbox v-model="form.autoRights" :disabled="disabled || !form.firstPublish">
        授权平台自动维权
      </el-checkbox>
    </div>

    <div class="setting-card">
      <div class="setting-label">投放广告</div>
      <div class="setting-hint">平台必填(默认投放广告赚收益)。「平台默认」= 不改动平台设置(当前账号默认投放)</div>
      <el-radio-group v-model="form.adRevenue" :disabled="disabled">
        <el-radio value="default">平台默认</el-radio>
        <el-radio value="on">投放广告赚收益</el-radio>
        <el-radio value="off">不投放广告</el-radio>
      </el-radio-group>
    </div>

    <div class="setting-card">
      <div class="setting-label">同时发布微头条</div>
      <div class="setting-hint">对应编辑器「发布得更多收益」。平台可能按账号资质/内容状态锁定该开关(实测禁用状态不稳定、与头条首发无稳定联动),禁用时自动化回读并跳过</div>
      <el-checkbox v-model="form.publishMicroHeadline" :disabled="disabled">
        发布得更多收益
      </el-checkbox>
    </div>

    <div class="setting-card">
      <div class="setting-label">添加位置</div>
      <div class="setting-hint">可选。选择平台内置城市(如「北京」「上海」),可提升同城推荐;支持输入过滤</div>
      <el-select
        v-model="form.location"
        placeholder="留空则不添加位置"
        filterable
        :disabled="disabled"
        clearable
        style="width: 100%;"
      >
        <el-option v-for="city in cityOptions" :key="city" :label="city" :value="city" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">添加至合集</div>
      <div class="setting-hint">可选。输入关键词回车搜索你的头条合集(与平台「添加合集」弹窗同源),选中后自动化在弹窗中选择同名合集</div>
      <CompilationSelect
        v-model="form.collectionName"
        :account-id="accountId"
        platform="toutiao"
        :disabled="disabled"
      />
    </div>

    <div class="setting-card setting-card--full">
      <div class="setting-label">定时发布</div>
      <div class="setting-hint">可选。仅「直接发表」模式生效,当前时间后 2 小时 ~ 7 天;无封面时同样可定时(平台不限制)</div>
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
      <div class="setting-label">今日头条文章说明</div>
      <div class="setting-hint">
        标题(2~30 字,超长截断)、正文富文本、图片使用左侧公共配置;
        正文图片自动上传头条图床,封面自动使用公共封面或正文首图。
        作品声明 / 头条首发 / 授权平台自动维权 / 投放广告 / 微头条 / 添加位置 /
        添加至合集 / 定时在发表前自动在编辑器设置区完成(逐项回读日志 + 发表前截图)。
        头条号图文编辑器无「原创声明」「创作获益」「评论权限」等独立控件。
        成功判定依据平台发表接口/草稿箱接口的 code(失败会带 code+msg)。
      </div>
    </div>
    <div class="setting-card setting-card--full">
      <div class="setting-label">封面建议</div>
      <div class="setting-hint">
        平台推荐 16:9，建议 1200×675（或 1920×1080）；三图模式三张同比例。
        发布时后端会自动按平台比例居中裁剪封面；未设置封面时按平台默认取正文首图。
      </div>
    </div>
  </div>
</template>

<script setup>
import { useAccountStore } from '@/stores/account'
import { articlePublishApi } from '@/api/articlePublish'
import { useChannelForm } from '@/composables/useChannelForm'
import CompilationSelect from '@/components/alipay/CompilationSelect.vue'
import { CHINA_CITIES } from '@/config/china-cities'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// 平台内置城市候选(可搜索本地过滤;自动化在平台下拉中按名称精确匹配)
const cityOptions = CHINA_CITIES

// 今日头条文章平台字段(与后端 publish_article kwargs 一一对应)
const TOUTIAO_ARTICLE_DEFAULTS = {
  scheduleTime: '',
  creationDeclaration: '',
  firstPublish: false,
  autoRights: false,
  adRevenue: 'default',
  publishMicroHeadline: true,
  coverMode: '单图',
  location: '',
  collectionName: '',
}

// 作品声明选项(头条编辑器 2026-10 实测 7 项, 平台实际单选取最后一项)
const declarationOptions = [
  '取材网络',
  '引用站内',
  '个人观点，仅供参考',
  '引用AI',
  '虚构演绎，故事经历',
  '投资观点，仅供参考',
  '健康医疗分享，仅供参考',
]

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  TOUTIAO_ARTICLE_DEFAULTS,
  { props, emit },
  {
    publishFn: async (accountId, accountName, commonData, merged, extra) => {
      const account = accountStore.accounts.find(a => a.id === accountId)
      if (!account) {
        emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
        return
      }
      try {
        // 投放广告三态: default=不改动平台默认(不传 adRevenue)
        const adRevenue = merged.adRevenue === 'on' ? true
          : merged.adRevenue === 'off' ? false : undefined
        await articlePublishApi.publish({
          account_configs: {
            account_id: accountId,
            account_name: accountName,
            platform: 'toutiao',
            filePath: account.filePath,
            articleTitle: commonData.articleTitle,
            articleHtml: commonData.articleHtml,
            coverStoredPath: extra?.coverStoredPath || '',
            creationDeclaration: merged.creationDeclaration || '',
            firstPublish: !!merged.firstPublish,
            adRevenue,
            publishMicroHeadline: merged.publishMicroHeadline !== false,
            // 自动维权仅首发勾选时平台才显示; 未勾选首发时不传(不改动)
            autoRights: merged.firstPublish ? !!merged.autoRights : undefined,
            location: merged.location || '',
            collectionName: merged.collectionName || '',
            coverMode: merged.coverMode || '单图',
            scheduleTime: merged.scheduleTime || '',
            dryRun: extra?.dryRun ?? true,
            isDraft: extra?.isDraft ?? true,
          },
          batchId: extra?.batchId || '',
        })
        const isDraft = extra?.isDraft !== false
        emit('publish-result', {
          accountName,
          status: 'success',
          message: isDraft ? '已存草稿' : '发表成功',
        })
      } catch (e) {
        emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
      }
    },
    // 文章标题/正文在公共区校验;面板只校验平台字段
    validateFn: (accountId, merged) => {
      const errors = []
      if (merged.scheduleTime) {
        const t = new Date(merged.scheduleTime.replace(/-/g, '/')).getTime()
        const diffMin = (t - Date.now()) / 60000
        if (Number.isNaN(diffMin)) errors.push('定时时间格式无效')
        else if (diffMin < 2 * 60) errors.push('定时时间需晚于当前 2 小时以上')
        else if (diffMin > 7 * 24 * 60) errors.push('定时时间不能超过 7 天')
      }
      if (merged.location && merged.location.length > 20) {
        errors.push('位置名称不能超过 20 字')
      }
      if (merged.collectionName && merged.collectionName.length > 50) {
        errors.push('合集名称不能超过 50 字')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

defineExpose(publicApi)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.toutiao-article-panel {
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
  color: #f04142;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.6;
}
</style>
