<template>
  <div class="hotspot-select">
    <el-select
      v-model="selectedHotspot"
      placeholder="输入热点词搜索"
      clearable
      filterable
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
        v-for="item in hotspotList"
        :key="item.sentence_id"
        :label="item.word"
        :value="item.word"
      >
        <div class="hotspot-option">
          <img
            v-if="item.word_cover?.url_list?.[0]"
            :src="item.word_cover.url_list[0]"
            class="hotspot-cover"
            @error="onImageError"
          />
          <div v-else class="hotspot-cover-placeholder">
            <el-icon><TrendCharts /></el-icon>
          </div>
          <div class="hotspot-info">
            <div class="hotspot-word">{{ item.word }}</div>
            <div class="hotspot-meta">
              <span class="hotspot-hot">热度：{{ formatHotValue(item.hot_value) }}</span>
            </div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading, TrendCharts } from '@element-plus/icons-vue'
import { douyinImageApi } from '@/api/douyinImage'

const props = defineProps({
  accountId: {
    type: [String, Number],
    default: ''
  },
  modelValue: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const hotspotList = ref([])
const selectedHotspot = ref(props.modelValue)
const searchKeyword = ref('')

watch(() => props.modelValue, (val) => {
  selectedHotspot.value = val
})

async function handleSearch() {
  const keyword = searchKeyword.value?.trim()
  if (!keyword) {
    hotspotList.value = []
    return
  }

  console.log('触发热点搜索:', keyword)
  loading.value = true
  try {
    const resp = await douyinImageApi.searchHotspot(props.accountId || '', keyword)
    console.log('热点搜索结果:', resp)
    if (resp.code === 200) {
      hotspotList.value = resp.data?.sentences || []
      console.log('热点列表:', hotspotList.value)
    }
  } catch (e) {
    console.error('搜索热点失败:', e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  hotspotList.value = []
}

function handleChange(val) {
  emit('update:modelValue', val)
  const hotspot = hotspotList.value.find(h => h.word === val)
  emit('change', hotspot || null)
}

function formatHotValue(value) {
  if (!value) return '0'
  if (value >= 10000) {
    return (value / 10000).toFixed(1) + '万'
  }
  return value.toString()
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjZjVmNWY1Ii8+PHRleHQgeD0iMjAiIHk9IjI0IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPvCflKk8L3RleHQ+PC9zdmc+'
}
</script>

<style scoped lang="scss">
.hotspot-select {
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
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }
}

.hotspot-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.hotspot-cover {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
}

.hotspot-cover-placeholder {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  background: #27273B;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #EF4444;
  flex-shrink: 0;
}

.hotspot-info {
  flex: 1;
  min-width: 0;
}

.hotspot-word {
  font-size: 14px;
  color: #F8FAFC;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hotspot-meta {
  font-size: 12px;
  color: #94A3B8;
}

.hotspot-hot {
  color: #EF4444;
}
</style>
