<template>
  <div class="csdn-article-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="grid-column: 1 / -1; margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card">
      <div class="setting-label">文章标签（必填）</div>
      <div class="setting-hint">CSDN 发表必填，最多 6 个。搜索平台联想标签后点选添加（支持自定义标签回车）</div>
      <div v-if="form.tags.length" class="tag-chips">
        <el-tag
          v-for="t in form.tags"
          :key="t"
          closable
          :disable-transitions="true"
          @close="removeTag(t)"
        >
          {{ t }}
        </el-tag>
      </div>
      <RemoteSearchSelect
        v-model="pendingTag"
        :fetcher="tagFetcher"
        search-mode="backend"
        placeholder="搜索并添加标签"
        search-placeholder="输入关键词，停顿 2 秒自动联想"
        @change="onTagPicked"
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">分类专栏</div>
      <div class="setting-hint">可选。填入专栏名，发布时尝试「新建分类专栏」（失败自动跳过）</div>
      <el-input
        v-model="form.category"
        placeholder="如: 千帆同步实战"
        maxlength="30"
        :disabled="disabled"
        clearable
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">文章类型</div>
      <div class="setting-hint">
        原创(默认)/转载/翻译。转载时「原文链接」必填且不能设为 VIP 可见
      </div>
      <el-radio-group v-model="form.articleType" :disabled="disabled">
        <el-radio value="原创">原创</el-radio>
        <el-radio value="转载">转载</el-radio>
        <el-radio value="翻译">翻译</el-radio>
      </el-radio-group>
    </div>

    <div class="setting-card">
      <div class="setting-label">可见范围</div>
      <div class="setting-hint">可选。转载文章平台不允许 VIP 可见</div>
      <el-select v-model="form.readType" :disabled="disabled" style="width: 100%;">
        <el-option label="全部可见" value="public" />
        <el-option label="仅我可见" value="private" />
        <el-option label="粉丝可见" value="fans" />
        <el-option label="VIP可见" value="vip" :disabled="form.articleType === '转载'" />
      </el-select>
    </div>

    <div class="setting-card setting-card--full" v-if="form.articleType !== '原创'">
      <div class="setting-label">
        原文链接<span v-if="form.articleType === '转载'" class="required-mark">（必填）</span>
      </div>
      <div class="setting-hint">
        {{ form.articleType === '转载' ? '转载时平台要求必填原文链接' : '翻译时选填原文链接' }}
      </div>
      <el-input
        v-model="form.originalLink"
        placeholder="https://..."
        maxlength="500"
        :disabled="disabled"
        clearable
      />
      <el-checkbox
        v-if="form.articleType === '转载'"
        v-model="form.authorizedStatus"
        :disabled="disabled"
        style="margin-top: 8px;"
      >
        原文允许转载或者本次转载已经获得原文作者授权
      </el-checkbox>
    </div>

    <div class="setting-card">
      <div class="setting-label">创作声明</div>
      <div class="setting-hint">可选。对应平台「创作声明」下拉</div>
      <el-select v-model="form.creationStatement" :disabled="disabled" style="width: 100%;">
        <el-option label="无声明" value="无声明" />
        <el-option label="部分内容由AI辅助生成" value="部分内容由AI辅助生成" />
        <el-option label="内容来源网络，进行整合/再创作" value="内容来源网络，进行整合/再创作" />
        <el-option label="个人观点，仅供参考" value="个人观点，仅供参考" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">文章摘要</div>
      <div class="setting-hint">可选，最多 256 字（对应平台「文章摘要」）</div>
      <el-input
        v-model="form.digest"
        type="textarea"
        :rows="2"
        maxlength="256"
        show-word-limit
        placeholder="不填则由平台自动提取"
        :disabled="disabled"
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">文章备份</div>
      <div class="setting-hint">可选。勾选后同步备份到 GitCode（平台「文章备份」）</div>
      <el-checkbox v-model="form.syncGitCode" :disabled="disabled">
        同时备份到 GitCode
      </el-checkbox>
    </div>

    <div class="setting-card">
      <div class="setting-label">定时发布</div>
      <div class="setting-hint">可选。仅「直接发表」模式生效，需当前时间后 4 小时 ~ 7 天内</div>
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
      <div class="setting-label">CSDN 文章说明</div>
      <div class="setting-hint">
        标题(5~100 字)、正文图文、封面使用左侧公共配置。正文图片自动上传 CSDN 图床
        (i-blog.csdnimg.cn) 并替换为 CDN URL；封面自动走「从本地上传 + 裁剪确认」。
        发表成功判定为监听保存接口 postedit/saveArticle 响应 code=200。
      </div>
    </div>
    <div class="setting-card setting-card--full">
      <div class="setting-label">封面建议</div>
      <div class="setting-hint">
        平台推荐 16:9，建议 960×540（或 1920×1080）。
        发布时后端会自动按平台比例居中裁剪封面；未设置封面时按平台默认取正文首图。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useAccountStore } from '@/stores/account'
