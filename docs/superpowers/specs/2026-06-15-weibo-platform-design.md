# 微博渠道接入设计 Spec

**日期**: 2026-06-15
**分支**: `feature/20260615-1`
**作者**: Claude (brainstorming + implementation)

## 目标

把微博（weibo.com）作为第 11 个平台接入到现有 Registry 模式，与 iqiyi / tencent_video / xiaohongshu 等保持同构。

本轮范围**仅包含账号管理**：
- 浏览器内登录流程
- cookie 有效性检查
- 同步昵称头像
- 打开创作中心

**不做**：发布视频（`publish_video` 保持 `NotImplementedError`）、发布图文、抽帧、定时发布等。后续按平台补齐节奏单独排期。

## 架构总览

不动 `BasePlatform` 抽象、不动 `app.py` 路由（`/login` `/syncProfile` `/openCreatorCenter` 已是平台无关）、不动 `_browser.py`、不动数据库 schema。

变更面：
```
backend/impl/
├── registry.py          # +1 行注册 (11, ".weibo.platform", "WeiboPlatform")
├── _utils.py            # +scrape_weibo_profile / +PLATFORM_SYNC_URLS[11] / +PLATFORM_SCRAPE_FNS[11]
└── weibo/               # 新目录
    ├── __init__.py
    └── platform.py      # WeiboPlatform

backend/app.py           # PLATFORM_MAP[11] / PLATFORM_ID_TO_KEY[11]
frontend/src/config/platforms.js   # +PLATFORMS.WEIBO 条目
frontend/src/assets/logos/weibo.png # +logo（若无则用首字母占位）
```

## 平台常量

```python
platform_id  = 11
platform_key = "weibo"
platform_name = "微博"

_WEIBO_CREATOR_URL    = "https://weibo.com/set/index"   # 创作中心主入口
_WEIBO_LOGIN_HOST     = "passport.weibo.com"            # 用于判断是否在登录页
_WEIBO_LOGIN_PATH     = "/sso/signin"                   # 用于判断是否在登录页
```

注册表注入：
```python
(11, ".weibo.platform", "WeiboPlatform")
```

`PLATFORM_MAP[11] = "微博"`
`PLATFORM_ID_TO_KEY[11] = "weibo"`

## 组件设计

### `WeiboPlatform` 类

继承 `BasePlatform`，实现 4 个方法（`publish_video` 不实现，继承基类抛 `NotImplementedError`）。

#### `login(id, status_queue, account_id=None)`

伪代码：
```python
async def login(self, id, status_queue, account_id=None):
    browser = await self.create_browser(login_mode=True)
    success = False
    try:
        context = await self.create_context(browser)
        try:
            page = await context.new_page()
            await page.goto(_WEIBO_CREATOR_URL)
            # 等待用户登录的 framenavigated
            enter_login = asyncio.Event()
            exit_login = asyncio.Event()

            async def _on_nav(frame):
                if frame != page.main_frame:
                    return
                url = frame.url
                if _WEIBO_LOGIN_HOST in url and _WEIBO_LOGIN_PATH in url:
                    enter_login.set()
                elif enter_login.is_set() and _WEIBO_LOGIN_HOST not in url:
                    exit_login.set()

            page.on("framenavigated", lambda f: asyncio.create_task(_on_nav(f)))
            # 等到登录后回到 weibo.com
            await exit_login.wait()
            await save_login_result(
                context, page,
                platform_id=self.platform_id,
                platform_name=self.platform_name,
                status_queue=status_queue,
                scrape_fn=scrape_weibo_profile,
                account_id=account_id,
            )
            success = True
        finally:
            await context.close()
    finally:
        if success:
            await browser.close()
```

**关键决策**：
- 不点击任何"登录"按钮 —— `goto weibo.com/set/index` 命中未登录即被服务器重定向到 `passport.weibo.com/sso/signin`，省去对微博 DOM 的耦合。
- `enter_login` / `exit_login` 双事件：避免用户开多个标签导致首屏 framenavigated 误判为"进入登录"。
- `login_mode=True` 浏览器关闭自动 cancel asyncio task，沿用小红书模式。

#### `check_cookie(cookie_file)`

与小红书同构：
```python
async def check_cookie(self, cookie_file):
    cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
    if not os.path.exists(cookie_path):
        return False
    browser = await self.create_browser(headless=True)
    try:
        context = await self.create_context(browser, storage_state=cookie_path)
        page = await context.new_page()
        try:
            await page.goto(_WEIBO_CREATOR_URL, timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await asyncio.sleep(2)
            if _WEIBO_LOGIN_HOST in page.url:
                return False
            return True
        except Exception:
            return False
        finally:
            await context.close()
    finally:
        await browser.close()
```

#### `open_creator_center(cookie_file)`

100% 复制 `XiaohongshuPlatform.open_creator_center` 的 daemon thread 模式（同步入口 + `wait_for_event("close", timeout=0)`），把 URL 换为 `_WEIBO_CREATOR_URL`。

#### `sync_profile(cookie_file)`

