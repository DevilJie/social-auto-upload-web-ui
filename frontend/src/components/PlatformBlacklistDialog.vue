<template>
  <el-dialog
    :model-value="modelValue"
    width="680px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onOpen"
    @opened="onOpened"
  >
    <template #header>
      <div class="pb-dialog-header">
        <span class="pb-dialog-title">添加黑名单渠道</span>
        <el-tooltip content="重新查看引导" placement="top">
          <button class="pb-guide-btn" type="button" @click="startGuide">
            <el-icon><Guide /></el-icon>
            新手引导
          </button>
        </el-tooltip>
      </div>
    </template>
    <div class="blacklist-dialog-body">
      <p class="dialog-hint">选择要加入黑名单的渠道(已加入的不可重复选择)</p>
      <div class="platform-grid" data-tour="pb-list">
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
        data-tour="pb-confirm"
        :disabled="selectedKeys.length === 0"
        @click="onConfirm"
      >
        确认添加{{ selectedKeys.length > 0 ? `(${selectedKeys.length})` : '' }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 弹窗新手引导（teleport 到 body，首次打开自动播放） -->
  <GuideTour
    ref="tourRef"
    :steps="blacklistGuideSteps"
    @finish="onGuideDone"
    @skip="onGuideDone"
  />
</template>

<script setup>
import { ref, watch } from 'vue'
import { Guide } from '@element-plus/icons-vue'
import { platformList } from '@/config/platforms'
import GuideTour from '@/components/GuideTour.vue'
import { blacklistGuideSteps, GUIDE_KEYS, isGuideDone, markGuideDone } from '@/config/guides'

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

// ===== 弹窗新手引导 =====
const tourRef = ref(null)

const startGuide = () => tourRef.value?.start()

// 引导完成/跳过都记为"已看过"，之后打开弹窗不再自动播放
const onGuideDone = () => markGuideDone(GUIDE_KEYS.blacklist)

// @opened：弹窗打开动画结束后再启动引导，保证高亮定位准确
function onOpened () {
  if (!isGuideDone(GUIDE_KEYS.blacklist)) {
    setTimeout(() => tourRef.value?.start(), 150)
  }
}

// 保险：弹窗关闭时结束可能还开着的引导
watch(() => props.modelValue, (v) => {
  if (!v) tourRef.value?.stop()
})
</script>

<style scoped>
/* 自定义 header：标题 + 新手引导重看入口（padding-right 给右上角关闭按钮留位） */
.pb-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-right: 32px;
}

.pb-dialog-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.pb-guide-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px dashed var(--el-border-color);
  background: transparent;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.pb-guide-btn:hover {
  color: var(--el-color-primary);
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

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
