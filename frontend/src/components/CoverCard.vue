<template>
  <div :class="['cover-card', { 'has-cover': modelValue }]">
    <!-- Header -->
    <div class="cover-header">
      <div class="cover-title">
        <span class="cover-dot"></span>
        <span>{{ label }}</span>
      </div>
      <!-- 比例切换 tab -->
      <div class="cover-ratio-tabs">
        <button
          v-for="r in ratios"
          :key="r"
          :class="['cover-ratio-tab', { active: activeRatio === r }]"
          @click="$emit('update:activeRatio', r)"
        >{{ r }}</button>
      </div>
    </div>

    <!-- Cover preview area -->
    <div class="cover-body">
      <!-- Has cover image -->
      <div v-if="modelValue" class="cover-preview-wrap">
        <img :src="modelValue.url" class="cover-preview" />
        <div class="cover-preview-overlay">
          <button class="overlay-action" @click="$emit('edit')">
            <el-icon :size="16"><Edit /></el-icon>
            <span>编辑封面</span>
          </button>
          <button class="overlay-action danger" @click.stop="$emit('update:modelValue', null)">
            <el-icon :size="14"><Delete /></el-icon>
            <span>移除</span>
          </button>
        </div>
      </div>

      <!-- 自动裁剪中（用户上传视频后，后台正在抽帧 + 生成多比例封面） -->
      <div v-else-if="cropping" class="cover-cropping">
        <div class="cover-cropping-glow"></div>
        <div class="cover-cropping-spin">
          <el-icon :size="32" class="spin"><Loading /></el-icon>
        </div>
        <span class="cover-cropping-title">正在自动裁剪封面</span>
        <span class="cover-cropping-desc">{{ cropStageText }}</span>
        <div class="cover-cropping-bar">
          <div class="cover-cropping-bar-fill"></div>
        </div>
      </div>

      <!-- No cover yet -->
      <div v-else :class="['cover-empty', { disabled }]" @click="!disabled && $emit('edit')">
        <div class="cover-empty-icon">
          <el-icon :size="28"><Picture /></el-icon>
        </div>
        <span class="cover-empty-title">{{ activeRatio }} 封面未设置</span>
        <span class="cover-empty-desc">点击上传 / 编辑</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Picture, Edit, Delete, Loading } from '@element-plus/icons-vue'
import { getFileUrl } from '@/utils/storage'

const props = defineProps({
  label: { type: String, default: '横版封面' },
  // 比例列表，如 ['3:4', '9:16'] 或 ['4:3', '16:9']
  ratios: { type: Array, default: () => ['16:9'] },
  // 当前激活的比例（v-model:activeRatio）
  activeRatio: { type: String, required: true },
  // 当前激活比例对应的封面对象（v-model）
  modelValue: { type: Object, default: null },
  hasVideo: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  // 是否正在后台自动裁剪封面（用户上传视频后）
  cropping: { type: Boolean, default: false },
  // 裁剪阶段：'extracting' 抽帧中 / 'saving' 生成多比例中
  cropStage: { type: String, default: '' },
})

const cropStageText = computed(() => {
  if (props.cropStage === 'extracting') return '正在抽取第 1-5 秒关键帧…'
  if (props.cropStage === 'saving') return '正在生成 4 种比例封面…'
  return '处理中，请稍候…'
})

defineEmits([
  'update:modelValue',     // 移除当前激活 tab 的封面 → null
  'update:activeRatio',    // 切换 tab
  'edit',                  // 编辑当前激活 tab 的封面
  'open-library',          // 从素材库选择（预留）
])
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.cover-card {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  overflow: hidden;
  transition: $transition-base;
  flex: 1;

  &:hover {
    border-color: $border-active;
  }
  &.has-cover {
    border-color: rgba($brand-start, 0.15);
    box-shadow: 0 0 0 1px rgba($brand-start, 0.06);
  }
}

.cover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid $border-light;
  gap: 8px;
}

.cover-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: $text-primary;
}

