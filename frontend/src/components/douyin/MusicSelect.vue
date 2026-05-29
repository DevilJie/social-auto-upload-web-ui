<template>
  <div class="music-select">
    <el-select
      v-model="selectedMusicId"
      placeholder="搜索音乐"
      clearable
      filterable
      remote
      :remote-method="searchMusic"
      :loading="loading"
      @change="handleChange"
      style="width: 100%"
    >
      <el-option
        v-for="music in musicList"
        :key="music.id"
        :label="`${music.title} - ${music.author}`"
        :value="music.title"
      >
        <div class="music-option">
          <img
            :src="music.cover_medium?.url_list?.[0] || music.cover_thumb?.url_list?.[0]"
            :alt="music.title"
            class="music-cover"
            @error="onImageError"
          />
          <div class="music-info">
            <div class="music-title">{{ music.title }}</div>
            <div class="music-meta">
              <span class="music-author">{{ music.author }}</span>
              <span class="music-duration">{{ formatDuration(music.duration) }}</span>
            </div>
          </div>
          <span class="music-users">{{ formatUserCount(music.user_count) }}人使用</span>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { douyinImageApi } from '@/api/douyinImage'

const props = defineProps({
  accountId: {
    type: [String, Number],
    default: ''
  },
  modelValue: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const musicList = ref([])
const selectedMusicId = ref(props.modelValue || '')

watch(() => props.modelValue, (val) => {
  selectedMusicId.value = val || ''
})

let searchTimer = null

async function searchMusic(keyword) {
  if (!keyword) {
    musicList.value = []
    return
  }

  // 防抖
  if (searchTimer) clearTimeout(searchTimer)

  searchTimer = setTimeout(async () => {
    loading.value = true
    try {
      const resp = await douyinImageApi.searchMusic(props.accountId || '', keyword)
      if (resp.code === 200) {
        musicList.value = resp.data?.music || []
      }
    } catch (e) {
      console.error('搜索音乐失败:', e)
    } finally {
      loading.value = false
    }
  }, 500)
}

function handleChange(val) {
  if (val) {
    const music = musicList.value.find(m => m.title === val)
    emit('update:modelValue', val)
    emit('change', music)
  } else {
    emit('update:modelValue', null)
    emit('change', null)
  }
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
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjMjIyIi8+PHRleHQgeD0iMjAiIHk9IjI0IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM2NjYiIHRleHQtYW5jaG9yPSJtaWRkbGUiPvCflKQ8L3RleHQ+PC9zdmc+'
}
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.music-select {
  width: 100%;
}

.music-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.music-cover {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
}

.music-info {
  flex: 1;
  min-width: 0;
}

.music-title {
  font-size: 14px;
  color: #F8FAFC;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.music-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: #94A3B8;
}

.music-users {
  font-size: 12px;
  color: #94A3B8;
  flex-shrink: 0;
}
</style>
