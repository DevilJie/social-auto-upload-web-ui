<template>
  <el-dialog
    :model-value="visible"
    title="草稿批量发布预览"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
    :close-on-click-modal="false"
  >
    <div v-if="drafts.length === 0" class="empty">未选中任何草稿</div>
    <div v-else>
      <el-table
        ref="tableRef"
        :data="tableData"
        @selection-change="onSelectionChange"
        :max-height="400"
      >
        <el-table-column type="selection" width="50" />
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
        :disabled="selectedIds.length === 0"
        :loading="submitting"
        @click="onConfirm"
      >
        确认发布 {{ selectedIds.length }} 项
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  drafts: { type: Array, default: () => [] },        // [{id, type, title, platforms}]
  failures: { type: Array, default: () => [] },      // [{draft_id, reason}]
})

const emit = defineEmits(['update:visible', 'confirm'])

const tableRef = ref(null)
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

// 默认勾选：仅未失败的
watch(
  () => [props.visible, props.drafts],
  ([vis]) => {
    if (vis) {
      selectedIds.value = tableData.value
        .filter((r) => r.status === 'ok')
        .map((r) => r.id)
      // 同步 el-table 选中状态
      nextTick(() => {
        if (tableRef.value) {
          tableRef.value.clearSelection()
          for (const row of tableData.value) {
            if (selectedIds.value.includes(row.id)) {
              tableRef.value.toggleRowSelection(row, true)
            }
          }
        }
      })
    }
  },
  { immediate: true }
)

function onSelectionChange(rows) {
  selectedIds.value = rows.map((r) => r.id)
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