<template>
  <el-dialog
    :model-value="modelValue"
    title="发布前账号检查"
    width="640px"
    :close-on-click-modal="false"
    @update:model-value="onVisibleChange"
  >
    <div class="check-dialog-body">
      <!-- 检查中：进度条 + 所有账号卡片实时状态 -->
      <div v-if="phase === 'checking'" class="checking-section">
        <div class="progress-info">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在检查账号 Cookie 状态... {{ checkedCount }} / {{ totalCount }}</span>
        </div>
        <el-progress
          :percentage="progressPercent"
          :stroke-width="8"
          :show-text="false"
          striped
          striped-flow
          class="check-progress-bar"
        />
        <div class="check-grid">
          <div
            v-for="card in cards"
            :key="card.id"
            :class="['check-card', `check-${card.checkStatus}`, card.valid ? 'is-valid' : (card.checkStatus === 'checked' ? 'is-invalid' : '')]"
          >
            <div class="card-logo" :style="{ background: card.bgColor }">
              <img v-if="card.logo" :src="card.logo" :alt="card.platformName" class="logo-img" />
              <span v-else class="logo-letter" :style="{ color: card.color }">{{ card.letter }}</span>
            </div>
            <div class="card-info">
              <div class="card-name">{{ card.name }}</div>
              <div class="card-platform">{{ card.platformName }}</div>
            </div>
            <div class="card-status-badge">
              <template v-if="card.checkStatus === 'pending'">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span class="status-pending">检查中</span>
              </template>
              <template v-else-if="card.valid">
                <el-icon><Select /></el-icon>
                <span class="status-ok">正常</span>
              </template>
              <template v-else>
                <el-icon><WarningFilled /></el-icon>
                <span class="status-fail">失效</span>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- 全部正常 -->
      <div v-if="phase === 'all-valid'" class="all-valid-section">
        <el-icon class="all-valid-icon"><CircleCheckFilled /></el-icon>
        <span>所有账号状态正常，即将开始发布...</span>
      </div>

      <!-- 失效账号修复列表 -->
      <div v-if="phase === 'fixing'" class="fix-section">
        <p class="fix-hint">
          <el-icon color="#f56c6c"><WarningFilled /></el-icon>
          检测到 <strong>{{ invalidCards.length }}</strong> 个账号 Cookie 失效，请逐个重新登录后再发布
        </p>
        <div class="invalid-grid">
          <div
            v-for="card in invalidCards"
            :key="card.id"
            :class="['invalid-card', `is-${card.fixStatus}`]"
          >
            <!-- 平台 logo -->
            <div class="card-logo" :style="{ background: card.bgColor }">
              <img v-if="card.logo" :src="card.logo" :alt="card.platformName" class="logo-img" />
              <span v-else class="logo-letter" :style="{ color: card.color }">{{ card.letter }}</span>
            </div>

            <!-- 账号信息 -->
            <div class="card-info">
              <div class="card-name">{{ card.name }}</div>
              <div class="card-platform">{{ card.platformName }}</div>
              <div v-if="card.fixStatus === 'fail'" class="card-error">{{ card.fixError }}</div>
            </div>

            <!-- 操作按钮 -->
            <div class="card-action">
              <button
                v-if="card.fixStatus === 'idle'"
                class="action-btn action-relogin"
                @click="startRelogin(card)"
              >
                <el-icon><RefreshRight /></el-icon> 重新登录
              </button>
              <template v-else-if="card.fixStatus === 'logging'">
                <el-icon class="is-loading loading-icon"><Loading /></el-icon>
                <button class="action-btn action-cancel" @click="cancelRelogin(card)">取消</button>
              </template>
              <el-icon v-else-if="card.fixStatus === 'success'" class="success-mark"><Select /></el-icon>
              <button
                v-else-if="card.fixStatus === 'fail'"
                class="action-btn action-retry"
                @click="startRelogin(card)"
              >
                重试
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 全部修复完成 -->
      <div v-if="phase === 'done'" class="all-valid-section">
        <el-icon class="all-valid-icon"><CircleCheckFilled /></el-icon>
        <span>所有账号已修复，即将开始发布...</span>
      </div>
    </div>

    <template #footer>
      <el-button
        v-if="phase === 'fixing'"
        @click="onCancel"
      >
        取消发布
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Loading, Select, CircleCheckFilled, WarningFilled, RefreshRight,
} from '@element-plus/icons-vue'
import { http } from '@/utils/request'
import { getPlatformByKey } from '@/config/platforms'
import { useAccountStore } from '@/stores/account'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'all-valid'])

// ===== 状态 =====
// phase: 'checking' → 'all-valid' | 'fixing' → 'done'
const phase = ref('checking')
const cards = ref([])              // 全部账号卡片
const eventSources = new Map()     // accountId → EventSource

