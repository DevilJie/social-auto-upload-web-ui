<template>
  <div class="poi-select">
    <el-select
      v-model="selectedName"
      placeholder="搜索拍摄地点"
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
        v-for="poi in poiList"
        :key="poi.poi_id"
        :label="poi.name"
        :value="poi.name"
      >
        <div class="poi-option">
          <div class="poi-info">
            <div class="poi-name">{{ poi.name }}</div>
            <div class="poi-address">{{ poi.full_address || poi.address || '' }}</div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading } from '@element-plus/icons-vue'
import { xhsApi } from '@/api/xiaohongshu'

const props = defineProps({
  // 拍摄地点是平台级,但 POI 搜索需账号 cookie,故透传 selectedAccountId
  accountId: {
    type: [String, Number],
    default: ''
  },
  // v-model 存地点名称
  modelValue: {
    type: String,
    default: ''
  },
  // 回显用的完整对象(含 poi_id)
  data: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const poiList = ref([])
const selectedName = ref(props.modelValue)
const searchKeyword = ref('')

// 切换账号时清空
watch(() => props.accountId, () => {
  poiList.value = []
  searchKeyword.value = ''
})

// 外部值变化时同步 + 用 data 补占位项保证回显
watch(() => props.modelValue, (val) => {
  selectedName.value = val
  if (val && props.data && !poiList.value.find(p => p.name === val)) {
    poiList.value.unshift(props.data)
  }
}, { immediate: true })

async function handleSearch() {
  const kw = searchKeyword.value?.trim()
  if (!kw) {
    poiList.value = []
    return
  }
  if (!props.accountId) {
    console.warn('未选择账号，无法搜索小红书拍摄地点')
    return
  }

  console.log('[小红书POI] 触发搜索:', kw)
  loading.value = true
  try {
    const resp = await xhsApi.searchPoi(props.accountId, kw)
    if (resp.code === 200) {
      poiList.value = resp.data?.poi_list || []
      console.log('[小红书POI] 列表:', poiList.value.length, '条')
    }
  } catch (e) {
    console.error('搜索小红书拍摄地点失败:', e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  poiList.value = []
}

function handleChange(val) {
  emit('update:modelValue', val)
  const poi = poiList.value.find(p => p.name === val)
  emit('change', poi ? { ...poi, _searchKeyword: searchKeyword.value } : null)
}
</script>

<style scoped lang="scss">
.poi-select {
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
  color: #94A3B8;
  font-size: 13px;

  .is-loading {
    animation: rotating 1s linear infinite;
  }

  @keyframes rotating {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
}

.poi-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.poi-info {
  flex: 1;
  min-width: 0;
}

.poi-name {
  font-size: 14px;
  color: #F8FAFC;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.poi-address {
  font-size: 12px;
  color: #94A3B8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
