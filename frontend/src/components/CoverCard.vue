<template>
  <div :class="['cover-card', { 'has-cover': modelValue }]">
    <!-- Header -->
    <div class="cover-header">
      <div class="cover-title">
        <span class="cover-dot"></span>
        <span>{{ label }}</span>
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

      <!-- No cover yet -->
      <div v-else class="cover-empty" @click="$emit('edit')">
        <div class="cover-empty-icon">
          <el-icon :size="28"><Picture /></el-icon>
        </div>
        <span class="cover-empty-title">上传{{ label }}</span>
        <span class="cover-empty-desc">支持 JPG、PNG 格式</span>
      </div>
    </div>
  </div>

  <input ref="fileInputRef" type="file" accept="image/*" style="display: none" @change="onFileSelected" />
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture, Upload, Edit, Delete } from '@element-plus/icons-vue'
import { http } from '@/utils/request'
import { materialApi } from '@/api/material'

const props = defineProps({
  label: { type: String, default: '横版封面' },
  ratioLabel: { type: String, default: '16:9' },
  modelValue: { type: Object, default: null },
  hasVideo: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'edit', 'open-library'])
const fileInputRef = ref(null)

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

</style>
