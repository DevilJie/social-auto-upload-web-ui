<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    :width="mode === 'relogin' ? '420px' : '680px'"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onDialogOpen"
    @close="handleClose"
  >
    <!-- add 模式: 平台卡片网格(扁平横向) -->
    <div v-if="mode === 'add'" class="login-dialog-body">
      <p class="dialog-hint">选择要登录的平台,点击卡片即开始登录</p>
      <div v-if="cardList.length === 0" class="empty-state">
        所有渠道都已加入黑名单,请先在系统设置中移除后再来登录
      </div>
      <div v-else class="platform-grid">
        <div
          v-for="p in cardList"
          :key="p.key"
          :class="[
            'platform-card',
            `platform-${p.cssClass}`,
            `is-${p.status}`
          ]"
          @click="onCardClick(p)"
        >
          <!-- logo/letter -->
          <div class="platform-logo-wrap" :style="{ background: p.bgColor }">
            <img v-if="p.logo" :src="p.logo" :alt="p.name" class="platform-logo" />
            <span v-else class="platform-letter" :style="{ color: p.color }">{{ p.letter }}</span>
          </div>

          <!-- 名称 + 状态 -->
          <div class="platform-text">
            <div class="platform-name">{{ p.name }}</div>
            <div v-if="p.status !== 'idle'" class="platform-status" :class="`is-${p.status}`">
              <template v-if="p.status === 'logging'">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>登录中...</span>
              </template>
              <template v-else-if="p.status === 'success'">
                <el-icon><Select /></el-icon>
                <span>登录成功</span>
              </template>
              <template v-else-if="p.status === 'fail'">
                <el-icon><CloseBold /></el-icon>
                <span>登录失败</span>
              </template>
            </div>
          </div>

          <!-- 右侧操作 -->
          <div class="platform-action">
            <button v-if="p.status === 'logging'" class="mini-btn" type="button" @click.stop="cancelLogin(p.key)">取消</button>
            <button v-else-if="p.status === 'fail'" class="mini-btn mini-btn-retry" type="button" @click.stop="retryLogin(p.key)">重试</button>
            <el-icon v-else-if="p.status === 'success'" class="success-mark"><Select /></el-icon>
          </div>
        </div>
      </div>
    </div>

    <!-- relogin 模式: 单卡片 -->
    <div v-else class="login-dialog-body relogin-body">
      <div v-if="reloginPlatform" class="relogin-card" :class="`platform-${reloginPlatform.cssClass}`">
        <div class="platform-logo-wrap">
          <img v-if="reloginPlatform.logo" :src="reloginPlatform.logo" :alt="reloginPlatform.name" class="platform-logo" />
          <span v-else class="platform-letter">{{ reloginPlatform.letter }}</span>
        </div>
        <div class="platform-name">{{ reloginPlatform.name }}</div>
        <template v-if="reloginStatus === 'logging'">
          <el-icon class="loading-icon is-loading"><Loading /></el-icon>
          <div class="status-text">登录中...</div>
        </template>
        <template v-else-if="reloginStatus === 'success'">
          <el-icon class="success-icon"><Select /></el-icon>
          <div class="status-text">登录成功</div>
        </template>
        <template v-else-if="reloginStatus === 'fail'">
          <el-icon class="fail-icon"><CloseBold /></el-icon>
          <div class="status-text fail-text">{{ reloginErrMsg || '登录失败' }}</div>
          <button class="retry-btn" type="button" @click="startRelogin">重试</button>
        </template>
        <p class="relogin-hint">正在打开浏览器,请在弹出的浏览器窗口中完成登录</p>
      </div>
      <div v-else class="empty-state">账号信息异常</div>
    </div>

    <template #footer>
      <el-button v-if="mode === 'relogin' && reloginStatus === 'logging'"
                 @click="cancelRelogin">取消登录</el-button>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, Select, CloseBold } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import { platformList, getPlatformByName, getPlatformByKey } from '@/config/platforms'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  mode: { type: String, default: 'add' },  // 'add' | 'relogin'
  account: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue', 'success', 'fail'])

