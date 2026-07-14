<template>
  <el-dialog
    :model-value="modelValue"
    title="批量设置标签"
    width="900px"
    :close-on-click-modal="false"
    class="batch-tag-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <div class="batch-dialog-body">
      <!-- 左侧:账号网格 -->
      <div class="batch-section batch-accounts">
        <div class="batch-section-header">
          <span class="batch-section-title">选择账号</span>
          <span class="batch-section-count">已选 {{ selectedAccountIds.size }} / {{ accounts.length }}</span>
          <el-button size="small" link type="primary" @click="toggleSelectAll">
            {{ isAllSelected ? '取消全选' : '一键全选' }}
          </el-button>
        </div>
        <div class="batch-account-grid">
          <div
            v-for="account in accounts"
            :key="account.id"
            :class="['batch-account-card', { selected: selectedAccountIds.has(account.id), disabled: account.status !== '正常' }]"
            @click="account.status === '正常' && toggleAccount(account.id)"
          >
            <div class="batch-account-avatar">
              <img v-if="account.avatar" :src="proxyAvatar(account.avatar)" :alt="account.name">
              <img v-else :src="getDefaultAvatar(account.name)" :alt="account.name">
            </div>
            <div class="batch-account-info">
              <div class="batch-account-name" :title="account.name">{{ account.name }}</div>
              <div class="batch-account-platform">{{ account.platform }}</div>
            </div>
            <div v-if="selectedAccountIds.has(account.id)" class="batch-account-check">
              <el-icon><Check /></el-icon>
            </div>
          </div>
          <div v-if="accounts.length === 0" class="batch-empty">暂无可选账号</div>
        </div>
      </div>

      <!-- 右侧:标签区 -->
      <div class="batch-section batch-tags">
        <div class="batch-section-header">
          <span class="batch-section-title">选择标签</span>
          <span class="batch-section-count">已选 {{ selectedTagIds.size }}</span>
        </div>

        <div class="batch-tag-create">
          <el-input
            v-model="keyword"
            size="default"
            placeholder="搜索或新建标签..."
            clearable
            @keyup.enter="handleCreate"
          >
            <template #append>
              <el-button :disabled="!keyword.trim()" @click="handleCreate">新建</el-button>
            </template>
          </el-input>
        </div>

        <div class="batch-tag-list">
          <div
            v-for="tag in filteredTags"
            :key="tag.id"
            :class="['batch-tag-chip', { selected: selectedTagIds.has(tag.id) }]"
            :style="selectedTagIds.has(tag.id) ? { background: tag.color, borderColor: tag.color, color: '#fff' } : { borderColor: tag.color, color: tag.color }"
            @click="toggleTag(tag)"
          >
            <el-icon v-if="selectedTagIds.has(tag.id)" class="batch-tag-check"><Check /></el-icon>
            <span>{{ tag.name }}</span>
            <el-icon
              class="batch-tag-delete"
              title="删除此标签"
              @click.stop="handleDeleteTag(tag)"
            ><Close /></el-icon>
          </div>
          <div v-if="filteredTags.length === 0" class="batch-empty">
            暂无标签,输入名称按回车创建
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="batch-footer">
        <span class="batch-footer-hint">
          将追加到所选账号现有的标签,不会清除已有标签
        </span>
        <div class="batch-footer-actions">
          <el-button @click="$emit('update:modelValue', false)">取消</el-button>
          <el-button
            type="primary"
            :disabled="selectedAccountIds.size === 0"
            :loading="submitting"
            @click="handleApply"
          >
            追加到 {{ selectedAccountIds.size }} 个账号
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Close } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { accountApi } from '@/api/account'
import { getDefaultAvatar, proxyAvatar } from '@/utils/avatar'

const props = defineProps({
  modelValue: { type: Boolean, required: true }
})

const emit = defineEmits(['update:modelValue', 'done'])

