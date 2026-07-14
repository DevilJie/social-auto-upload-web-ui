<template>
  <div class="draft-box">
    <div class="draft-header">
      <h2>草稿箱</h2>
      <el-tabs v-model="activeTab" class="draft-tabs">
        <el-tab-pane label="视频草稿" name="video">
          <span class="draft-count">{{ videoDrafts.length }} 个草稿</span>
        </el-tab-pane>
        <el-tab-pane label="图集草稿" name="image">
          <span class="draft-count">{{ imageDrafts.length }} 个草稿</span>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- Batch operations toolbar -->
    <div class="draft-toolbar" :class="{ 'is-active': selectMode }">
      <el-button
        v-if="!selectMode"
        size="default"
        :icon="Select"
        class="toolbar-trigger"
        @click="toggleSelectMode"
      >
        多选
      </el-button>

      <template v-else>
        <el-checkbox
          :model-value="isAllSelected"
          :indeterminate="isIndeterminate"
          class="toolbar-select-all"
          @change="toggleSelectAll"
        >
          全选
        </el-checkbox>

        <div class="selected-info">
          <el-icon class="selected-icon"><Check /></el-icon>
          <span>已选 <strong>{{ selection.size }}</strong> / {{ currentTabTotal }}</span>
        </div>

        <div class="toolbar-spacer"></div>

        <el-button
          size="default"
          :icon="Promotion"
          type="primary"
          :disabled="selection.size === 0 || isPublishing"
          @click="onBatchPublish"
        >
          批量发布<template v-if="selection.size > 0"> ({{ selection.size }})</template>
        </el-button>
        <el-button
          size="default"
          :icon="Delete"
          :disabled="selection.size === 0"
          @click="onBatchDelete"
        >
          批量删除
        </el-button>
        <el-button
          size="default"
          :icon="Close"
          class="toolbar-exit"
          @click="toggleSelectMode"
        >
          退出多选
        </el-button>
      </template>
    </div>

    <!-- Video Drafts -->
    <template v-if="activeTab === 'video'">
      <div v-if="!loading && videoDrafts.length === 0" class="empty-state">
        <el-empty description="还没有保存的视频草稿">
          <el-button type="primary" @click="router.push('/publish-center')">去发布视频</el-button>
        </el-empty>
      </div>

      <div v-else class="draft-grid">
        <div
          v-for="draft in videoDrafts"
          :key="draft.id"
          class="draft-card"
          :class="{
            'is-selected': selection.has(draft.id),
            'select-mode': selectMode,
          }"
          @click="onCardClick(draft.id)"
        >
          <div
            v-if="selectMode"
            class="card-selector"
            :class="{ 'is-checked': selection.has(draft.id) }"
            @click.stop="toggleSelection(draft.id, !selection.has(draft.id))"
          >
            <el-icon class="selector-icon"><Check /></el-icon>
          </div>
          <div class="card-cover">
            <img
              v-if="draft.cover_path"
              :src="getCoverUrl(draft.cover_path)"
              alt="封面"
            />
            <div v-else class="cover-placeholder">
              <el-icon :size="32"><Picture /></el-icon>
            </div>
            <span v-if="draft.video_duration" class="duration-badge">
              {{ formatDuration(draft.video_duration) }}
            </span>
          </div>

          <div class="card-body">
            <div class="card-title">{{ draft.title || '无标题' }}</div>

            <div v-if="draft.channels_summary && draft.channels_summary.length" class="card-channels">
              <div class="channels-track" :class="{ 'channels-marquee': isOverflow(draft.id) }" :ref="el => setChannelRef(draft.id, el)">
                <span v-for="ch in draft.channels_summary" :key="ch.platform" class="channel-tag">
                  <img
                    v-if="getPlatformLogo(ch.platform)"
                    :src="getPlatformLogo(ch.platform)"
                    class="channel-icon"
                  />
                  {{ ch.name }} × {{ ch.count }}
                </span>
              </div>
            </div>

            <div class="card-meta">
              <span v-if="draft.video_file_size">{{ formatFileSize(draft.video_file_size) }}</span>
              <span>{{ formatTime(draft.updated_at) }}</span>
            </div>
          </div>

          <div class="card-actions">
            <button class="action-btn action-edit" @click.stop="editVideoDraft(draft.id)">
              <el-icon><Edit /></el-icon> 编辑
            </button>
            <button class="action-btn action-delete" @click.stop="confirmDelete(draft.id, 'video')">
              <el-icon><Delete /></el-icon> 删除
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Batch draft publish dialog -->
    <BatchDraftPublishDialog
      v-model:visible="dialogVisible"
      :drafts="dialogDrafts"
      :failures="dialogFailures"
      @confirm="onDialogConfirm"
    />

    <!-- Image Drafts -->
    <template v-if="activeTab === 'image'">
      <div v-if="!loading && imageDrafts.length === 0" class="empty-state">
        <el-empty description="还没有保存的图集草稿">
          <el-button type="primary" @click="router.push('/image-publish')">去发布图集</el-button>
        </el-empty>
      </div>

      <div v-else class="draft-grid">
        <div
          v-for="draft in imageDrafts"
          :key="draft.id"
          class="draft-card"
          :class="{
            'is-selected': selection.has(draft.id),
            'select-mode': selectMode,
          }"
          @click="onCardClick(draft.id)"
        >
          <div
            v-if="selectMode"
            class="card-selector"
            :class="{ 'is-checked': selection.has(draft.id) }"
            @click.stop="toggleSelection(draft.id, !selection.has(draft.id))"
          >
            <el-icon class="selector-icon"><Check /></el-icon>
          </div>
          <div class="card-cover">
            <img
              v-if="draft.cover_path"
              :src="getCoverUrl(draft.cover_path)"
              alt="封面"
            />
            <div v-else class="cover-placeholder">
              <el-icon :size="32"><Picture /></el-icon>
            </div>
          </div>

          <div class="card-body">
            <div class="card-title">{{ getImageDraftTitle(draft) || '无标题' }}</div>

            <div v-if="draft.channels_summary && draft.channels_summary.length" class="card-channels">
              <div class="channels-track">
                <span v-for="ch in draft.channels_summary" :key="ch.platform" class="channel-tag">
                  <img
                    v-if="getPlatformLogo(ch.platform)"
                    :src="getPlatformLogo(ch.platform)"
                    class="channel-icon"
                  />
                  {{ ch.name }} × {{ ch.count }}
                </span>
              </div>
            </div>

            <div class="card-meta">
              <span>{{ formatTime(draft.updated_at) }}</span>
            </div>
          </div>

          <div class="card-actions">
            <button class="action-btn action-edit" @click.stop="editImageDraft(draft.id)">
              <el-icon><Edit /></el-icon> 编辑
            </button>
            <button class="action-btn action-delete" @click.stop="confirmDelete(draft.id, 'image')">
              <el-icon><Delete /></el-icon> 删除
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Picture, Edit, Delete, Check, Select, Promotion, Close } from '@element-plus/icons-vue'
import { draftApi } from '@/api/draft'
import { imagePublishApi } from '@/api/imagePublish'
import { getPlatformByKey } from '@/config/platforms'
import { getFileUrl } from '@/utils/storage'
import BatchDraftPublishDialog from '@/components/BatchDraftPublishDialog.vue'

