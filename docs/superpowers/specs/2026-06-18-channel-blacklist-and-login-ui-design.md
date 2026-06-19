# 渠道黑名单 + 登录弹窗 UI 重设计

**日期**: 2026-06-18
**分支**: `feature/20260618`
**作者**: Claude (brainstorming + implementation)

## 目标

1. 在「系统设置」页面新增「渠道黑名单」功能:用户可以把某些渠道(平台)加入黑名单,被加入黑名单的渠道在「视频发布」「图集发布」「账号登录」三大场景下不可选择。
2. 重新设计「账号管理」页面的登录弹窗:渠道选择从下拉框改为平台 Logo 卡片网格,点击卡片即直接进入登录流程;同步优化整体视觉风格、等待反馈、登录前引导、登录结果反馈。

## 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 黑名单数据存储 | 复用现有 `settings` 表,新增 key `disabledPlatforms`(JSON 数组) | 后端 `/api/v2/settings` 已通用,零后端改动 |
| 黑名单数据格式 | 平台 key 字符串数组(如 `["xiaohongshu","youtube"]`) | 与 `frontend/src/config/platforms.js` 中 `PLATFORMS[key]` 对齐,可读性强 |
| JSON 序列化策略 | PUT 时直接传数组(后端自动 `json.dumps`);GET 时前端手动 `JSON.parse`(后端只对 `storage` 自动反序列化) | 由 `backend/ext_api/__init__.py:575-656` 现状决定,无后端改动 |
| 持久化路径 | 数据存后端 `settings` 表,不写 localStorage(与 store 现有 autoFillTitle 等的双写模式不同) | 黑名单只与本机 SQLite 交互即可,无需 localStorage 缓存;避免双写不一致 |
| `account.platform` 字段类型 | **中文名**(如「小红书」),非 key — 由 `account.js:19` 用 `platformIdToName[item[1]]` 写入 | 现有项目约定;过滤黑名单时需 `platformNameToKey[acc.platform]` 转换 |
| `isPlatformDisabled` 入参 | **接受平台 key**(如 `xiaohongshu`),消费方负责中文→key 转换 | store 内部存 key 更稳定(中文显示名可能改);转换在调用点显式做,避免歧义 |
| 前端状态管理 | 扩展 Pinia `stores/app.js`(Composition API 风格,与现有一致),新增 `disabledPlatforms` ref + `isPlatformDisabled(key)` 函数 + `addDisabledPlatforms` / `removeDisabledPlatform` actions | 与现有 store 风格一致;启动时已有 `fetchSettings` 机制 |
| 黑名单生效策略 | 即时生效(增删即 PUT + 更新 store,不等 Settings 底部 save-bar) | 小卡片 ✕ 移除/添加交互直觉;跨页面立刻反映 |
| 批量添加 | 一次 PUT 多个 key(单次请求),不循环单 key PUT | 减少请求次数,保证原子性 |
| 黑名单对已有账号的处理 | 账号管理页依然显示账号,但带「已拉黑」tag + 禁用「登录」「同步」「创作中心」按钮(**保留「删除」按钮**,用户可清理账号) | 用户选择「仅禁用选择,账号依然显示」,避免误删账号信息;AccountManagement 卡片实际只有「登录(异常时)/ 检查 / 同步 / 创作中心 / 删除」5 个按钮,无「发布」按钮 |
| Settings 页黑名单 UI | card 内直接展示已拉黑渠道的小卡片网格(logo+名称,hover 显示右上角 ✕ 移除) + 「+ 添加渠道」按钮 → 弹窗选择 | 现代标签管理风格,所见即所得 |
| 添加黑名单弹窗里已黑名单的渠道 | 灰显 + 「已添加」标记,不可点击 | 用户能看到全平台全貌,知道哪些没加 |
| 登录弹窗组件化 | 抽出独立 `LoginDialog.vue`,承载 `add` / `relogin` 两种模式 | `AccountManagement.vue` 已 1109 行,继续堆不利维护 |
| 登录弹窗渠道选择 | 平台 Logo 卡片网格(过滤黑名单),点击卡片直接进入登录(不再输入账号名) | 用户明确「直接登陆,不需要填写账号名,因为都是登陆成功过后自动获取的」 |
| 登录账号名来源 | 后端登录成功后 `sync_profile` 写入 nickname;前端 SSE 成功后调 `fetchAccountsQuick` 刷新列表展示 | 沿用 `AccountManagement.vue:545-555` 现有机制,**SSE 本身不携带 nickname** |
| 登录成功卡片反馈 | 卡片显示「✓ 登录成功」绿色描边(不显示 nickname),保持 success 态不淡出 | SSE 不返回 nickname,nickname 在弹窗关闭后由账号列表展示;保持 success 态可让用户清楚已登录哪些 |
| 登录弹窗自动关闭 | 不自动关闭,用户手动 ✕;成功后用顶部成功提示 + 卡片 success 态双重反馈 | 自动关闭逻辑复杂(成功/失败混合场景),让用户控制更可预测 |
| 登录状态展示 | 同卡片状态切换(登录中 → 成功 → 失败),不弹子表单 | 视觉聚焦,操作连贯 |
| 多平台并发登录 | 允许同时点多个卡片并行登录;`LoginDialog` 内部维护 `Map<key, EventSource>` 支持多并发 | 后端 Worker 已支持;现有 `AccountManagement.vue:514` 是单例 `eventSource`,迁移时需改成 Map |
| SSE 取消 | 仅前端 `eventSource.close()`,后端 Playwright 不主动中断 | 后端无现成取消接口;资源泄漏本次不处理(用户通常会在浏览器中完成或关闭窗口) |

