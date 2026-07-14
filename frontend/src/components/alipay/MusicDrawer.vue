<template>
  <el-drawer
    v-model="visible"
    title="选择音乐"
    direction="rtl"
    size="520px"
    :before-close="handleClose"
  >
    <!-- 提示 -->
    <div class="music-hint">
      <el-icon><InfoFilled /></el-icon>
      <span>添加音乐会提升内容的消费性,帮助内容拿到更多的流量</span>
    </div>

    <!-- 音乐列表 -->
    <div class="music-list" v-loading="loading">
      <div
        v-for="music in pagedMusicList"
        :key="music.musicId || music.title"
        class="music-item"
        :class="{ 'is-playing': playingId === (music.musicId || music.title) }"
        @mouseenter="hoverId = music.musicId || music.title"
        @mouseleave="hoverId = ''"
      >
        <div class="music-left">
          <div class="music-cover" @click="togglePlay(music)">
            <img
              :src="music.coverUrl"
              :alt="music.title"
              @error="onImageError"
            />
            <div class="music-play-icon" :class="{ playing: playingId === (music.musicId || music.title) }">
              <el-icon v-if="playingId === (music.musicId || music.title)"><VideoPause /></el-icon>
              <el-icon v-else><VideoPlay /></el-icon>
            </div>
          </div>
          <div class="music-info">
            <div class="music-title" :title="music.title">{{ music.title }}</div>
            <div class="music-duration">{{ formatDuration(music.duration) }}</div>
          </div>
        </div>
        <div class="music-right">
          <el-button
            v-show="hoverId === (music.musicId || music.title) || playingId === (music.musicId || music.title)"
            type="primary"
            size="small"
            @click="handleSelect(music)"
          >
            使 用
          </el-button>
        </div>
      </div>

      <!-- 空状态(无错误且无数据) -->
      <div v-if="!loading && !errorMsg && musicList.length === 0" class="empty-state">
        <el-empty description="暂无音乐" />
      </div>

      <!-- 错误状态 -->
      <div v-if="!loading && errorMsg" class="error-state">
        <el-icon :size="36"><WarningFilled /></el-icon>
        <p class="error-msg">{{ errorMsg }}</p>
        <el-button type="primary" size="small" @click="fetchMusicList">重试</el-button>
      </div>
    </div>

    <!-- 分页(客户端切片,贴近支付宝原生每页 5 条) -->
    <template #footer>
      <div class="drawer-footer">
        <el-pagination
          v-if="musicList.length > 0"
          v-model:current-page="pageNum"
          :page-size="PAGE_SIZE"
          :total="musicList.length"
          layout="prev, pager, next"
          :pager-count="7"
          background
        />
        <div class="footer-tip">
          <el-icon><InfoFilled /></el-icon>
          <span>共 {{ musicList.length }} 首 · 音乐封面以发布后播放页面展示为准</span>
        </div>
      </div>
    </template>

    <!-- 隐藏的 audio 元素用于试听 -->
    <audio
      ref="audioRef"
      :src="currentAudioUrl"
      @ended="onAudioEnded"
      @error="onAudioError"
    />
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { VideoPlay, VideoPause, InfoFilled, WarningFilled } from '@element-plus/icons-vue'
import { alipayApi } from '@/api/alipay'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  accountId: { type: [String, Number], default: '' },
})
const emit = defineEmits(['update:modelValue', 'select'])

const visible = ref(props.modelValue)
const loading = ref(false)
const errorMsg = ref('')
// 全量音乐列表(queryAllMaterial.json 一次性返回全部)
const allMusicList = ref([])
const pageNum = ref(1)
// 每页条数:贴近支付宝原生音乐弹窗(实测每页 5 条)
const PAGE_SIZE = 5

// 当前页切片(客户端分页,无需重新请求)
const pagedMusicList = computed(() => {
  const start = (pageNum.value - 1) * PAGE_SIZE
  return allMusicList.value.slice(start, start + PAGE_SIZE)
})

// hover 状态用 id 而非 idx(因为列表是切片,idx 会跨页复用)
const hoverId = ref('')

// 试听状态(单例播放)
const audioRef = ref(null)
const playingId = ref(null)
const currentAudioUrl = ref('')

// 兼容旧模板引用(musicList 指向全量,空状态判断用)
const musicList = computed(() => allMusicList.value)