const router = useRouter()
const activeTab = ref('video')
const videoDrafts = ref([])
const imageDrafts = ref([])
const loading = ref(true)
const channelRefs = {}
const overflowMap = ref({})

// Batch operations state
const selection = ref(new Set())           // 选中的草稿 id
const selectMode = ref(false)              // 多选模式开关
const dialogVisible = ref(false)
const dialogDrafts = ref([])                // 给 dialog 的草稿列表
const dialogFailures = ref([])              // 校验失败列表
const isPublishing = ref(false)

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

function getCoverUrl(path) {
  return getFileUrl(path)
}

function getPlatformLogo(platformKey) {
  const p = getPlatformByKey(platformKey)
  return p?.logo || null
}

function getImageDraftTitle(draft) {
  // 优先使用 title 字段（后端已提取）
  if (draft.title && draft.title !== '无标题') {
    return draft.title
  }
  // 从 draft_data 中提取
  if (draft.draft_data) {
    const pc = draft.draft_data.platformConfigs || {}
    for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
      const title = pc[key]?.title
      if (title && title.trim()) {
        return title.trim()
      }
    }
  }
  return ''
}

function formatDuration(seconds) {
  if (!seconds) return ''
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes >= 1024 * 1024 * 1024) return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB'
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / 1024).toFixed(0) + ' KB'
}

