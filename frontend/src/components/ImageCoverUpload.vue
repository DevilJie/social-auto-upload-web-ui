<template>
  <div class="image-cover-upload">
    <div class="cover-header">
      <div class="cover-title">
        <span class="cover-dot"></span>
        <span>{{ label }}</span>
      </div>
    </div>

    <div class="cover-body">
      <!-- 已上传封面 -->
      <div v-if="modelValue" class="cover-preview-wrap">
        <img :src="modelValue.url" class="cover-preview" />
        <div class="cover-preview-overlay">
          <button class="overlay-action" @click="uploaderVisible = true">
            <el-icon :size="14"><Upload /></el-icon>
            <span>重新上传</span>
          </button>
          <button class="overlay-action" @click="$emit('open-library')">
            <el-icon :size="14"><FolderOpened /></el-icon>
            <span>素材库</span>
          </button>
          <button class="overlay-action danger" @click="$emit('update:modelValue', null)">
            <el-icon :size="14"><Delete /></el-icon>
            <span>移除</span>
          </button>
        </div>
      </div>

      <!-- 未上传封面 -->
      <div v-else class="cover-empty">
        <div class="cover-empty-actions">
          <button class="empty-action-btn" @click="uploaderVisible = true">
            <el-icon :size="20"><Upload /></el-icon>
            <span>本地上传</span>
          </button>
          <button class="empty-action-btn" @click="$emit('open-library')">
            <el-icon :size="20"><FolderOpened /></el-icon>
            <span>素材库选择</span>
          </button>
        </div>
        <span class="cover-empty-desc">支持 JPG、PNG、WebP 格式</span>
      </div>
    </div>

    <MaterialUploader
      v-model="uploaderVisible"
      accept="image/jpeg,image/png,image/webp"
      :max-size="10"
      :multiple="false"
      :title="`上传${label}`"
      tip="支持 JPG、PNG、WebP 格式，单文件不超过 10MB"
      @uploaded="onUploaded"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload, Delete, FolderOpened } from '@element-plus/icons-vue'
import { getFileUrl } from '@/utils/storage'
import MaterialUploader from '@/components/MaterialUploader.vue'

const props = defineProps({
  label: { type: String, default: '封面图片' },
  modelValue: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'open-library'])
const uploaderVisible = ref(false)

function onUploaded(d) {
  emit('update:modelValue', {
    id: d.id,
    name: d.original_filename,
    url: getFileUrl(d.stored_path),
    stored_path: d.stored_path,
    size: d.file_size,
    type: d.mime_type,
  })
  ElMessage.success('封面上传成功')
}
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.image-cover-upload {
  background: $bg-elevated;
  border: 1px solid $border;
  border-radius: $radius-card;
  overflow: hidden;
  transition: $transition-base;

  &:hover {
    border-color: $border-active;
  }
}

.cover-header {
  display: flex;
  align-items: center;
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

.cover-body {
  min-height: 120px;
}

// ===== 已上传封面 =====
.cover-preview-wrap {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  background: rgba(0, 0, 0, 0.3);
  padding: 12px;
  min-height: 140px;
}

.cover-preview {
  display: block;
  max-height: 200px;
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
  gap: 8px;
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
  padding: 6px 12px;
  border: 1px solid rgba($overlay-rgb, 0.2);
  border-radius: 6px;
  background: rgba($overlay-rgb, 0.1);
  backdrop-filter: blur(8px);
  color: #fff;
  font-size: 12px;
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

// ===== 未上传封面 =====
.cover-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
}

.cover-empty-actions {
  display: flex;
  gap: 12px;
}

.empty-action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 16px 24px;
  border: 1px dashed $border;
  border-radius: 8px;
  background: transparent;
  color: $text-secondary;
  font-size: 13px;
  cursor: pointer;
  transition: $transition-base;
  font-family: inherit;

  &:hover {
    border-color: $brand-start;
    color: $brand-start;
    background: rgba($brand-start, 0.04);
  }
}

.cover-empty-desc {
  font-size: 11px;
  color: $text-muted;
}
</style>
