<template>
  <div class="cover-card">
    <div class="cover-card-label">
      <span>{{ label }}</span>
      <span class="cover-ratio">{{ ratioLabel }}</span>
    </div>

    <!-- Recommended frames row -->
    <div v-if="recommendedFrames.length > 0" class="recommended-frames">
      <div
        v-for="(frame, index) in recommendedFrames"
        :key="frame.seconds"
        :class="['frame-thumb', { active: isSelected(frame.seconds) }]"
        @click="onFrameClick(frame)"
      >
        <img :src="frame.url" />
        <div v-if="isSelected(frame.seconds)" class="frame-check">
          <el-icon :size="10"><Check /></el-icon>
        </div>
      </div>
      <button class="frame-thumb edit-btn" @click="$emit('edit')">
        <el-icon :size="16"><Edit /></el-icon>
      </button>
    </div>

    <!-- Cover preview or empty -->
    <div v-if="modelValue" class="cover-preview-wrap">
      <img :src="modelValue.url" class="cover-preview" />
      <div class="cover-preview-overlay">
        <button class="overlay-btn" @click="$emit('edit')">编辑</button>
        <button class="overlay-btn" @click="triggerUpload">更换</button>
        <button class="overlay-btn danger" @click="$emit('update:modelValue', null)">删除</button>
      </div>
    </div>
    <div v-else-if="recommendedFrames.length === 0" class="cover-empty" @click="triggerUpload">
      <el-icon :size="24"><Picture /></el-icon>
      <span class="cover-empty-text">上传{{ label }}</span>
    </div>

    <!-- Action buttons -->
    <div class="cover-card-actions">
      <button class="cover-action-btn" @click="triggerUpload">
        <el-icon :size="14"><Upload /></el-icon><span>上传</span>
      </button>
      <button class="cover-action-btn" @click="$emit('open-library')">
        <el-icon :size="14"><Picture /></el-icon><span>素材库</span>
      </button>
    </div>

    <input ref="fileInputRef" type="file" accept="image/*" style="display: none" @change="onFileSelected" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture, Upload, Edit, Check } from '@element-plus/icons-vue'
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
  // Fetch HD frame for better quality cover
  const hdUrl = props.videoPath
    ? frameApi.getFrameImageUrl(props.videoPath, frame.seconds, false)
    : frame.url

  const coverData = {
    name: `frame_${frame.seconds}s.jpg`,
    url: hdUrl,
    path: '',
    size: 0,
    type: 'image/jpeg',
    _fromFrame: frame.seconds,
  }
  emit('update:modelValue', coverData)
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
  flex: 1;
  border: 1px dashed $border;
  border-radius: $radius-base;
  overflow: hidden;
  transition: $transition-base;
  &:hover { border-color: $border-active; }
}

.cover-card-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.03);
  font-size: 12px;
  font-weight: 500;
  color: $text-secondary;
}

.cover-ratio {
  font-size: 10px;
  color: $text-muted;
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
}

.recommended-frames {
  display: flex;
  gap: 4px;
  padding: 8px 10px;
  overflow-x: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.08) transparent;
  &::-webkit-scrollbar { height: 3px; }
  &::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 2px; }
}

.frame-thumb {
  width: 48px;
  height: 32px;
  border-radius: 4px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  flex-shrink: 0;
  position: relative;
  transition: border-color 0.15s;

  img { width: 100%; height: 100%; object-fit: cover; }
  &.active { border-color: $brand-start; }
  &:hover:not(.active) { border-color: rgba($brand-start, 0.4); }
}

.frame-check {
  position: absolute;
  inset: 0;
  background: rgba($brand-start, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.edit-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.03);
  border: 1px dashed $border;
  border-radius: 4px;
  color: $text-muted;
  transition: $transition-fast;
  &:hover { border-color: $border-active; color: $brand-start; }
}

.cover-preview-wrap {
  position: relative;
  display: flex;
  justify-content: center;
  background: rgba(0,0,0,0.2);
}

.cover-preview {
  display: block;
  height: 200px;
  width: auto;
  max-width: 100%;
  object-fit: contain;
}

.cover-preview-overlay {
  position: absolute;
  bottom: 0; left: 0; right: 0;
  display: flex;
  justify-content: center;
  gap: 10px;
  padding: 6px 0;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
  opacity: 0;
  transition: opacity 0.2s;
}
.cover-preview-wrap:hover .cover-preview-overlay { opacity: 1; }

.overlay-btn {
  padding: 3px 10px;
  border: none;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: $transition-fast;
  &:hover { background: rgba(255, 255, 255, 0.25); }
  &.danger:hover { background: rgba($danger-color, 0.6); }
}

.cover-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 28px 0;
  color: $text-muted;
  cursor: pointer;
  transition: $transition-base;
  &:hover { background: rgba(255, 255, 255, 0.03); color: $brand-start; }
}

.cover-empty-text { font-size: 12px; }

.cover-card-actions {
  display: flex;
  gap: 6px;
  padding: 6px 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.cover-action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 5px 12px;
  border: 1px solid $border;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.02);
  color: $text-secondary;
  font-size: 12px;
  cursor: pointer;
  transition: $transition-fast;
  outline: none;
  font-family: inherit;
  &:hover {
    border-color: rgba($brand-start, 0.3);
    background: linear-gradient(135deg, rgba($brand-start, 0.06), rgba($brand-end, 0.04));
    color: $text-primary;
  }
}
</style>