const appStore = useAppStore()

// add 模式: 多卡片状态
const cardStates = reactive({})  // key -> { status, errMsg }
const eventSources = new Map()   // key -> EventSource(非响应式)

// relogin 模式: 单卡片状态
const reloginStatus = ref('idle')
const reloginErrMsg = ref('')
const reloginPlatform = computed(() => {
  if (props.mode !== 'relogin' || !props.account) return null
  return getPlatformByName(props.account.platform)
})
const reloginKey = computed(() => reloginPlatform.value?.key)

const dialogTitle = computed(() => {
  if (props.mode === 'relogin' && reloginPlatform.value) {
    return `重新登录:${reloginPlatform.value.name}`
  }
  return '添加账号'
})

// 卡片列表(响应式:平台状态变化时自动更新)
const cardList = computed(() =>
  platformList
    .filter(p => !appStore.isPlatformDisabled(p.key))
    .map(p => ({
      ...p,
      status: cardStates[p.key]?.status || 'idle',
      errMsg: cardStates[p.key]?.errMsg || ''
    }))
)

function setCardStatus(key, status, errMsg = '') {
  cardStates[key] = { status, errMsg }
}

function onDialogOpen() {
  if (props.mode === 'add') {
    initCardStates()
  } else if (props.mode === 'relogin') {
    startRelogin()
  }
}

function initCardStates() {
  // 清掉旧状态
  for (const k of Object.keys(cardStates)) delete cardStates[k]
}

function handleClose() {
  // 清理所有 SSE 连接(el-dialog 关闭时已经会通过 @update:model-value 通知父组件)
  for (const key of eventSources.keys()) closeSSE(key)
}

// ===== SSE 逻辑 =====
function startLogin(platformKey, accountId = null) {
  const platform = getPlatformByKey(platformKey)
  if (!platform) return

  const type = platform.id  // 1-10
  const tempId = crypto.randomUUID()
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  let url = `${baseUrl}/login?type=${type}&id=${encodeURIComponent(tempId)}`
  if (accountId) {
    url += `&account_id=${encodeURIComponent(accountId)}`
  }

  setCardStatus(platformKey, 'logging')
  // 若是 relogin 模式,由 startRelogin 单独处理 reloginStatus
  if (props.mode === 'relogin' && reloginKey.value === platformKey) {
    reloginStatus.value = 'logging'
  }

  const es = new EventSource(url)
  eventSources.set(platformKey, es)

  es.onmessage = (event) => {
    let result
    try {
      result = JSON.parse(event.data)
    } catch (e) {
      // 非 JSON,忽略(本场景不应出现二维码)
      return
    }

    if (result.status === '200') {
      setCardStatus(platformKey, 'success')
      closeSSE(platformKey)
      if (props.mode === 'relogin' && reloginKey.value === platformKey) {
        reloginStatus.value = 'success'
      }
      emit('success', { platform: platformKey, accountId: accountId || undefined })
      ElMessage.success(`${platform.name} 登录成功`)
      // relogin 模式: 1.5s 后自动关闭弹窗
      if (props.mode === 'relogin') {
        setTimeout(() => {
          emit('update:modelValue', false)
        }, 1500)
      }
      return
    }

    if (result.status === '500' || result.status === '0' || result.status === 'error') {
      const errMsg = result.msg || result.error || '登录失败'
      setCardStatus(platformKey, 'fail', errMsg)
      closeSSE(platformKey)
      if (props.mode === 'relogin' && reloginKey.value === platformKey) {
        reloginStatus.value = 'fail'
        reloginErrMsg.value = errMsg
      }
      emit('fail', { platform: platformKey, errMsg })
      return
    }

    // status === '1' 或其他: 等待中,保持 logging
  }

  es.onerror = () => {
    // 成功后 closeSSE 也会触发 onerror,需检查状态防误判
    if (cardStates[platformKey]?.status === 'success') return
    if (props.mode === 'relogin' && reloginStatus.value === 'success') return

    const errMsg = '连接断开,请检查后端服务'
    setCardStatus(platformKey, 'fail', errMsg)
    closeSSE(platformKey)
    if (props.mode === 'relogin' && reloginKey.value === platformKey) {
      reloginStatus.value = 'fail'
      reloginErrMsg.value = errMsg
    }
    emit('fail', { platform: platformKey, errMsg })
  }
}

