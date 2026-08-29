<template>
  <el-dialog
    :model-value="visible"
    title="批量发布确认"
    width="720px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:visible', $event)"
  >
    <div v-if="rows.length === 0" class="empty">队列为空</div>
    <template v-else>
      <el-table
        ref="tableRef"
        :data="tableData"
        :max-height="380"
        row-key="index"
        :expand-row-keys="expandedKeys"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div v-if="row.errors.length" class="err-list">
              <div v-for="(e, i) in row.errors" :key="i" class="err-item">
                <span class="err-dot"></span>{{ e }}
              </div>
            </div>
            <div v-else class="err-list err-list--ok">发布前检查全部通过</div>
          </template>
        </el-table-column>
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
              :model-value="selectedIndexes.includes(row.index)"
              :disabled="row.errors.length > 0"
              @change="(val) => toggleRow(row.index, val)"
            />
          </template>
        </el-table-column>
        <el-table-column label="视频" min-width="200">
          <template #default="{ row }">
            <div class="video-cell">
              <div class="video-thumb">
                <img v-if="row.coverUrl" :src="row.coverUrl" alt="" />
                <el-icon v-else :size="16"><VideoCameraFilled /></el-icon>
              </div>
              <div class="video-info">
                <div class="video-name" :title="row.name">{{ row.name }}</div>
                <div class="video-title" :title="row.title">{{ row.title || '（无标题）' }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="账号数" width="80" align="center">
          <template #default="{ row }">
            <span>{{ row.accountCount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定时" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.hasSchedule" type="warning" size="small">定时</el-tag>
            <span v-else class="muted">立即</span>
          </template>
        </el-table-column>
        <el-table-column label="校验" min-width="220">
          <template #default="{ row }">
            <div v-if="row.errors.length === 0" class="check-cell">
              <el-tag type="success" size="small">通过</el-tag>
            </div>
            <div v-else class="check-cell">
              <el-tag type="danger" size="small">未通过 ({{ row.errors.length }})</el-tag>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary">
        已选 <b>{{ selectedIndexes.length }}</b> / {{ rows.length }} 个视频
        · 预计产生 <b>{{ estimatedTasks }}</b> 个发布任务
        <span v-if="failedCount > 0" class="summary-fail">
          · <b>{{ failedCount }}</b> 个视频未通过检查（已展开详情，修复后重新发布）
        </span>
        <span class="hint">（提交后即可关闭页面，任务在后端继续执行）</span>
      </div>
    </template>

    <template #footer>
      <el-button @click="$emit('update:visible', false)" :disabled="submitting">取消</el-button>
      <el-button
        type="primary"
        :disabled="selectedIndexes.length === 0"
        :loading="submitting"
        @click="onConfirm"
      >
        发布 {{ selectedIndexes.length }} 个视频
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { VideoCameraFilled } from '@element-plus/icons-vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  // [{index, name, coverUrl, title, accountCount, hasSchedule, errors: []}]
  rows: { type: Array, default: () => [] },
  submitting: { type: Boolean, default: false },
})

const emit = defineEmits(['update:visible', 'confirm'])

const selectedIndexes = ref([])
// 有校验错误的行自动展开（row-key 为 index，需字符串）
const expandedKeys = ref([])

const failedCount = computed(() => props.rows.filter((r) => r.errors.length > 0).length)

const tableData = computed(() => props.rows)

// 默认勾选：所有校验通过的视频（每次打开重算）+ 自动展开错误行
watch(
  () => props.visible,
  (vis) => {
    if (vis) {
      selectedIndexes.value = props.rows
        .filter((r) => r.errors.length === 0)
        .map((r) => r.index)
      expandedKeys.value = props.rows
        .filter((r) => r.errors.length > 0)
        .map((r) => String(r.index))
    }
  },
  { immediate: true }
)

const okIndexes = computed(() => props.rows.filter((r) => r.errors.length === 0).map((r) => r.index))
const allChecked = computed(() =>
  okIndexes.value.length > 0 && okIndexes.value.every((i) => selectedIndexes.value.includes(i))
)
const someChecked = computed(() => !allChecked.value && selectedIndexes.value.length > 0)

const estimatedTasks = computed(() =>
  props.rows
    .filter((r) => selectedIndexes.value.includes(r.index))
    .reduce((sum, r) => sum + (r.accountCount || 0), 0)
)

function toggleRow(index, checked) {
  if (checked) {
    if (!selectedIndexes.value.includes(index)) selectedIndexes.value.push(index)
  } else {
    selectedIndexes.value = selectedIndexes.value.filter((i) => i !== index)
  }
}

function toggleAll(checked) {
  selectedIndexes.value = checked ? [...okIndexes.value] : []
}

function onConfirm() {
  if (selectedIndexes.value.length === 0) return
  emit('confirm', [...selectedIndexes.value])
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.empty {
  text-align: center;
  color: $text-muted;
  padding: 40px 0;
}

.video-cell {
  display: flex;
  align-items: center;
  gap: 10px;

  .video-thumb {
    width: 56px;
    height: 32px;
    border-radius: 4px;
    overflow: hidden;
    flex-shrink: 0;
    background: rgba($overlay-rgb, 0.06);
    display: flex;
    align-items: center;
    justify-content: center;
    color: $text-muted;

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
  }

  .video-info {
    min-width: 0;

    .video-name {
      font-size: 13px;
      color: $text-primary;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 220px;
    }
    .video-title {
      font-size: 12px;
      color: $text-muted;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 220px;
    }
  }
}

.muted {
  color: $text-muted;
  font-size: 12px;
}

// 校验列：仅 tag，详情看展开行
.check-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

// 展开行详情面板
.err-list {
  margin: 4px 12px 10px 24px;  // 少量缩进，贴近展开箭头即可
  padding: 8px 14px;
  background: rgba($overlay-rgb, 0.04);
  border-left: 3px solid $danger-color;
  border-radius: 4px;

  .err-item {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 12px;
    color: $danger-color;
    line-height: 1.9;
  }

  .err-dot {
    flex-shrink: 0;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: $danger-color;
    transform: translateY(-2px);
  }

  &.err-list--ok {
    border-left-color: $success-color;
    color: $text-muted;
  }
}

.summary {
  margin-top: 12px;
  font-size: 13px;
  color: $text-secondary;

  b {
    color: $brand-start;
  }
  .summary-fail {
    color: $danger-color;

    b { color: $danger-color; }
  }
  .hint {
    color: $text-muted;
    font-size: 12px;
    margin-left: 6px;
  }
}
</style>