## 范围

### 在范围内

**渠道黑名单**:
1. 扩展 `frontend/src/stores/app.js`(Composition API):新增 `disabledPlatforms` ref、`isPlatformDisabled` 计算属性、`addDisabledPlatforms(keys[])` / `removeDisabledPlatform(key)` actions
2. 新组件 `frontend/src/components/PlatformBlacklistDialog.vue`(添加黑名单渠道弹窗)
3. `frontend/src/views/Settings.vue` 新增「渠道黑名单」card + 内嵌小卡片网格 + ✕ 移除交互
4. `frontend/src/components/AccountSidebar.vue` 过滤黑名单平台分组
5. `frontend/src/components/AccountSelectDialog.vue` 平台筛选条 + 账号列表(`useAccountStore`)过滤黑名单
6. `frontend/src/views/PublishCenter.vue` 渠道个性化 checkbox 区域过滤黑名单 + 进入页面时清理 `publishAccountIds` 中黑名单平台的账号
7. `frontend/src/views/ImagePublish.vue` 同上(注意基于 `IMAGE_PLATFORMS` 而非 `platformList`)
8. `frontend/src/views/AccountManagement.vue` 卡片显示「已拉黑」tag + 禁用「登录」「同步」「创作中心」按钮(保留「删除」)

**登录弹窗重设计**:
9. 新组件 `frontend/src/components/LoginDialog.vue`,支持 `add` / `relogin` 两种模式,内部用 `Map<key, EventSource>` 支持多并发
10. `frontend/src/views/AccountManagement.vue` 替换内嵌 `el-dialog` 为 `<LoginDialog>`,删除关联的 SSE 代码(单例 `eventSource`、`connectSSE`、`closeSSEConnection`)
11. 平台卡片网格 + 同卡片状态切换(登录中 / 成功 / 失败)+ 多卡片并发

**测试**(项目当前 `frontend/` 下无测试目录,无 Vitest 配置 — 测试通过 gstack `/qa` 走 Playwright E2E):
12. E2E 验证:加入黑名单 → 发布页/登录弹窗不再出现该渠道;移除黑名单 → 恢复显示
13. E2E 验证登录弹窗新流程:点卡片直接登录、登录成功显示卡片 success、失败可重试

### 不在范围内

- 后端 settings API 改动(已通用,无改动)
- 后端 `/login` SSE 协议改动(不扩展返回字段)
- 后端 SSE 取消接口(无,资源清理本次不处理)
- 账号级别的黑名单(本期只做渠道级)
- 黑名单的批量导入/导出
- 黑名单变更的审计日志
- 重新设计「重新登录」之外的其他 AccountManagement 卡片视觉
- 引入 Vitest 等单测基础设施

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│  Settings.vue                                                 │
│    新增「渠道黑名单」card                                      │
│    内嵌小卡片网格:logo + 名称,hover 显示 ✕ 移除              │
│    右上角「+ 添加渠道」按钮                                    │
└────────────────────┬─────────────────────────────────────────┘
                     │ 点 ✕ / 点 + 添加
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  stores/app.js (Pinia, Composition API)                       │
│    const disabledPlatforms = ref<string[]>([])                │
│    const isPlatformDisabled = (key) => computed               │
│    async function addDisabledPlatforms(keys: string[])        │
│      [optimistic + 单次 PUT]                                  │
│    async function removeDisabledPlatform(key: string)         │
│      [optimistic + 单次 PUT]                                  │
│    fetchSettings() 内:                                        │
│      if (data.disabledPlatforms) {                            │
│        disabledPlatforms.value = JSON.parse(data.disabledPla…) │
│      }                                                        │
└────────────────────┬─────────────────────────────────────────┘
                     │
       ┌─────────────┼──────────────────────────────────┐
       ▼             ▼                                  ▼
