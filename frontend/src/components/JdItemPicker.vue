<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v) => emit('update:modelValue', v)"
    width="1100px"
    top="5vh"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :before-close="onClose"
    class="jd-picker-dialog"
  >
    <template #header>
      <div class="jd-picker-header">
        <h3>京东 · 关联商品</h3>
        <span class="jd-picker-tip">本店商品,最多选择 10 个</span>
      </div>
    </template>

    <!-- 搜索框 -->
    <div class="jd-picker-search">
      <el-input
        v-model="searchKeyword"
        placeholder="请输入商品名称或 skuid 搜索本店商品"
        clearable
        @keyup.enter="onSearch"
        @clear="onSearch"
      >
        <template #suffix>
          <el-icon class="cursor-pointer" @click="onSearch"><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 商品网格 -->
    <div
      class="jd-picker-grid"
      v-loading="loading"
      element-loading-text="加载中..."
    >
      <el-empty
        v-if="!loading && currentProducts.length === 0"
        description="暂无商品"
      />
      <div
        v-for="item in currentProducts"
        :key="item.id || item.title"
        :class="['jd-card', { selected: isSelected(item.id) }]"
        @click="onCardClick(item)"
      >
        <div class="jd-card-img">
          <img
            v-if="item.image"
            :src="item.image"
            :alt="item.title"
            loading="lazy"
            referrerpolicy="no-referrer"
          />
          <div v-else class="jd-card-img-placeholder">
            {{ (item.title || '?').toString().slice(0, 1) }}
          </div>
          <span class="jd-card-check">
            <el-icon v-if="isSelected(item.id)"><Check /></el-icon>
          </span>
        </div>
        <div class="jd-card-info">
          <div class="jd-card-title" :title="item.title">{{ item.title }}</div>
          <div v-if="item.price" class="jd-card-price">{{ item.price }}</div>
          <div v-if="item.shop_name" class="jd-card-shop">
            <el-icon><Shop /></el-icon>
            <span>{{ item.shop_name }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页器 -->
    <div class="jd-picker-pagination">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="onPageChange"
      />
    </div>

    <!-- 底部 -->
    <template #footer>
      <div class="jd-picker-footer">
        <div class="jd-picker-selected">
          <span>已选 <b>{{ selectedItems.length }}</b>/10</span>
          <div class="jd-picker-chips">
            <el-tag
              v-for="(item, i) in selectedItems"
              :key="(item.id || item.title) + '_' + i"
              size="small"
              closable
              @close="removeSelected(item)"
            >{{ item.title }}</el-tag>
          </div>
        </div>
        <div class="jd-picker-actions">
          <el-button @click="onClose">取消</el-button>
          <el-button
            type="primary"
            :disabled="selectedItems.length === 0"
            @click="onConfirm"
          >确定</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Check, Shop } from '@element-plus/icons-vue'
import { jdApi } from '@/api/jd'