function formatTime(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  const now = new Date()
  const diff = now - date
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  return date.toLocaleDateString('zh-CN')
}

function editVideoDraft(id) {
  router.push(`/publish-center?draft=${id}`)
}

function editImageDraft(id) {
  router.push(`/image-publish?draft=${id}`)
}

function setChannelRef(draftId, el) {
  if (el) {
    channelRefs[draftId] = el
    nextTick(() => {
      overflowMap.value[draftId] = el.scrollWidth > el.parentElement.clientWidth
    })
  }
}

function isOverflow(draftId) {
  return overflowMap.value[draftId]
}

async function confirmDelete(id, type) {
  const typeName = type === 'video' ? '视频' : '图集'
  try {
    await ElMessageBox.confirm(`确定删除这个${typeName}草稿吗？`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await draftApi.deleteDraft(id)
    ElMessage.success('草稿已删除')
    await loadAllDrafts()
  } catch {
    // cancelled or error
  }
}

async function loadAllDrafts() {
  loading.value = true
  try {
    // 统一从 /api/v2/drafts 获取，根据 type 分类
    const [videoResp, imageResp] = await Promise.all([
      draftApi.getDrafts('video'),
      draftApi.getDrafts('image')
    ])
    videoDrafts.value = videoResp.data || []
    imageDrafts.value = imageResp.data || []
  } catch (e) {
    console.error('Failed to load drafts:', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadAllDrafts)

// ===== Batch operations =====

const currentTabTotal = computed(() => getCurrentDrafts().length)
const isAllSelected = computed(() => {
  const total = currentTabTotal.value
  return total > 0 && selection.value.size >= total
})
const isIndeterminate = computed(() => {
  return selection.value.size > 0 && selection.value.size < currentTabTotal.value
})

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) {
    selection.value = new Set()
  }
}

function toggleSelectAll(checked) {
  if (checked) {
    selection.value = new Set(getCurrentDrafts().map((d) => d.id))
  } else {
    selection.value = new Set()
  }
}

function onCardClick(id) {
  if (!selectMode.value) return
  toggleSelection(id, !selection.value.has(id))
}

function clearSelection() {
  selection.value = new Set()
}

function toggleSelection(id, checked) {
  if (checked) selection.value.add(id)
  else selection.value.delete(id)
  // 触发响应式更新（Set 本身无深度响应）
  selection.value = new Set(selection.value)
}

function getCurrentDrafts() {
  return activeTab.value === 'video' ? videoDrafts.value : imageDrafts.value
}

async function onBatchDelete() {
  const count = selection.value.size
  if (count === 0) return
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${count} 个草稿？此操作不可恢复。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  const ids = [...selection.value]
  try {
    const resp = await draftApi.batchDeleteDrafts(ids)
    const { deleted = [], failed = [] } = resp || {}
    if (deleted.length) {
      ElMessage.success(`已删除 ${deleted.length} 个草稿`)
      // 从本地列表移除
      videoDrafts.value = videoDrafts.value.filter((d) => !deleted.includes(d.id))
      imageDrafts.value = imageDrafts.value.filter((d) => !deleted.includes(d.id))
    }
    if (failed.length) {
      ElMessage.warning(`${failed.length} 个草稿删除失败：${failed.map((f) => f.reason).join('; ')}`)
    }
    selection.value = new Set()
  } catch (e) {
    ElMessage.error(`批量删除失败：${e.message || e}`)
  }
}

function extractPlatforms(draft) {
  // 从 channels_summary（list of {platform, name, count}）提取平台 key 列表
  const list = draft?.channels_summary || []
  return list.map((c) => c.platform).filter(Boolean)
}

async function onBatchPublish() {
  const ids = [...selection.value]
  const current = getCurrentDrafts()
  // 仅推送当前 tab 下选中的草稿
  dialogDrafts.value = current
    .filter((d) => ids.includes(d.id))
    .map((d) => ({
      id: d.id,
      type: d.type,
      title: d.title,
      platforms: extractPlatforms(d),
    }))
  dialogFailures.value = []
  dialogVisible.value = true
}

async function onDialogConfirm(confirmedIds) {
  dialogVisible.value = false
  if (!confirmedIds || confirmedIds.length === 0) return

  isPublishing.value = true
  const isImage = activeTab.value === 'image'
  try {
    // 根据当前 tab 调不同的批量发布端点
    const resp = isImage
      ? await imagePublishApi.batchPublishImageDrafts(confirmedIds)
      : await draftApi.batchPublishVideoDrafts(confirmedIds)
    const { task_ids = [], failed = [] } = resp || {}
    if (task_ids.length) {
      ElMessage.success({
        message: `已入队 ${task_ids.length} 个任务，去任务中心查看 →`,
        duration: 4000,
      })
    }
    if (failed.length) {
      ElMessage.warning({
        message: `${failed.length} 个草稿发布失败：${failed.map((f) => f.reason).join('; ')}`,
      })
    }
    selection.value = new Set()
  } catch (e) {
    ElMessage.error({ message: `批量发布失败：${e?.message || e}` })
  } finally {
    isPublishing.value = false
  }
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.draft-box {
  padding: 24px;
  min-height: 100%;
}

.draft-header {
  margin-bottom: 24px;

  h2 {
    margin: 0 0 16px 0;
    font-size: 20px;
    font-weight: 600;
    color: $text-primary;
  }
}

.draft-tabs {
  :deep(.el-tabs__header) {
    margin: 0;
  }

  :deep(.el-tabs__item) {
    color: $text-muted;

    &.is-active {
      color: $brand-start;
    }
  }

  :deep(.el-tabs__active-bar) {
    background: $gradient-brand;
  }
}

.draft-count {
  font-size: 13px;
  color: $text-muted;
  margin-left: 12px;
}

.empty-state {
  display: flex;
  justify-content: center;
  padding: 80px 0;
}

.draft-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.draft-card {
  position: relative;
  background: rgba($overlay-rgb, 0.04);
  border: 1px solid $border;
  border-radius: $radius-lg;
  overflow: hidden;
  transition: $transition-base;
  display: flex;
  flex-direction: column;
}

.card-cover {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: rgba($overlay-rgb, 0.03);
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .cover-placeholder {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: $text-muted;
  }

  .duration-badge {
    position: absolute;
    bottom: 8px;
    right: 8px;
    background: rgba(0, 0, 0, 0.7);
    color: #fff;
    font-size: 12px;
    padding: 2px 6px;
    border-radius: 4px;
  }
}

.card-body {
  padding: 12px 16px;
  flex: 1;
}

.card-title {
  font-size: 14px;
  font-weight: 500;
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 8px;
}

.card-channels {
  overflow: hidden;
  margin-bottom: 8px;
}

.channels-track {
  display: inline-flex;
  gap: 6px;
  white-space: nowrap;
}

.channels-marquee {
  animation: marquee-scroll 8s linear infinite;
}

.channel-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: $text-secondary;
  background: rgba($overlay-rgb, 0.06);
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
}

.channel-icon {
  width: 14px;
  height: 14px;
  border-radius: 2px;
}

@keyframes marquee-scroll {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}

.card-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: $text-muted;
}