┌─────────────┐ ┌────────────────────┐ ┌──────────────────────┐
│ Settings 页 │ │ 发布/图集页         │ │ AccountManagement    │
│ PlatformBl- │ │ AccountSidebar     │ │ 卡片显示「已拉黑」   │
│ acklistDia- │ │ AccountSelectD-    │ │ tag + 禁用重登/发布  │
│ log (添加)  │ │ ialog 过滤         │ │                      │
│             │ │   - useAccountStore│ │ LoginDialog          │
│             │ │ PublishCenter /    │ │ add 模式不显示该卡片 │
│             │ │ ImagePublish       │ │                      │
│             │ │ 渠道个性化过滤      │ │                      │
└─────────────┘ └────────────────────┘ └──────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  LoginDialog.vue (新增组件,从 AccountManagement 抽出)         │
│                                                               │
│  内部 state:                                                  │
│    cardStates: Map<platformKey, {                             │
│      status: 'idle'|'logging'|'success'|'fail',               │
│      errMsg?: string                                          │
│    }>                                                         │
│    eventSources: Map<platformKey, EventSource>  ← 多并发核心  │
│                                                               │
│  mode='add':                                                  │
│    平台 Logo 卡片网格 (过滤 disabledPlatforms)                │
│    点击卡片 → 该卡 cardStates[key].status = 'logging'         │
│            → eventSources.set(key, new EventSource(...))      │
│    SSE onmessage status:'200' → status = 'success' (保持)     │
│                              + emit success(accountInfo)      │
│                              + 父组件 fetchAccountsQuick()    │
│    SSE onmessage status:'500' → status = 'fail' + errMsg      │
│    SSE onerror              → status = 'fail' + errMsg        │
│    支持 Map 中多个 EventSource 并发                            │
│                                                               │
│  mode='relogin':                                              │
│    单一平台大卡片 + 「登录中」spinner                         │
│    头部展示「重新登录:{平台}」(不显示 nickname,因为可能已失效)│
│    立即启动 SSE (带 account_id)                               │
│    成功 → 1.5s 后关闭弹窗 → emit success                      │
│                                                               │
│  Emits: success({platform, accountId?}),                      │
│         fail({platform, errMsg}), close                       │
└──────────────────────────────────────────────────────────────┘
```

## 组件设计

### 1. `stores/app.js` 扩展(Composition API,与现有一致)

```js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { settingsApi } from '@/api/v2'

export const useAppStore = defineStore('app', () => {
  // ... 现有代码保持不变 ...

  // 渠道黑名单(平台 key 数组,如 ['xiaohongshu', 'youtube'])
  const disabledPlatforms = ref([])

  // getter: 判断某平台是否被拉黑
  const isPlatformDisabled = (key) => disabledPlatforms.value.includes(key)

  // 启动时调用(在 fetchSettings 中):
  //   const data = await settingsApi.getSettings()
  //   if (data.disabledPlatforms) {
  //     try {
  //       disabledPlatforms.value = typeof data.disabledPlatforms === 'string'
  //         ? JSON.parse(data.disabledPlatforms)
  //         : data.disabledPlatforms
  //     } catch (e) { disabledPlatforms.value = [] }
  //   }

  // 批量添加(一次 PUT 多个 key)
  const addDisabledPlatforms = async (keys) => {
    const newKeys = keys.filter(k => !disabledPlatforms.value.includes(k))
    if (newKeys.length === 0) return
    const snapshot = [...disabledPlatforms.value]           // 用于回滚
    disabledPlatforms.value = [...disabledPlatforms.value, ...newKeys]
    try {
      await settingsApi.updateSettings({
        disabledPlatforms: disabledPlatforms.value
      })
    } catch (e) {
      disabledPlatforms.value = snapshot                    // 回滚
      throw e
    }
  }

  // 移除单个
  const removeDisabledPlatform = async (key) => {
    const snapshot = [...disabledPlatforms.value]
    disabledPlatforms.value = disabledPlatforms.value.filter(k => k !== key)
    try {
      await settingsApi.updateSettings({
        disabledPlatforms: disabledPlatforms.value
      })
    } catch (e) {
      disabledPlatforms.value = snapshot
      throw e
    }
  }

  return {
    // ... 现有 return 保持不变 ...
    disabledPlatforms,
    isPlatformDisabled,
    addDisabledPlatforms,
    removeDisabledPlatform,
  }
})
```

**JSON 序列化要点**(由后端 `backend/ext_api/__init__.py:625-656` 现状决定):
- PUT 时:前端直接传数组,**后端会自动 `json.dumps`**(`if isinstance(value, (dict, list))`)
- GET 时:后端**只对 `storage` 自动反序列化**,其他 key 都是字符串 → 前端**必须手动 `JSON.parse`**

### 2. `PlatformBlacklistDialog.vue`

**职责**: 添加新渠道到黑名单的弹窗(批量选择)

**Props**:
```ts
{
  modelValue: boolean,
  disabledKeys: string[],   // 当前已黑名单的 key 数组(从 store 传入,用于灰显)
}
```

**Emits**:
```ts
{
  'update:modelValue': (visible: boolean) => void
  // 一次性回传本次新选的所有 key,父组件调 store.addDisabledPlatforms 批量 PUT
  confirm: (newKeys: string[]) => void
}
```

**UI**:
- 标题:「添加黑名单渠道」
- 副标题:「选择要加入黑名单的渠道(已加入的不可重复选择)」
- 主体:平台 Logo 网格(4 列响应式)
  - 已黑名单的平台(`disabledKeys.includes(key)`): 灰显 + 右下角 `✓ 已添加`,不可点击
  - 未黑名单的平台: hover 高亮,点击切换选中状态(选中 = 主题色描边 + 右上角对勾)
- 底部:`[取消]` `[确认添加(N)]`,N 为本次新选数量,无新选时禁用

**交互**:
- 点「确认添加」→ emit `confirm(newSelectedKeys)` → 父组件一次调 `store.addDisabledPlatforms(newKeys)`(单次 PUT)
- 点「取消」/`✕` → emit `update:modelValue(false)`

### 3. `Settings.vue` 「渠道黑名单」card

```html
<div class="settings-card">
  <div class="card-header">
    <h3>渠道黑名单</h3>
    <el-button type="primary" @click="openBlacklistDialog">
      <el-icon><Plus /></el-icon> 添加渠道
    </el-button>
  </div>
  <p class="card-desc">
    被加入黑名单的渠道,将无法在视频发布、图集发布、账号登录场景下被选择
  </p>

  <!-- 已拉黑渠道的小卡片网格 -->
  <div v-if="disabledPlatformObjects.length" class="blacklist-grid">
    <div
      v-for="p in disabledPlatformObjects"
      :key="p.key"
      class="blacklist-chip"
      :class="`platform-${p.cssClass}`"
    >
      <img :src="p.logo" :alt="p.name" class="chip-logo" />
      <span class="chip-name">{{ p.name }}</span>
      <button class="chip-remove" @click="removeFromBlacklist(p.key)">
        <el-icon><Close /></el-icon>
      </button>
    </div>
  </div>

  <!-- 空态 -->
  <div v-else class="blacklist-empty">
    <el-icon class="empty-icon"><Warning /></el-icon>
    <span>暂无黑名单渠道,点击右上角「添加渠道」开始</span>
  </div>

  <PlatformBlacklistDialog
    v-model="blacklistDialogVisible"
    :disabled-keys="appStore.disabledPlatforms"
    @confirm="onBlacklistConfirm"
  />
