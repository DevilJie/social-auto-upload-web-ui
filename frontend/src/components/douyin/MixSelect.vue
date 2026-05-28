<template>
  <div class="mix-select">
    <el-select
      v-model="selectedMixId"
      placeholder="不选择合集"
      clearable
      filterable
      :loading="loading"
      @change="handleChange"
      style="width: 100%"
    >
      <el-option
        v-for="mix in mixList"
        :key="mix.mix_id"
        :label="mix.mix_name"
        :value="mix.mix_id"
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
import { ref, onMounted, watch } from 'vue'
import { Picture } from '@element-plus/icons-vue'
import { douyinImageApi } from '@/api/douyinImage'

const props = defineProps({
  accountId: {
    type: [String, Number],
    required: true
  },
  modelValue: {
    type: [String, Number],
    default: ''
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const mixList = ref([])
const selectedMixId = ref(props.modelValue)

watch(() => props.modelValue, (val) => {
  selectedMixId.value = val
})

onMounted(() => {
  loadMixList()
})

async function loadMixList() {
  if (!props.accountId) return

  loading.value = true
  try {
    const resp = await douyinImageApi.getMixList(props.accountId)
    if (resp.code === 200) {
      mixList.value = resp.data?.mix_list || []
    }
  } catch (e) {
    console.error('加载合集列表失败:', e)
  } finally {
    loading.value = false
  }
}

function handleChange(val) {
  emit('update:modelValue', val)
  const mix = mixList.value.find(m => m.mix_id === val)
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

.mix-option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
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
  background: #f5f5f5;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #999;
  flex-shrink: 0;
}

.mix-info {
  flex: 1;
  min-width: 0;
}

.mix-name {
  font-size: 14px;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mix-desc {
  font-size: 12px;
  color: #999;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
