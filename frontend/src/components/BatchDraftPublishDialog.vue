<template>
  <el-dialog
    :model-value="visible"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
  >
    <template #header>
      <div class="bdp-dialog-header">
        <span class="bdp-dialog-title">草稿批量发布预览</span>
        <el-tooltip content="引导" placement="top">
          <button class="bdp-guide-btn" type="button" @click="startGuide">?</button>
        </el-tooltip>
      </div>
    </template>
    <div v-if="drafts.length === 0" class="empty">未选中任何草稿</div>
    <div v-else>
      <el-table
        :data="tableData"
        :max-height="400"
        data-tour="bdp-table"
      >
        <el-table-column width="50">
          <template #header>
            <el-checkbox
              :model-value="allChecked"
              :indeterminate="someChecked"
              @change="toggleAll"
            />
          </template>
          <template #default="{ row }">
            <el-checkbox
              :model-value="selectedIds.includes(row.id)"
              :disabled="row.status !== 'ok'"
              @change="(val) => toggleRow(row.id, val)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="platforms" label="目标平台" width="180" />
        <el-table-column prop="status" label="状态" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'ok'" type="success" size="small">通过</el-tag>
            <el-tooltip v-else :content="row.reason" placement="top">
              <el-tag type="danger" size="small">失败</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary">
        已选 <b>{{ selectedIds.length }}</b> / {{ drafts.length }} 项
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        data-tour="bdp-confirm"
        :disabled="selectedIds.length === 0"
        :loading="submitting"
        @click="onConfirm"
      >
        确认发布 {{ selectedIds.length }} 项
      </el-button>
    </template>
  </el-dialog>

  <!-- 弹窗新手引导（teleport 到 body；流程中弹窗，仅标题栏「?」按钮按需查看，不自动播放） -->
  <GuideTour
    ref="tourRef"
    :steps="draftBatchGuideSteps"
  />
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import GuideTour from '@/components/GuideTour.vue'
import { draftBatchGuideSteps } from '@/config/guides'

const props = defineProps({
  visible: { type: Boolean, default: false },
  drafts: { type: Array, default: () => [] },        // [{id, type, title, platforms}]
  failures: { type: Array, default: () => [] },      // [{draft_id, reason}]
})

const emit = defineEmits(['update:visible', 'confirm'])

// ===== 弹窗新手引导（按需查看：标题栏「?」按钮触发，不自动播放） =====
const tourRef = ref(null)
const startGuide = () => tourRef.value?.start()

const submitting = ref(false)
const selectedIds = ref([])

// 失败集合（draft_id → reason）
const failureMap = computed(() => {
  const m = new Map()
  for (const f of props.failures) m.set(f.draft_id, f.reason)
  return m
})

// 表格数据：每条草稿带 status/reason/platforms
const tableData = computed(() =>
  props.drafts.map((d) => {
    const reason = failureMap.value.get(d.id)
    return {
      id: d.id,
      title: d.title || `草稿 #${d.id}`,
      platforms: (d.platforms || []).join('、') || '—',
      status: reason ? 'fail' : 'ok',
      reason: reason || '',
    }
  })
)

// 默认勾选：所有"通过"状态的草稿（dialog 每次打开重新计算）
watch(
  () => props.visible,
  (vis) => {
    if (vis) {
      selectedIds.value = tableData.value
        .filter((r) => r.status === 'ok')
        .map((r) => r.id)
    } else {
      // 保险：弹窗关闭时结束可能还开着的引导
      tourRef.value?.stop()
    }
  },
  { immediate: true }
)

// 头部 checkbox 三态
const okIds = computed(() => tableData.value.filter((r) => r.status === 'ok').map((r) => r.id))
const allChecked = computed(() => okIds.value.length > 0 && okIds.value.every((id) => selectedIds.value.includes(id)))
const someChecked = computed(() => !allChecked.value && selectedIds.value.length > 0)

function toggleRow(id, checked) {
  if (checked) {
    if (!selectedIds.value.includes(id)) selectedIds.value.push(id)
  } else {
    selectedIds.value = selectedIds.value.filter((i) => i !== id)
  }
}

function toggleAll(checked) {
  selectedIds.value = checked ? [...okIds.value] : []
}

function onConfirm() {
  if (selectedIds.value.length === 0) return
  submitting.value = true
  emit('confirm', selectedIds.value)
}

// 父组件拿到响应后调 resetSubmitting()
function resetSubmitting() {
  submitting.value = false
}
defineExpose({ resetSubmitting })
</script>

<style scoped>
/* 自定义 header：标题 + 引导入口（padding-right 给右上角关闭按钮留位） */
.bdp-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 32px;
}

.bdp-dialog-title {
  font-size: 18px;
  font-weight: 600;
}

.bdp-guide-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: 1px dashed rgba(144, 147, 153, 0.6);
  border-radius: 50%;
  background: transparent;
  color: #909399;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: all 0.2s;
}

.bdp-guide-btn:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.empty {
  text-align: center;
  color: #909399;
  padding: 40px 0;
}
.summary {
  margin-top: 12px;
  text-align: right;
  color: #606266;
}
</style>