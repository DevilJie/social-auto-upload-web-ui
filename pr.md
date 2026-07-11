# CSDN 平台接入 + Cookie 一键导入 15 平台 + 批量检查稳定性修复 — v1.2.0

## 概述

本次迭代围绕「账号接入效率」展开，做了三件事：**① 接入 CSDN 创作平台**（登录 + 视频发布）；**② 把 cookie 字符串一键导入账号的能力从 2 个平台扩展到全部 15 个**，并重设计了导入弹窗 UI；**③ 修复账号管理「批量检查」功能导致后端假死的严重 bug**。同时统一了 CSDN/知乎的资料同步为无头模式，CSDN 的 cookie 导入按真实多子域结构智能推断 domain/secure/httpOnly 属性。

---

## PR 类型

- [x] 新功能（CSDN 平台接入、15 平台 cookie 导入、导入弹窗重设计）
- [x] Bug 修复（批量检查后端假死、检查弹窗不显示、CSDN cookie 登录态丢失）
- [x] 工程效率（启动脚本强制更新）
- [x] 文档（v1.2.0 更新日志）

---

## 核心变更

### 1. CSDN 创作平台接入（`backend/impl/csdn/`）

- 新增 `CsdnPlatform`（platform_id=15），继承 `BasePlatform`，注册到 `registry.py`
- **登录**：打开 `mp.csdn.net` 创作者首页，用户在可见浏览器手动登录，检测到 `div.user-info-box` 出现即视为登录成功
- **check_cookie**：headless 访问创作者首页，判断用户信息卡是否存在
- **sync_profile**：从 `div.user-info-box` 抓昵称（`p.name` 的 title 属性）+ 头像
- **publish_video**：完整的视频发布流程
  - 上传视频文件（定位 `input[type=file][accept*=video]`）
  - 等待「上传成功」文案（`.gement li.text`）
  - 设置封面（隐藏 input + 裁剪弹窗确认）
  - 填写标题（≤30 字）、简介（≤150 字）、标签（≤3 个，输入+回车激活）
  - 可选「是否推荐」勾选
  - 点击发布按钮，页面跳转即成功
- 视频限制常量：`CSDN_MAX_TAGS=3` / `CSDN_MAX_TITLE_LEN=30` / `CSDN_MAX_DESC_LEN=150`，同步到 `videoLimits.js`
- 前端 logo + platforms.js 配置接入

### 2. Cookie 字符串一键导入 — 扩展到全部 15 平台

#### 后端：抽象到 BasePlatform，子类 3 行接入

- `BasePlatform` 新增 `supports_cookie_import` / `platform_cookie_domain` 类属性 + `_parse_cookie_to_storage_state` hook
- `BasePlatform.import_cookie` 默认实现，封装完整 4 步进度流程：
  1. **解析 cookie 字符串**（子类 hook）
  2. **生成 storage_state JSON**（先不写 user_info，验证有效性）
  3. **sync_profile** 抓取真实昵称/头像（复用账号列表「同步」按钮的同一调用）
  4. **创建账号记录**（写入 user_info；cookie 失效则清理临时文件并报错）
- **15 个平台全部接入**，各平台只需声明 `supports_cookie_import = True` + `platform_cookie_domain` + `_parse_cookie_to_storage_state`：

  | 平台 | cookie domain |
  |------|--------------|
  | 小红书 | `.xiaohongshu.com` |
  | 视频号 | `.qq.com` |
  | 抖音 | `.douyin.com` |
  | 快手 | `.kuaishou.com` |
  | B站 | `.bilibili.com` |
  | 百家号 | `.baidu.com` |
  | TikTok | `.tiktok.com` |
  | YouTube | `.youtube.com` |
  | 腾讯视频 | `.qq.com` |
  | 爱奇艺 | `.iqiyi.com` |
  | 微博 | `.weibo.com` |
  | 支付宝 | `.alipay.com` |
  | 今日头条 | `.toutiao.com` |
  | 知乎 | `.zhihu.com` |
  | CSDN | `.csdn.net` |

#### CSDN 专属：智能推断 cookie 属性

- CSDN 的登录态 cookie 散落在多个子域（`.csdn.net` / `passport.csdn.net` / `msg.csdn.net` 等），纯 `k=v` 字符串不带 domain/secure/httpOnly 信息
- `_parse_cookie_to_storage_state` 重写，维护从真实文件 dump 得到的属性映射表：
  - waf 系列（`https_waf_cookie`/`waf_captcha_marker`）分到 `passport.csdn.net`
  - `SESSION` 复制一份到 `msg.csdn.net`
  - `httpOnly`/`secure` 按真实登录态精确设置（不再一刀切 True/False）

