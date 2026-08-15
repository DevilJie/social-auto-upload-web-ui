# 京东视频发布 · 设计文档

- 日期: 2026-08-13
- 影响范围: 京东平台(`platform_id = 20`)视频发布全流程,含关联商品 picker、关联小说下拉、封面、标题、创作声明、定时发布
- 关联文档: [`docs/平台发布商品店铺关联功能实现说明.md`](../../平台发布商品店铺关联功能实现说明.md)
- 参考实现: 淘宝光合 [`backend/impl/taobao_guanghe/`](../../../backend/impl/taobao_guanghe/) + [`frontend/src/components/GuangheItemPicker.vue`](../../../frontend/src/components/GuangheItemPicker.vue)

## 1. 背景与问题

项目当前已有 11 个平台的发布实现,但**京东平台尚未实现视频发布**。京东有独立的发布后台 `https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop`,与 jingmai(京东京麦,platform_id 19)是两个不同的产品。

京东发布页 UI 与淘宝光合相比:
- 视频上传 + 封面 + 标题 + 创作声明 + 定时发布 等基础字段类似
- 关联挂件(京东叫"关联商品/小说")独立:**只有本店商品**一种来源,无 tab/rule/category 筛选
- 关联**小说**是简单下拉搜索,无需 picker
- 京东发布页**无跨域 iframe**,所有 DOM 在同一个 page 上(对比淘宝光合有跨域 iframe)

参考淘宝光合的 trace 快照方案,京东的关联商品批量勾选需要:
- 选中时记录 `(keyword, page)` 轨迹
- 发布时按 trace 分组重现(搜索 → 翻页 → 按 id 勾选)
- 京东无 tab/rule/category,所以 trace 模型比光合更简单

## 2. 目标

- 实现京东视频发布的完整流程:上传 → 封面 → 标题 → 关联挂件(商品/小说)→ 创作声明 → 定时发布 → 发布
- 复用淘宝光合的"无头 picker + trace 快照 + 分组重现"架构,但简化 trace 模型
- 关联小说采用简单下拉搜索组件(参考视频号 RemoteSearchSelect)
- 与现有 PublishCenter、drafts、发布历史等系统无缝对接

## 3. 关键决策(brainstorming 已确认)

| 维度 | 决策 |
|---|---|
| 整体架构 | **完全沿用淘宝光合 picker 架构**(独立 `_jd_link_ops.py` / `picker.py` / `platform.py`) |
| trace 模型 | **简化版** `{keyword: str, page: int}`,无 tab/rule/category |
| 批量勾选 | **按 trace 分组重现**(类似淘宝光合 `_replay_groups`) |
| picker 来源 | **只支持"本店商品"**(无 tab/站内搜索/链接导入) |
| 关联小说 | **下拉搜索组件**(参考视频号 RemoteSearchSelect),不开 picker |
| 浏览器策略 | 发布 `headless=False`,picker `headless=True`(与光合一致) |
| 失败处理 | **任一商品找不到即中断整个视频发布** |
| 持久化 | 写入 `drafts.draft_data` JSON,不新增表/字段 |

## 4. 架构与文件改动

### 4.1 新增文件

```
backend/impl/jd/
├── __init__.py                       【新】空
├── _jd_link_ops.py                   【新】约 350 行,帧级纯函数 DOM 操作库
├── picker.py                         【新】约 300 行,JdPickerSession + _SessionPool
└── platform.py                       【新】约 600 行,JdPlatform 实现

backend/blueprints/jd_bp.py           【新】约 200 行,picker 路由蓝图

frontend/src/
├── api/jd.js                         【新】约 45 行,picker API 客户端
└── components/JdItemPicker.vue       【新】约 550 行,京东选品弹窗
```

### 4.2 修改文件

```
backend/impl/registry.py              【改】_populate_registry 添加 register(JdPlatform)
backend/app.py                        【改】注册 jd_bp;4 处 publish 路由透传 jd 字段
backend/ext_api/__init__.py           【改】_PLATFORM_ID_MAP / platform_map / type_to_platform

frontend/src/
├── config/platforms.js               【改】添加 JD 配置
├── views/PublishCenter.vue           【改】添加京东专属卡片 + 引入 JdItemPicker
└── assets/logos/jd.png              【改/新增】京东 logo(png 格式,与 jingmai 同目录)
```

