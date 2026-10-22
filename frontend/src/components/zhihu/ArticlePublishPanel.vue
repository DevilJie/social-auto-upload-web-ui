<template>
  <div class="zhihu-article-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="grid-column: 1 / -1; margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card">
      <div class="setting-label">创作声明</div>
      <div class="setting-hint">可选。默认「无声明」不设置</div>
      <el-select v-model="form.creationStatement" placeholder="无声明" :disabled="disabled" clearable style="width: 100%;">
        <el-option v-for="opt in declarationOptions" :key="opt" :label="opt" :value="opt" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">投稿至问题</div>
      <div class="setting-hint">可选。填问题关键词,发布时弹窗内搜索并选第一条(最多 1 个)</div>
      <el-input v-model="form.targetQuestion" placeholder="问题关键词,如: 目标检测数据标注" maxlength="50" :disabled="disabled" clearable />
    </div>

    <div class="setting-card">
      <div class="setting-label">文章话题</div>
      <div class="setting-hint">可选。最多 5 个,输入后回车添加,发布时按名称搜索联想选中</div>
      <el-select
        v-model="form.topics"
        multiple filterable allow-create default-first-option
        :reserve-keyword="false"
        placeholder="输入话题名后回车"
        :disabled="disabled"
        style="width: 100%;"
      >
        <el-option v-for="t in form.topics" :key="t" :label="t" :value="t" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">内容来源</div>
      <div class="setting-hint">可选。发布新闻类内容需标注信息来源</div>
      <el-select v-model="form.contentSource" placeholder="选择具体的信息来源（可选）" :disabled="disabled" clearable style="width: 100%;">
        <el-option v-for="opt in sourceOptions" :key="opt" :label="opt" :value="opt" />
      </el-select>
      <el-checkbox v-model="form.sourceSelfShot" :disabled="disabled" style="margin-top: 8px;">
        图片/视频为自行拍摄
      </el-checkbox>
      <template v-if="form.sourceSelfShot">
        <div class="setting-hint" style="margin-top: 8px;">自行拍摄需补齐拍摄时间与地点(知乎必填)</div>
        <el-date-picker
          v-model="form.shotTime"
          type="date"
          placeholder="拍摄时间(默认今天)"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          :disabled="disabled"
          style="width: 100%;"
        />
        <div style="display: flex; gap: 8px; margin-top: 8px;">
          <el-select v-model="form.shotProvince" placeholder="省份" :disabled="disabled" filterable allow-create style="width: 50%;">
            <el-option v-for="p in provinceOptions" :key="p" :label="p" :value="p" />
          </el-select>
          <el-input v-model="form.shotCity" placeholder="城市,如: 杭州" :disabled="disabled" maxlength="20" style="width: 50%;" />
        </div>
      </template>
    </div>

    <div class="setting-card">
      <div class="setting-label">定时发布</div>
      <div class="setting-hint">可选。仅「直接发表」模式生效,未来 30 分钟 ~ 48 小时内</div>
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
      <div class="setting-label">知乎文章说明</div>
      <div class="setting-hint">
        标题(≤100 字)、正文图文、封面使用左侧公共配置。封面自动上传知乎图床;
        正文图片自动上传知乎图床。创作声明/话题/投稿至问题/内容来源发布时
        自动在知乎编辑器「发布设置」区完成。
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

// 知乎文章平台字段(与知乎编辑器「发布设置」区一一对应)
const ZHIHU_ARTICLE_DEFAULTS = {
  scheduleTime: '',
  creationStatement: '',
  targetQuestion: '',
  topics: [],
  contentSource: '',
  sourceSelfShot: false,
  shotTime: '',
  shotProvince: '',
  shotCity: '',
}

// 创作声明选项(知乎编辑器实测 2026-10)
const declarationOptions = [
  '包含剧透',
  '包含医疗建议',
  '虚构创作',
  '包含理财内容',
  '包含 AI 辅助创作，作者对内容负责',
]

// 内容来源选项(知乎「添加内容来源」弹窗实测 2026-10)
const sourceOptions = ['官方网站', '新闻报道', '电视媒体', '纸质媒体']

// 拍摄省份选项(知乎省份下拉实测 2026-10)
const provinceOptions = [
  '北京', '天津', '上海', '重庆',
  '河北省', '山西省', '辽宁省', '吉林省', '黑龙江省',
  '江苏省', '浙江省', '安徽省', '福建省', '江西省', '山东省',
  '河南省', '湖北省', '湖南省', '广东省', '海南省',
  '四川省', '贵州省', '云南省', '陕西省', '甘肃省', '青海省',
  '内蒙古自治区', '西藏自治区', '宁夏回族自治区', '新疆维吾尔自治区',
  '广西壮族自治区', '台湾省', '香港特别行政区', '澳门特别行政区', '海外地区',
]

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
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
            creationStatement: merged.creationStatement || '',
            targetQuestion: merged.targetQuestion || '',
            topics: merged.topics || [],
            contentSource: merged.contentSource || '',
            sourceSelfShot: !!merged.sourceSelfShot,
            shotTime: merged.shotTime || '',
            shotProvince: merged.shotProvince || '',
            shotCity: merged.shotCity || '',
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
    // 文章标题/正文在公共区校验;面板覆盖默认校验(否则必报「标题不能为空」)
    validateFn: (accountId, merged) => {
      const errors = []
      if (merged.scheduleTime) {
        const t = new Date(merged.scheduleTime.replace(/-/g, '/')).getTime()
        const diffMin = (t - Date.now()) / 60000
        if (Number.isNaN(diffMin)) errors.push('定时时间格式无效')
        else if (diffMin < 30) errors.push('定时时间需晚于当前 30 分钟以上')
        else if (diffMin > 48 * 60) errors.push('定时时间不能超过 48 小时')
      }
      if ((merged.topics || []).length > 5) errors.push('文章话题最多 5 个')
      if (merged.sourceSelfShot && !merged.shotProvince) errors.push('自行拍摄需选择拍摄省份')
      if (merged.sourceSelfShot && !merged.shotCity) errors.push('自行拍摄需填写拍摄城市')
      return { valid: errors.length === 0, errors }
    },
  },
)

defineExpose(publicApi)

// 取消自行拍摄时清空子字段(知乎必填项只在开关开启时有意义)
watch(() => form.sourceSelfShot, (v) => {
  if (!v) {
    form.shotTime = ''
    form.shotProvince = ''
    form.shotCity = ''
  }
})
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
