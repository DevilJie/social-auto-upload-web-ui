<template>
  <div class="collection-select">
    <el-select
      v-model="selectedName"
      placeholder="输入合集名称搜索"
      clearable
      filterable
      no-data-text=" "
      @change="handleChange"
      style="width: 100%"
    >
      <template #header>
        <div class="search-input-wrapper">
          <el-input
            v-model="searchKeyword"
            placeholder="输入关键词后按回车搜索"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleClear"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
        <div v-if="loading" class="loading-indicator">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>加载中...</span>
        </div>
      </template>
      <el-option
        v-for="col in collectionList"
        :key="col.name"
        :label="col.name"
        :value="col.name"
      >
        <div class="collection-option">
          <div class="collection-info">
            <div class="collection-name">{{ col.name }}</div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading } from '@element-plus/icons-vue'
import { biliApi } from '@/api/bilibili'

const props = defineProps({
  accountId: {
    type: [String, Number],
    required: true
  },
  modelValue: {
    type: String,
    default: ''
  },
  data: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const collectionList = ref([])
const selectedName = ref(props.modelValue)
const searchKeyword = ref('')
const allCollections = ref([])

// 切换账号时清空
watch(() => props.accountId, () => {
  collectionList.value = []
  allCollections.value = []
  searchKeyword.value = ''
})

// 外部值变化时同步 + 用 data 补占位项保证回显
watch(() => props.modelValue, (val) => {
  selectedName.value = val
  if (val && props.data && !collectionList.value.find(c => c.name === val)) {
    collectionList.value.unshift(props.data)
  }
}, { immediate: true })

async function handleSearch() {
  if (!props.accountId) {
    console.warn('未选择账号，无法搜索 B 站合集')
    return
  }

  console.log('[B站合集] 触发搜索:', searchKeyword.value || '(全部)')
  loading.value = true
  try {
    const resp = await biliApi.getCollections(props.accountId)
    if (resp.code === 200) {
      allCollections.value = resp.data?.list || []
      const kw = searchKeyword.value?.trim().toLowerCase()
      collectionList.value = kw
        ? allCollections.value.filter(c =>
            c.name?.toLowerCase().includes(kw)
          )
        : allCollections.value
      console.log('[B站合集] 列表:', collectionList.value.length, '条')
    }
  } catch (e) {
    console.error('搜索 B 站合集失败:', e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  collectionList.value = []
}

function handleChange(val) {
  emit('update:modelValue', val)
  const col = collectionList.value.find(c => c.name === val)
  emit('change', col ? { ...col, _searchKeyword: searchKeyword.value } : null)
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.collection-select {
  width: 100%;
}

.search-input-wrapper {
  padding: 8px 12px;
}

.loading-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 12px;
  color: $text-secondary;
  font-size: 13px;

  .is-loading {
    animation: rotating 1s linear infinite;
  }

  @keyframes rotating {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
}

.collection-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.collection-info {
  flex: 1;
  min-width: 0;
}

.collection-name {
  font-size: 14px;
  color: $popper-text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