## 5. 数据结构(trace schema)

### 5.1 前端 form 字段(持久化到 `drafts.draft_data` JSON)

```js
// form.jdProducts(关联商品数组)
[
  {
    title: "洛丽塔裙子甜美可爱洋装公主裙 均码",  // 显示用
    image: "//m.360buyimg.com/.../xxx.png",       // 显示用
    id: "1234567890",                            // 商品 skuId(从 DOM 中提取)
    trace: {
      keyword: "洛丽塔",  // 搜索词,空串=未搜索(列出所有)
      page: 1             // 页码,从 1 开始
    }
  },
  // ...
]

// form.jdNovel(关联小说,单选;空时为字符串 '',非空时为对象)
{
  title: "耳根清净:好音乐与好唱片",
  image: "https://img10.360buyimg.com/.../xxx.jpg",
  id: "novel-uuid-or-name"  // 小说唯一标识(用 title 文本作为 id)
}
```

**说明:** 京东发布页"小说"是单选下拉,只能选 1 个,所以 `jdNovel` 是单值字段(非数组)。空值用 `''` 表示未选择,非空值是 `{title, image, id}` 对象。

### 5.2 payload 字段(app.py 透传到 platform.py)

| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `jdRelatedType` | str | form | `'product'` / `'novel'` / `''` |
| `jdProducts` | list[dict] | form.jdProducts | 完整对象数组(含 id+trace),兼容旧字段名 `jdProductNames`(字符串数组) |
| `jdNovel` | dict \| str | form.jdNovel | 单个小说对象或空字符串 `''`(单选) |
| `jdDeclaration` | str | form | 创作声明文本(`'含AI生成内容'` 等 6 种之一) |
| `scheduleTime` | str | form | 定时发布时间 ISO 字符串,空时为 `''` |

## 6. 后端实现

### 6.1 `backend/impl/jd/_jd_link_ops.py`(约 350 行)

**纯函数,frame-first,所有操作以 frame 为参数。**

```python
# trace 签名
def trace_signature(trace: dict) -> tuple[str, int]:
    """(keyword, page)"""

# 商品抓取与导航
def scrape_products(frame) -> list[dict]:
    """抓当前激活面板的商品列表 -> [{title, image, id, price, shop_name}, ...]
    DOM 锚点: ._sku-card-mygoods-con_jvzh5_77
              ._sku-card-img_jvzh5_154 -> image
              ._sku-name_jvzh5_204 -> title
              ._price-value_jvzh5_277 -> price
              ._shop-name_jvzh5_295 -> shop_name
              商品 id 从 ._sku-card-desc_jvzh5_94 的 data-spm-click 属性或 SKU ID 提取"""

def switch_radio(frame, type_: str):
    """切商品/小说 radio: .jd-radio-wrapper input[value='1' 或 '3']"""

def click_add_card(frame):
    """点 .addgoods-upload[data-spm-click='publishGoodsAddGood']"""

def wait_panel_ready(frame, timeout: float = 10):
    """等 .jd-drawer-wrapper-body 出现且内容非空"""

# 搜索与分页
def clear_search(frame):
    """清空搜索框(京东有专门的搜索 input,.search-input-content-input 或 .jd-input)"""

def search(frame, keyword: str):
    """type + Enter 触发搜索,无条件复原 trace.keyword"""

def get_current_page(frame) -> int:
    """从 .jd-pagination-item-active 读取当前页码"""

def get_total_pages(frame) -> int:
    """从 .jd-pagination 最后一个 .jd-pagination-item 读取"""

def go_page(frame, page: int):
    """点击页码按钮或上下页按钮"""

# 勾选与关闭
def locate_and_check(frame, target_ids: list[str]) -> LocateResult:
    """按 id 精准勾选 -> {checked: [], already: [], disabled: [], missing: []}"""

def click_confirm(frame):
    """点 ._custom-footer-btns_38ot8_105 内 [data-spm-click='...SelectionAdd']"""

def close_panel(frame):
    """按 Esc 或点 .jd-drawer-close"""

# 小说下拉
def select_novel(frame, novel_id: str):
    """点 .jd-select 后输入关键词,等下拉出现,点目标 jd-select-item-option"""
```