const accountStore = useAccountStore()
const accounts = computed(() => accountStore.accounts)
const selectedAccountIds = ref(new Set())
const selectedTagIds = ref(new Set())
const keyword = ref('')
const submitting = ref(false)

const filteredTags = computed(() => {
  if (!keyword.value.trim()) return accountStore.allTags
  const kw = keyword.value.trim().toLowerCase()
  return accountStore.allTags.filter(t => t.name.toLowerCase().includes(kw))
})

const isAllSelected = computed(() => {
  const validIds = accounts.value.filter(a => a.status === '正常').map(a => a.id)
  if (validIds.length === 0) return false
  return validIds.every(id => selectedAccountIds.value.has(id))
})

function toggleAccount(id) {
  const next = new Set(selectedAccountIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedAccountIds.value = next
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    selectedAccountIds.value = new Set()
  } else {
    const validIds = accounts.value.filter(a => a.status === '正常').map(a => a.id)
    selectedAccountIds.value = new Set(validIds)
  }
}

function toggleTag(tag) {
  const next = new Set(selectedTagIds.value)
  if (next.has(tag.id)) next.delete(tag.id)
  else next.add(tag.id)
  selectedTagIds.value = next
}

async function handleCreate() {
  const name = keyword.value.trim()
  if (!name) return
  const exists = accountStore.allTags.some(t => t.name.toLowerCase() === name.toLowerCase())
  if (exists) {
    ElMessage.warning(`标签「${name}」已存在`)
    return
  }
  try {
    const res = await accountApi.createTag({ name })
    if (res.code === 200 && res.data) {
      await accountStore.loadTags()
      selectedTagIds.value = new Set([...selectedTagIds.value, res.data.id])
      keyword.value = ''
      ElMessage.success(`已创建标签「${name}」`)
    }
  } catch (e) {
    console.error('创建标签失败:', e)
    ElMessage.error('创建标签失败')
  }
}

async function handleDeleteTag(tag) {
  try {
    await ElMessageBox.confirm(
      `确认删除标签「${tag.name}」？\n该标签会从所有账号上移除,且不可恢复。`,
      '删除标签',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger'
      }
    )
  } catch {
    return
  }
  try {
    const res = await accountApi.deleteTag(tag.id)
    if (res.code === 200) {
      // 从 store 同步移除,避免一次额外网络请求
      accountStore.allTags = accountStore.allTags.filter(t => t.id !== tag.id)
      const next = new Set(selectedTagIds.value)
      next.delete(tag.id)
      selectedTagIds.value = next
      ElMessage.success(`已删除标签「${tag.name}」`)
    } else {
      ElMessage.error(res.msg || '删除失败')
    }
  } catch (e) {
    console.error('删除标签失败:', e)
    ElMessage.error('删除标签失败')
  }
}

async function handleApply() {
  if (selectedAccountIds.value.size === 0) return
  submitting.value = true
  try {
    const res = await accountApi.setBatchAccountTags(
      [...selectedAccountIds.value],
      [...selectedTagIds.value]
    )
    if (res.code === 200) {
      ElMessage.success(`已为 ${res.data?.updated ?? selectedAccountIds.value.size} 个账号追加标签`)
      emit('done')
      emit('update:modelValue', false)
    } else {
      ElMessage.error(res.msg || '批量追加失败')
    }
  } catch (e) {
    console.error('批量设置标签失败:', e)
    ElMessage.error('批量设置标签失败')
  } finally {
    submitting.value = false
  }
}

function onOpen() {
  selectedAccountIds.value = new Set()
  selectedTagIds.value = new Set()
  keyword.value = ''
}