#### 前端：导入弹窗 UI 重设计

- 左右分栏布局（660px）：左侧平台扁平卡片列表 + 搜索框，右侧 cookie 输入
- 平台卡片复用 `LoginDialog` 风格（32×32 logo + 品牌色背景）
- 支持搜索过滤（按中文名/key）、垂直滚动（自定义滚动条）
- cookie 输入框等宽字体 + 底部 InfoFilled 提示框
- 导入进度走 SSE 4 步流式推送（解析 → 生成文件 → 同步资料 → 创建账号）

### 3. 批量检查稳定性修复（后端假死）

**根因**：账号管理「批量检查」复用了发布前检查弹窗 `PrePublishCheckDialog`，但该弹窗的 fixing 阶段会同时对所有失效账号自动发起 SSE 登录。并发 4 个 `checkAccount`（占满 Waitress 默认 4 线程）+ N 个 SSE `/login` 长连接（挤不进线程池）→ 后端假死（HTTP 000）。

**修复**：
- **后端 Waitress 线程数 4 → 16**（`app.py`：`serve(..., threads=16)`），让并发 check + SSE login 不再互相挤占
- **前端检查并发数 4 → 2**，降低同时拉起的 headless 浏览器数量
- **fixing 阶段移除自动并发重登**，改为用户在失效列表里逐个点「重新登录」（不再一次弹 N 个浏览器窗口）
- **修复检查弹窗不显示**：`PrePublishCheckDialog` 缺 `v-model` 绑定，导致 `emit('update:modelValue')` 无接收方，弹窗永远不显示
- **新增 `mode` prop** 区分「账号检查」/「发布前检查」文案，交互逻辑完全一致

### 4. CSDN / 知乎资料同步改无头

- `csdn/platform.py` + `zhihu/platform.py` 的 `sync_profile` 由 `headless=False` 改为 `headless=True`，与其它 13 个平台一致
- 导入 cookie 时不再弹出可见浏览器窗口

### 5. Dashboard 平台统计跑马灯

- 参考 `DraftBox.channels` 风格，平台统计区改为横向滚动跑马灯
- 有账号的平台高亮（品牌色），溢出时自动滚动
- `ResizeObserver` 监听容器宽度变化，动态触发跑马灯

### 6. 启动脚本强制更新

- `start.sh` / `start-beta.sh` / `start.bat` / `start-beta.bat`
- 移除「发现新版本！是否更新？[Y/n]」交互询问
- 已有项目代码时直接 `git fetch + reset --hard origin/<branch>`
- 无法连接 GitHub 时提示并继续使用本地版本
- 修复 `start-beta.sh` 第 88/105 行误引 `start.sh` 的 bug

---

## 涉及文件

```
backend/app.py                                    | 后端假死修复(threads=16)
backend/impl/csdn/                                | 新增 CSDN 平台实现(852 行)
backend/impl/base_platform.py                     | cookie 导入抽象层
backend/impl/{各平台}/platform.py                 | 15 平台接入 cookie 导入
backend/impl/zhihu/platform.py                    | sync_profile 改无头
backend/impl/_utils.py                            | scrape_csdn_profile
frontend/src/components/PrePublishCheckDialog.vue | mode prop + 交互修复
frontend/src/views/AccountManagement.vue          | 批量检查复用 + 导入弹窗
frontend/src/views/Dashboard.vue                  | 平台统计跑马灯
frontend/src/views/PublishCenter.vue              | 适配
changelog/20260708.html                           | v1.2.0 更新日志
start*.sh / start*.bat                            | 强制更新
```

---

## 验证

- ✅ Cookie 导入：15 平台粘贴 cookie 字符串 → 4 步进度 → 抓到昵称头像 → 账号列表出现
- ✅ CSDN cookie 导入：属性对齐真实文件（domain/secure/httpOnly 分布一致）
- ✅ 批量检查：进度条正常滚动 → 失效账号显示「重新登录」按钮（不再自动弹窗）→ 后端全程响应正常
- ✅ 发布前检查：与账号管理交互一致，文案区分显示

---

## 不在本次范围

- 纯 `k=v` 字符串无法获取 httpOnly 的 WAF cookie（如 CSDN 的 `https_waf_cookie`），若平台强制校验 WAF 仍可能登录失败，需后续支持浏览器扩展导出完整 JSON
- 不含数据库 schema 变更