const props = defineProps({
  modelValue: Boolean,
  accountId: String,
  initSelected: { type: Array, default: () => [] },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const MAX_SELECTED = 10
const pageSize = 10

const loading = ref(false)
const searchKeyword = ref('')
const currentProducts = ref([])
const selectedItems = ref([])
const currentPage = ref(1)
const total = ref(0)

// 乱序保护:用户快速翻页/搜多次时,只渲染最后一次请求的结果。
// 每次发请求前 ++pendingOpId,await 后比对,不一致就丢弃旧响应。
let pendingOpId = 0

watch(
  () => props.modelValue,
  async (val) => {
    if (val) {
      selectedItems.value = (props.initSelected || []).map(normalizeItem)
      searchKeyword.value = ''
      currentPage.value = 1
      await openPanel()
    }
  }
)

function normalizeItem(item) {
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
  if (!props.accountId) {
    ElMessage.warning('请先选择账号')
    onClose()
    return
  }
  loading.value = true
  try {
    // 后端响应 {code:200, data:{products, total, sessionId}} 已被 utils/request.js
    // 拦截器整体放行,res 即整个响应体,res.data 才是业务数据。
    const res = await jdApi.pickerOpen(props.accountId)
    currentProducts.value = res.data?.products || []
    total.value = res.data?.total || 0
  } catch (e) {
    // 拦截器已弹错误提示;picker 打不开就没法继续,关窗
    emit('update:modelValue', false)
  } finally {
    loading.value = false
  }
}

async function onSearch() {
  const opId = ++pendingOpId
  currentPage.value = 1
  loading.value = true
  try {
    const res = await jdApi.pickerSearch(props.accountId, searchKeyword.value)
    if (opId !== pendingOpId) return  // 旧请求,丢弃(用户又点了下一次)
    currentProducts.value = res.data?.products || []
    total.value = res.data?.total || currentProducts.value.length
  } catch (e) {
    // 拦截器已弹错误提示;弹窗保留,用户可重试
  } finally {
    if (opId === pendingOpId) loading.value = false
  }
}

async function onPageChange(page) {
  const opId = ++pendingOpId
  loading.value = true
  try {
    const res = await jdApi.pickerGoPage(props.accountId, page)
    if (opId !== pendingOpId) return
    currentProducts.value = res.data?.products || []
    total.value = res.data?.total || currentProducts.value.length
  } catch (e) {
    // 拦截器已弹错误提示;弹窗保留
  } finally {
    if (opId === pendingOpId) loading.value = false
  }
}

function isSelected(id) {
  if (!id) return false
  return selectedItems.value.some((s) => s.id === id)
}

function onCardClick(item) {
  const idx = selectedItems.value.findIndex((s) => s.id === item.id)
  if (idx >= 0) {
    selectedItems.value.splice(idx, 1)
  } else {
    if (selectedItems.value.length >= MAX_SELECTED) {
      ElMessage.warning(`最多选择 ${MAX_SELECTED} 个商品`)
      return
    }
    // 打包 trace 快照:keyword + page,发布时按 trace 重现
    selectedItems.value.push({
      title: item.title,
      image: item.image,
      id: item.id,
      trace: {
        keyword: searchKeyword.value || '',
        page: currentPage.value,
      },
    })
  }
}

function removeSelected(item) {
  selectedItems.value = selectedItems.value.filter((s) => s.id !== item.id)
}

async function releaseSession() {
  // 等后端真正关闭浏览器再继续 —— 否则会"弹窗关了但浏览器进程还在"。
  // 之前 onClose 是 fire-and-forget,JD 后端 pool.release 又因 Flask 线程无 event loop
  // 而失败;onConfirm 之前根本没调 pickerClose,导致确定后再次打开报"已有 picker 在运行"。
  // 任何关闭弹窗的路径(确认/取消/X)都必须经过这里。
  if (!props.accountId) return
  try {
    await jdApi.pickerClose(props.accountId)
  } catch (e) {
    // 关闭失败不阻塞弹窗关闭(后端会因下次 open 时 pool.has 检查兜底)
  }
}

async function onConfirm() {
  emit('confirm', selectedItems.value)
  await releaseSession()
  emit('update:modelValue', false)
}

async function onClose() {
  await releaseSession()
  emit('update:modelValue', false)
}
</script>

<style scoped lang="scss">
.jd-picker-dialog {
  :deep(.el-dialog__body) {
    padding: 0 20px;
  }
}

.jd-picker-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  h3 {
    margin: 0;
    font-size: 18px;
    color: #303133;
  }
  .jd-picker-tip {
    font-size: 12px;
    color: #999;
  }
}

.jd-picker-search {
  margin-bottom: 16px;
}

.jd-picker-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  min-height: 380px;
  max-height: 540px;
  overflow-y: auto;
  padding: 4px;

  // 空状态:跨所有列居中显示(el-empty 默认只占一个 grid cell,会被挤到第一格)
  :deep(.el-empty) {
    grid-column: 1 / -1;
    align-self: center;
    justify-self: center;
    padding: 60px 0;
  }

  // loading 遮罩:亮色模式下用淡白半透明 + 京东红 spinner,默认灰色太重
  :deep(.el-loading-mask) {
    background-color: rgba(255, 255, 255, 0.7);
    backdrop-filter: blur(2px);
    border-radius: 6px;
  }
  :deep(.el-loading-spinner) {
    .circular {
      width: 32px;
      height: 32px;
      .path {
        stroke: #e1251b;  // 京东红
        stroke-width: 4;
      }
    }
    .el-loading-text {
      color: #909399;
      font-size: 13px;
      margin: 8px 0 0;
    }
  }

  .jd-card {
    position: relative;
    border: 1px solid #ebeef5;
    border-radius: 6px;
    overflow: hidden;
    cursor: pointer;
    background: #fff;
    transition: all 0.15s;

    &:hover {
      border-color: #e1251b;
      box-shadow: 0 2px 8px rgba(225, 37, 27, 0.12);
    }
    &.selected {
      border-color: #e1251b;
      background: #fef0f0;
      .jd-card-check {
        opacity: 1;
      }
    }

    .jd-card-img {
      position: relative;
      width: 100%;
      aspect-ratio: 1;
      background: #fafafa;
      img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
      .jd-card-img-placeholder {
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 36px;
        color: #c0c4cc;
        background: #f5f7fa;
      }
      .jd-card-check {
        position: absolute;
        top: 6px;
        right: 6px;
        width: 22px;
        height: 22px;
        border-radius: 50%;
        background: #e1251b;
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0;
        transition: opacity 0.15s;
        .el-icon {
          font-size: 14px;
        }
      }
    }

    .jd-card-info {
      padding: 8px 10px;
      .jd-card-title {
        font-size: 13px;
        color: #303133;
        line-height: 1.4;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        min-height: 36px;
      }
      .jd-card-price {
        color: #e1251b;
        font-size: 15px;
        font-weight: 600;
        margin-top: 4px;
      }
      .jd-card-shop {
        display: flex;
        align-items: center;
        gap: 4px;
        font-size: 12px;
        color: #909399;
        margin-top: 4px;
        .el-icon {
          font-size: 12px;
        }
      }
    }
  }
}

.jd-picker-pagination {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}

.jd-picker-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;

  .jd-picker-selected {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: 1;
    flex-wrap: wrap;

    b {
      color: #e1251b;
      margin: 0 2px;
    }

    .jd-picker-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
    }
  }

  .jd-picker-actions {
    flex-shrink: 0;
  }
}
</style>