</div>
```

**样式**:
- `.blacklist-chip`: 圆角 8px,内边距 8px 12px,平台主题色淡彩底 + 描边
- `.chip-remove`: 默认 `opacity:0`,父级 hover 时 `opacity:1` 渐变;圆形 16×16,半透明黑底白字 ✕
- `.blacklist-grid`: flex-wrap,gap 8px

**逻辑**:
- `disabledPlatformObjects = computed(() => appStore.disabledPlatforms.map(k => PLATFORMS[k]).filter(Boolean))` — `filter(Boolean)` 防止后端返回不存在的 key 时 `.logo` 报错
- `removeFromBlacklist(key)` → `appStore.removeDisabledPlatform(key)` (optimistic + 单次 PUT);失败时 store 内部已回滚,UI 自动还原
- `onBlacklistConfirm(newKeys)` → `appStore.addDisabledPlatforms(newKeys)` 一次性 PUT;成功后 `ElMessage.success('已添加 N 个渠道到黑名单')`,关闭弹窗

### 4. `LoginDialog.vue`

**Props**:
```ts
{
  modelValue: boolean,
  mode: 'add' | 'relogin',
  account?: { id, platform, name, ... } | null,  // relogin 模式必填
}
```

**Emits**:
```ts
{
  'update:modelValue': (v: boolean) => void
  // accountId 在 add 模式下可能没有(SSE 不返回 id),所以只传 platform
  success: (payload: { platform: string, accountId?: number }) => void
  fail: (payload: { platform: string, errMsg: string }) => void
}
```

**内部 state**(setup 风格;**用 `reactive` 普通对象而非 Map** — Vue 对 `Map.set` 的响应式追踪在多数版本不可靠):
```js
import { reactive, ref, computed } from 'vue'

const cardStates = reactive({})   // key: platformKey -> { status, errMsg }
const eventSources = new Map()    // key: platformKey -> EventSource 实例(非响应式)

// 初始化所有非黑名单平台为 idle
function initCardStates() {
  // 清掉旧状态
  for (const k of Object.keys(cardStates)) delete cardStates[k]
  platformList
    .filter(p => !appStore.isPlatformDisabled(p.key))
    .forEach(p => { cardStates[p.key] = { status: 'idle', errMsg: '' } })
}

function setCardStatus(key, status, errMsg = '') {
  // 直接赋值整个对象,触发响应式
  cardStates[key] = { status, errMsg }
}