// ===== 计算属性 =====
const totalCount = computed(() => cards.value.length)
const checkedCount = computed(() => cards.value.filter(c => c.checkStatus !== 'pending').length)
const progressPercent = computed(() =>
  totalCount.value === 0 ? 0 : Math.round((checkedCount.value / totalCount.value) * 100)
)
const invalidCards = computed(() => cards.value.filter(c => !c.valid))

// ===== 对外暴露：open(accountList) → Promise<boolean> =====
let resolvePromise = null

function open(accounts) {
  // accounts: [{ id, type, filePath, name, platform(platformName) }]
  // 初始化卡片
  cards.value = accounts.map(a => {
    const p = getPlatformByKey(platformTypeToKey(a.type))
    return {
      id: a.id,
      name: a.name || '未知账号',
      platformName: a.platform || p?.name || '未知平台',
      type: a.type,
      logo: p?.logo || null,
      letter: p?.letter || '?',
      color: p?.color || '#999',
      bgColor: p?.bgColor || 'rgba(255,255,255,0.06)',
      cssClass: p?.cssClass || '',
      checkStatus: 'pending',  // pending / checked
      valid: false,
      fixStatus: 'idle',       // idle / logging / success / fail
      fixError: '',
    }
  })
  phase.value = 'checking'
  emit('update:modelValue', true)

  return new Promise(resolve => {
    resolvePromise = resolve
    // 启动并发检查
    runConcurrentChecks()
  })
}

// platform type(int) → key
function platformTypeToKey(type) {
  const map = {
    1: 'xiaohongshu', 2: 'channels', 3: 'douyin', 4: 'kuaishou',
    5: 'bilibili', 6: 'baijiahao', 7: 'tiktok', 8: 'youtube',
    9: 'tencent_video', 10: 'iqiyi', 11: 'weibo', 12: 'alipay', 13: 'toutiao',
  }
  return map[type] || ''
}

// ===== 并发检查（限流 4）=====
const CONCURRENCY = 4

async function runConcurrentChecks() {
  const queue = [...cards.value]
  const workers = []

  async function worker() {
    while (queue.length > 0) {
      const card = queue.shift()
      if (!card) break
      try {
        const res = await http.get('/checkAccount', { id: card.id })
        card.checkStatus = 'checked'
        card.valid = res?.data?.valid ?? false
        // 同步更新 accountStore 状态
        updateAccountStore(card.id, card.valid)
      } catch {
        card.checkStatus = 'checked'
        card.valid = false
      }
    }
  }

  for (let i = 0; i < Math.min(CONCURRENCY, queue.length); i++) {
    workers.push(worker())
  }
  await Promise.all(workers)

  // 检查完成，判断是否全部有效
  const hasInvalid = cards.value.some(c => !c.valid)
  if (!hasInvalid) {
    // 全部有效
    phase.value = 'all-valid'
    setTimeout(() => {
      emit('update:modelValue', false)
      resolvePromise?.(true)
      resolvePromise = null
    }, 1200)
  } else {
    // 有失效，进入修复阶段
    phase.value = 'fixing'
    // 失效卡片的 fixStatus 置为 idle
    invalidCards.value.forEach(c => { c.fixStatus = 'idle' })
  }
}

function updateAccountStore(accountId, valid) {
  // 更新 store 中的账号状态（让账号管理页也同步）
  try {
    const store = useAccountStore()
    store.updateAccount(accountId, { status: valid ? '正常' : '异常' })
  } catch {
    // store 可能未初始化，忽略
  }
}

// ===== 重新登录（复用 SSE 模式）=====
function startRelogin(card) {
  closeSSE(card.id)
  card.fixStatus = 'logging'
  card.fixError = ''

  const tempId = crypto.randomUUID()
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  const url = `${baseUrl}/login?type=${card.type}&id=${encodeURIComponent(tempId)}&account_id=${encodeURIComponent(card.id)}`

  const es = new EventSource(url)
  eventSources.set(card.id, es)

  es.onmessage = (event) => {
    let result
    try {
      result = JSON.parse(event.data)
    } catch {
      return // 非 JSON 忽略
    }

    if (result.status === '200') {
      card.fixStatus = 'success'
      card.valid = true
      closeSSE(card.id)
      ElMessage.success(`${card.name} 登录成功`)
      updateAccountStore(card.id, true)
      checkAllFixed()
    } else if (result.status === '500' || result.status === '0' || result.status === 'error') {
      card.fixStatus = 'fail'
      card.fixError = result.msg || result.error || '登录失败'
      closeSSE(card.id)
    }
  }

  es.onerror = () => {
    if (card.fixStatus === 'success') return
    card.fixStatus = 'fail'
    card.fixError = '连接断开，请检查后端服务'
    closeSSE(card.id)
  }
}

function cancelRelogin(card) {
  closeSSE(card.id)
  card.fixStatus = 'idle'
  ElMessage.info('已取消登录')
}

function closeSSE(accountId) {
  const es = eventSources.get(accountId)
  if (es) {
    es.close()
    eventSources.delete(accountId)
  }
}