.card-actions {
  display: flex;
  border-top: 1px solid $border;
  margin-top: auto;
}

.action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 0;
  border: none;
  background: transparent;
  color: $text-secondary;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: $transition-base;

  &:first-child {
    border-right: 1px solid $border;
  }

  &.action-edit:hover {
    background: rgba($info-color, 0.1);
    color: #409eff;
  }

  &.action-delete:hover {
    background: rgba($danger-color, 0.1);
    color: #f56c6c;
  }
}

.draft-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  padding: 8px 12px;
  border-radius: $radius-card;
  border: 1px solid transparent;
  transition: $transition-base;

  &.is-active {
    background: linear-gradient(135deg, rgba($brand-start, 0.1), rgba($brand-end, 0.06));
    border-color: $border-active;
    box-shadow: 0 0 24px rgba($brand-start, 0.08);
    backdrop-filter: blur(8px);
    padding: 10px 16px;
  }
}

.toolbar-trigger {
  --el-button-bg-color: rgba($overlay-rgb, 0.04);
  --el-button-border-color: rgba($overlay-rgb, 0.12);
  --el-button-hover-bg-color: rgba($brand-start, 0.12);
  --el-button-hover-border-color: rgba($brand-start, 0.4);
  --el-button-hover-text-color: lighten($brand-start, 12%);
  --el-button-text-color: $text-secondary;
}