watch(() => props.modelValue, (val) => {
  visible.value = val
  // 打开抽屉且无数据时加载(accountId 可空,后端用任意支付宝账号 cookie)
  if (val && allMusicList.value.length === 0) {
    pageNum.value = 1
    fetchMusicList()
  }
})
watch(visible, (val) => {
  emit('update:modelValue', val)
  if (!val) stopPlay()
})

// 翻页时停止试听
watch(pageNum, () => stopPlay())

async function fetchMusicList() {
  // accountId 可空:为空时后端用任意一个支付宝账号的 cookie
  // (音乐库对所有账号一致,不依赖具体登录态)
  loading.value = true
  errorMsg.value = ''
  try {
    const resp = await alipayApi.musicList(props.accountId)
    if (resp.code === 200) {
      allMusicList.value = resp.data?.list || []
      if (allMusicList.value.length === 0) {
        errorMsg.value = '未获取到音乐数据(接口返回空列表)'
      }
    } else {
      errorMsg.value = resp.msg || `获取失败 (code=${resp.code})`
      allMusicList.value = []
    }
  } catch (e) {
    console.error('[支付宝音乐] 加载失败:', e)
    errorMsg.value = e.message || '网络请求失败,请检查后端服务'
    allMusicList.value = []
  } finally {
    loading.value = false
  }
}

function togglePlay(music) {
  const id = music.musicId || music.title
  if (playingId.value === id) {
    // 当前正在播放 → 暂停
    stopPlay()
    return
  }
  // 切换到新音乐
  stopPlay()
  if (!music.audioUrl) {
    console.warn('[支付宝音乐] 该音乐无试听 URL:', music.title)
    return
  }
  currentAudioUrl.value = music.audioUrl
  playingId.value = id
  // 等 src 绑定后播放
  setTimeout(() => {
    const el = audioRef.value
    if (el) {
      el.play().catch(err => {
        console.warn('[支付宝音乐] 试听播放失败:', err)
        playingId.value = null
      })
    }
  }, 50)
}

function stopPlay() {
  const el = audioRef.value
  if (el) {
    el.pause()
    el.currentTime = 0
  }
  playingId.value = null
}

function onAudioEnded() {
  playingId.value = null
}

function onAudioError() {
  playingId.value = null
}

function handleSelect(music) {
  stopPlay()
  emit('select', { ...music })
  visible.value = false
}

function handleClose() {
  visible.value = false
}

function formatDuration(duration) {
  // 支付宝返回的 duration 是 audioTime 秒数(整数)
  if (!duration && duration !== 0) return '00:00'
  const sec = parseInt(duration, 10)
  if (isNaN(sec)) return String(duration)
  const m = Math.floor(sec / 60)
  const r = Math.floor(sec % 60)
  return `${m.toString().padStart(2, '0')}:${r.toString().padStart(2, '0')}`
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDgiIGhlaWdodD0iNDgiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQ4IiBoZWlnaHQ9IjQ4IiBmaWxsPSIjMmEyYTRhIi8+PHRleHQgeD0iMjQiIHk9IjI4IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTAiIGZpbGw9IiM2NDc0OGIiIHRleHQtYW5jaG9yPSJtaWRkbGUiPuWGm+S6rDwvdGV4dD48L3N2Zz4='
}

onBeforeUnmount(() => stopPlay())
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.music-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  color: $text-secondary;
  font-size: 12px;
  background: rgba($info-color, 0.06);
  border-bottom: 1px solid $border;
}

.music-list {
  height: calc(100% - 130px);
  overflow-y: auto;
  padding: 8px 12px;
}

.music-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 4px;
  transition: background 0.2s;
  cursor: default;
  border: 1px solid transparent;

  &:hover {
    background: rgba($overlay-rgb, 0.04);
  }

  &.is-playing {
    background: rgba($info-color, 0.08);
    border-color: rgba($info-color, 0.2);
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
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
  cursor: pointer;
  background: $bg-elevated;

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
    background: rgba(0, 0, 0, 0.5);
    color: white;
    font-size: 20px;
    opacity: 0;
    transition: opacity 0.2s;

    &.playing {
      opacity: 1;
    }
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

.music-duration {
  font-size: 12px;
  color: $text-muted;
  margin-top: 4px;
}

.music-right {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.empty-state {
  padding: 40px 0;
}

.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 20px;
  color: $text-secondary;

  .error-msg {
    font-size: 13px;
    text-align: center;
    margin: 0;
    line-height: 1.5;
    word-break: break-all;
  }
}

.drawer-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid $border;
}

.footer-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  color: $text-muted;
  font-size: 12px;
}
</style>
