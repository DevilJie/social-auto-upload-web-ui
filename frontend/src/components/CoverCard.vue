<template>
  <div class="cover-card">
    <div class="cover-card-label">
      <span>{{ label }}</span>
      <span class="cover-ratio">{{ ratioLabel }}</span>
    </div>

    <!-- Recommended frames row -->
    <div v-if="recommendedFrames.length > 0" class="recommended-frames">
      <div
        v-for="frame in recommendedFrames"
        :key="frame.seconds"
        :class="['frame-thumb', { active: isSelected(frame.seconds) }]"
        @click="onFrameClick(frame)"
      >
        <img :src="frame.url" />
        <div v-if="isSelected(frame.seconds)" class="frame-check">
          <el-icon :size="12"><Check /></el-icon>
        </div>
      </div>
      <button class="frame-thumb edit-btn" @click="$emit('edit')">
        <el-icon :size="20"><Edit /></el-icon>
        <span>编辑</span>
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
      <el-icon :size="28"><Picture /></el-icon>
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

const props = defineProps({
  label: { type: String, default: '横版封面' },
  ratioLabel: { type: String, default: '16:9' },
  modelValue: { type: Object, default: null },
  recommendedFrames: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'edit', 'open-library'])
const fileInputRef = ref(null)

function isSelected(seconds) {
  return props.modelValue?._fromFrame === seconds
}

function onFrameClick(frame) {
  const coverData = {
    name: `frame_${frame.seconds}s.jpg`,
    url: frame.url,
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
.cover-card { border: 1px solid #e4e7ed; border-radius: 8px; padding: 12px; background: #fafafa; }
.cover-card-label { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 14px; font-weight: 500; }
.cover-ratio { font-size: 11px; color: #999; background: #f0f0f0; padding: 1px 6px; border-radius: 3px; }
.recommended-frames { display: flex; gap: 4px; margin-bottom: 8px; overflow-x: auto; }
.frame-thumb { width: 52px; height: 36px; border-radius: 4px; overflow: hidden; cursor: pointer; border: 2px solid transparent; flex-shrink: 0; position: relative;
  img { width: 100%; height: 100%; object-fit: cover; }
  &.active { border-color: var(--el-color-primary); }
  &:hover { border-color: var(--el-color-primary-light-3); } }
.frame-check { position: absolute; top: 2px; right: 2px; background: var(--el-color-primary); color: #fff; border-radius: 50%; width: 16px; height: 16px; display: flex; align-items: center; justify-content: center; }
.edit-btn { display: flex; flex-direction: column; align-items: center; justify-content: center; background: #fff; border: 2px dashed #dcdfe6; font-size: 10px; color: #999; gap: 2px;
  &:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); } }
.cover-preview-wrap { position: relative; border-radius: 6px; overflow: hidden; margin-bottom: 8px; }
.cover-preview { width: 100%; display: block; }
.cover-preview-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; gap: 8px; opacity: 0; transition: opacity 0.2s; }
.cover-preview-wrap:hover .cover-preview-overlay { opacity: 1; }
.overlay-btn { padding: 4px 12px; border: 1px solid rgba(255,255,255,0.6); border-radius: 4px; background: rgba(255,255,255,0.2); color: #fff; font-size: 12px; cursor: pointer;
  &:hover { background: rgba(255,255,255,0.4); }
  &.danger:hover { background: rgba(245,108,108,0.7); } }
.cover-empty { border: 2px dashed #dcdfe6; border-radius: 6px; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 24px; cursor: pointer; color: #c0c4cc; margin-bottom: 8px;
  &:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); } }
.cover-empty-text { font-size: 13px; margin-top: 6px; }
.cover-card-actions { display: flex; gap: 8px; }
.cover-action-btn { flex: 1; display: flex; align-items: center; justify-content: center; gap: 4px; padding: 6px; border: 1px solid #dcdfe6; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px;
  &:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); } }
</style>