// 比例切换 tab（header 行右侧）
.cover-ratio-tabs {
  display: flex;
  gap: 2px;
  padding: 2px;
  background: rgba($overlay-rgb, 0.05);
  border: 1px solid $border-light;
  border-radius: 7px;
}
.cover-ratio-tab {
  border: none;
  background: transparent;
  color: $text-muted;
  font-size: 11px;
  font-weight: 600;
  font-family: monospace;
  padding: 3px 9px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    color: $text-primary;
  }
  &.active {
    background: $gradient-brand;
    color: #fff;
    box-shadow: 0 1px 4px rgba($brand-start, 0.3);
  }
}

.cover-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: $gradient-brand;
}

.cover-body {
  min-height: 160px;
}

.cover-preview-wrap {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  background: $bg-surface;
  padding: 12px;
  min-height: 180px;
}

.cover-preview {
  display: block;
  max-height: 260px;
  max-width: 100%;
  object-fit: contain;
  border-radius: 4px;
}

.cover-preview-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: rgba(0, 0, 0, 0.5);
  opacity: 0;
  transition: opacity 0.2s;
}
.cover-preview-wrap:hover .cover-preview-overlay {
  opacity: 1;
}

.overlay-action {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 16px;
  border: 1px solid rgba($overlay-rgb, 0.2);
  border-radius: 8px;
  background: rgba($overlay-rgb, 0.1);
  backdrop-filter: blur(8px);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: $transition-fast;
  font-family: inherit;

  &:hover {
    background: rgba($overlay-rgb, 0.2);
    border-color: rgba($overlay-rgb, 0.35);
  }
  &.danger:hover {
    background: rgba($danger-color, 0.5);
    border-color: rgba($danger-color, 0.7);
  }
}

.cover-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 24px;
  cursor: pointer;
  transition: $transition-base;

  &:hover {
    background: rgba($brand-start, 0.04);
  }
  &.disabled {
    cursor: not-allowed;
    opacity: 0.5;
    pointer-events: none;
  }
}

.cover-empty-icon {
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: $gradient-brand-subtle;
  color: $brand-start;
  margin-bottom: 4px;
}

.cover-empty-title {
  font-size: 14px;
  font-weight: 500;
  color: $text-secondary;
}

.cover-empty-desc {
  font-size: 11px;
  color: $text-muted;
}

// ===== 自动裁剪中状态 =====
// 上传视频后，后台抽帧 + 生成多比例封面（一般 5-20s），
// 用旋转图标 + 不定进度条 + 阶段文案告诉用户在跑任务
.cover-cropping {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 24px;
  min-height: 180px;
  cursor: default;
  background: rgba($brand-start, 0.03);
  overflow: hidden;

  .cover-cropping-glow {
    position: absolute;
    inset: 0;
    background: radial-gradient(
      ellipse at center,
      rgba($brand-start, 0.08) 0%,
      transparent 70%
    );
    animation: cropping-pulse 2.4s ease-in-out infinite;
    pointer-events: none;
  }

  .cover-cropping-spin {
    position: relative;
    z-index: 1;
    width: 56px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: rgba($brand-start, 0.12);
    color: $brand-start;
  }

  .cover-cropping-title {
    position: relative;
    z-index: 1;
    font-size: 14px;
    font-weight: 600;
    color: $text-primary;
  }

  .cover-cropping-desc {
    position: relative;
    z-index: 1;
    font-size: 12px;
    color: $text-secondary;
  }

  .cover-cropping-bar {
    position: relative;
    z-index: 1;
    width: 60%;
    max-width: 160px;
    height: 3px;
    border-radius: 2px;
    background: rgba($brand-start, 0.12);
    overflow: hidden;
    margin-top: 4px;
  }
  .cover-cropping-bar-fill {
    position: absolute;
    top: 0;
    left: -40%;
    width: 40%;
    height: 100%;
    border-radius: 2px;
    background: $gradient-brand;
    animation: cropping-bar 1.6s ease-in-out infinite;
  }
}
@keyframes cropping-pulse {
  0%, 100% { opacity: 0.6; }
  50% { opacity: 1; }
}
@keyframes cropping-bar {
  0% { left: -40%; }
  100% { left: 100%; }
}
</style>