// 渲染时按 platformList 顺序遍历,而不是 Object.keys 顺序
const cardList = computed(() =>
  platformList
    .filter(p => !appStore.isPlatformDisabled(p.key))
    .map(p => ({ ...p, ...cardStates[p.key] }))
)
```

**UI - add 模式**:
```
┌───────────────────────────────────────────────────────────────┐
│  添加账号                                              [✕]     │
│  ───────────────────────────────────────────────────────────  │
│   选择要登录的平台,点击卡片即开始登录                         │
│                                                                │
│   [logo 4列响应式网格,过滤 disabledPlatforms]                 │
│                                                                │
│   每张卡片可独立切换 4 态(单卡尺寸固定,状态切换不引起布局抖动):│
│     idle:     logo + 平台名(主题色淡彩底)                    │
│     logging:  spinner + 「登录中...」+ 卡片底部「取消」文字   │
│     success:  ✓ + logo + 平台名 + 「登录成功」(绿色描边)    │
│               保持 success 态不淡出,可继续点其他卡片          │
│     fail:     ✕ + logo + 平台名 + 错误文案 + 「重试」按钮     │
│                                                                │
│   不自动关闭弹窗;用户手动 ✕;顶部 toast 反馈「X 个账号登录成功」│
└───────────────────────────────────────────────────────────────┘
```

**UI - relogin 模式**:
```
┌─────────────────────────────────────────────────┐
│  重新登录:{平台名}                       [✕]   │
│  ─────────────────────────────────────────────  │
│                                                  │
│         ┌────────────┐                          │
│         │   [logo]   │                          │
│         │   {平台名} │                          │
│         │ ⟳ 登录中...│                          │
│         └────────────┘                          │
│                                                  │
│   正在打开浏览器,请在弹出的浏览器窗口完成登录  │
│                                                  │
│             [取消登录]                          │
└─────────────────────────────────────────────────┘
```
- 头部只显示「重新登录:{平台名}」,**不显示 @nickname**(账号可能已失效,nickname 不可靠)
- 立即启动 SSE(带 `account_id`)
- 成功 → 卡片显示 ✓ → 1.5s 后自动关闭弹窗 → emit success
- 失败 → 卡片显示错误 + 「重试」

**SSE 启动逻辑**(从 `AccountManagement.vue:520-608` 迁移,改为多并发):
```js
function startLogin(platformKey, accountId = null) {
  const platform = PLATFORMS[platformKey]
  const type = platform.id  // 1-10
  const tempId = crypto.randomUUID()  // 沿用现有 UUID 方案
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  let url = `${baseUrl}/login?type=${type}&id=${encodeURIComponent(tempId)}`
  if (accountId) url += `&account_id=${encodeURIComponent(accountId)}`

  setCardStatus(platformKey, 'logging')

  const es = new EventSource(url)
  eventSources.set(platformKey, es)

  es.onmessage = (event) => {
    // 沿用现有 onmessage 多格式解析(JSON / 纯字符串 '200'/'500' / 二维码 base64)
    // 但本期场景是 Playwright 浏览器登录,后端只推送 JSON status,不会有二维码
    try {
      const result = JSON.parse(event.data)
      if (result.status === '200') {
        setCardStatus(platformKey, 'success')
        closeSSE(platformKey)
        emit('success', { platform: platformKey, accountId: accountId || undefined })
        ElMessage.success(`${platform.name} 登录成功`)
        return
      }
      if (result.status === '500' || result.status === '0' || result.status === 'error') {
        setCardStatus(platformKey, 'fail', result.msg || result.error || '登录失败')
        closeSSE(platformKey)
        emit('fail', { platform: platformKey, errMsg: result.msg || '登录失败' })
        return
      }
    } catch (e) {
      // 非 JSON 数据,忽略(本场景不应出现二维码)
    }
  }

  es.onerror = () => {
    // 成功后 closeSSE 也会触发 onerror,需检查状态防误判
    if (cardStates[platformKey]?.status === 'success') return
    setCardStatus(platformKey, 'fail', '连接断开,请检查后端服务')
    closeSSE(platformKey)
  }
}

function closeSSE(platformKey) {
  const es = eventSources.get(platformKey)
  if (es) {
    es.close()
    eventSources.delete(platformKey)
  }
}

function cancelLogin(platformKey) {
  closeSSE(platformKey)
  setCardStatus(platformKey, 'idle')
  ElMessage.info('已取消登录')
}

function retryLogin(platformKey, accountId = null) {
  closeSSE(platformKey)  // 清理可能残留的旧连接
  startLogin(platformKey, accountId)
}

// 弹窗关闭时清理所有 SSE
function handleClose() {
  for (const key of eventSources.keys()) closeSSE(key)
  emit('update:modelValue', false)
}

// 用 el-dialog 的 @open 事件触发初始化(比 watch modelValue 更明确)
function onDialogOpen() {
  if (props.mode === 'add') {
    initCardStates()
  } else if (props.mode === 'relogin' && props.account) {
    // relogin 模式:把账号中文名转 key 后启动 SSE
    const key = platformNameToKey[props.account.platform]
    if (key) startLogin(key, props.account.id)
  }
}
```

模板:
```html
<el-dialog
  :model-value="modelValue"
  @update:model-value="$emit('update:modelValue', $event)"
  @open="onDialogOpen"
  @close="handleClose"
>
  ...
</el-dialog>
```

**注意**:不实现前端超时,让 SSE 的 `onerror` 自然处理断连(原 spec 中的 60s 超时移除 — 实际登录可能需要数分钟)。

### 5. 各消费方的过滤实现

**AccountSidebar.vue**(`group.platform` 是中文名):
```js
import { useAppStore } from '@/stores/app'
import { platformNameToKey } from '@/config/platforms'
const appStore = useAppStore()

const groupedAccounts = computed(() => {
  return allGroupedAccounts.filter(group => {
    const key = platformNameToKey[group.platform]
    return key && !appStore.isPlatformDisabled(key)
  })
})
```

**AccountSelectDialog.vue**(账号来自 `useAccountStore`,`account.platform` 是中文名):
```js
import { useAppStore } from '@/stores/app'
import { useAccountStore } from '@/stores/account'
import { platformNameToKey } from '@/config/platforms'
const appStore = useAppStore()
const accountStore = useAccountStore()

// 平台筛选条(平台对象本身有 key 字段,可直接用)
const visiblePlatforms = computed(() =>
  props.platforms.filter(p => !appStore.isPlatformDisabled(p.key))
)

