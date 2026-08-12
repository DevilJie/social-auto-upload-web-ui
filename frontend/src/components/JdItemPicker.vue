<template>
  <el-dialog
    v-model="visible"
    title="关联商品 - 京东本店商品"
    width="900px"
    :close-on-click-modal="false"
    @close="onClose"
  >
    <!-- 搜索框 -->
    <div class="jd-picker-search">
      <el-input
        v-model="searchKeyword"
        placeholder="请输入商品名称或 skuid 搜索本店商品"
        clearable
        @keyup.enter="onSearch"
        @clear="onSearch"
      >
        <template #append>
          <el-button @click="onSearch">搜索</el-button>
        </template>
      </el-input>
    </div>

    <!-- 已选提示 -->
    <div class="jd-picker-counter">
      已选 <strong>{{ selectedItems.length }}</strong> / 10
    </div>

    <!-- 商品列表 -->
    <div class="jd-picker-list" v-loading="loading">
      <el-empty
        v-if="!loading && currentProducts.length === 0"
        description="暂无商品"
      />
      <JdProductCard
        v-for="item in currentProducts"
        :key="item.id"
        :item="item"
        :selected="isSelected(item.id)"
        @click="onCardClick(item)"
      />
    </div>

    <!-- 分页器 -->
    <el-pagination
      v-model:current-page="currentPage"
      :page-size="10"
      :total="total"
      layout="prev, pager, next, total"
      class="jd-picker-pagination"
      @current-change="onPageChange"
    />

    <!-- 底部按钮 -->
    <template #footer>
      <el-button @click="onClose">取消</el-button>
      <el-button type="primary" @click="onConfirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { jdApi } from '@/api/jd'
import JdProductCard from './JdProductCard.vue'

const props = defineProps({
  modelValue: Boolean,
  accountId: String,
  initSelected: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

// 状态
const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
const loading = ref(false)
const searchKeyword = ref('')
const currentProducts = ref([])
const selectedItems = ref([])
const currentPage = ref(1)
const total = ref(0)

// 打开 picker
watch(
  () => props.modelValue,
  async (val) => {
    if (val) {
      // 回显已选
      selectedItems.value = (props.initSelected || []).map(normalizeItem)
      await openPanel()
    }
  }
)

function normalizeItem(item) {
  // 兼容字符串数组(旧格式)与对象数组(新格式)
  if (typeof item === 'string') {
    return { title: item, image: '', id: '', trace: { keyword: '', page: 1 } }
  }
  return {
    title: item.title || '',
    image: item.image || '',
    id: item.id || '',
    trace: item.trace || { keyword: '', page: 1 },
  }
}

async function openPanel() {
  loading.value = true
  try {
    const resp = await jdApi.pickerOpen(props.accountId)
    if (resp.ok) {
      currentProducts.value = resp.products || []
      total.value = currentProducts.value.length > 0 ? 100 : 0
    } else {
      throw new Error(resp.error || '打开 picker 失败')
    }
  } catch (e) {
    ElMessage.error(`打开失败: ${e.message}`)
    visible.value = false
  } finally {
    loading.value = false
  }
}

async function onSearch() {
  currentPage.value = 1
  loading.value = true
  try {
    const resp = await jdApi.pickerSearch(
      props.accountId,
      searchKeyword.value,
      1
    )
    if (resp.ok) {
      currentProducts.value = resp.products || []
      total.value = Math.max(currentProducts.value.length * 10, total.value)
    }
  } finally {
    loading.value = false
  }
}

async function onPageChange(page) {
  loading.value = true
  try {
    const resp = await jdApi.pickerGoPage(props.accountId, page)
    if (resp.ok) {
      currentProducts.value = resp.products || []
    }
  } finally {
    loading.value = false
  }
}

function isSelected(id) {
  return selectedItems.value.some((s) => s.id === id)
}

function onCardClick(item) {
  const idx = selectedItems.value.findIndex((s) => s.id === item.id)
  if (idx >= 0) {
    selectedItems.value.splice(idx, 1)
  } else {
    if (selectedItems.value.length >= 10) {
      ElMessage.warning('最多选择 10 个商品')
      return
    }
    // 关键:打包 trace 快照
    selectedItems.value.push({
      title: item.title,
      image: item.image,
      id: item.id,
      trace: {
        keyword: searchKeyword.value,
        page: currentPage.value,
      },
    })
  }
}

function onConfirm() {
  emit('confirm', selectedItems.value)
  visible.value = false
}

function onClose() {
  // 释放 picker session
  if (props.accountId) {
    jdApi.pickerClose(props.accountId).catch(() => {})
  }
  visible.value = false
}
</script>

<style scoped>
.jd-picker-search {
  margin-bottom: 12px;
}
.jd-picker-counter {
  margin-bottom: 12px;
  font-size: 14px;
  color: #666;
}
.jd-picker-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  min-height: 300px;
  max-height: 500px;
  overflow-y: auto;
  padding: 8px;
  border: 1px solid #eee;
  border-radius: 4px;
}
.jd-picker-pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>