.toolbar-select-all {
  :deep(.el-checkbox__label) {
    color: $text-secondary;
    font-size: 13px;
  }
}

.toolbar-exit {
  --el-button-bg-color: rgba($overlay-rgb, 0.03);
  --el-button-border-color: rgba($overlay-rgb, 0.12);
  --el-button-text-color: $text-secondary;
  --el-button-hover-bg-color: rgba($accent-rose, 0.12);
  --el-button-hover-border-color: rgba($accent-rose, 0.4);
  --el-button-hover-text-color: lighten($accent-rose, 8%);
  --el-button-active-bg-color: rgba($accent-rose, 0.16);
  --el-button-active-border-color: rgba($accent-rose, 0.5);
  --el-button-active-text-color: lighten($accent-rose, 12%);
}

.toolbar-spacer {
  flex: 1;
}

.selected-info {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: linear-gradient(135deg, rgba($brand-start, 0.18), rgba($brand-end, 0.12));
  border: 1px solid rgba($brand-start, 0.25);
  color: lighten($brand-start, 12%);
  font-size: 13px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;

  .selected-icon {
    font-size: 12px;
    color: $brand-start;
  }

  strong {
    color: $text-primary;
    font-weight: 600;
  }
}

.draft-card {
  position: relative;
  transition: $transition-base;

  &.select-mode {
    cursor: pointer;
  }

  &:hover:not(.is-selected) {
    border-color: rgba($overlay-rgb, 0.15);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  }

  &.is-selected {
    border-color: rgba($brand-start, 0.5);
    background: linear-gradient(135deg, rgba($brand-start, 0.08), rgba($brand-end, 0.04));
    box-shadow:
      0 0 0 1px rgba($brand-start, 0.45),
      0 8px 24px rgba($brand-start, 0.18);
    transform: translateY(-2px);
  }
}

.card-selector {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 3;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(8px);
  border: 1.5px solid rgba($overlay-rgb, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: $transition-base;
  opacity: 0;
  transform: scale(0.85);

  .selector-icon {
    font-size: 14px;
    color: white;
    opacity: 0;
    transform: scale(0.5);
    transition: $transition-base;
  }

  .draft-card.select-mode:hover & {
    opacity: 1;
    transform: scale(1);
  }

  .draft-card.is-selected & {
    opacity: 1;
    transform: scale(1);
    background: $gradient-brand;
    border-color: transparent;
    box-shadow: 0 0 14px rgba($brand-start, 0.6);

    .selector-icon {
      opacity: 1;
      transform: scale(1);
    }
  }
}
</style>