// 账号列表(从 accountStore 拿;account.platform 是中文名,需转换)
const visibleAccounts = computed(() =>
  accountStore.accounts.filter(a => {
    const key = platformNameToKey[a.platform]
    return key && !appStore.isPlatformDisabled(key)
  })
)

// 「一键全选」只针对 visibleAccounts
const toggleSelectAll = () => { /* 基于 visibleAccounts 操作 tempSelectedAccounts */ }
```

**PublishCenter.vue / ImagePublish.vue**(`acc.platform` 是中文名):
- 进入页面时清理 `publishAccountIds`:
  ```js
  onMounted(() => {
    const filtered = new Set()
    for (const id of publishAccountIds.value) {
      const acc = accountStore.accounts.find(a => a.id === id)
      if (!acc) continue
      const key = platformNameToKey[acc.platform]
      if (key && !appStore.isPlatformDisabled(key)) {
        filtered.add(id)
      }
    }
    publishAccountIds.value = filtered
  })
  ```
  > 注:这里清理的是发布页内存中的 `publishAccountIds` Set,本来就不写后端,无需强调"不持久化"。
- 「渠道个性化」checkbox 区域:
  ```js
  // PublishCenter 用 platformList,ImagePublish 用 IMAGE_PLATFORMS
  // 这俩是平台对象数组,有 key 字段,直接过滤
  const visiblePlatformsForCustomize = computed(() =>
    IMAGE_PLATFORMS.filter(p => !appStore.isPlatformDisabled(p.key))  // ImagePublish 用
    // platformList.filter(p => !appStore.isPlatformDisabled(p.key)) // PublishCenter 用
  )
  ```

**AccountManagement.vue**(`account.platform` 是中文名;AccountManagement 卡片实际按钮:登录(异常时)、检查、同步、创作中心、删除):
- 卡片右上角条件 tag:
  ```html
  <el-tag v-if="isAccountDisabled(account)"
          type="info" size="small" effect="plain">
    已拉黑
  </el-tag>
  ```
- **禁用「登录」「同步」「创作中心」**(`handleReLogin` / `handleSyncProfile` / `handleOpenCreatorCenter`),**保留「检查」「删除」**(允许用户清理):
  ```html
  <button class="action-btn login"
          :disabled="isAccountDisabled(account)"
          @click="handleReLogin(account)">
    {{ isAccountDisabled(account) ? '已拉黑' : '登录' }}
  </button>
  <button class="action-btn sync"
          :disabled="isAccountDisabled(account) || syncingIds.has(account.id)"
          @click="handleSyncProfile(account)">同步</button>
  <button class="action-btn creator"
          :disabled="isAccountDisabled(account) || account.status === '异常'"
          @click="handleOpenCreatorCenter(account)">创作中心</button>
  ```
- 用 `<el-tooltip>` 包裹禁用态按钮,提示「该渠道已被加入黑名单,请先在系统设置中移除」(只对拉黑状态触发)
- 工具函数:
  ```js
  import { platformNameToKey } from '@/config/platforms'
  const isAccountDisabled = (acc) => {
    const key = platformNameToKey[acc.platform]
    return key && appStore.isPlatformDisabled(key)
  }
  ```
- 替换内嵌 dialog:
  ```html
  <LoginDialog
    v-model="loginDialogVisible"
    :mode="loginMode"
    :account="reloginAccount"
    @success="onLoginSuccess"
    @fail="onLoginFail"
  />
  ```
  - `handleAddAccount` 设 `loginMode = 'add'`,打开弹窗
  - `handleReLogin(acc)` 设 `loginMode = 'relogin'; reloginAccount = acc`,打开弹窗
  - `onLoginSuccess` 调 `fetchAccountsQuick()` 刷新列表(沿用现有机制)
  - 删除文件中的 `connectSSE` / `closeSSEConnection` / 单例 `eventSource` / `qrCodeData` / `loginStatus` / `sseConnecting` 等遗留代码

## 数据流

### 黑名单变更流

```
用户点 ✕ 或在弹窗选新渠道
        ↓
Pinia action (optimistic 更新 state)
        ↓
PUT /api/v2/settings { disabledPlatforms: [...] }   ← 单次 PUT
        ↓
后端 INSERT OR REPLACE INTO settings(key, value)
       (value = JSON.stringify(数组),自动)
        ↓
返回 200 → state 保持
返回 error → 回滚 state + ElMessage.error
        ↓
所有响应式组件自动更新 (isPlatformDisabled)
        ↓
发布页/账号管理/登录弹窗立刻反映
```

### 登录流

```
add 模式:
  打开弹窗 → initCardStates() 把所有非黑名单平台置为 idle
        ↓
  用户点平台卡片 → startLogin(key)
        ↓
  cardStates[key].status = 'logging'
  eventSources.set(key, new EventSource('/login?type=ID&id=UUID'))
        ↓
  后端打开 Playwright 浏览器 → 用户在浏览器登录
        ↓
  后端 sync_profile 写入账号记录(nickname 等)
        ↓
  SSE 推送 {status:'200'} (不含 nickname)
        ↓
  cardStates[key].status = 'success' (保持)
  emit('success', { platform: key })
  父组件 fetchAccountsQuick() 刷新账号列表
        ↓
  ElMessage.success('{平台} 登录成功')
        ↓
  用户可继续点其他卡片,或手动关闭弹窗

