<template>
  <div class="location-select">
    <el-select
      v-model="selectedName"
      placeholder="输入位置关键词搜索"
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
        v-for="loc in locationList"
        :key="loc.name"
        :label="loc.name"
        :value="loc.name"
      >
        <div class="location-option">
          <div class="location-info">
            <div class="location-name">{{ loc.name }}</div>
            <div v-if="loc.desc" class="location-desc">{{ loc.desc }}</div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading } from '@element-plus/icons-vue'
import { channelsApi } from '@/api/channels'

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
const locationList = ref([])
const selectedName = ref(props.modelValue)
const searchKeyword = ref('')

// 切账号:清空列表 + 关键字
watch(() => props.accountId, () => {
  locationList.value = []
  searchKeyword.value = ''
})

// 外部 modelValue 变化(草稿加载/账号切换):回填 + 注入缓存 data 让 label 能渲染
watch(() => props.modelValue, (val) => {
  selectedName.value = val
  if (val && props.data && !locationList.value.find(c => c.name === val)) {
    locationList.value.unshift(props.data)
  }
}, { immediate: true })

async function handleSearch() {
  if (!props.accountId) {
    console.warn('未选择账号，无法搜索视频号位置')
    return
  }
  const kw = searchKeyword.value?.trim()
  if (!kw) {
    console.warn('请输入位置关键词后再搜索')
    return
  }

  console.log('[视频号位置] 触发搜索:', kw)
  loading.value = true
  try {
    // 与合集不同:位置搜索必须把关键字传到后端,后端用 CloakBrowser 真实搜索
    const resp = await channelsApi.getLocations(props.accountId, kw)
    if (resp.code === 200) {
      locationList.value = resp.data?.list || []
      console.log('[视频号位置] 列表:', locationList.value.length, '条')
    }
  } catch (e) {
    console.error('搜索视频号位置失败:', e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  locationList.value = []
}

function handleChange(val) {
  emit('update:modelValue', val)
  const loc = locationList.value.find(c => c.name === val)
  emit('change', loc ? { ...loc, _searchKeyword: searchKeyword.value } : null)
}
</script>

<style scoped lang="scss">
.location-select { width: 100%; }
.search-input-wrapper { padding: 8px 12px; }
.loading-indicator {
  display: flex; align-items: center; justify-content: center;
  gap: 8px; padding: 8px 12px; color: #94A3B8; font-size: 13px;
  .is-loading { animation: rotating 1s linear infinite; }
  @keyframes rotating { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
}
.location-option { display: flex; align-items: center; gap: 12px; padding: 8px 0; }
.location-info { flex: 1; min-width: 0; }
.location-name {
  font-size: 14px; color: #F8FAFC; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.location-desc {
  font-size: 12px; color: #94A3B8; margin-top: 2px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
</style>
