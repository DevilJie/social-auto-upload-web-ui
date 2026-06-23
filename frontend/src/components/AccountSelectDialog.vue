<template>
  <el-dialog
    :model-value="modelValue"
    title="选择账号"
    width="80%"
    :close-on-click-modal="false"
    class="account-select-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="account-dialog-body">
      <!-- 左:渠道筛选 -->
      <div class="account-section platform-section">
        <div class="account-section-header">
          <span class="account-section-title">渠道筛选</span>
          <span class="account-section-count">已选 {{ selectedPlatformNames.size }}</span>
        </div>
        <div class="platform-list">
          <label
            v-for="p in platforms"
            :key="p.key"
            :class="['platform-item', 'cursor-pointer', { active: selectedPlatformNames.has(p.name) }]"
          >
            <el-checkbox
              :model-value="selectedPlatformNames.has(p.name)"
              @change="togglePlatform(p.name)"
            />
            <span class="platform-badge">
              <img v-if="p.logo" :src="p.logo" :alt="p.name" class="platform-badge-img">
              <template v-else>{{ p.letter }}</template>
            </span>
            <span class="platform-name">{{ p.name }}</span>
          </label>
          <div v-if="platforms.length === 0" class="empty-hint">暂无可选渠道</div>
        </div>
      </div>

      <!-- 中:账号卡片 -->
      <div class="account-section accounts-section">
        <div class="account-section-header">
          <span class="account-section-title">账号</span>
          <span class="account-section-count">已选 {{ tempSelectedAccounts.length }} / {{ accountStore.accounts.length }}</span>
          <el-button size="small" type="primary" plain class="ml-auto" :disabled="validFilteredAccounts.length === 0" @click="toggleSelectAll">
            {{ isAllSelected ? '取消全选' : '一键全选' }}
          </el-button>
        </div>
        <div class="account-grid">
          <div
            v-for="account in filteredAccounts"
            :key="account.id"
            :class="['account-card', { selected: tempSelectedAccounts.includes(account.id), disabled: account.status !== '正常' }]"
            @click="account.status === '正常' && toggleAccount(account.id)"
          >
            <div class="account-avatar">
              <img v-if="account.avatar" :src="proxyAvatar(account.avatar)" :alt="account.name">
              <img v-else :src="getDefaultAvatar(account.name)" :alt="account.name">
            </div>
            <div class="account-info">
              <div class="account-name" :title="account.name">{{ account.name }}</div>
              <div class="account-meta">
                <span class="account-platform">{{ account.platform }}</span>
                <span
                  v-for="tag in account.tags || []"
                  :key="tag.id"
                  class="account-tag-pill"
                  :style="{ borderColor: tag.color, color: tag.color }"
                >{{ tag.name }}</span>
              </div>
            </div>
            <div v-if="tempSelectedAccounts.includes(account.id)" class="account-check">
              <el-icon><Check /></el-icon>
            </div>
          </div>
          <div v-if="filteredAccounts.length === 0" class="empty-hint">暂无可选账号</div>
        </div>
      </div>

      <!-- 右:标签筛选 -->
      <div class="account-section tag-section">
        <div class="account-section-header">
          <span class="account-section-title">标签筛选</span>
          <span class="account-section-count">已选 {{ selectedTagIds.size }}</span>
          <el-button
            size="small"
            link
            type="primary"
            class="ml-auto"
            :disabled="selectedTagIds.size === 0"
            @click="clearAllTags"
          >全不选</el-button>
        </div>

        <div v-if="accountStore.allTags.length > 0" class="tag-search">
          <el-input
            v-model="tagKeyword"
            size="default"
            placeholder="搜索标签..."
            clearable
          />
        </div>

        <div class="tag-list">
          <div
            v-for="tag in filteredTags"
            :key="tag.id"
            :class="['tag-chip', { selected: selectedTagIds.has(tag.id) }]"
            :style="selectedTagIds.has(tag.id)
              ? { background: tag.color, borderColor: tag.color, color: '#fff' }
              : { borderColor: tag.color, color: tag.color }"
            @click="toggleTag(tag.id)"
          >
            <el-icon v-if="selectedTagIds.has(tag.id)" class="tag-check"><Check /></el-icon>
            <span>{{ tag.name }}</span>
          </div>
          <div v-if="accountStore.allTags.length === 0" class="empty-hint">暂无标签</div>
          <div v-else-if="filteredTags.length === 0" class="empty-hint">没有匹配的标签</div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <span class="selected-count">已选择 {{ tempSelectedAccounts.length }} 个账号</span>
        <div class="dialog-footer-btns">
          <el-button @click="$emit('update:modelValue', false)">取消</el-button>
          <el-button type="primary" @click="confirmSelection">确认设置</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Check } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { accountApi } from '@/api/account'