relogin 模式:
  AccountManagement 点「登录」按钮
        ↓
  设 mode='relogin', account=acc, 打开 LoginDialog
        ↓
  立即 startLogin(acc.platformKey, acc.id)  ← 带 account_id
        ↓
  后端打开浏览器 → 用户登录 → sync_profile
        ↓
  SSE 推送 200 → 卡片显示 ✓ → 1.5s 后自动关闭弹窗 → emit success
```

## 错误处理

| 场景 | 处理 |
|------|------|
| PUT settings 失败 | store 内回滚 state,父组件 catch 后 `ElMessage.error('保存黑名单失败,请重试')` |
| SSE 连接失败(onerror) | 卡片设为 fail,错误文案「连接断开,请检查后端服务」 |
| SSE 推送 status:'500' / '0' / 'error' | 卡片设为 fail,显示后端返回的 `msg` 或 `error` |
| 用户点取消 | `closeSSE(key)`,卡片回到 idle,提示「已取消登录」。**后端 Playwright 不主动中断**(无现成接口),允许其自然结束 |
| 重试登录 | `closeSSE` 清旧连接 → 重新生成 tempId(UUID) → `new EventSource`,卡片切回 logging |
| 弹窗关闭时仍有 logging 卡片 | `handleClose` 中循环 `closeSSE(key)` 清理所有 EventSource |
| 黑名单变更时 LoginDialog 已打开 | `cardStates` 不实时响应式更新(已存在的卡片不打断),用户下次打开弹窗才反映;若需立即生效可在 watch 中处理(可选,本期不做) |

## 边界情况

| 场景 | 处理 |
|------|------|
| 拉黑前 `publishAccountIds` 已有该渠道账号 | 进入发布页时清理 Set(仅本地内存状态,Set 本就不持久化) |
| 账号已异常 + 平台被拉黑 | 账号管理页卡片显示「已拉黑」tag,「登录」按钮禁用 + tooltip「该渠道已被加入黑名单,请先在系统设置中移除」 |
| 用户在 add 弹窗登录中,Settings 拉黑该平台 | 当前登录 SSE 不打断(已完成或失败);下次打开 LoginDialog 时该卡片不出现 |
| 黑名单为空 | Settings 页显示空态文案「暂无黑名单渠道」 |
| 黑名单满(全 10 个平台) | Settings 页正常显示所有 chip;LoginDialog add 模式无卡片,显示「所有渠道都已加入黑名单,请先移除」 |
| 拉黑/取消拉黑时网络断开 | optimistic 更新前端可见,PUT 失败 store 内回滚 + Toast |
| 后端返回不存在的 platform key | `disabledPlatformObjects` 用 `.filter(Boolean)` 过滤掉 `PLATFORMS[k]` 为 undefined 的项 |
| 多 tab 同时操作 | 不处理(单桌面应用场景,无并发 tab 需求) |

## 实现注意(给写代码的自己)

1. **JSON 序列化**:GET settings 后,`disabledPlatforms` 是字符串,必须 `JSON.parse`;PUT 时直接传数组,后端自动序列化。
2. **Pinia 风格**:`stores/app.js` 是 Composition API(setup 函数),不要用 Options API 的 `state: {}` 写法;新加的 ref / function 都在 setup 函数体内,最后 return 出去。
3. **SSE 多并发**:现有 `AccountManagement.vue:514` 是 `let eventSource = null` 单例;`LoginDialog` 必须用 `Map<key, EventSource>` 支持同时多个登录。`EventSource` 实例本身**不需要响应式**,放在普通变量(不是 ref)。
4. **EventSource 浏览器连接数限制**:HTTP/1.1 同源限 6 个连接;Flask 默认 HTTP/1.1。理论上同时点 7+ 个卡片会卡住,实际用户不会一次点这么多,本期不特殊处理。
5. **SSE 取消的资源清理**:本期不做后端 Playwright 取消;用户取消后后端浏览器实例可能继续运行直到用户在浏览器中完成或关闭。资源泄漏问题留待后续优化。
6. **`fetchAccountsQuick`**:`AccountManagement.vue` 现有方法,登录成功后调它刷新账号列表(后端 sync_profile 已写库,刷新即可看到真实 nickname)。
7. **`/login` SSE 协议**:本期**不扩展**返回字段(nickname 不通过 SSE 返回),保持后端零改动。
8. **`IMAGE_PLATFORMS`**:ImagePublish.vue 用的是 `IMAGE_PLATFORMS = platformList.filter(p => IMAGE_PLATFORM_KEYS.includes(p.key))`,过滤黑名单时要基于这个子集,不要用全量 `platformList`。
9. **持久化路径**:disabledPlatforms **只写后端 settings 表**,不写 localStorage(项目里 autoFillTitle 等是双写,有历史包袱;黑名单是新功能,走"单一数据源"更干净)。这是 Tauri 桌面应用,数据本来就只在本地 SQLite,**不存在跨设备场景**。
10. **`PLATFORMS[k]` 容错**:遍历 `disabledPlatforms` 时,`PLATFORMS[k]` 可能返回 undefined(后端返回了已废弃的 key),用 `.filter(Boolean)` 兜底;模板中也要加 `v-if="p"` 保护 `<img :src="p.logo">` 防止请求 `undefined` 路径。
11. **`account.platform` 是中文名**(非 key),由 `stores/account.js:19` 的 `platformIdToName[item[1]]` 写入。所有按 account 过滤黑名单的地方都要 `const key = platformNameToKey[a.platform]; key && !isPlatformDisabled(key)`。但平台**对象数组**(`platformList`、`IMAGE_PLATFORMS`、`props.platforms`)本身有 `key` 字段,直接 `p.key` 即可。
12. **Vue Map 响应式陷阱**:`reactive(new Map())` 在 Vue 3 中需 3.4+ 才稳定,且 `Map.set` 不一定触发模板重渲染。`LoginDialog.cardStates` 用 `reactive({})` 普通对象,**直接赋值整个对象** `cardStates[key] = {...}` 才稳。

## 测试策略

项目 `frontend/` 下当前无测试目录、无 Vitest 配置。**本期不引入单测基础设施**,所有验证通过 gstack `/qa` + Playwright E2E。

### E2E 测试用例

1. **黑名单基础流**:
   - 进入 Settings → 点「添加渠道」→ 勾选小红书、抖音 → 确认
   - 进入视频发布 → 验证左侧账号栏无小红书/抖音分组
   - 进入账号管理 → 添加账号 → 验证弹窗无小红书/抖音卡片
   - 回到 Settings → 点小红书 chip 的 ✕ → 验证发布页/登录弹窗恢复小红书

2. **登录弹窗 add 模式**:
   - 进入账号管理 → 添加账号
   - 点击「B站」卡片 → 验证卡片切到 logging 状态(spinner)
   - 等待 SSE 成功 → 验证卡片显示 ✓ + 绿色描边
   - 关闭弹窗 → 验证账号列表新增了 B 站账号(带真实 nickname)

3. **登录弹窗 relogin 模式**:
   - 已有异常账号 → 点「登录」按钮
   - 验证弹窗显示「重新登录:{平台}」+ 立即进入 logging 状态
   - 等待成功 → 验证 1.5s 后弹窗自动关闭 + 账号状态变正常

4. **失败重试**:
   - 关闭后端 / mock 后端返回 500 → 验证卡片显示失败 + 「重试」
   - 点击「重试」→ 验证重新发起 SSE

5. **黑名单 + 账号管理共存**:
   - 添加小红书到黑名单
   - 已有的小红书账号依然显示,带「已拉黑」tag
   - 「登录」「同步」「创作中心」按钮禁用,「删除」按钮仍可用
   - tooltip 显示「该渠道已被加入黑名单,请先在系统设置中移除」

6. **JSON 持久化**:
   - 添加几个渠道 → 刷新页面 → 验证黑名单依然存在(GET 后正确 JSON.parse)

7. **多并发**(可选):
   - 同时点 3 个平台卡片 → 验证 3 个卡片同时 logging → 都能独立成功/失败

## 文件改动清单

### 新增

- `frontend/src/components/PlatformBlacklistDialog.vue`
- `frontend/src/components/LoginDialog.vue`

### 修改

- `frontend/src/stores/app.js` — Composition API 风格扩展 disabledPlatforms + actions
- `frontend/src/views/Settings.vue` — 新增黑名单 card + 弹窗挂载
- `frontend/src/views/AccountManagement.vue` — 替换内嵌 dialog 为 `<LoginDialog>`,加「已拉黑」tag + 禁用「登录」「同步」「创作中心」按钮(**保留「删除」**),**删除** 单例 `eventSource` / `connectSSE` / `closeSSEConnection` / `qrCodeData` / `loginStatus` / `sseConnecting` 等遗留代码
- `frontend/src/components/AccountSidebar.vue` — 过滤黑名单平台分组
- `frontend/src/components/AccountSelectDialog.vue` — 过滤黑名单平台筛选条 + 账号列表(基于 `useAccountStore`)
- `frontend/src/views/PublishCenter.vue` — 渠道个性化过滤 + 进入页时清理 publishAccountIds
- `frontend/src/views/ImagePublish.vue` — 同上(基于 `IMAGE_PLATFORMS`)

### 不改动

- `backend/`(零改动)
- `frontend/src/config/platforms.js`(只读消费)
- `frontend/src/api/v2.js`(已通用)

## 实现顺序建议(供后续 plan 参考)

1. **基础设施**:Pinia store 扩展(`disabledPlatforms` / `isPlatformDisabled` / `addDisabledPlatforms` / `removeDisabledPlatform`)+ `fetchSettings` 内 JSON.parse
2. **Settings 黑名单 card**:小卡片网格 + ✕ 移除交互(独立可测,可先不接 PlatformBlacklistDialog,空态点 ✕ 无效即可)
3. **PlatformBlacklistDialog**(添加黑名单):勾选 + 批量 confirm
4. **黑名单生效到消费方**:AccountSidebar / AccountSelectDialog / PublishCenter / ImagePublish / AccountManagement 「已拉黑」tag
5. **LoginDialog**(从 AccountManagement 抽出 + 新交互):先做 add 模式,再做 relogin 模式
6. **E2E 验证**:gstack `/qa` 走完测试用例 1-7