### 6.2 `backend/impl/jd/picker.py`(约 300 行)

```python
class JdPickerSession:
    """单账号单 headless browser session"""
    def __init__(self, account_id: str):
        self.account_id = account_id
        self.browser = None   # headless
        self.page = None

    async def open(self, cookie_file: str):
        """create_browser(headless=True) → goto JD_PUBLISH_URL → wait_for_load
        → switch_radio('product') → click_add_card → wait_panel_ready
        → 返回首屏商品列表(无搜索 keyword 的全量)"""

    async def search(self, keyword: str) -> list[dict]:
        """clear_search → search → wait_for_results → scrape_products"""

    async def go_page(self, page: int) -> list[dict]:
        """go_page → wait_for_change → scrape_products"""

    async def close(self):
        """close_browser(self.browser, is_close_by_code=True)"""


class _SessionPool:
    """按 account_id 管理,同账号同时只能开一个 picker"""
    _sessions: dict[str, JdPickerSession] = {}

    def get_or_create(self, account_id: str) -> JdPickerSession: ...
    def release(self, account_id: str): ...


pool = _SessionPool()
```

**关键差异(vs 淘宝光合 picker):**
- 无 `switch_type`(京东只有商品一种 picker 来源)
- 无 `switch_tab`(京东无 tab 切换)
- 无 `apply_filter`(京东无 rule/category 筛选)
- 无 `load_more`(京东是分页器,不是"加载更多")

### 6.3 `backend/impl/jd/platform.py`(约 600 行)

```python
JD_PUBLISH_URL = "https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop"
JD_CREATOR_CENTER_URL = "https://dr.jd.com/jm/"
JD_COOKIE_INVALID_HOSTS = ["passport.jd.com", "passport.shop.jd.com"]


class JdPlatform(BasePlatform):
    platform_id = 20
    platform_key = "jd"
    platform_name = "京东"

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """create_browser(headless=False, login_mode=True) → goto JD_CREATOR_CENTER_URL
        → 等待用户扫码完成 → save cookie"""

    async def check_cookie(self, cookie_file: str) -> bool:
        """create_browser(headless=True) → goto JD_CREATOR_CENTER_URL
        → 检测 current_url 是否包含 JD_COOKIE_INVALID_HOSTS"""

    async def sync_profile(self, cookie_file: str):
        """create_browser(headless=True) → goto JD_CREATOR_CENTER_URL
        → 抓昵称头像 → 返回 {name, avatar}"""

    def open_creator_center(self, cookie_file: str) -> None:
        """同步版本包装(参考光合 L1702)"""

    def publish_video(self, **kwargs) -> bool:
        """同步入口"""
        return asyncio.run(self._publish_async(**kwargs))

    async def _publish_async(self, **kwargs):
        """主流程:create_browser(headless=False) → goto JD_PUBLISH_URL"""
        try:
            page = await self._goto_publish_page(cookie_file)

            # 1. 上传视频
            await self._upload_video(page, kwargs['video_path'])
            await self._wait_upload_complete(page)

            # 2. 设置封面(必填)
            if kwargs.get('cover_path'):
                await self._set_cover(page, kwargs['cover_path'])

            # 3. 填写标题(最多 27 字)
            await self._fill_title(page, kwargs['title'])

            # 4. 关联挂件
            related_type = kwargs.get('jd_related_type', '')
            if related_type == 'product' and kwargs.get('jd_products'):
                await _replay_products(page, kwargs['jd_products'])
            elif related_type == 'novel' and kwargs.get('jd_novel'):
                await self._select_novel(page, kwargs['jd_novel'])

            # 5. 创作声明(可选)
            if kwargs.get('jd_declaration'):
                await self._set_declaration(page, kwargs['jd_declaration'])

            # 6. 定时发布(可选)
            if kwargs.get('schedule_time'):
                await self._set_schedule_time(page, kwargs['schedule_time'])

            # 7. 点击发布按钮
            await self._click_publish(page)
            return await self._check_publish_success(page)
        finally:
            await close_browser(self.browser)
```

**`_replay_products`(参考淘宝光合 `_replay_groups` 但简化):**