import { getDefaultAvatar, proxyAvatar } from '@/utils/avatar'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  platforms: { type: Array, required: true },
  publishAccountIds: { type: Set, required: true },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const accountStore = useAccountStore()
const appStore = useAppStore()

const selectedPlatformNames = ref(new Set())
const selectedTagIds = ref(new Set())
const tempSelectedAccounts = ref([])
const tagKeyword = ref('')

const isPlatformKeyDisabled = (key) => appStore.isPlatformDisabled(key)

const filteredAccounts = computed(() => {
  let list = accountStore.accounts
  // 只显示 props.platforms 里有的渠道账号（图集发布只显示支持的渠道）
  const allowedPlatformNames = new Set(props.platforms.map(p => p.name))
  list = list.filter(a => allowedPlatformNames.has(a.platform))
  list = list.filter(a => !isPlatformKeyDisabled(platformKeyOf(a)))
  if (selectedPlatformNames.value.size > 0) {
    list = list.filter(a => selectedPlatformNames.value.has(a.platform))
  }
  if (selectedTagIds.value.size > 0) {
    list = list.filter(a => a.tags?.some(t => selectedTagIds.value.has(t.id)))
  }
  return list
})

const validFilteredAccounts = computed(() =>
  filteredAccounts.value.filter(a => a.status === '正常')
)

const filteredTags = computed(() => {
  const all = accountStore.allTags
  if (!tagKeyword.value.trim()) return all
  const kw = tagKeyword.value.trim().toLowerCase()
  return all.filter(t => t.name.toLowerCase().includes(kw))
})

const isAllSelected = computed(() => {
  const ids = validFilteredAccounts.value.map(a => a.id)
  if (ids.length === 0) return false
  return ids.every(id => tempSelectedAccounts.value.includes(id))
})

function platformKeyOf(account) {
  const entry = props.platforms.find(p => p.name === account.platform)
  return entry?.key || ''
}

function togglePlatform(name) {
  const next = new Set(selectedPlatformNames.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  selectedPlatformNames.value = next
}

function toggleAccount(id) {
  if (tempSelectedAccounts.value.includes(id)) {
    tempSelectedAccounts.value = tempSelectedAccounts.value.filter(x => x !== id)
  } else {
    tempSelectedAccounts.value = [...tempSelectedAccounts.value, id]
  }
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    const visibleIds = new Set(validFilteredAccounts.value.map(a => a.id))
    tempSelectedAccounts.value = tempSelectedAccounts.value.filter(id => !visibleIds.has(id))
  } else {
    const visibleIds = validFilteredAccounts.value.map(a => a.id)
    const merged = new Set([...tempSelectedAccounts.value, ...visibleIds])
    tempSelectedAccounts.value = [...merged]
  }
}

function toggleTag(tagId) {
  const next = new Set(selectedTagIds.value)
  if (next.has(tagId)) next.delete(tagId)
  else next.add(tagId)
  selectedTagIds.value = next
}

function clearAllTags() {
  selectedTagIds.value = new Set()
}

function confirmSelection() {
  emit('confirm', [...tempSelectedAccounts.value])
  emit('update:modelValue', false)
}

