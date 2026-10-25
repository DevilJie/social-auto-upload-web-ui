<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    width="80%"
    top="5vh"
    :close-on-press-escape="false"
    @opened="onOpened"
  >
    <template #header>
      <div class="ocf-dialog-header">
        <span class="ocf-dialog-title">从历史发布一键填写</span>
        <el-tooltip content="重新查看引导" placement="top">
          <button class="ocf-guide-btn" type="button" @click="startGuide">
            <el-icon><Guide /></el-icon>
            新手引导
          </button>
        </el-tooltip>
      </div>
    </template>
    <div v-loading="loading" class="grid" data-tour="ocf-cards">
      <el-empty
        v-if="!loading && list.length === 0"
        :description="`还没有可用的历史记录，去 ${type === 'video' ? '视频发布' : '图集发布'} 试试？`"
      />
      <div v-for="record in list" :key="record.id" class="card" @click="handlePick(record)">
        <div class="card-cover">
          <img v-if="record.coverSrc" :src="record.coverSrc" alt="封面" />
          <div v-else class="cover-placeholder">
            <el-icon :size="32"><Picture /></el-icon>
          </div>
        </div>
        <div class="card-body">
          <div class="card-title">{{ record.title || '无标题' }}</div>
          <div class="card-desc">{{ (record.description || '').slice(0, 60) }}</div>
          <div class="card-channels">
            <span v-for="ch in record.channels" :key="(ch.platform || '') + '-' + (ch.account_id || '')" class="channel-tag">
              {{ ch.platform || '未知平台' }}
            </span>
          </div>
          <div class="card-time">{{ formatRelativeTime(record.created_at) }}</div>
        </div>
      </div>
    </div>

    <el-pagination
      v-if="total > 0"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="load"
      @size-change="load"
    />
  </el-dialog>

  <!-- 弹窗新手引导（teleport 到 body，首次打开自动播放） -->
  <GuideTour
    ref="ocfTourRef"
    :steps="oneClickFillGuideSteps"
    @finish="onGuideDone"
    @skip="onGuideDone"
  />
</template>

<script setup>
import { ref, watch } from 'vue'
import { http } from '@/utils/request'
import { Picture, Guide } from '@element-plus/icons-vue'
import GuideTour from '@/components/GuideTour.vue'
import { oneClickFillGuideSteps, GUIDE_KEYS, isGuideDone, markGuideDone } from '@/config/guides'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  type: { type: String, required: true },
})
const emit = defineEmits(['update:modelValue', 'pick'])

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

function formatRelativeTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = (now - d) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`
  return d.toLocaleDateString('zh-CN')
}

function buildVideoCoverUrl(thumbPath) {
  if (!thumbPath) return ''
  return `${window.location.protocol}//${window.location.hostname}:5409/api/materials/file/${thumbPath}`
}

async function load() {
  loading.value = true
  try {
    const res = await http.get('/api/v2/publish-templates', {
      type: props.type, page: page.value, page_size: pageSize.value
    })
    const items = res.data?.list || []
    for (const item of items) {
      if (item.type === 'video' && item.thumbnail_path) {
        item.coverSrc = buildVideoCoverUrl(item.thumbnail_path)
      } else if (item.type === 'image' && item.first_image_id) {
        try {
          const m = await http.get(`/api/materials/${item.first_image_id}`)
          const mat = m.data
          if (mat) {
            item.coverSrc = mat.stored_path
              ? `${window.location.protocol}//${window.location.hostname}:5409/api/materials/file/${mat.stored_path.replace(/^\/+/, '')}`
              : mat.url || ''
          } else {
            item.coverSrc = ''
          }
        } catch (_) {
          item.coverSrc = ''
        }
      } else {
        item.coverSrc = ''
      }
    }
    list.value = items
    total.value = res.data?.total || 0
  } catch (e) {
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

// ========== 弹窗新手引导 ==========
const ocfTourRef = ref(null)

const startGuide = () => ocfTourRef.value?.start()

// 引导完成/跳过都记为"已看过"，之后打开弹窗不再自动播放
const onGuideDone = () => markGuideDone(GUIDE_KEYS.oneClickFill)

// @opened：弹窗打开动画结束后再启动引导，保证高亮定位准确
function onOpened() {
  if (!isGuideDone(GUIDE_KEYS.oneClickFill)) {
    setTimeout(() => ocfTourRef.value?.start(), 150)
  }
}

watch(() => props.modelValue, (open) => {
  if (open) {
    page.value = 1
    load()
  } else {
    // 保险：弹窗关闭时结束可能还开着的引导
    ocfTourRef.value?.stop()
  }
})

function handlePick(record) {
  emit('pick', record)
  emit('update:modelValue', false)
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

// 自定义 header（#header 插槽内容编译自本组件，scoped 直接命中）：
// 标题 + 新手引导入口，padding-right 给右上角关闭按钮留位
.ocf-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 32px;
}

.ocf-dialog-title {
  font-size: 18px;
  font-weight: 600;
  color: $text-primary;
}

.ocf-guide-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px dashed rgba($overlay-rgb, 0.28);
  background: transparent;
  color: $text-muted;
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all $transition-fast;

  &:hover {
    color: $brand-start;
    border-color: rgba($brand-start, 0.5);
    background: rgba($brand-start, 0.08);
  }
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  min-height: 200px;
}

.card {
  border: 1px solid $border;
  border-radius: 12px;
  background: $bg-elevated;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.2s;
  &:hover {
    border-color: $brand-start;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  }
}

.card-cover {
  position: relative;
  width: 100%;
  padding-top: 56.25%;
  background: $bg-surface;
  img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .cover-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: $text-muted;
  }
}

.card-body { padding: 12px; }

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  font-size: 12px;
  color: $text-muted;
  margin: 4px 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-channels {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  .channel-tag {
    font-size: 11px;
    padding: 2px 6px;
    background: $bg-surface;
    border-radius: 4px;
    color: $text-secondary;
  }
}

.card-time {
  font-size: 11px;
  color: $text-muted;
  margin-top: 8px;
}
</style>
