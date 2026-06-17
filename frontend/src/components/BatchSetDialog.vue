<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    :title="title"
    width="720px"
    top="8vh"
    :close-on-click-modal="false"
  >
    <el-form label-position="top">
      <el-form-item label="标题">
        <el-input
          v-model="formTitle"
          maxlength="100"
          show-word-limit
          placeholder="留空表示清空原值"
          clearable
        />
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="formDescription"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="留空表示清空原值"
        />
      </el-form-item>
      <el-form-item label="标签">
        <div class="tag-input-wrap">
          <el-input
            v-model="tagInput"
            placeholder="输入标签内容，按回车添加"
            @keyup.enter="addTag"
            clearable
          />
          <div v-if="formTags.length > 0" class="tags-list">
            <el-tag
              v-for="(tag, index) in formTags"
              :key="index"
              closable
              @close="removeTag(index)"
              size="small"
            >#{{ tag }}</el-tag>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="渠道">
        <div class="channel-grid">
          <div
            v-for="p in platforms"
            :key="p.key"
            :class="['channel-card', {
              'is-checked': checkedKeys.has(p.key),
              'is-disabled': p.count === 0
            }]"
            role="checkbox"
            :aria-checked="checkedKeys.has(p.key)"
            :aria-disabled="p.count === 0"
            :tabindex="p.count === 0 ? -1 : 0"
            @click="toggleKey(p)"
            @keydown.enter.prevent="toggleKey(p)"
            @keydown.space.prevent="toggleKey(p)"
          >
            <img v-if="p.logo" :src="p.logo" :alt="p.name" class="channel-logo" />
            <div v-else class="channel-logo channel-logo-fallback">{{ p.name?.charAt(0) }}</div>
            <div class="channel-name">{{ p.name }}</div>
            <div class="channel-count">{{ p.count }} 账号</div>
            <el-icon v-if="checkedKeys.has(p.key) && p.count > 0" class="check-icon"><Check /></el-icon>
          </div>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :disabled="checkedCount === 0"
        @click="handleApply"
      >
        应用到 {{ checkedCount }} 个渠道
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const MAX_TAGS = 10

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  platforms: { type: Array, required: true },
  title: { type: String, default: '批量设置' },
})

const emit = defineEmits(['update:modelValue', 'apply'])

const formTitle = ref('')
const formDescription = ref('')
const formTags = ref([])
const tagInput = ref('')
const checkedKeys = ref(new Set())

const checkedCount = computed(() => checkedKeys.value.size)

watch(() => props.modelValue, (open) => {
  if (open) {
    formTitle.value = ''
    formDescription.value = ''
    formTags.value = []
    tagInput.value = ''
    checkedKeys.value = new Set(
      props.platforms.filter(p => p.count > 0).map(p => p.key)
    )
  }
})

function toggleKey(p) {
  if (p.count === 0) return
  const next = new Set(checkedKeys.value)
  if (next.has(p.key)) {
    next.delete(p.key)
  } else {
    next.add(p.key)
  }
  checkedKeys.value = next
}

function addTag() {
  const v = (tagInput.value || '').trim()
  if (!v) return
  if (formTags.value.length >= MAX_TAGS) {
    ElMessage.warning(`最多 ${MAX_TAGS} 个标签`)
    return
  }
  if (formTags.value.includes(v)) {
    tagInput.value = ''
    return
  }
  formTags.value = [...formTags.value, v]
  tagInput.value = ''
}

function removeTag(idx) {
  formTags.value = formTags.value.filter((_, i) => i !== idx)
}

function handleApply() {
  emit('apply', Array.from(checkedKeys.value), {
    title: formTitle.value,
    description: formDescription.value,
    tags: [...formTags.value],
  })
  emit('update:modelValue', false)
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
  width: 100%;
}

.channel-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  border: 1.5px solid $border;
  border-radius: 10px;
  background: $bg-elevated;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;

  &:hover:not(.is-disabled) {
    border-color: $brand-start;
    background: rgba(139, 92, 246, 0.04);
  }

  &.is-checked {
    border-color: $brand-start;
    background: rgba(139, 92, 246, 0.1);
    box-shadow: 0 0 0 1px $brand-start inset;
  }

  &.is-disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .channel-logo {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    object-fit: contain;
  }
  .channel-logo-fallback {
    display: flex;
    align-items: center;
    justify-content: center;
    background: $bg-surface;
    color: $text-muted;
    font-size: 14px;
    font-weight: 700;
  }

  .channel-name {
    font-size: 13px;
    font-weight: 600;
    color: $text-primary;
    text-align: center;
  }

  .channel-count {
    font-size: 11px;
    color: $text-muted;
  }

  .check-icon {
    position: absolute;
    top: 4px;
    right: 4px;
    color: $brand-start;
    font-size: 14px;
  }
}

.tag-input-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