```python
# platform.py 顶部 import
from backend.impl.jd import _jd_link_ops as link_ops


async def _replay_products(page, items: list[dict]):
    # 1. 打开关联商品抽屉(如果未开)
    await _link_ops.switch_radio(page, 'product')
    await _link_ops.click_add_card(page)
    await _link_ops.wait_panel_ready(page)

    # 2. 按 (keyword, page) 分组
    groups = defaultdict(list)
    for item in items:
        sig = (item['trace']['keyword'], item['trace']['page'])
        groups[sig].append(item)

    # 3. 每组单独重走
    for (keyword, page), group_items in groups.items():
        await _link_ops.clear_search(page)
        if keyword:
            await _link_ops.search(page, keyword)
            await _link_ops.wait_search_results(page)
        if page > 1:
            for _ in range(page - 1):
                await _link_ops.go_next_page(page)
                await _link_ops.wait_page_change(page)
        target_ids = [it['id'] for it in group_items]
        result = await _link_ops.locate_and_check(page, target_ids)
        if result.missing:
            raise RuntimeError(f"关联商品失败,未找到商品: {result.missing}")

    # 4. 关闭抽屉
    await _link_ops.click_confirm(page)
```

### 6.4 `backend/blueprints/jd_bp.py`(约 200 行)

参考 `backend/blueprints/taobao_guanghe_bp.py`:

- 全局 picker event loop(后台 daemon 线程,`asyncio.new_event_loop()` + `run_forever()`)
- `run_picker_async(coro, timeout)` 跨线程提交协程
- 4 个路由:
  - `POST /api/jd/picker/open` → 启动浏览器进入选择面板
  - `POST /api/jd/picker/search` → 搜索并返回商品列表
  - `POST /api/jd/picker/go_page` → 翻页并返回商品列表
  - `POST /api/jd/picker/close` → 释放浏览器

## 7. 前端实现

### 7.1 `frontend/src/components/JdItemPicker.vue`(约 550 行)

仿 `GuangheItemPicker.vue` 但简化:

**Props:**
- `modelValue: Boolean` — 可见性
- `accountId: String` — 用于打开 picker 的账号
- `initSelected: Array` — 已选项回显

**UI 元素:**
- 顶部搜索框(placeholder: "请输入商品名称或 skuid 搜索本店商品")
- 商品列表(网格卡片,点击切换选中状态)
- 底部 el-pagination 分页器
- 底部"确定/取消"按钮
- 选中数量提示 "已选 N/10"

**关键方法:**
- `onCardClick(item)` — 选中/取消时打包 trace `{keyword, page}`
- `onSearch()` — 触发 `pickerSearch`,重置 currentPage = 1
- `onPageChange(page)` — 触发 `pickerGoPage`
- `onConfirm()` — emit `confirm` 事件,传完整对象数组 `[{title, image, id, trace}, ...]`
- `onClose()` — 调 `pickerClose` 释放浏览器

**与光合差异:**
- 无 `mode` 参数(只支持商品)
- 无 tab 切换 UI
- 无 rule/category 筛选 UI
- 用 el-pagination 替代"加载更多"

### 7.2 `frontend/src/api/jd.js`(约 45 行)

```javascript
import { request } from '@/utils/request'

export const jdApi = {
  pickerOpen: (accountId) => request.post('/api/jd/picker/open', { accountId }),
  pickerSearch: (accountId, keyword, page) =>
    request.post('/api/jd/picker/search', { accountId, keyword, page }),
  pickerGoPage: (accountId, page) =>
    request.post('/api/jd/picker/go_page', { accountId, page }),
  pickerClose: (accountId) =>
    request.post('/api/jd/picker/close', { accountId }),
}
```

### 7.3 `frontend/src/views/PublishCenter.vue` 修改

参考光合 L184-256 块,添加京东专属卡片:

```vue
<template v-if="selectedPlatform === 'jd'">
  <!-- 关联挂件 radio: 不关联 / 商品 / 小说 -->
  <el-radio-group v-model="form.jdRelatedType">
    <el-radio value="">不关联</el-radio>
    <el-radio value="product">商品</el-radio>
    <el-radio value="novel">小说</el-radio>
  </el-radio-group>

  <!-- 商品选择 -->
  <div v-if="form.jdRelatedType === 'product'">
    <div v-for="(item, idx) in form.jdProducts" :key="item.id">
      <img :src="item.image" />
      <span>{{ item.title }}</span>
      <el-button @click="form.jdProducts.splice(idx, 1)">删除</el-button>
    </div>
    <el-button :disabled="form.jdProducts.length >= 10" @click="openJdPicker">
      添加商品 ({{ form.jdProducts.length }}/10)
    </el-button>
  </div>

  <!-- 小说选择(下拉搜索) -->
  <div v-if="form.jdRelatedType === 'novel'">
    <RemoteSearchSelect
      v-model="form.jdNovel"
      platform="jd"
      type="novel"
      :account-id="getCurrentJdAccountId()"
    />
  </div>
</template>

<JdItemPicker
  v-model="jdPickerVisible"
  :account-id="jdPickerAccountId"
  :init-selected="form.jdProducts"
  @confirm="onJdPickerConfirm"
/>
```

**Script 关键方法:**
- `openJdPicker()` — 从已勾选账号找京东账号 → 设置 `jdPickerAccountId` → 打开 picker
- `onJdPickerConfirm(items)` — 用 picker 返回数组替换 `form.jdProducts`
- `removeJdProduct(idx)` — 删除某项
- `getCurrentJdAccountId()` / `findAnyJdAccountId()` — 兜底找账号

**form 字段默认值(在 platforms.js 的 defaultSettings 中):**
```js
{
  title: '',
  description: '',  // 京东无描述,可不填
  jdRelatedType: '',
  jdProducts: [],
  jdNovel: '',
  jdDeclaration: '',
  scheduleTime: '',
}
```

### 7.4 `frontend/src/config/platforms.js` 添加 JD 配置

```javascript
// 顶部 import 区追加
import logoJd from '@/assets/logos/jd.png'

// PLATFORMS 对象内添加 JD 配置
JD: {
  id: 20,
  key: 'jd',
  name: '京东',
  shortName: '京东',
  letter: '京',
  logo: logoJd,
  color: '#E1251B',
  bgColor: 'rgba(225, 37, 27, 0.15)',
  cssClass: 'jd',
  creatorUrl: 'https://dr.jd.com/jm/',
  settingsFields: [
    { key: 'jdDeclaration', label: '创作声明', type: 'select', required: false,
      options: [
        { value: '含AI生成内容', label: '含AI生成内容' },
        { value: '含虚构演绎内容', label: '含虚构演绎内容' },
        { value: '内容为转载', label: '内容为转载' },
        { value: '个人观点,仅供参考', label: '个人观点,仅供参考' },
        { value: '内容含营销广告', label: '内容含营销广告' },
        { value: '内容无需标注', label: '内容无需标注' },
      ]},
    { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
  ],
  defaultSettings: {
    title: '',
    description: '',
    jdRelatedType: '',
    jdProducts: [],
    jdNovel: '',
    jdDeclaration: '',
    scheduleTime: '',
  },
},
```

## 8. 平台注册与集成

### 8.1 `backend/impl/registry.py`

```python
def _populate_registry():
    ...
    from backend.impl.jingmai.platform import JingmaiPlatform
    from backend.impl.jd.platform import JdPlatform  # 新增

    register(JingmaiPlatform)
    register(JdPlatform)  # 新增
```

### 8.2 `backend/app.py`(4 处 publish 路由)

```python
# 顶部 import + 注册新蓝图
from backend.blueprints.jd_bp import bp as jd_bp
app.register_blueprint(jd_bp)

# 4 处 publish 路由统一添加 jd 字段(参考光合 L1062-1066)
publish_video_platform(
    data, ...,
    # jd 字段
    jd_related_type=data.get('jdRelatedType', ''),
    jd_products=data.get('jdProducts') or data.get('jdProductNames') or [],
    jd_novel=data.get('jdNovel', ''),
    jd_declaration=data.get('jdDeclaration', ''),
    schedule_time=data.get('scheduleTime', ''),
)
```

### 8.3 `backend/ext_api/__init__.py`

