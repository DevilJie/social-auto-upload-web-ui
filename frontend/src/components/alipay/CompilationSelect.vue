<template>
  <div class="compilation-select">
    <el-select
      v-model="selectedCompilationId"
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
        v-for="comp in compilationList"
        :key="comp.compilationId"
        :label="comp.title"
        :value="comp.title"
      >
        <div class="compilation-option">
          <img
            v-if="comp.coverUrl"
            :src="comp.coverUrl"
            class="compilation-cover"
            @error="onImageError"
          />
          <div v-else class="compilation-cover-placeholder">
            <el-icon><Picture /></el-icon>
          </div>
          <div class="compilation-info">
            <div class="compilation-title">{{ comp.title }}</div>
            <div class="compilation-meta">
              <span v-if="comp.category" class="compilation-category">{{ comp.category }}</span>
              <span class="compilation-count">{{ comp.total || 0 }} 个内容</span>
            </div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading, Picture } from '@element-plus/icons-vue'
import { alipayApi } from '@/api/alipay'
import { toutiaoApi } from '@/api/toutiao'

const props = defineProps({
  accountId: {
    type: [String, Number],
    default: ''
  },
  modelValue: {
    type: String,
    default: ''
  },
  data: {
    type: Object,
    default: null
  },
  platform: {
    type: String,
    default: 'alipay', // 'alipay' | 'toutiao'
    validator: (value) => ['alipay', 'toutiao'].includes(value)
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const compilationList = ref([])
const selectedCompilationId = ref(props.modelValue || '')
const searchKeyword = ref('')

// 根据平台获取对应的 API
function getApi() {
  if (props.platform === 'toutiao') {
    return toutiaoApi
  }
  return alipayApi
}

// 获取平台显示名称
function getPlatformName() {
  return props.platform === 'toutiao' ? '今日头条' : '支付宝'
}

// 切换账号时清空(不同账号合集不同)
watch(() => props.accountId, () => {
  compilationList.value = []
  searchKeyword.value = ''
})

// 外部值变化时同步;若列表里没有,用 data 补一个占位项保证回显
// 注意:v-model 存的是合集 title(名字),不是 compilationId
watch(() => props.modelValue, (val) => {
  selectedCompilationId.value = val || ''
  if (val && !compilationList.value.find(c => c.title === val)) {
    if (props.data && props.data.title === val) {
      compilationList.value.unshift(props.data)
    } else {
      compilationList.value.unshift({
        compilationId: '',
        title: val,
        coverUrl: '',
        category: '',
        total: 0,
      })
    }
  }
}, { immediate: true })

async function handleSearch() {
  const keyword = searchKeyword.value?.trim()
  if (!keyword) {
    compilationList.value = []
    return
  }

  if (!props.accountId) {
    console.warn(`[${getPlatformName()}合集] 未选择账号,无法搜索`)
    return
  }

  console.log(`[${getPlatformName()}合集] 触发搜索:`, keyword)
  loading.value = true
  try {
    const api = getApi()
    const resp = await api.searchCompilation(props.accountId, keyword)
    console.log(`[${getPlatformName()}合集] 搜索结果:`, resp)
    if (resp.code === 200) {
      compilationList.value = resp.data?.list || []
      console.log(`[${getPlatformName()}合集] 列表:`, compilationList.value)
    }
  } catch (e) {
    console.error(`[${getPlatformName()}合集] 搜索失败:`, e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  compilationList.value = []
}

function handleChange(val) {
  emit('update:modelValue', val || '')
  const comp = compilationList.value.find(c => c.title === val)
  emit('change', comp ? { ...comp, _searchKeyword: searchKeyword.value } : null)
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjZjVmNWY1Ii8+PHRleHQgeD0iMjAiIHk9IjI0IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPuWGm+S6rDwvdGV4dD48L3N2Zz4='
}
</script>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.compilation-select {
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

.compilation-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.compilation-cover {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
}

.compilation-cover-placeholder {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  background: $popper-hover;
  display: flex;
  align-items: center;
  justify-content: center;
  color: $text-secondary;
  flex-shrink: 0;
}

.compilation-info {
  flex: 1;
  min-width: 0;
}

.compilation-title {
  font-size: 14px;
  color: $text-primary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compilation-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: $text-muted;
}

.compilation-category {
  padding: 0 6px;
  background: rgba($info-color, 0.1);
  color: #1677FF;
  border-radius: 3px;
}
</style>
