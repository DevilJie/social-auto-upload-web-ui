<template>
  <div class="mix-select">
    <el-select
      v-model="selectedMixId"
      placeholder="输入合集名称搜索"
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
        v-for="mix in mixList"
        :key="mix.mix_id"
        :label="mix.mix_name"
        :value="mix.mix_name"
      >
        <div class="mix-option">
          <img
            v-if="mix.cover_url?.url_list?.[0]"
            :src="mix.cover_url.url_list[0]"
            class="mix-cover"
            @error="onImageError"
          />
          <div v-else class="mix-cover-placeholder">
            <el-icon><Picture /></el-icon>
          </div>
          <div class="mix-info">
            <div class="mix-name">{{ mix.mix_name }}</div>
            <div class="mix-desc">{{ mix.desc || '暂无描述' }}</div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading, Picture } from '@element-plus/icons-vue'
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
const mixList = ref([])
const selectedMixId = ref(props.modelValue)
const searchKeyword = ref('')

watch(() => props.modelValue, (val) => {
  selectedMixId.value = val
})

async function handleSearch() {
  const keyword = searchKeyword.value?.trim()
  if (!keyword) {
    mixList.value = []
    return
  }

  if (!props.accountId) {
    console.warn('未选择账号，无法搜索合集')
    return
  }

  console.log('触发合集搜索:', keyword)
  loading.value = true
  try {
    const resp = await douyinImageApi.getMixList(props.accountId)
    console.log('合集搜索结果:', resp)
    if (resp.code === 200) {
      // 前端过滤合集列表
      const allMixes = resp.data?.mix_list || []
      mixList.value = allMixes.filter(m =>
        m.mix_name?.toLowerCase().includes(keyword.toLowerCase())
      )
      console.log('合集列表:', mixList.value)
    }
  } catch (e) {
    console.error('搜索合集失败:', e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  mixList.value = []
}

function handleChange(val) {
  emit('update:modelValue', val)
  const mix = mixList.value.find(m => m.mix_name === val)
  emit('change', mix || null)
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjZjVmNWY1Ii8+PHRleHQgeD0iMjAiIHk9IjI0IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPuWGm+S6rDwvdGV4dD48L3N2Zz4='
}
</script>

<style scoped lang="scss">
.mix-select {
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

.mix-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.mix-cover {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
}

.mix-cover-placeholder {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  background: #27273B;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94A3B8;
  flex-shrink: 0;
}

.mix-info {
  flex: 1;
  min-width: 0;
}

.mix-name {
  font-size: 14px;
  color: #F8FAFC;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mix-desc {
  font-size: 12px;
  color: #94A3B8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
