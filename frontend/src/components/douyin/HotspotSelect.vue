<template>
  <div class="hotspot-select">
    <el-select
      v-model="selectedHotspot"
      placeholder="输入热点词搜索"
      clearable
      filterable
      remote
      :remote-method="searchHotspot"
      :loading="loading"
      @change="handleChange"
      style="width: 100%"
    >
      <el-option
        v-for="item in hotspotList"
        :key="item.sentence_id"
        :label="item.word"
        :value="item.sentence_id"
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
import { TrendCharts } from '@element-plus/icons-vue'
import { douyinImageApi } from '@/api/douyinImage'

const props = defineProps({
  accountId: {
    type: [String, Number],
    required: true
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

watch(() => props.modelValue, (val) => {
  selectedHotspot.value = val
})

let searchTimer = null

async function searchHotspot(keyword) {
  if (!keyword || !props.accountId) return

  // 防抖
  if (searchTimer) clearTimeout(searchTimer)

  searchTimer = setTimeout(async () => {
    loading.value = true
    try {
      const resp = await douyinImageApi.searchHotspot(props.accountId, keyword)
      if (resp.code === 200) {
        hotspotList.value = resp.data?.sentences || []
      }
    } catch (e) {
      console.error('搜索热点失败:', e)
    } finally {
      loading.value = false
    }
  }, 300)
}

function handleChange(val) {
  emit('update:modelValue', val)
  const hotspot = hotspotList.value.find(h => h.sentence_id === val)
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

.hotspot-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
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
  background: #ffebee;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f44336;
  flex-shrink: 0;
}

.hotspot-info {
  flex: 1;
  min-width: 0;
}

.hotspot-word {
  font-size: 14px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hotspot-meta {
  font-size: 12px;
  color: #999;
}

.hotspot-hot {
  color: #ff4444;
}
</style>