watch(() => props.modelValue, (v) => {
  if (!v) {
    selectedAccountIds.value = new Set()
    selectedTagIds.value = new Set()
    keyword.value = ''
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.batch-tag-dialog {
  :deep(.el-dialog__body) {
    padding: 16px 20px;
  }

  .batch-dialog-body {
    display: flex;
    gap: 16px;
    height: 480px;
  }

  .batch-section {
    display: flex;
    flex-direction: column;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid $border;
    border-radius: $radius-card;
    overflow: hidden;
  }

  .batch-accounts {
    flex: 1.4;
  }

  .batch-tags {
    flex: 1;
  }

  .batch-section-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border-bottom: 1px solid $border-light;
    background: rgba($overlay-rgb, 0.02);

    .batch-section-title {
      font-size: 13px;
      font-weight: 600;
      color: $text-primary;
    }

    .batch-section-count {
      font-size: 12px;
      color: $brand-start;
      font-weight: 500;
      padding: 2px 8px;
      background: rgba($brand-start, 0.12);
      border-radius: 10px;
    }

    .el-button {
      margin-left: auto;
      font-size: 12px;
    }
  }

  // ── 账号卡片网格 ──
  .batch-account-grid {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 8px;
    padding: 12px;
    overflow-y: auto;
    align-content: start;
  }

  .batch-account-card {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: $bg-surface;
    border: 1px solid $border;
    border-radius: $radius-sm;
    cursor: pointer;
    transition: all $transition-fast;

    &:hover:not(.disabled) {
      background: rgba($brand-start, 0.06);
      border-color: $border-active;
    }

    &.selected {
      background: rgba($brand-start, 0.12);
      border-color: $brand-start;
      box-shadow: 0 0 0 1px rgba($brand-start, 0.25);

      .batch-account-name { color: #fff; font-weight: 600; }
    }

    &.disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }

    .batch-account-avatar {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: rgba($brand-start, 0.12);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      overflow: hidden;
      color: #c4b5fd;
      font-size: 12px;
      font-weight: 700;

      img { width: 100%; height: 100%; object-fit: cover; }
    }

    .batch-account-info {
      flex: 1;
      min-width: 0;
    }

    .batch-account-name {
      font-size: 12px;
      font-weight: 500;
      color: $text-primary;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      transition: color $transition-fast;
    }

    .batch-account-platform {
      font-size: 10px;
      color: $text-muted;
      margin-top: 2px;
    }

    .batch-account-check {
      position: absolute;
      top: 4px;
      right: 4px;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: $brand-start;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
    }
  }

  // ── 标签区 ──
  .batch-tag-create {
    padding: 12px 14px 8px;

    :deep(.el-input__wrapper) {
      background: $bg-surface;
      box-shadow: none;
      border-radius: $radius-sm;
      padding: 2px 12px;
    }

    :deep(.el-input-group__append) {
      background: rgba($brand-start, 0.15);
      .el-button { color: #c4b5fd; font-weight: 500; }
    }
  }

  .batch-tag-list {
    flex: 1;
    padding: 8px 14px 14px;
    overflow-y: auto;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-content: start;
  }

  .batch-tag-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 5px 12px;
    border: 1px solid;
    border-radius: 14px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all $transition-fast;
    background: transparent;
    user-select: none;

    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);

      .batch-tag-delete {
        opacity: 0.85;
      }
    }

    &.selected {
      font-weight: 600;

      .batch-tag-delete {
        color: #fff !important;
        opacity: 0.85;
      }

      .batch-tag-delete:hover {
        opacity: 1;
        background: rgba($overlay-rgb, 0.2);
      }
    }

    .batch-tag-check { font-size: 12px; }

    .batch-tag-delete {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      margin-left: 2px;
      margin-right: -4px;
      border-radius: 50%;
      font-size: 11px;
      opacity: 0;
      transition: all $transition-fast;
      cursor: pointer;

      &:hover {
        opacity: 1 !important;
        background: rgba($danger-color, 0.85);
        color: #fff !important;
      }
    }
  }

  .batch-empty {
    grid-column: 1 / -1;
    text-align: center;
    padding: 24px 0;
    color: $text-muted;
    font-size: 13px;
  }

  // ── Footer ──
  .batch-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .batch-footer-hint {
      font-size: 12px;
      color: $text-muted;
    }

    .batch-footer-actions {
      display: flex;
      gap: 8px;
    }
  }
}
</style>