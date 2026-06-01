<template>
  <el-dialog
    :model-value="modelValue"
    title="选择账号"
    width="680px"
    :close-on-click-modal="false"
    class="account-select-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="account-dialog-body">
      <div class="account-dialog-content">
        <div class="dialog-platform-list">
          <div
            :class="['dialog-platform-item', 'cursor-pointer', { active: !accountFilterPlatform }]"
            @click="accountFilterPlatform = ''"
          >全部平台</div>
          <div
            v-for="p in platforms"
            :key="p.key"
            :class="['dialog-platform-item', 'cursor-pointer', { active: accountFilterPlatform === p.name }]"
            @click="accountFilterPlatform = p.name"
          >
            <span class="dialog-platform-badge">
              <img v-if="p.logo" :src="p.logo" :alt="p.name" class="dialog-platform-badge-img">
              <template v-else>{{ p.letter }}</template>
            </span>
            {{ p.name }}
          </div>
        </div>

        <div class="dialog-account-list">
          <div class="dialog-select-all">
            <el-button size="small" @click="toggleSelectAll">
              {{ isAllSelected ? '取消全选' : '一键全选' }}
            </el-button>
          </div>
          <el-checkbox-group v-model="tempSelectedAccounts">
            <div
              v-for="account in filteredAccounts"
              :key="account.id"
              :class="['dialog-account-item', { disabled: account.status !== '正常' }]"
            >
              <el-checkbox :label="account.id" class="cursor-pointer">
                <div class="dialog-account-info">
                  <div class="dialog-account-avatar">{{ account.name ? account.name.charAt(0) : '?' }}</div>
                  <span class="dialog-account-name">{{ account.name }}</span>
                  <span class="dialog-account-platform">{{ account.platform }}</span>
                  <span :class="['dialog-account-status', account.status === '正常' ? 'ok' : 'err']">
                    {{ account.status === '正常' ? '正常' : '已失效' }}
                  </span>
                </div>
              </el-checkbox>
            </div>
          </el-checkbox-group>
          <div v-if="filteredAccounts.length === 0" class="dialog-empty">暂无可选账号</div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <span class="selected-count">已选择 {{ tempSelectedAccounts.length }} 个账号</span>
        <div class="dialog-footer-btns">
          <el-button @click="$emit('update:modelValue', false)">取消</el-button>
          <el-button type="primary" @click="confirmSelection">确认添加</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useAccountStore } from '@/stores/account'
import { accountApi } from '@/api/account'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  platforms: { type: Array, required: true },
  publishAccountIds: { type: Set, required: true },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const accountStore = useAccountStore()
const accountFilterPlatform = ref('')
const tempSelectedAccounts = ref([])

const platformNames = computed(() => props.platforms.map(p => p.name))

const filteredAccounts = computed(() => {
  let list = accountStore.accounts.filter(a => platformNames.value.includes(a.platform))
  if (accountFilterPlatform.value) {
    list = list.filter(a => a.platform === accountFilterPlatform.value)
  }
  return list
})

const validFilteredAccounts = computed(() =>
  filteredAccounts.value.filter(a => a.status === '正常')
)

const isAllSelected = computed(() =>
  validFilteredAccounts.value.length > 0 &&
  validFilteredAccounts.value.every(a => tempSelectedAccounts.value.includes(a.id))
)

function toggleSelectAll() {
  if (isAllSelected.value) {
    const validIds = new Set(validFilteredAccounts.value.map(a => a.id))
    tempSelectedAccounts.value = tempSelectedAccounts.value.filter(id => !validIds.has(id))
  } else {
    const validIds = validFilteredAccounts.value.map(a => a.id)
    const merged = new Set([...tempSelectedAccounts.value, ...validIds])
    tempSelectedAccounts.value = [...merged]
  }
}

function confirmSelection() {
  emit('confirm', [...tempSelectedAccounts.value])
  emit('update:modelValue', false)
}

watch(() => props.modelValue, async (visible) => {
  if (visible) {
    tempSelectedAccounts.value = [...props.publishAccountIds]
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
  .account-dialog-body {
    .account-dialog-content {
      display: flex;
      gap: 0;
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 12px;
      overflow: hidden;
      height: 420px;
    }

    .dialog-platform-list {
      width: 160px;
      flex-shrink: 0;
      border-right: 1px solid rgba(255, 255, 255, 0.06);
      background: rgba(0, 0, 0, 0.25);
      overflow-y: auto;

      .dialog-platform-item {
        padding: 14px 16px;
        font-size: 15px;
        color: $text-secondary;
        display: flex;
        align-items: center;
        gap: 12px;
        transition: all 0.2s ease;
        border-left: 3px solid transparent;

        &:hover { background: rgba(255, 255, 255, 0.03); }

        &.active {
          background: rgba(139, 92, 246, 0.08);
          color: #f8fafc;
          font-weight: 600;
          border-left-color: $brand-start;
        }

        .dialog-platform-badge {
          width: 28px;
          height: 28px;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: #fff;
          font-size: 11px;
          font-weight: 700;
          flex-shrink: 0;
          overflow: hidden;

          .dialog-platform-badge-img { width: 22px; height: 22px; object-fit: contain; }
        }
      }
    }

    .dialog-account-list {
      flex: 1;
      padding: 12px;
      overflow-y: auto;

      .dialog-select-all {
        display: flex;
        justify-content: flex-end;
        margin-bottom: 8px;
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      }

      .dialog-account-item {
        padding: 8px 10px;
        border-radius: 8px;
        transition: all 0.2s ease;
        margin-bottom: 2px;

        &:hover { background: rgba(255, 255, 255, 0.03); }
        &.disabled { opacity: 0.5; }
      }

      .dialog-account-info {
        display: flex;
        align-items: center;
        gap: 8px;

        .dialog-account-avatar {
          width: 26px;
          height: 26px;
          border-radius: 50%;
          background: rgba(139, 92, 246, 0.12);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 11px;
          color: #c4b5fd;
          font-weight: 700;
          flex-shrink: 0;
        }

        .dialog-account-name { font-size: 13px; color: #f8fafc; font-weight: 500; }
        .dialog-account-platform { font-size: 11px; color: $text-muted; }

        .dialog-account-status {
          font-size: 11px;
          margin-left: auto;
          &.ok { color: $success-color; }
          &.err { color: $danger-color; }
        }
      }
    }
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

.dialog-empty {
  text-align: center;
  padding: 40px 0;
  color: $text-muted;
  font-size: 14px;
}
</style>
