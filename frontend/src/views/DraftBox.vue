<template>
  <div class="draft-box">
    <div class="draft-header">
      <h2>草稿箱</h2>
      <span class="draft-count">{{ drafts.length }} 个草稿</span>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && drafts.length === 0" class="empty-state">
      <el-empty description="还没有保存的草稿">
        <el-button type="primary" @click="router.push('/publish-center')">去发布视频</el-button>
      </el-empty>
    </div>

    <!-- Card grid -->
    <div v-else class="draft-grid">
      <div v-for="draft in drafts" :key="draft.id" class="draft-card">
        <!-- Cover thumbnail -->
        <div class="card-cover">
          <img
            v-if="draft.cover_path"
            :src="getCoverUrl(draft.cover_path)"
            alt="封面"
          />
          <div v-else class="cover-placeholder">
            <el-icon :size="32"><Picture /></el-icon>
          </div>
          <!-- Duration badge -->
          <span v-if="draft.video_duration" class="duration-badge">
            {{ formatDuration(draft.video_duration) }}
          </span>
        </div>

        <!-- Card body -->
        <div class="card-body">
          <div class="card-title">{{ draft.title || '无标题' }}</div>

          <!-- Channels summary (single line with marquee) -->
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

          <!-- Meta info -->
          <div class="card-meta">
            <span v-if="draft.video_file_size">{{ formatFileSize(draft.video_file_size) }}</span>
            <span>{{ formatTime(draft.updated_at) }}</span>
          </div>
        </div>

        <!-- Card actions - full width at bottom -->
        <div class="card-actions">
          <button class="action-btn action-edit" @click="editDraft(draft.id)">
            <el-icon><Edit /></el-icon> 编辑
          </button>
          <button class="action-btn action-delete" @click="confirmDelete(draft.id)">
            <el-icon><Delete /></el-icon> 删除
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Picture, Edit, Delete } from '@element-plus/icons-vue'
import { draftApi } from '@/api/draft'
import { getPlatformByKey } from '@/config/platforms'

const router = useRouter()
const drafts = ref([])
const loading = ref(true)
const channelRefs = {}
const overflowMap = ref({})

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

function getCoverUrl(path) {
  if (!path) return ''
  if (path.startsWith('http')) return path
  return `${apiBaseUrl}${path.startsWith('/') ? '' : '/'}${path}`
}

function getPlatformLogo(platformKey) {
  const p = getPlatformByKey(platformKey)
  return p?.logo || null
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

function editDraft(id) {
  router.push(`/publish-center?draft=${id}`)
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

async function confirmDelete(id) {
  try {
    await ElMessageBox.confirm('确定删除这个草稿吗？', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await draftApi.deleteDraft(id)
    ElMessage.success('草稿已删除')
    await loadDrafts()
  } catch {
    // cancelled or error
  }
}

async function loadDrafts() {
  loading.value = true
  try {
    const resp = await draftApi.getDrafts()
    drafts.value = resp.data || []
  } catch (e) {
    console.error('Failed to load drafts:', e)
  } finally {
    loading.value = false
  }
}

onMounted(loadDrafts)
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.draft-box {
  padding: 24px;
  min-height: 100%;
}

.draft-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;

  h2 {
    margin: 0;
    font-size: 20px;
    font-weight: 600;
    color: $text-primary;
  }

  .draft-count {
    font-size: 13px;
    color: $text-muted;
  }
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
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid $border;
  border-radius: $radius-lg;
  overflow: hidden;
  transition: $transition-base;
  display: flex;
  flex-direction: column;

  &:hover {
    border-color: rgba(255, 255, 255, 0.15);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  }
}

.card-cover {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: rgba(255, 255, 255, 0.03);
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
  background: rgba(255, 255, 255, 0.06);
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
    background: rgba(64, 158, 255, 0.1);
    color: #409eff;
  }

  &.action-delete:hover {
    background: rgba(245, 108, 108, 0.1);
    color: #f56c6c;
  }
}
</style>
