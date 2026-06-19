<template>
  <aside class="account-sidebar">
    <div class="sidebar-header">
      <span class="sidebar-title">账号管理</span>
      <span class="sidebar-count">{{ totalCount }}</span>
    </div>

    <div class="group-list">
      <!-- 空态:edit 模式下没有已选账号时,显示提示 -->
      <div v-if="mode === 'edit' && visibleAccountGroups.length === 0" class="empty-hint">
        <p>暂无选中账号</p>
        <p class="empty-sub">点击下方「添加账号」开始</p>
      </div>

      <div
        v-for="group in visibleAccountGroups"
        :key="group.key"
        :class="['group-wrap', { 'is-selected': selectedPlatform === group.key }]"
      >
        <div class="group-header cursor-pointer" @click="$emit('toggle-group', group.key)">
          <el-icon class="expand-icon" :style="{ color: selectedPlatform === group.key ? group.color : '' }">
            <component :is="expandedGroups.has(group.key) ? ArrowDown : ArrowRight" />
          </el-icon>
          <span class="platform-badge">
            <img v-if="group.logo" :src="group.logo" :alt="group.name" class="platform-badge-img">
            <template v-else>{{ group.letter }}</template>
          </span>
          <span class="group-name">{{ group.name }}</span>
          <span class="group-count">{{ mode === 'readonly' ? group.accounts.length : group.accounts.filter(a => publishAccountIds.has(a.id)).length }}</span>
        </div>

        <transition name="slide">
          <div v-show="expandedGroups.has(group.key)" class="group-accounts">
            <div
              v-for="account in group.accounts.filter(a => mode === 'readonly' ? true : publishAccountIds.has(a.id))"
              :key="account.id"
              :class="['account-item cursor-pointer', {
                active: selectedAccountId === account.id,
                'has-override': hasAccountOverride(account.id)
              }]"
              @click="$emit('select-account', account, group)"
            >
              <div class="account-avatar" :style="{ borderColor: group.color }">
                {{ account.name ? account.name.charAt(0) : '?' }}
              </div>
              <span class="account-name">{{ account.name }}</span>
              <span :class="['dot', account.status === '正常' ? 'on' : 'off']"></span>
              <el-icon v-if="hasAccountOverride(account.id) && mode === 'edit'" class="override-icon" title="已自定义配置"><StarFilled /></el-icon>
              <el-icon v-if="mode === 'edit'" class="account-remove" @click.stop="$emit('remove-account', account.id)"><Close /></el-icon>
            </div>
            <div v-if="(mode === 'readonly' ? group.accounts : group.accounts.filter(a => publishAccountIds.has(a.id))).length === 0" class="no-accounts">暂无账号</div>
          </div>
        </transition>
      </div>
    </div>

    <div v-if="mode === 'edit'" class="sidebar-footer">
      <div class="add-btn cursor-pointer" @click="$emit('open-account-dialog')">+ 添加账号</div>
    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { ArrowDown, ArrowRight, StarFilled, Close } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

const props = defineProps({
  mode: {
    type: String,
    default: 'edit',
    validator: v => ['edit', 'readonly'].includes(v),
  },
  accountGroups: { type: Array, required: true },
  totalCount: { type: Number, required: true },
  selectedPlatform: { type: String, default: null },
  selectedAccountId: { type: [Number, String], default: null },
  expandedGroups: { type: Set, required: true },
  publishAccountIds: { type: Set, required: true },
  hasAccountOverride: { type: Function, required: true },
})

defineEmits(['toggle-group', 'select-account', 'remove-account', 'open-account-dialog'])

