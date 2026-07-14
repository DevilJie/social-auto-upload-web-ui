<template>
  <el-dialog
    :model-value="modelValue"
    title="批量发布进度"
    width="500px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    class="batch-progress-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="publish-progress">
      <el-progress
        :percentage="progress"
        :status="progress === 100 ? 'success' : ''"
      />
      <div v-if="currentAccount" class="current-publishing">
        正在发布：{{ currentAccount }}
      </div>

      <div class="publish-results" v-if="results.length > 0">
        <div
          v-for="(result, index) in results"
          :key="index"
          :class="['result-item', result.status]"
        >
          <el-icon v-if="result.status === 'success'"><Check /></el-icon>
          <el-icon v-else-if="result.status === 'error'"><Close /></el-icon>
          <el-icon v-else><InfoFilled /></el-icon>
          <span class="result-label">{{ result.label }}</span>
          <span class="result-message">{{ result.message }}</span>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer-right">
        <el-button @click="$emit('cancel')" :disabled="progress === 100">取消发布</el-button>
        <el-button type="primary" @click="$emit('update:modelValue', false)" v-if="progress === 100">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { Check, Close, InfoFilled } from '@element-plus/icons-vue'

defineProps({
  modelValue: { type: Boolean, required: true },
  progress: { type: Number, default: 0 },
  results: { type: Array, default: () => [] },
  currentAccount: { type: String, default: '' },
})

defineEmits(['update:modelValue', 'cancel'])
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.batch-progress-dialog {
  .publish-progress {
    padding: 12px 0;

    .current-publishing {
      margin: 16px 0;
      text-align: center;
      color: $text-secondary;
      font-size: 14px;
    }

    .publish-results {
      margin-top: 20px;
      border-top: 1px solid rgba($overlay-rgb, 0.06);
      padding-top: 16px;
      max-height: 300px;
      overflow-y: auto;

      .result-item {
        display: flex;
        align-items: center;
        padding: 8px 0;
        color: $text-secondary;

        .el-icon { margin-right: 8px; }
        .result-label { margin-right: 10px; font-weight: 600; color: $popper-text; }
        .result-message { color: $text-muted; font-size: 13px; }

        &.success { .el-icon, .result-label { color: $success-color; } }
        &.error { .el-icon, .result-label { color: $danger-color; } }
        &.cancelled { color: $text-muted; .result-label { color: $text-muted; } }
      }
    }
  }
}

.dialog-footer-right { display: flex; justify-content: flex-end; gap: 8px; }
</style>