function checkAllFixed() {
  // 所有失效卡片都已修复
  const allFixed = invalidCards.value.every(c => c.fixStatus === 'success')
  if (allFixed) {
    phase.value = 'done'
    setTimeout(() => {
      emit('update:modelValue', false)
      resolvePromise?.(true)
      resolvePromise = null
    }, 1200)
  }
}

// ===== 弹窗关闭处理 =====
function onVisibleChange(val) {
  if (!val) {
    // 清理 SSE
    for (const id of eventSources.keys()) closeSSE(id)
    // 如果不是 all-valid/done 阶段关闭的，视为取消
    if (phase.value !== 'all-valid' && phase.value !== 'done') {
      resolvePromise?.(false)
      resolvePromise = null
    }
  }
  emit('update:modelValue', val)
}

function onCancel() {
  emit('update:modelValue', false)
}

defineExpose({ open })
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.check-dialog-body {
  min-height: 120px;
}

// ── 检查阶段：进度条 + 卡片网格 ──
.checking-section {
  .progress-info {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    font-size: 14px;
    color: $text-secondary;

    .is-loading {
      color: $brand-start;
    }
  }

  .check-progress-bar {
    margin-bottom: 16px;
  }
}

.check-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}

.check-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: $bg-surface;
  border: 1px solid $border;
  border-radius: $radius-sm;
  transition: all 0.25s;

  &.is-valid {
    border-color: rgba($success-color, 0.3);
    background: rgba($success-color, 0.05);
  }

  &.is-invalid {
    border-color: rgba(245, 108, 108, 0.3);
    border-left: 3px solid #f56c6c;
    background: rgba(245, 108, 108, 0.04);
  }
}

.card-status-badge {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  font-size: 12px;

  .is-loading {
    color: $brand-start;
    font-size: 14px;
  }

  .status-pending { color: $text-muted; }
  .status-ok { color: $success-color; font-weight: 500; }
  .status-fail { color: #f56c6c; font-weight: 500; }
}

// ── 进度区（保留旧选择器兼容） ──
.progress-section {
  margin-bottom: 20px;

  .progress-info {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;
    font-size: 14px;
    color: $text-secondary;

    .is-loading {
      color: $brand-start;
    }
  }
}

// ── 全部正常 / 全部修复 ──
.all-valid-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 40px 0;

  .all-valid-icon {
    font-size: 48px;
    color: $success-color;
  }

  span {
    font-size: 15px;
    color: $text-primary;
  }
}

// ── 失效修复区 ──
.fix-section {
  .fix-hint {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 14px;
    color: $text-secondary;
    margin: 0 0 16px 0;

    strong {
      color: #f56c6c;
      font-weight: 600;
    }
  }
}

.invalid-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}

.invalid-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: rgba(245, 108, 108, 0.06);
  border: 1px solid rgba(245, 108, 108, 0.2);
  border-left: 3px solid #f56c6c;
  border-radius: $radius-sm;
  transition: all 0.2s;

  &.is-logging {
    border-color: rgba($brand-start, 0.3);
    border-left-color: $brand-start;
    background: rgba($brand-start, 0.06);
  }

  &.is-success {
    border-color: rgba($success-color, 0.3);
    border-left-color: $success-color;
    background: rgba($success-color, 0.06);
  }

  &.is-fail {
    border-color: rgba(245, 108, 108, 0.3);
  }
}

.card-logo {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  .logo-img {
    width: 22px;
    height: 22px;
    border-radius: 3px;
  }

  .logo-letter {
    font-size: 16px;
    font-weight: 700;
  }
}

.card-info {
  flex: 1;
  min-width: 0;

  .card-name {
    font-size: 14px;
    font-weight: 500;
    color: $text-primary;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .card-platform {
    font-size: 12px;
    color: $text-muted;
    margin-top: 2px;
  }

  .card-error {
    font-size: 12px;
    color: #f56c6c;
    margin-top: 2px;
  }
}

.card-action {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;

  .loading-icon {
    font-size: 16px;
    color: $brand-start;
  }

  .success-mark {
    font-size: 20px;
    color: $success-color;
  }
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border: 1px solid $border-active;
  border-radius: $radius-sm;
  background: rgba($brand-start, 0.08);
  color: lighten($brand-start, 12%);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;

  &:hover {
    background: rgba($brand-start, 0.16);
    border-color: $brand-start;
  }

  &.action-cancel {
    background: rgba(255, 255, 255, 0.04);
    border-color: $border;
    color: $text-muted;

    &:hover {
      background: rgba(245, 108, 108, 0.1);
      border-color: rgba(245, 108, 108, 0.3);
      color: #f56c6c;
    }
  }

  &.action-retry {
    background: rgba(245, 108, 108, 0.08);
    border-color: rgba(245, 108, 108, 0.3);
    color: #f56c6c;

    &:hover {
      background: rgba(245, 108, 108, 0.16);
    }
  }
}
</style>