// 过滤逻辑:
// 1. 永远过滤掉被渠道黑名单禁用的平台分组
// 2. edit 模式下,只显示「该平台下有 publishAccountIds 中已选账号」的分组(默认空,选了账号才出现)
// 3. readonly 模式下,显示所有非黑名单平台分组(用于历史详情查看等场景)
// group.key 已经是平台 key(如 'xiaohongshu'),无需再走 platformNameToKey
const visibleAccountGroups = computed(() =>
  props.accountGroups.filter(group => {
    if (!group.key || appStore.isPlatformDisabled(group.key)) return false
    if (props.mode === 'edit') {
      // edit 模式:必须有已选账号才显示分组
      return group.accounts.some(a => props.publishAccountIds.has(a.id))
    }
    return true
  })
)
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.account-sidebar {
  width: 232px;
  flex-shrink: 0;
  background: linear-gradient(180deg, #0d0d22 0%, #0a0a1a 100%);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;

  .sidebar-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 20px 16px 16px;

    .sidebar-title {
      font-size: 16px;
      font-weight: 700;
      color: #e2e8f0;
    }

    .sidebar-count {
      font-size: 11px;
      color: #a78bfa;
      background: rgba(139, 92, 246, 0.12);
      padding: 3px 10px;
      border-radius: 12px;
      font-weight: 700;
    }
  }

  .group-list {
    flex: 1;
    overflow-y: auto;
    padding: 4px 0;

    &::-webkit-scrollbar { width: 3px; }
    &::-webkit-scrollbar-thumb { background: rgba(139, 92, 246, 0.15); border-radius: 2px; }
  }

  .group-wrap {
    margin: 2px 10px;
    border-radius: 10px;
    transition: all 0.2s ease;
    border: 1px solid transparent;

    &.is-selected {
      background: rgba(139, 92, 246, 0.1);
      border-color: rgba(139, 92, 246, 0.2);
      margin: 2px 9px;
    }
  }

  .group-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 12px;
    border-radius: 10px;
    transition: all 0.2s ease;
    user-select: none;

    &:hover { background: rgba(255, 255, 255, 0.03); }

    .expand-icon {
      font-size: 12px;
      color: $text-muted;
      transition: all 0.2s ease;
    }

    .platform-badge {
      width: 34px;
      height: 34px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-size: 14px;
      font-weight: 700;
      flex-shrink: 0;
      overflow: hidden;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);

      .platform-badge-img {
        width: 24px;
        height: 24px;
        object-fit: contain;
      }
    }

    .group-name {
      flex: 1;
      font-size: 15px;
      color: $text-secondary;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .group-count {
      font-size: 11px;
      color: #a78bfa;
      background: rgba(139, 92, 246, 0.1);
      padding: 2px 8px;
      border-radius: 8px;
      font-weight: 600;
    }
  }

  .group-accounts {
    padding: 0 12px 8px 48px;

    .no-accounts {
      font-size: 12px;
      color: $text-muted;
      padding: 6px 0;
    }
  }

  .group-list > .empty-hint {
    padding: 48px 16px;
    text-align: center;
    color: $text-muted;
    font-size: 13px;

    p {
      margin: 0 0 6px;
    }

    .empty-sub {
      font-size: 11px;
      opacity: 0.7;
    }
  }

  .slide-enter-active, .slide-leave-active {
    transition: all 200ms ease;
    overflow: hidden;
  }
  .slide-enter-from, .slide-leave-to { opacity: 0; max-height: 0; }
  .slide-enter-to, .slide-leave-from { opacity: 1; max-height: 500px; }

  .account-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 8px;
    border-radius: 8px;
    transition: all 0.2s ease;
    border: 1px solid transparent;

    &:hover {
      background: rgba(255, 255, 255, 0.04);
      border-color: rgba(255, 255, 255, 0.04);
    }

    &.active {
      background: rgba(139, 92, 246, 0.1);
      border-color: rgba(139, 92, 246, 0.15);
    }

    .account-avatar {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: rgba(139, 92, 246, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
      color: #c4b5fd;
      font-weight: 700;
      flex-shrink: 0;
      border: 2px solid transparent;
      transition: all 0.2s ease;
    }

    .account-name {
      flex: 1;
      font-size: 12px;
      color: $text-secondary;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 500;
    }

    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      flex-shrink: 0;

      &.on { background: $success-color; box-shadow: 0 0 6px rgba(34, 197, 94, 0.5); }
      &.off { background: $danger-color; box-shadow: 0 0 6px rgba(239, 68, 68, 0.5); }
    }

    .account-remove {
      font-size: 16px;
      color: $text-muted;
      opacity: 0;
      transition: all 0.15s ease;
      flex-shrink: 0;
      margin-left: 4px;
      cursor: pointer;

      &:hover { color: $danger-color; opacity: 1 !important; }
    }

    &:hover .account-remove { opacity: 0.5; }

    &.has-override {
      background: rgba(245, 158, 11, 0.06);
      border-color: rgba(245, 158, 11, 0.1);
      .account-name { font-weight: 600; }
    }

    .override-icon {
      font-size: 12px;
      color: #f59e0b;
      flex-shrink: 0;
    }
  }

  .sidebar-footer {
    padding: 12px 10px;
    border-top: 1px solid rgba(255, 255, 255, 0.04);

    .add-btn {
      border: 1.5px dashed rgba(139, 92, 246, 0.25);
      border-radius: 10px;
      padding: 10px;
      text-align: center;
      font-size: 13px;
      font-weight: 600;
      color: #a78bfa;
      transition: all 0.2s ease;

      &:hover {
        border-color: rgba(139, 92, 246, 0.5);
        color: #c4b5fd;
        background: rgba(139, 92, 246, 0.08);
      }
    }
  }
}

.cursor-pointer { cursor: pointer; }
</style>