```python
# 1. _PLATFORM_ID_MAP
_PLATFORM_ID_MAP = {
    ...
    19: ('jingmai', '京东京麦'),
    20: ('jd', '京东'),
}

# 2. platform_map
platform_map = {
    ...
    'jingmai': '京东京麦',
    'jd': '京东',
}

# 3. type_to_platform
type_to_platform = {
    ...
    'jingmai': 19,
    'jd': 20,
}
```

## 9. 浏览器策略

| 阶段 | headless | 理由 |
|---|---|---|
| `login()` | False | 用户扫码需要看到浏览器 |
| `check_cookie()` | True | 后台探测,不打扰用户 |
| `sync_profile()` | True | 后台抓取 |
| `publish_video()` | False | 便于调试/dry-run 时观察 |
| `picker`(`picker.py`) | True | 后台运行,减少对用户桌面的干扰 |

发布收尾必须用 `close_browser(self.browser, is_close_by_code=True)`,让 watchdog 不 cancel 当前 task。

## 10. 错误处理

| 场景 | 处理 |
|---|---|
| Cookie 失效 | `check_cookie` 返回 False,前端提示重新登录 |
| 视频上传超时(默认 5 分钟) | `wait_upload_complete` 抛 `RuntimeError("视频上传超时")` |
| 视频封面未设置 | 检测 `jd-form-item-has-success`,未设则阻断发布 |
| 关联商品 missing | `_replay_products` 抛 `RuntimeError(f"未找到商品: {ids}")` |
| 关联商品 disabled(被禁卖) | 同上,纳入 missing 列表 |
| 关联小说无结果 | `_select_novel` 抛 `RuntimeError("未找到小说")` |
| 创作声明未选 | 可选,不阻断 |
| 定时发布时间早于当前 | DatePicker 校验失败,前端提示 |
| 发布按钮 disabled 持续 | 检测 `_publishBtn` 的 `disabled`,超时未变 false 抛错 |
| 发布跳转失败 | 检测 URL 跳转到其他页面,超时抛 `RuntimeError("发布失败,未检测到跳转")` |
| picker session 冲突 | `_SessionPool` 同账号已有 session,抛 `RuntimeError` 提示前端先关闭 |

## 11. 边界情况

1. **京东视频发布页无 iframe** — 整个 DOM 在同一个 page,不需要 `_find_publish_frame`(对比淘宝光合)
2. **小说下拉异步加载** — type 后需等下拉出现再 click,参考视频号 RemoteSearchSelect
3. **草稿模式** — 京东有"保存草稿"按钮,工具不主动调用(与光合一致)
4. **关联挂件为空** — `jdRelatedType == ''` 时跳过整段关联挂件设置
5. **视频封面必填** — DOM 有 `*` 标记,需先 set cover 再 fill title,否则表单校验失败
6. **picker session 复用冲突** — `_SessionPool` 按 account_id 锁
7. **同一商品多账号重复选择** — picker 关闭时释放,每个账号独立 session
8. **京东 SPA 路由切换** — 发布页是 hash 路由,`goto JD_PUBLISH_URL` 后需等待 `#/n/publish-video.html` 路由渲染完毕

## 12. dry-run 模式

参考光合 `f95570b`,添加 `JD_DRY_RUN` 环境变量开关:

```python
if os.environ.get('JD_DRY_RUN'):
    # 走完上传/封面/标题/关联挂件/创作声明/定时发布,但跳过点击发布
    return True
```

便于本地调试,不需要真发布就能验证整个流程。

## 13. 后续扩展(本期不做)

- **关联京东店铺**: 京东未来可能允许关联店铺,届时可扩展 picker 支持店铺 tab
- **章节分段**: 京东发布页有"章节分段"功能(测评标签),本期不实现
- **任务活动**: 京东发布页有"任务活动"选择,本期不实现
- **关联商品"站内搜索"和"链接导入"**: 用户已确认只保留"本店商品"

## 14. 验证方式

用户自行测试,不写自动化测试。验证清单:
- 单视频 + 单商品(单一 keyword + page=1)
- 多商品(同一 keyword 不同页 + 不同 keyword)trace 分组重现
- 关联小说(无 picker)
- 定时发布(无/有)
- 创作声明(6 种不同选项)
- 视频上传超时场景
- 关联商品 missing 场景
- 草稿保存/恢复(往返 draft_data JSON)