```python
async def sync_profile(self, cookie_file):
    cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
    browser = await self.create_browser(headless=True)
    try:
        context = await self.create_context(browser, storage_state=cookie_path)
        page = await context.new_page()
        try:
            await page.goto(_WEIBO_CREATOR_URL, wait_until="networkidle", timeout=30000)
            return await scrape_weibo_profile(page)
        except Exception as e:
            logger.info(f"[weibo] sync profile failed: {e}")
            return "", ""
        finally:
            await context.close()
    finally:
        await browser.close()
```

### `scrape_weibo_profile(page)` —— 专用 scraper

微博创作中心 DOM 使用 CSS-in-JS hash class（如 `_wrap_1l406_3`），通用 JS 注入的 class 选择器会全部失效。需要专用函数。

**抓取策略**（按优先级）：

1. **头像**：遍历所有 `<img>`，按域名优先级匹配 `sinaimg.cn` / `tvax2.sinaimg.cn` / `wx1.sinaimg.cn` 等微博 CDN。过滤掉 `icon` / `logo` / `qrcode` / `placeholder`。
2. **昵称**：找到头像 `<img>` 后，向上 5 层父容器内查找 leaf 元素（`span` / `div` 文本节点），用 `_utils.py` 中已有的 `isValidName` 函数过滤。
3. **失败兜底**：返回 `("", "")`，由 `save_login_result` 兜底生成 `"微博用户{时间戳}"`。

实现放在 `backend/impl/_utils.py`，与 `scrape_bilibili_profile` / `scrape_tencent_profile` 等并列。

注册到 `PLATFORM_SCRAPE_FNS[11] = scrape_weibo_profile`。
`PLATFORM_SYNC_URLS[11] = "https://weibo.com/set/index"`。

## 错误处理

| 场景 | 行为 |
|---|---|
| 用户关浏览器 | `login_mode=True` 自动 cancel task → SSE 推 `{"status": "error", "msg": "用户关闭了浏览器"}` |
| profile 抓取失败 | `scrape_weibo_profile` 返回 `("", "")` → `save_login_result` 兜底用户名 |
| cookie 文件不存在 | `check_cookie` 返回 `False` |
| `goto` 超时 | `check_cookie` 异常路径返回 `False`；`sync_profile` 返回 `("", "")` |
| context / browser 异常 | `finally` 块保证释放资源 |

## 数据流

```
前端 AccountManagement.vue 点击"登录微博"
  → GET /login?type=11&id=xxx
    → app.py 启动 daemon thread 跑 platform.login(...)
      → 打开 stealth 浏览器到 weibo.com/set/index
        → 未登录被重定向到 passport.weibo.com → 等待用户
      → 用户在弹窗内完成登录 → URL 回到 weibo.com
        → save_login_result: 抓 profile / 存 cookie / 写 DB
        → SSE 推 {"status": "200", "name": ..., "avatar": ...}
前端关闭 SSE 连接
```

## 测试

后端浏览器自动化本身不写 E2E（与现有平台一致），但**注册完整性与纯函数**需覆盖。

新增 `backend/tests/impl/test_weibo_platform.py`：

1. **类属性**：
   - `WeiboPlatform().platform_id == 11`
   - `WeiboPlatform().platform_key == "weibo"`
   - `WeiboPlatform().platform_name == "微博"`

2. **注册表**：
   - `from impl.registry import is_supported, get_platform`
   - `is_supported(11) is True`
   - `get_platform(11).__class__.__name__ == "WeiboPlatform"`

3. **平台映射**：
   - `from app import PLATFORM_MAP, PLATFORM_ID_TO_KEY`
   - `PLATFORM_MAP[11] == "微博"`
   - `PLATFORM_ID_TO_KEY[11] == "weibo"`

4. **scraper 纯函数**（用 `unittest.mock.AsyncMock` 模拟 page）：
   - 给定 `evaluate()` 返回含 `sinaimg.cn` 头像 + 合法昵称 → 返回正确 (name, avatar)
   - 给定 `evaluate()` 抛异常 → 返回 `("", "")`
   - 头像 src 含 `icon` / `logo` → 被过滤

5. **基类抽象**：
   - `WeiboPlatform().publish_video()` 抛 `NotImplementedError`（本轮范围外）

## 风险与权衡

| 风险 | 缓解 |
|---|---|
| 微博前端 DOM 经常改版，scraper 选择器失效 | 抓取逻辑只依赖图片 CDN 域名 + leaf 文本，相对稳定；若完全失效 fallback 到默认昵称 |
| 微博登录风控（异地/设备/IP） | 不在代码层处理；浏览器走 cloakbrowser 隐匿；用户自己重试 |
| `weibo.com` 改路径（如 `/set/index` 改名） | 集中在一个常量 `_WEIBO_CREATOR_URL`；改时单点替换 |
| passport 登录页改 URL | `enter_login` / `exit_login` 监听 `framenavigated`，不写死具体 URL；判断条件仅检查 host |

## 后续任务（不在本轮）

- 实现 `publish_video` 微博视频发布（覆盖创作中心"头条文章"或"视频"入口）
- 接入前端 `PublishCenter.vue` 的微博发布面板
- 接入 `frontend/src/views/AccountManagement.vue` 的微博账号管理（如果只是 platforms.js 加条目，前端默认就支持）
- `data/cookiesFile/` 清理策略（多平台 UUID 不冲突，已自动规避）
