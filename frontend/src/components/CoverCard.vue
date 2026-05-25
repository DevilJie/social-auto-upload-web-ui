<template>
  <div :class="['cover-card', { 'has-cover': modelValue }]">
    <!-- Header -->
    <div class="cover-header">
      <div class="cover-title">
        <span class="cover-dot"></span>
        <span>{{ label }}</span>
      </div>
      <div class="cover-header-actions">
        <button class="icon-btn" title="上传图片" @click="triggerUpload">
          <el-icon :size="14"><Upload /></el-icon>
        </button>
        <button class="icon-btn" title="从素材库选择" @click="$emit('open-library')">
          <el-icon :size="14"><Picture /></el-icon>
        </button>
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
          <button class="overlay-action danger" @click="$emit('update:modelValue', null)">
            <el-icon :size="14"><Delete /></el-icon>
            <span>移除</span>
          </button>
        </div>
        <span class="cover-ratio-badge">{{ ratioLabel }}</span>
      </div>

      <!-- No cover, has frames -->
      <div v-else-if="recommendedFrames.length > 0" class="cover-no-selection">
        <span class="cover-hint">点击下方画面选择封面</span>
      </div>

      <!-- No cover, no frames -->
      <div v-else class="cover-empty" @click="triggerUpload">
        <div class="cover-empty-icon">
          <el-icon :size="28"><Picture /></el-icon>
        </div>
        <span class="cover-empty-title">上传{{ label }}</span>
        <span class="cover-empty-desc">支持 JPG、PNG 格式</span>
      </div>
    </div>

    <!-- Recommended frames strip -->
    <div v-if="recommendedFrames.length > 0" class="frames-strip">
      <div class="frames-scroll">
        <div
          v-for="frame in recommendedFrames"
          :key="frame.seconds"
          :class="['frame-item', { selected: isSelected(frame.seconds) }]"
          @click="onFrameClick(frame)"
        >
          <img :src="frame.url" />
          <div v-if="isSelected(frame.seconds)" class="frame-selected-mark">
            <el-icon :size="8"><Check /></el-icon>
          </div>
        </div>
        <button class="frame-item frame-edit-btn" @click="$emit('edit')">
          <el-icon :size="14"><Edit /></el-icon>
        </button>
      </div>
    </div>
  </div>

  <input ref="fileInputRef" type="file" accept="image/*" style="display: none" @change="onFileSelected" />
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture, Upload, Edit, Check, Delete } from '@element-plus/icons-vue'
import { http } from '@/utils/request'
import { materialApi } from '@/api/material'
import { frameApi } from '@/api/frame'

const props = defineProps({
  label: { type: String, default: '横版封面' },
  ratioLabel: { type: String, default: '16:9' },
  modelValue: { type: Object, default: null },
  recommendedFrames: { type: Array, default: () => [] },
  videoPath: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'edit', 'open-library'])
const fileInputRef = ref(null)

function isSelected(seconds) {
  return props.modelValue?._fromFrame === seconds
}

async function onFrameClick(frame) {
  const hdUrl = props.videoPath
    ? frameApi.getFrameImageUrl(props.videoPath, frame.seconds, false)
    : frame.url
  emit('update:modelValue', {
    name: `frame_${frame.seconds}s.jpg`,
    url: hdUrl,
    path: '',
    size: 0,
    type: 'image/jpeg',
    _fromFrame: frame.seconds,
  })
}

function triggerUpload() {
  fileInputRef.value?.click()
}

async function onFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const resp = await http.post('/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    if (resp.code === 200) {
      const filePath = resp.data.filepath || resp.data
      const filename = filePath.split('/').pop()
      emit('update:modelValue', {
        name: file.name,
        url: materialApi.getMaterialPreviewUrl(filename),
        path: filePath,
        size: file.size,
        type: file.type,
      })
      ElMessage.success('封面上传成功')
    } else {
      ElMessage.error(resp.msg || '上传失败')
    }
  } catch {
    ElMessage.error('上传失败')
  }
  e.target.value = ''
}
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

// ===== Header =====
.cover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid $border-light;
}

.cover-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: $text-primary;
}

.cover-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: $gradient-brand;
}

.cover-header-actions {
  display: flex;
  gap: 4px;
}

.icon-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: $text-muted;
  cursor: pointer;
  transition: $transition-fast;

  &:hover {
    background: rgba($brand-start, 0.1);
    color: $brand-start;
  }
}

// ===== Body =====
.cover-body {
  min-height: 160px;
}

.cover-preview-wrap {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  background: rgba(0, 0, 0, 0.3);
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
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(8px);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: $transition-fast;
  font-family: inherit;

  &:hover {
    background: rgba(255, 255, 255, 0.2);
    border-color: rgba(255, 255, 255, 0.35);
  }
  &.danger:hover {
    background: rgba($danger-color, 0.5);
    border-color: rgba($danger-color, 0.7);
  }
}

.cover-ratio-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 2px 8px;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
  border-radius: 4px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.7);
  font-family: monospace;
}

.cover-no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  padding: 24px;
}

.cover-hint {
  font-size: 13px;
  color: $text-muted;
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

// ===== Frames strip =====
.frames-strip {
  padding: 8px 12px 12px;
  border-top: 1px solid $border-light;
}

.frames-scroll {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.08) transparent;
  &::-webkit-scrollbar { height: 3px; }
  &::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.1); border-radius: 2px; }
}

.frame-item {
  width: 64px;
  height: 40px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  flex-shrink: 0;
  position: relative;
  transition: all 0.15s;

  img { width: 100%; height: 100%; object-fit: cover; display: block; }

  &:hover:not(.selected) {
    border-color: rgba($brand-start, 0.4);
    transform: translateY(-1px);
  }
  &.selected {
    border-color: $brand-start;
    box-shadow: 0 0 0 1px rgba($brand-start, 0.3);
  }
}

.frame-selected-mark {
  position: absolute;
  inset: 0;
  background: rgba($brand-start, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.frame-edit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.03);
  border: 1px dashed $border;
  color: $text-muted;
  &:hover {
    border-color: rgba($brand-start, 0.4);
    color: $brand-start;
    background: rgba($brand-start, 0.06);
  }
}
</style>
