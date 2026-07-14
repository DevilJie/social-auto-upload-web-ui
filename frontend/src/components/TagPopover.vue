<template>
  <el-popover
    :visible="visible"
    placement="bottom"
    :width="240"
    @update:visible="$emit('update:visible', $event)"
  >
    <template #reference>
      <slot />
    </template>
    <div class="tag-popover">
      <div class="tag-popover-search">
        <el-input
          v-model="keyword"
          size="small"
          placeholder="搜索或创建标签..."
          clearable
          @keyup.enter="handleCreate"
        />
      </div>
      <div class="tag-popover-list">
        <div
          v-for="tag in filteredTags"
          :key="tag.id"
          class="tag-popover-item"
          @click="toggleTag(tag)"
        >
          <span class="tag-dot" :style="{ background: tag.color }"></span>
          <span class="tag-name">{{ tag.name }}</span>
          <el-icon v-if="isSelected(tag)" class="tag-check"><Check /></el-icon>
        </div>
        <div v-if="keyword && !exactMatch" class="tag-popover-create" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          创建 "{{ keyword }}"
        </div>
        <div v-if="filteredTags.length === 0 && !keyword" class="tag-popover-empty">
          暂无标签
        </div>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Check, Plus } from '@element-plus/icons-vue'
import { accountApi } from '@/api/account'
import { useAccountStore } from '@/stores/account'

const props = defineProps({
  visible: { type: Boolean, default: false },
  accountId: { type: Number, required: true },
  selectedTags: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'changed'])

const accountStore = useAccountStore()
const keyword = ref('')

const filteredTags = computed(() => {
  if (!keyword.value) return accountStore.allTags
  const kw = keyword.value.toLowerCase()
  return accountStore.allTags.filter(t => t.name.toLowerCase().includes(kw))
})

const exactMatch = computed(() =>
  accountStore.allTags.some(t => t.name.toLowerCase() === keyword.value.toLowerCase())
)

const selectedIds = computed(() => new Set(props.selectedTags.map(t => t.id)))

const isSelected = (tag) => selectedIds.value.has(tag.id)

async function toggleTag(tag) {
  const ids = [...selectedIds.value]
  const idx = ids.indexOf(tag.id)
  if (idx >= 0) ids.splice(idx, 1)
  else ids.push(tag.id)
  await accountApi.setAccountTags(props.accountId, ids)
  emit('changed')
}

async function handleCreate() {
  const name = keyword.value.trim()
  if (!name) return
  try {
    const res = await accountApi.createTag({ name })
    if (res.code === 200) {
      await accountStore.loadTags()
      const newTag = res.data
      const ids = [...selectedIds.value, newTag.id]
      await accountApi.setAccountTags(props.accountId, ids)
      keyword.value = ''
      emit('changed')
    }
  } catch (e) {
    console.error('创建标签失败:', e)
  }
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;
.tag-popover {
  .tag-popover-search { margin-bottom: 8px; }
  .tag-popover-list { max-height: 200px; overflow-y: auto; }
  .tag-popover-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    &:hover { background: rgba($overlay-rgb, 0.06); }
    .tag-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .tag-name { flex: 1; }
    .tag-check { color: #8b5cf6; }
  }
  .tag-popover-create {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    font-size: 13px;
    color: #8b5cf6;
    cursor: pointer;
    border-radius: 6px;
    &:hover { background: rgba($brand-start, 0.1); }
  }
  .tag-popover-empty { text-align: center; padding: 12px; font-size: 13px; color: $text-muted; }
}
</style>
