<template>
  <RemoteSearchSelect
    v-model="modelValue"
    :data="data"
    :fetcher="fetchPoi"
    :field-map="poiFieldMap"
    search-mode="backend"
    empty-behavior="block"
    placeholder="搜索拍摄地点"
    search-placeholder="输入地点关键词,按回车搜索"
    @change="$emit('change', $event)"
  />
</template>

<script setup>
import { xhsApi } from '@/api/xiaohongshu'
import RemoteSearchSelect from '@/components/common/RemoteSearchSelect.vue'

const props = defineProps({
  // POI 搜索需账号 cookie,透传 selectedAccountId
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

defineEmits(['update:modelValue', 'change'])

// 走全局公共组件 RemoteSearchSelect:后端搜索模式(必须传 keyword,空关键词不请求)。
// 与视频号位置 fetchChannelsLocations 保持一致风格。
async function fetchPoi(keyword) {
  const resp = await xhsApi.searchPoi(props.accountId, keyword || '')
  return { list: resp.data?.poi_list || [] }
}

// 字段映射:name 作 label,full_address || address 作 desc 副文案,poi_id 作 key
const poiFieldMap = {
  key: 'poi_id',
  label: 'name',
  desc: (item) => item.full_address || item.address || ''
}
</script>