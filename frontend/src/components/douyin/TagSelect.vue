<template>
  <div class="tag-select">
    <div class="tag-row">
      <!-- 标签类型选择 -->
      <el-select
        v-model="selectedType"
        placeholder="选择标签类型"
        class="tag-type-select"
        @change="handleTypeChange"
      >
        <el-option label="位置" value="poi" />
        <el-option label="小程序" value="miniapp" />
        <el-option label="游戏手柄" value="game" />
        <el-option label="标记万物" value="mark" />
      </el-select>

      <!-- 搜索和选择区域 -->
      <el-select
        v-if="selectedType"
        v-model="selectedTagId"
        :placeholder="getPlaceholder()"
        clearable
        filterable
        no-data-text=" "
        class="tag-search-select"
        @change="handleChange"
      >
        <template #header>
          <div class="search-input-wrapper">
            <el-input
              v-model="searchKeyword"
              :placeholder="getSearchPlaceholder()"
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
          v-for="tag in tagList"
          :key="tag.id"
          :label="tag.name"
          :value="tag.id"
        >
          <div class="tag-option">
            <img
              v-if="tag.icon"
              :src="tag.icon"
              class="tag-icon"
              @error="onImageError"
            />
            <div v-else class="tag-icon-placeholder">
              <el-icon><component :is="getTagIcon()" /></el-icon>
            </div>
            <div class="tag-info">
              <div class="tag-name">{{ tag.name }}</div>
              <div class="tag-meta" v-if="tag.desc">{{ tag.desc }}</div>
            </div>
          </div>
        </el-option>
      </el-select>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading, Location, Connection, Menu, Goods } from '@element-plus/icons-vue'
import { douyinImageApi } from '@/api/douyinImage'

const props = defineProps({
  accountId: {
    type: [String, Number],
    default: ''
  },
  modelValue: {
    type: Object,
    default: () => null
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const selectedType = ref('')
const loading = ref(false)
const tagList = ref([])
const selectedTagId = ref('')
const searchKeyword = ref('')

watch(() => props.modelValue, (val) => {
  console.log('TagSelect watch modelValue:', val)
  if (val) {
    selectedType.value = val.type || ''
    selectedTagId.value = val.id || ''
    // 如果有值但 tagList 中没有对应的选项，添加一个占位项
    if (val.id && !tagList.value.find(t => t.id === val.id)) {
      console.log('Adding tag to tagList:', val)
      tagList.value.unshift({
        id: val.id,
        name: val.name,
        desc: val.desc || '',
        icon: val.icon || '',
        type: val.type,
        data: val.data || val
      })
    }
  } else {
    selectedTagId.value = ''
  }
}, { immediate: true, deep: true })

function handleTypeChange() {
  // 切换类型时清空搜索结果和已选标签
  tagList.value = []
  searchKeyword.value = ''
  selectedTagId.value = ''
  emit('update:modelValue', null)
  emit('change', null)
}

function getPlaceholder() {
  const placeholders = {
    poi: '选择位置',
    miniapp: '选择小程序',
    game: '选择游戏',
    mark: '选择商品'
  }
  return placeholders[selectedType.value] || '选择标签'
}

function getSearchPlaceholder() {
  const placeholders = {
    poi: '输入地点名称搜索',
    miniapp: '粘贴抖音小程序链接',
    game: '输入游戏名称搜索',
    mark: '输入商品名称搜索'
  }
  return placeholders[selectedType.value] || '输入关键词后按回车搜索'
}

function getTagIcon() {
  const icons = {
    poi: Location,
    miniapp: Connection,
    game: Menu,
    mark: Goods
  }
  return icons[selectedType.value] || Location
}

async function handleSearch() {
  const keyword = searchKeyword.value?.trim()
  if (!keyword) {
    tagList.value = []
    return
  }

  console.log(`触发${selectedType.value}标签搜索:`, keyword)
  loading.value = true
  try {
    let resp
    switch (selectedType.value) {
      case 'poi':
        resp = await douyinImageApi.searchPoi(props.accountId || '', keyword)
        console.log('位置搜索结果:', resp)
        if (resp.code === 200) {
          tagList.value = (resp.data?.poi_list || []).map(poi => ({
            id: poi.poi_id,
            name: poi.poi_name,
            desc: poi.simple_address_str,
            icon: poi.cover_item?.url_list?.[0],
            type: 'poi',
            data: poi
          }))
        }
        break
      case 'miniapp':
        resp = await douyinImageApi.searchMiniapp(props.accountId || '', keyword)
        console.log('小程序搜索结果:', resp)
        if (resp.code === 200) {
          tagList.value = (resp.data?.anchor_list || []).map(anchor => ({
            id: anchor.id,
            name: anchor.name,
            desc: anchor.summary,
            icon: anchor.poster?.url_list?.[0],
            type: 'miniapp',
            data: anchor
          }))
        }
        break
      case 'game':
        resp = await douyinImageApi.searchGame(props.accountId || '', keyword)
        console.log('游戏搜索结果:', resp)
        if (resp.code === 200) {
          // 注意：游戏数据在 resp.data.data.mount_games 中
          const gameData = resp.data?.data || resp.data
          tagList.value = (gameData?.mount_games || []).map(game => ({
            id: game.game_info?.unified_game_id,
            name: game.game_info?.name,
            desc: game.game_info?.tag_names?.join('、'),
            icon: game.game_info?.icon,
            type: 'game',
            data: game
          }))
        }
        break
      case 'mark':
        resp = await douyinImageApi.searchMarkSpu(props.accountId || '', keyword)
        console.log('标记万物搜索结果:', resp)
        if (resp.code === 200) {
          // 注意：标记万物数据在 resp.data.data.spu_list 中
          const markData = resp.data?.data || resp.data
          tagList.value = (markData?.spu_list || []).map(spu => ({
            id: spu.spu_id,
            name: spu.title,
            desc: spu.front_category?.front_category_name,
            icon: spu.cover,
            type: 'mark',
            data: spu
          }))
        }
        break
    }
    console.log(`${selectedType.value}标签搜索结果:`, tagList.value)
  } catch (e) {
    console.error('搜索标签失败:', e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  tagList.value = []
}

function handleChange(val) {
  if (val) {
    const tag = tagList.value.find(t => t.id === val)
    emit('update:modelValue', tag)
    emit('change', tag ? { ...tag, _searchKeyword: searchKeyword.value } : null)
  } else {
    emit('update:modelValue', null)
    emit('change', null)
  }
}

function onImageError(e) {
  e.target.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNDAiIGhlaWdodD0iNDAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjQwIiBoZWlnaHQ9IjQwIiBmaWxsPSIjZjVmNWY1Ii8+PHRleHQgeD0iMjAiIHk9IjI0IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM5OTkiIHRleHQtYW5jaG9yPSJtaWRkbGUiPiM8L3RleHQ+PC9zdmc+'
}
</script>

<style scoped lang="scss">
.tag-select {
  width: 100%;
}

.tag-row {
  display: flex;
  gap: 8px;
}

.tag-type-select {
  width: 120px;
  flex-shrink: 0;
}

.tag-search-select {
  flex: 1;
  min-width: 0;
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
  color: #94a3b8;
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

.tag-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.tag-icon {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
}

.tag-icon-placeholder {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  background: #27273b;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  flex-shrink: 0;
}

.tag-info {
  flex: 1;
  min-width: 0;
}

.tag-name {
  font-size: 14px;
  color: #f8fafc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-meta {
  font-size: 12px;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 4px;
}
</style>
