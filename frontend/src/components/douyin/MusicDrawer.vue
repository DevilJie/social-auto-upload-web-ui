<template>
  <el-drawer
    v-model="visible"
    title="选择音乐"
    direction="rtl"
    size="448px"
    :before-close="handleClose"
  >
    <!-- 搜索框 -->
    <div class="music-search">
      <el-input
        v-model="keyword"
        placeholder="搜索音乐"
        clearable
        @input="handleSearch"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 音乐列表 -->
    <div
      class="music-list"
      v-loading="loading"
      @scroll="handleScroll"
      ref="listRef"
    >
      <div
        v-for="music in musicList"
        :key="music.id"
        class="music-item"
        @mouseenter="hoverId = music.id"
        @mouseleave="hoverId = null"
      >
        <div class="music-left">
          <div class="music-cover">
            <img
              :src="music.cover_medium?.url_list?.[0] || music.cover_thumb?.url_list?.[0]"
              :alt="music.title"
              @error="onImageError"
            />
            <div class="music-play-icon">
              <el-icon><VideoPlay /></el-icon>
            </div>
          </div>
          <div class="music-info">
            <div class="music-title">{{ music.title }}</div>
            <div class="music-author">{{ music.author }}</div>
            <div class="music-duration">{{ formatDuration(music.duration) }}</div>
          </div>
        </div>
        <div class="music-right">
          <span class="music-users">{{ formatUserCount(music.user_count) }}人使用</span>
          <el-button
            v-show="hoverId === music.id"
            type="primary"
            size="small"
            @click="handleSelect(music)"
          >
            使用
          </el-button>
        </div>
      </div>

      <!-- 加载更多 -->
      <div v-if="loading && musicList.length > 0" class="loading-more">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>

      <!-- 空状态 -->
      <div v-if="!loading && musicList.length === 0 && searched" class="empty-state">
        <el-empty description="暂无搜索结果" />
      </div>
    </div>

    <!-- 底部提示 -->
    <template #footer>
      <div class="drawer-footer">
        <el-icon><InfoFilled /></el-icon>
        <span>音乐封面以发布后播放页面展示为准</span>
      </div>
    </template>
  </el-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, VideoPlay, Loading, InfoFilled } from '@element-plus/icons-vue'
import { douyinImageApi } from '@/api/douyinImage'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  },
  accountId: {
    type: [String, Number],
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'select'])

const visible = ref(props.modelValue)
const keyword = ref('')
const loading = ref(false)
const musicList = ref([])
const searched = ref(false)
const hoverId = ref(null)
const listRef = ref(null)

// 分页
const cursor = ref(0)
const hasMore = ref(true)

watch(() => props.modelValue, (val) => {
  visible.value = val
})

watch(visible, (val) => {
  emit('update:modelValue', val)
})

let searchTimer = null

function handleSearch() {
  if (searchTimer) clearTimeout(searchTimer)

  searchTimer = setTimeout(() => {
    if (keyword.value) {
      resetAndSearch()
    } else {
      musicList.value = []
      searched.value = false
    }
  }, 500)
}

function resetAndSearch() {
  cursor.value = 0
  hasMore.value = true
  musicList.value = []
  searchMusic()
}

async function searchMusic() {
  if (!keyword.value || !hasMore.value) return

  loading.value = true
  try {
    const resp = await douyinImageApi.searchMusic(
      props.accountId || '',
      keyword.value,
      cursor.value
    )

    if (resp.code === 200) {
      const data = resp.data
      const newMusic = data?.music || []

      if (cursor.value === 0) {
        musicList.value = newMusic
      } else {
        musicList.value = [...musicList.value, ...newMusic]
      }

      hasMore.value = data?.has_more === 1
      cursor.value = data?.cursor || 0
      searched.value = true
    }
  } catch (e) {
    console.error('搜索音乐失败:', e)
  } finally {
    loading.value = false
  }
}

function handleScroll(e) {
  const { scrollTop, scrollHeight, clientHeight } = e.target
  if (scrollHeight - scrollTop - clientHeight < 100 && !loading.value && hasMore.value) {
    searchMusic()
  }
}

function handleSelect(music) {
  emit('select', music)
  visible.value = false
}

function handleClose() {
  visible.value = false
}

function formatDuration(seconds) {
  if (!seconds) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function formatUserCount(count) {
  if (!count) return '0'
  if (count >= 10000) {
    return (count / 10000).toFixed(1) + '万'
  }
  return count.toString()
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjZjVmNWY1Ii8+PHRleHQgeD0iMjAiIHk9IjI0IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPvCflKQ8L3RleHQ+PC9zdmc+'
}
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.music-search {
  padding: 16px;
  border-bottom: 1px solid $border;
}

.music-list {
  height: calc(100% - 120px);
  overflow-y: auto;
  padding: 8px 16px;
}

.music-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  transition: background 0.2s;

  &:hover {
    background: rgba(255, 255, 255, 0.02);
  }
}

.music-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.music-cover {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .music-play-icon {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.3);
    opacity: 0;
    transition: opacity 0.2s;
    color: white;
    font-size: 20px;
  }

  &:hover .music-play-icon {
    opacity: 1;
  }
}

.music-info {
  flex: 1;
  min-width: 0;
}

.music-title {
  font-size: 14px;
  color: $text-primary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.music-author {
  font-size: 12px;
  color: $text-secondary;
  margin-top: 4px;
}

.music-duration {
  font-size: 12px;
  color: $text-muted;
  margin-top: 2px;
}

.music-right {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.music-users {
  font-size: 12px;
  color: $text-muted;
}

.loading-more {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  color: $text-muted;
  font-size: 14px;
}

.empty-state {
  padding: 40px 0;
}

.drawer-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  color: $text-muted;
  font-size: 12px;
  padding: 12px 16px;
  border-top: 1px solid $border;
}
</style>
