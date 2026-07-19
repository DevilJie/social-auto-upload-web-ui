<template>
  <div class="position-select">
    <el-select
      v-model="selectedName"
      placeholder="输入地理位置"
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
            placeholder="输入地点后按回车搜索"
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
        v-for="pos in positionList"
        :key="pos.name + pos.address"
        :label="pos.name"
        :value="pos.name"
      >
        <div class="position-option">
          <div class="position-info">
            <div class="position-name">{{ pos.name }}</div>
            <div class="position-address">{{ pos.address || '' }}</div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading } from '@element-plus/icons-vue'
import { vivoApi } from '@/api/vivo'

const props = defineProps({
  // 位置是平台级,但搜索需账号 cookie,故透传 selectedAccountId
  accountId: {
    type: [String, Number],
    default: ''
  },
  // v-model 存位置名称
  modelValue: {
    type: String,
    default: ''
  },
  // 回显用的完整对象(含 address)
  data: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const positionList = ref([])
const selectedName = ref(props.modelValue)
const searchKeyword = ref('')

// 切换账号时清空
watch(() => props.accountId, () => {
  positionList.value = []
  searchKeyword.value = ''
})

// 外部值变化时同步 + 用 data 补占位项保证回显
watch(() => props.modelValue, (val) => {
  selectedName.value = val
  if (val && props.data && !positionList.value.find(p => p.name === val)) {
    positionList.value.unshift(props.data)
  }
}, { immediate: true })

async function handleSearch() {
  const kw = searchKeyword.value?.trim()
  if (!kw) {
    positionList.value = []
    return
  }
  if (!props.accountId) {
    console.warn('未选择账号，无法搜索 VIVO 位置')
    return
  }

  console.log('[VIVO位置] 触发搜索:', kw)
  loading.value = true
  try {
    const resp = await vivoApi.searchPosition(props.accountId, kw)
    if (resp.code === 200) {
      positionList.value = resp.data?.position_list || []
      console.log('[VIVO位置] 列表:', positionList.value.length, '条')
    }
  } catch (e) {
    console.error('搜索 VIVO 位置失败:', e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  positionList.value = []
}

function handleChange(val) {
  emit('update:modelValue', val)
  const pos = positionList.value.find(p => p.name === val)
  emit('change', pos ? { ...pos, _searchKeyword: searchKeyword.value } : null)
}
</script>

<style scoped lang="scss">
@use '@/styles/variables.scss' as *;

.position-select {
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

.position-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.position-info {
  flex: 1;
  min-width: 0;
}

.position-name {
  font-size: 14px;
  color: $popper-text;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.position-address {
  font-size: 12px;
  color: $text-secondary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
