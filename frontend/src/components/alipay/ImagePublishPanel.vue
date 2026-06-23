<template>
  <div class="alipay-image-publish-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标题 <span class="required">*</span></div>
      <el-input v-model="form.title" placeholder="一个好的标题，能获得更多人的喜欢哦" maxlength="30" show-word-limit :disabled="disabled" />
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
      <div class="setting-label">音乐</div>
      <div class="setting-hint">可选。添加音乐会提升内容的消费性,帮助内容拿到更多的流量</div>
      <!-- 已选音乐展示 -->
      <div v-if="form.music && form.music.title" class="music-selected">
        <div class="music-cover-mini">
          <img v-if="form.music.coverUrl" :src="form.music.coverUrl" :alt="form.music.title" @error="onMusicImgError" />
          <el-icon v-else><Headset /></el-icon>
        </div>
        <span class="music-name">{{ form.music.title }}</span>
        <el-button text size="small" @click="openMusicDrawer" :disabled="disabled">更换</el-button>
        <el-button text size="small" type="danger" @click="clearMusic" :disabled="disabled">移除</el-button>
      </div>
      <!-- 未选 → 添加音乐按钮 -->
      <el-button v-else :icon="Headset" @click="openMusicDrawer" :disabled="disabled">添加音乐</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">作者声明</div>
      <div class="setting-hint">可选。选择作者声明</div>
      <el-select v-model="form.authorStatement" placeholder="请选择作者声明（可选）" :disabled="disabled" clearable style="width: 100%;">
        <el-option label="内容由AI生成" value="内容由AI生成" />
      </el-select>
    </div>

    <!-- 音乐选择抽屉 -->
    <MusicDrawer
      v-model="musicDrawerVisible"
      :account-id="accountId"
      @select="onMusicSelect"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Headset } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { useChannelForm } from '@/composables/useChannelForm'
import MusicDrawer from './MusicDrawer.vue'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// 支付宝图集默认字段
// authorStatement 不在面板显示(图集下拉只有「内容由AI生成」一项,后端兜底默认填它)
const ALIPAY_DEFAULTS = {
  title: '',
  description: '',
  tags: [],
  music: null, // { musicId, title, coverUrl, audioUrl, duration }
  authorStatement: '',
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  ALIPAY_DEFAULTS,
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
            platform: '支付宝',
            filePath: account.filePath,
            title: merged.title, // 图集标题(独立字段,≤30 字)
            description: merged.description,
            tags: merged.tags || [],
            music_id: merged.music?.musicId || '',
            music_title: merged.music?.title || '',
            author_statement: merged.authorStatement || '', // 可选
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
        errors.push('请填写标题(≤30 字)')
      }
      return { valid: errors.length === 0, errors }
    },
  },
)

const tagInput = ref('')
const musicDrawerVisible = ref(false)

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) return
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

function openMusicDrawer() {
  musicDrawerVisible.value = true
}

function onMusicSelect(music) {
  form.music = { ...music }
}

function clearMusic() {
  form.music = null
}

function onMusicImgError(e) {
  e.target.style.display = 'none'
}

defineExpose(publicApi)
</script>

<style scoped>
.alipay-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.setting-card {
  border: 1px solid rgba(22, 119, 255, 0.15);
  background: rgba(22, 119, 255, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #1677FF;
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

.music-selected {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid rgba(22, 119, 255, 0.2);
  border-radius: 6px;
}

.music-cover-mini {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  overflow: hidden;
  background: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  flex-shrink: 0;
}

.music-cover-mini img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.music-name {
  flex: 1;
  font-size: 13px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
