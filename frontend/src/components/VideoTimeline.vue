<template>
  <div class="video-timeline">
    <div class="timeline-track" ref="trackRef" @mousedown="onTrackMouseDown" @wheel.prevent="onWheel">
      <div class="timeline-thumbs">
        <img
          v-for="frame in frames"
          :key="frame.seconds"
          :src="frame.url"
          class="timeline-thumb"
          :style="{ width: thumbWidth + 'px' }"
          draggable="false"
        />
        <div v-if="extracting" class="timeline-loading" :style="{ width: thumbWidth + 'px' }">
          <el-icon class="loading-spin"><Loading /></el-icon>
        </div>
      </div>
      <div
        class="timeline-slider"
        :style="{ left: sliderLeft + 'px', width: thumbWidth + 'px' }"
      ></div>
    </div>
    <div class="timeline-markers">
      <span v-for="marker in timeMarkers" :key="marker.seconds" class="time-marker" :style="{ left: marker.position + 'px' }">
        {{ marker.label }}
      </span>
    </div>
    <div class="timeline-time-display">
      {{ formatTime(modelValue) }} / {{ formatTime(duration) }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'

const THUMB_WIDTH = 80
const MARKER_INTERVAL = 10

const props = defineProps({
  frames: { type: Array, default: () => [] },
  duration: { type: Number, default: 0 },
  modelValue: { type: Number, default: 0 },
  extracting: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue'])

const trackRef = ref(null)
const thumbWidth = THUMB_WIDTH

const sliderLeft = computed(() => props.modelValue * THUMB_WIDTH)

const timeMarkers = computed(() => {
  const markers = []
  for (let s = 0; s <= props.duration; s += MARKER_INTERVAL) {
    markers.push({
      seconds: s,
      label: formatTime(s),
      position: s * THUMB_WIDTH,
    })
  }
  return markers
})

function formatTime(secs) {
  const m = Math.floor(secs / 60)
  const s = secs % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function onWheel(e) {
  e.preventDefault()
  const track = trackRef.value
  if (!track) return
  track.scrollLeft += e.deltaY
}

function onTrackMouseDown(e) {
  e.preventDefault()
  const track = trackRef.value
  if (!track) return

  const updatePosition = (clientX) => {
    const rect = track.getBoundingClientRect()
    const scrollLeft = track.scrollLeft || 0
    const x = clientX - rect.left + scrollLeft
    const seconds = Math.floor(x / THUMB_WIDTH)
    const clamped = Math.max(0, Math.min(seconds, props.frames.length - 1))
    emit('update:modelValue', clamped)
  }

  updatePosition(e.clientX)

  const onMove = (ev) => updatePosition(ev.clientX)
  const onUp = () => {
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', onUp)
  }
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
}
</script>

<style scoped lang="scss">
.video-timeline {
  user-select: none;
}
.timeline-track {
  overflow-x: auto;
  overflow-y: hidden;
  position: relative;
  height: 56px;
  background: #1a1a1a;
  border-radius: 4px;
  cursor: pointer;
  scrollbar-width: thin;
  scrollbar-color: #555 #222;
  &::-webkit-scrollbar { height: 4px; }
  &::-webkit-scrollbar-thumb { background: #555; border-radius: 2px; }
  &::-webkit-scrollbar-track { background: #222; }
}
.timeline-thumbs {
  display: flex;
  height: 100%;
}
.timeline-thumb {
  height: 100%;
  object-fit: cover;
  flex-shrink: 0;
  pointer-events: none;
  opacity: 0.7;
}
.timeline-slider {
  position: absolute;
  top: 0;
  height: 100%;
  border: 2px solid var(--el-color-primary);
  background: rgba(64, 158, 255, 0.15);
  pointer-events: none;
  transition: left 0.05s ease;
}
.timeline-loading {
  height: 100%;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-color-primary);
  font-size: 18px;
}
.loading-spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.timeline-markers {
  position: relative;
  height: 18px;
  margin-top: 2px;
  overflow: hidden;
}
.time-marker {
  position: absolute;
  top: 0;
  font-size: 10px;
  color: #999;
  transform: translateX(-50%);
}
.timeline-time-display {
  margin-top: 4px;
  font-size: 12px;
  color: #ccc;
  text-align: center;
}
</style>