import { articlePublishApi } from '@/api/articlePublish'
import { csdnApi } from '@/api/csdn'
import { useChannelForm } from '@/composables/useChannelForm'
import RemoteSearchSelect from '@/components/common/RemoteSearchSelect.vue'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// ===== 文章标签: 复用全局 RemoteSearchSelect(平台联想标签) =====
// fetcher 契约: (keyword) => Promise<{ list }> ; 后端返回字符串数组 → 映射为 {name}
const pendingTag = ref('')

const tagFetcher = async (keyword) => {
  const resp = await csdnApi.searchTags(props.accountId, keyword || '')
  const list = (resp.code === 200 ? resp.data?.list : []) || []
  return { list: list.map(name => ({ name })) }
}

// 选中 → 加入标签(去重, ≤6), 清空搜索框可连续添加
function onTagPicked(item) {
  const name = item?.name || ''
  pendingTag.value = ''
  if (!name || form.tags.includes(name)) return
  if (form.tags.length >= 6) return
  form.tags.push(name)
}

function removeTag(t) {
  form.tags = form.tags.filter(x => x !== t)
}

// 切换账号清空联想缓存
watch(() => props.accountId, () => {
  pendingTag.value = ''
})

// CSDN 文章平台字段（对应 CSDN 编辑器「发文设置」区）
const CSDN_ARTICLE_DEFAULTS = {
  tags: [],
  category: '',
  articleType: '原创',
  readType: 'public',
  creationStatement: '无声明',
  digest: '',
  originalLink: '',
  authorizedStatus: false,
  syncGitCode: false,
  scheduleTime: '',
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  CSDN_ARTICLE_DEFAULTS,
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
            platform: 'csdn',
            filePath: account.filePath,
            articleTitle: commonData.articleTitle,
            articleHtml: commonData.articleHtml,
            coverStoredPath: extra?.coverStoredPath || '',
            tags: merged.tags || [],
            category: merged.category || '',
            articleType: merged.articleType || '原创',
            readType: merged.readType || 'public',
            creationStatement: merged.creationStatement || '无声明',
            digest: merged.digest || '',
            // 兼容 article_publish_bp 现有 articleDigest 透传
            articleDigest: merged.digest || '',
            originalLink: merged.originalLink || '',
            authorizedStatus: !!merged.authorizedStatus,
            syncGitCode: !!merged.syncGitCode,
            // 兼容: article_publish_bp 目前只透传 topics，CLI 侧
            // backend 以 topics 作为 tags 兜底；bp 增加 tags 透传后
            // 以 tags 为准，两者值一致不冲突
            topics: merged.tags || [],
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
    // 标题/正文在公共区校验；CSDN 特有校验：标签必填 + 定时窗口 +
    // 文章类型联动(转载必填原文链接 / 不能 VIP 可见)
    validateFn: (accountId, merged) => {
      const errors = []
      const tags = merged.tags || []
      if (tags.length === 0) errors.push('CSDN 发表要求至少 1 个文章标签')
      if (tags.length > 6) errors.push('CSDN 文章标签最多 6 个')
      if (merged.articleType === '转载') {
        if (!String(merged.originalLink || '').trim()) {
          errors.push('文章类型为「转载」时原文链接必填')
        }
        if (merged.readType === 'vip') {
          errors.push('转载文章不能设置为 VIP 可见')
        }
      }
      if (merged.scheduleTime) {
        const t = new Date(merged.scheduleTime.replace(/-/g, '/')).getTime()
        const diffMin = (t - Date.now()) / 60000
        if (Number.isNaN(diffMin)) errors.push('定时时间格式无效')
        else if (diffMin < 4 * 60) errors.push('CSDN 定时发布需晚于当前 4 小时')
        else if (diffMin > 7 * 24 * 60) errors.push('CSDN 定时发布不能超过 7 天')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

// 联动: 切到「转载」时如选了 VIP 可见,自动回退「全部可见」
watch(() => form.articleType, (val) => {
  if (val === '转载' && form.readType === 'vip') {
    form.readType = 'public'
  }
})

defineExpose(publicApi)
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.csdn-article-panel {
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

// 已选标签 chips
.tag-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #fc5531;
  margin-bottom: 8px;
}

.required-mark {
  color: #f56c6c;
  font-weight: 500;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.6;
}
</style>
