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
        :data="tableData"
        :max-height="400"
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
import { ref, computed, watch } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  drafts: { type: Array, default: () => [] },        // [{id, type, title, platforms}]
  failures: { type: Array, default: () => [] },      // [{draft_id, reason}]
})

const emit = defineEmits(['update:visible', 'confirm'])

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