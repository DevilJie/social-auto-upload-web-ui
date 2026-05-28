<template>
  <div class="image-carousel" v-if="images.length > 0">
    <!-- Main carousel area -->
    <div class="carousel-main">
      <!-- Left arrow -->
      <button
        class="carousel-arrow left"
        :class="{ disabled: currentIndex === 0 }"
        @click="prev"
        :disabled="currentIndex === 0"
      >
        <el-icon :size="20"><ArrowLeft /></el-icon>
      </button>

      <!-- Image container -->
      <div class="carousel-image-wrap" @click="openPreview">
        <img
          :src="currentImage.url"
          :alt="currentImage.name"
          class="carousel-image"
          @error="onImageError"
        />
        <!-- Index badge -->
        <span class="carousel-index">{{ currentIndex + 1 }}/{{ images.length }}</span>
      </div>

      <!-- Right arrow -->
      <button
        class="carousel-arrow right"
        :class="{ disabled: currentIndex === images.length - 1 }"
        @click="next"
        :disabled="currentIndex === images.length - 1"
      >
        <el-icon :size="20"><ArrowRight /></el-icon>
      </button>
    </div>

    <!-- Bottom indicators -->
    <div class="carousel-indicators" v-if="images.length > 1">
      <span
        v-for="(image, index) in images"
        :key="image.id || index"
        class="indicator-dot"
        :class="{ active: index === currentIndex }"
        @click="goTo(index)"
      ></span>
    </div>

    <!-- Fullscreen preview dialog -->
    <el-dialog
      v-model="previewVisible"
      :show-close="true"
      :close-on-click-modal="true"
      class="preview-dialog"
      width="90vw"
      top="5vh"
      destroy-on-close
    >
      <div class="preview-container">
        <img
          :src="previewImageUrl"
          class="preview-image"
          @error="onPreviewImageError"
        />
      </div>
    </el-dialog>
  </div>

  <!-- Empty state -->
  <div class="image-carousel empty" v-else>
    <el-icon :size="48" class="empty-icon"><Picture /></el-icon>
    <span class="empty-text">暂无图片</span>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ArrowLeft, ArrowRight, Picture } from '@element-plus/icons-vue'

const props = defineProps({
  images: { type: Array, default: () => [] },
  initialIndex: { type: Number, default: 0 },
})

const emit = defineEmits(['change'])

const currentIndex = ref(props.initialIndex)
const previewVisible = ref(false)
const previewImageUrl = ref('')

// Computed
const currentImage = computed(() => props.images[currentIndex.value] || {})

// Watch for external index changes
watch(() => props.initialIndex, (val) => {
  if (val >= 0 && val < props.images.length) {
    currentIndex.value = val
  }
})

// Watch for images array changes - reset index if out of bounds
watch(() => props.images.length, (newLen) => {
  if (currentIndex.value >= newLen) {
    currentIndex.value = Math.max(0, newLen - 1)
  }
})

// Navigation methods
function prev() {
  if (currentIndex.value > 0) {
    currentIndex.value--
    emit('change', currentIndex.value)
  }
}

function next() {
  if (currentIndex.value < props.images.length - 1) {
    currentIndex.value++
    emit('change', currentIndex.value)
  }
}

function goTo(index) {
  if (index >= 0 && index < props.images.length) {
    currentIndex.value = index
    emit('change', currentIndex.value)
  }
}

// Preview methods
function openPreview() {
  if (currentImage.value.url) {
    previewImageUrl.value = currentImage.value.url
    previewVisible.value = true
  }
}

// Error handlers
function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iIzIyMiIvPjx0ZXh0IHg9IjEwMCIgeT0iMTAwIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM2NjYiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj7lm77niYfliqDovb3lpLHotJU8L3RleHQ+PC9zdmc+'
}

function onPreviewImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAwIiBoZWlnaHQ9IjMwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iNDAwIiBoZWlnaHQ9IjMwMCIgZmlsbD0iIzIyMiIvPjx0ZXh0IHg9IjIwMCIgeT0iMTUwIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTgiIGZpbGw9IiM2NjYiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj7lm77niYfliqDovb3lpLHotJU8L3RleHQ+PC9zdmc+'
}

// Expose methods for parent
defineExpose({
  prev,
  next,
  goTo,
  getCurrentIndex: () => currentIndex.value,
})
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.image-carousel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  width: 100%;
  height: 100%;
}

// ===== Main carousel =====
.carousel-main {
  position: relative;
  width: 100%;
  flex: 1;
  display: flex;
  align-items: center;
}

.carousel-image-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 3 / 4;
  border-radius: $radius-sm;
  overflow: hidden;
  background: $bg-base;
  cursor: pointer;
  transition: $transition-base;

  &:hover {
    box-shadow: 0 0 0 2px $border-active;

    .carousel-arrow {
      opacity: 1;
    }
  }
}

.carousel-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.carousel-index {
  position: absolute;
  bottom: 8px;
  right: 8px;
  padding: 4px 10px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.6);
  color: rgba(255, 255, 255, 0.9);
  font-size: 12px;
  font-weight: 600;
  backdrop-filter: blur(4px);
  user-select: none;
}

// ===== Arrows =====
.carousel-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: rgba(0, 0, 0, 0.6);
  color: rgba(255, 255, 255, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: $transition-base;
  z-index: 10;
  backdrop-filter: blur(4px);

  &.left {
    left: 8px;
  }

  &.right {
    right: 8px;
  }

  &:hover:not(:disabled) {
    background: rgba(0, 0, 0, 0.8);
    border-color: rgba(255, 255, 255, 0.5);
    transform: translateY(-50%) scale(1.1);
  }

  &.disabled,
  &:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
}

// ===== Indicators =====
.carousel-indicators {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-wrap: wrap;
  max-width: 100%;
  padding: 4px;
}

.indicator-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  cursor: pointer;
  transition: $transition-fast;

  &:hover {
    background: rgba(255, 255, 255, 0.4);
  }

  &.active {
    width: 20px;
    border-radius: 4px;
    background: $brand-start;
  }
}

// ===== Empty state =====
.image-carousel.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px 24px;
  background: $bg-surface;
  border-radius: $radius-sm;
  min-height: 200px;
}

.empty-icon {
  color: $text-muted;
  opacity: 0.5;
}

.empty-text {
  font-size: 14px;
  color: $text-muted;
}

// ===== Preview dialog =====
.preview-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  max-height: 80vh;
}

.preview-image {
  max-width: 100%;
  max-height: 80vh;
  object-fit: contain;
  border-radius: 4px;
}

// Override el-dialog styles for preview
:deep(.preview-dialog) {
  .el-dialog__body {
    padding: 0;
  }
}
</style>