function closeSSE(platformKey) {
  const es = eventSources.get(platformKey)
  if (es) {
    es.close()
    eventSources.delete(platformKey)
  }
}

function onCardClick(p) {
  if (p.status === 'idle' || p.status === 'fail') {
    startLogin(p.key)
  }
}

function cancelLogin(platformKey) {
  closeSSE(platformKey)
  setCardStatus(platformKey, 'idle')
  ElMessage.info('已取消登录')
}

function retryLogin(platformKey) {
  closeSSE(platformKey)
  startLogin(platformKey)
}

function startRelogin() {
  if (!reloginKey.value || !props.account) return
  closeSSE(reloginKey.value)  // 清旧连接
  startLogin(reloginKey.value, props.account.id)
}

function cancelRelogin() {
  if (reloginKey.value) closeSSE(reloginKey.value)
  reloginStatus.value = 'idle'
  ElMessage.info('已取消登录')
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.login-dialog-body {
  padding: 0 4px;
}

.dialog-hint {
  color: $text-secondary;
  font-size: 13px;
  margin: 0 0 12px 0;
}

.platform-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
}

// ── 扁平横向卡片(参考 BatchTagDialog 账号卡风格) ──
.platform-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: $bg-surface;
  border: 1px solid $border;
  border-radius: $radius-sm;
  cursor: pointer;
  transition: all $transition-fast;
  position: relative;
  min-height: 52px;
}

.platform-card.is-idle:hover {
  background: rgba($brand-start, 0.06);
  border-color: $border-active;
}

.platform-card.is-logging {
  border-color: $brand-start;
  background: rgba($brand-start, 0.08);
  cursor: progress;
}

.platform-card.is-success {
  border-color: rgba($success-color, 0.4);
  background: rgba($success-color, 0.08);
  cursor: default;
}

.platform-card.is-fail {
  border-color: rgba($danger-color, 0.4);
  background: rgba($danger-color, 0.08);
}

.platform-logo-wrap {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.platform-logo {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  object-fit: contain;
}

.platform-letter {
  font-size: 16px;
  font-weight: 700;
}

.platform-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.platform-name {
  font-size: 13px;
  font-weight: 500;
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.platform-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: $text-muted;

  .el-icon { font-size: 11px; }

  &.is-logging { color: $brand-start; }
  &.is-success { color: $success-color; }
  &.is-fail { color: $danger-color; }
}

.platform-action {
  flex-shrink: 0;
  display: flex;
  align-items: center;

  .success-mark {
    color: $success-color;
    font-size: 18px;
  }
}

.mini-btn {
  padding: 3px 10px;
  border: 1px solid $border;
  background: transparent;
  border-radius: 4px;
  font-size: 11px;
  color: $text-secondary;
  cursor: pointer;
  transition: all $transition-fast;

  &:hover {
    background: rgba($overlay-rgb, 0.06);
    color: $text-primary;
  }

  &.mini-btn-retry {
    color: $danger-color;
    border-color: rgba($danger-color, 0.4);

    &:hover {
      background: rgba($danger-color, 0.12);
    }
  }
}

.empty-state {
  text-align: center;
  color: $text-secondary;
  font-size: 13px;
  padding: 40px 20px;
}

/* relogin 模式 */
.relogin-body {
  display: flex;
  justify-content: center;
}

.relogin-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 24px;
  border: 1px solid $border;
  border-radius: $radius-card;
  min-width: 280px;
}

.relogin-hint {
  margin-top: 16px;
  font-size: 12px;
  color: $text-secondary;
  text-align: center;
}

@media (max-width: 640px) {
  .platform-grid {
    grid-template-columns: 1fr;
  }
}
</style>