watch(() => props.modelValue, async (visible) => {
  if (visible) {
    tempSelectedAccounts.value = [...props.publishAccountIds]
    selectedPlatformNames.value = new Set()
    selectedTagIds.value = new Set()
    tagKeyword.value = ''
    if (accountStore.accounts.length === 0) {
      try {
        const res = await accountApi.getAccounts()
        if (res.code === 200 && res.data) {
          accountStore.setAccounts(res.data)
        }
      } catch (e) {
        console.error('加载账号失败:', e)
      }
    }
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.account-select-dialog {
  :deep(.el-dialog__body) {
    padding: 16px 20px;
  }

  .account-dialog-body {
    display: flex;
    gap: 12px;
    height: 520px;
  }

  .account-section {
    display: flex;
    flex-direction: column;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid $border;
    border-radius: $radius-card;
    overflow: hidden;
  }

  .platform-section {
    flex: 1;
    min-width: 180px;
  }

  .accounts-section {
    flex: 2.2;
  }

  .tag-section {
    flex: 1;
    min-width: 220px;
  }

  .account-section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-bottom: 1px solid $border-light;
    background: rgba(255, 255, 255, 0.02);
    flex-shrink: 0;

    .account-section-title {
      font-size: 13px;
      font-weight: 600;
      color: $text-primary;
    }

    .account-section-count {
      font-size: 12px;
      color: $brand-start;
      font-weight: 500;
      padding: 2px 8px;
      background: rgba($brand-start, 0.12);
      border-radius: 10px;
    }

    .ml-auto {
      margin-left: auto;
      font-size: 12px;
    }
  }

  .platform-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .platform-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border-radius: 6px;
    cursor: pointer;
    transition: all $transition-fast;
    border-left: 3px solid transparent;

    &:hover { background: rgba(255, 255, 255, 0.04); }

    &.active {
      background: rgba($brand-start, 0.08);
      border-left-color: $brand-start;
    }

    .platform-badge {
      width: 24px;
      height: 24px;
      border-radius: 5px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      flex-shrink: 0;
      background: rgba(139, 92, 246, 0.12);

      .platform-badge-img { width: 20px; height: 20px; object-fit: contain; }
    }

    .platform-name {
      font-size: 13px;
      color: $text-primary;
    }

    :deep(.el-checkbox) {
      margin-right: 0;
    }
  }

  .account-grid {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 8px;
    padding: 12px;
    overflow-y: auto;
    align-content: start;
  }

  .account-card {
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

      .account-name { color: #fff; font-weight: 600; }
    }

    &.disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }

    .account-avatar {
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

    .account-info {
      flex: 1;
      min-width: 0;
    }

    .account-name {
      font-size: 12px;
      font-weight: 500;
      color: $text-primary;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      transition: color $transition-fast;
    }

    .account-meta {
      display: flex;
      align-items: center;
      gap: 4px;
      margin-top: 3px;
      flex-wrap: wrap;
    }

    .account-platform {
      font-size: 10px;
      color: $text-muted;
    }

    .account-tag-pill {
      display: inline-flex;
      align-items: center;
      padding: 0 5px;
      border: 1px solid;
      border-radius: 3px;
      font-size: 9px;
      font-weight: 500;
      line-height: 14px;
    }

    .account-check {
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

  .tag-search {
    padding: 12px 12px 4px;
    flex-shrink: 0;

    :deep(.el-input__wrapper) {
      background: $bg-surface;
      box-shadow: none;
      border-radius: $radius-sm;
      padding: 2px 12px;
    }
  }

  .tag-list {
    flex: 1;
    padding: 8px 12px 12px;
    overflow-y: auto;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-content: start;
  }

  .tag-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
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
    }

    &.selected {
      font-weight: 600;
    }

    .tag-check { font-size: 12px; }
  }

  .empty-hint {
    width: 100%;
    text-align: center;
    padding: 24px 0;
    color: $text-muted;
    font-size: 13px;
  }

  .dialog-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .selected-count { font-size: 13px; color: $text-muted; }
    .dialog-footer-btns { display: flex; gap: 8px; }
  }
}

.cursor-pointer { cursor: pointer; }
</style>
