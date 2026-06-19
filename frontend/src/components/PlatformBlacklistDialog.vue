<template>
  <el-dialog
    :model-value="modelValue"
    title="添加黑名单渠道"
    width="680px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <div class="blacklist-dialog-body">
      <p class="dialog-hint">选择要加入黑名单的渠道(已加入的不可重复选择)</p>
      <div class="platform-grid">
        <div
          v-for="p in platformList"
          :key="p.key"
          :class="[
            'platform-card',
            `platform-${p.cssClass}`,
            {
              'is-disabled': isAlreadyDisabled(p.key),
              'is-selected': isSelected(p.key)
            }
          ]"
          @click="toggleSelect(p.key)"
        >
          <div class="platform-logo-wrap">
            <img v-if="p.logo" :src="p.logo" :alt="p.name" class="platform-logo" />
            <span v-else class="platform-letter">{{ p.letter }}</span>
          </div>
          <div class="platform-name">{{ p.name }}</div>
          <div v-if="isAlreadyDisabled(p.key)" class="platform-badge added">已添加</div>
          <div v-else-if="isSelected(p.key)" class="platform-badge selected">✓</div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :disabled="selectedKeys.length === 0"
        @click="onConfirm"
      >
        确认添加{{ selectedKeys.length > 0 ? `(${selectedKeys.length})` : '' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { platformList } from '@/config/platforms'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  disabledKeys: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const selectedKeys = ref([])

const isAlreadyDisabled = (key) => props.disabledKeys.includes(key)
const isSelected = (key) => selectedKeys.value.includes(key)

const toggleSelect = (key) => {
  if (isAlreadyDisabled(key)) return
  if (isSelected(key)) {
    selectedKeys.value = selectedKeys.value.filter(k => k !== key)
  } else {
    selectedKeys.value = [...selectedKeys.value, key]
  }
}

const onOpen = () => {
  // 每次打开重置选择
  selectedKeys.value = []
}

const onConfirm = () => {
  emit('confirm', [...selectedKeys.value])
  selectedKeys.value = []
  emit('update:modelValue', false)
}
</script>

<style scoped>
.blacklist-dialog-body {
  padding: 0 4px;
}

.dialog-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0 0 16px 0;
}

.platform-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.platform-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 16px 8px;
  border: 2px solid var(--el-border-color);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--el-bg-color);
}

.platform-card:hover:not(.is-disabled) {
  border-color: var(--el-color-primary);
  transform: translateY(-2px);
}

.platform-card.is-selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.platform-card.is-disabled {
  opacity: 0.45;
  cursor: not-allowed;
  background: var(--el-fill-color-light);
}

.platform-logo-wrap {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
}

.platform-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
}

.platform-letter {
  font-size: 20px;
  font-weight: bold;
}

.platform-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.platform-badge {
  position: absolute;
  bottom: 4px;
  right: 4px;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  color: white;
}

.platform-badge.added {
  background: var(--el-text-color-disabled);
}

.platform-badge.selected {
  background: var(--el-color-primary);
}

@media (max-width: 640px) {
  .platform-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
