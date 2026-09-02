# IP 池集成设计方案

**日期**: 2026-09-02
**分支**: `feature/20260902`
**状态**: 方案评审（未实施）

## 目标

为多账号发布场景引入代理 IP 池：账号（或账号组）通过固定的出口 IP 访问平台，
降低多账号同 IP 导致的关联/风控风险；代理不可用时可检测、可更换、可降级。

## GitHub 开源 IP 池项目盘点

（star 数于 2026-09-02 从 GitHub 页面核实）

| 项目 | Stars | 维护状态 | 架构 | 存储 | License |
|---|---|---|---|---|---|
| [jhao104/proxy_pool](https://github.com/jhao104/proxy_pool) | 23.6k | **活跃**（持续提交，CI + codecov，fetcher 源 2026 年仍在更新） | fetcher → validator → db → Flask API/CLI，四层分离 | **Redis/SSDB（必须）** | MIT |
| [Python3WebSpider/ProxyPool](https://github.com/Python3WebSpider/ProxyPool) | 6.2k | 维护中 | getter/tester/server（aiohttp） | **Redis（必须）** | MIT |
| [qiyeboy/IPProxyPool](https://github.com/qiyeboy/IPProxyPool) | 4.3k | 停滞（py2 时代技术栈：web.py + gevent） | Django 风格 | SQLite | — |
| [constverum/ProxyBroker](https://github.com/constverum/ProxyBroker) | 4.2k | 不维护（Python 3.10+ 兼容问题 [#194](https://github.com/constverum/ProxyBroker/issues/194)） | async finder/checker/serve | 内存 | Apache-2.0 |

值得注意：Python3WebSpider/ProxyPool 的 README 官方原话——
「本代理池基于公开代理源搭建，可用性并不高，很可能上百上千个代理中才能找到一两个可用代理，
**不适合直接用于爬取任务**」。这是免费公共代理池的普遍现状。

## 选型结论与理由

**选择 jhao104/proxy_pool 作为参考框架，但不以服务方式部署，而是库化复用其设计。**

### 为什么选它

1. **社区与维护**：23.6k stars，四者中唯一保持高频维护（对比：IPProxyPool 停更、
   ProxyBroker 在 Python 3.12 上有兼容性问题），出问题能找到大量 issue/解答。
2. **架构最干净**：fetcher（15+ 免费代理源，`yield "host:port"` 极简接口）→
   validator（http/https 分别校验、fail_count 递增淘汰、`api.ip.sb` 地域识别）→
   db（工厂模式，接口为 get/put/update/delete/getAll/changeTable）→ API。
   分层边界清晰，非常适合拆开按需取用。
3. **MIT 协议**：唯一允许我们直接复制源码改造而不产生传染性义务的宽松协议
   （Apache-2.0 需保留 NOTICE 声明，GPL 系不可考虑）。
4. **Python 技术栈一致**：与本项目后端（Python 3.12 + requests）无缝。

### 为什么不以服务方式集成（关键决策）

proxy_pool 的运行形态是「独立进程 + Redis + Flask API」。对本项目是灾难：

| 约束 | 说明 |
|---|---|
| 桌面分发 | 本项目是 Tauri/NSIS 桌面应用，用户机器上**没有 Redis，也没有 Docker**。要求用户装 Redis 不可接受 |
| 进程模型 | 后端已由 Flask(5409) 承担。再加 proxy_pool 进程 + Redis 进程 = 3 个进程的安装/启动/守护复杂度 |
| 依赖污染 | 直接 `pip install` 会拉进 gunicorn、APScheduler、旧版 Flask/werkzeug 锁版等，与本项目 Flask 版本冲突风险高 |

因此：**复用其 fetcher 源码（MIT，可合法复制）与 validator 的校验/淘汰设计，
存储落在现有 SQLite，调度用本项目已有的后台线程模式（参考视频号保活线程），
不引入任何新进程、新中间件。**

### 为什么核心是「账号绑定」而不是「随机轮换」

这一点与爬虫代理池有本质区别，也是本方案与 proxy_pool 原设计最大的分歧：

- 爬虫模型：每次请求随机换 IP，IP 是消耗品。**免费代理适配这个模型。**
- 账号资产模型（本项目）：IP 是账号的「网络身份」。平台风控的核心信号正是
  **同一登录态账号的出口 IP 频繁地理跳变**（异地登录 → 强制验证 → 封号）。
  正确模型是 **sticky：一个账号固定绑定一个出口 IP**，尽量不换。

推论：**免费公共代理不适合本项目的登录/发布场景**，理由：

1. **账号安全**：登录态（cookie）流量经过陌生第三方代理。恶意代理可观测 SNI、
   劫持 DNS、对降级 HTTP 的请求直接读取内容——等于把账号交给陌生人。
2. **IP 质量**：免费代理是被大量爬虫共享的黑名单 IP，抖音/小红书/微博等平台
   对数据中心/被滥用 IP 秒级触发验证码与风控。
3. **存活时间**：分钟级失效，与「账号固定 IP」的需求完全相反。

所以方案的分层：**付费/自有代理管理为主路径，免费源采集为可选辅助（默认关闭）**。

## 集成方案

### 架构

```
┌────────────────────────────────────────────────────────────────┐
│ frontend                                                        │
│  Settings.vue:「代理池」卡片（列表/添加/测速/开关）              │
│  AccountManagement.vue: 账号卡片显示绑定代理 + 换绑              │
└───────────────┬────────────────────────────────────────────────┘
                │ REST（新 Blueprint backend/proxy_api/）
┌───────────────▼────────────────────────────────────────────────┐
│ backend                                                         │
│  impl/proxy_pool/                                               │
│   manager.py   取代理：账号绑定解析 → 健康代理；失败降级链        │
│   checker.py   后台线程：定时测活（延迟/出口IP/地域）→ 状态更新   │
│   fetcher.py   （可选）免费源采集，移植 jhao104 fetcher（MIT）    │
│  impl/_browser.py::create_browser(proxy=..., geoip=True)        │
│   ↑ 单一注入点。BasePlatform.create_browser 透传                 │
│  SQLite: proxy_pool 表 + user_info.proxy_id 列                   │
└────────────────────────────────────────────────────────────────┘
                │ launch_async(proxy="http://user:pass@host:port")
┌───────────────▼────────────────────────────────────────────────┐
│ CloakBrowser（已原生支持，0.5.7 实测确认）                       │
│  · HTTP/HTTPS/SOCKS5 + 凭证（inline auth / Playwright dict）    │
│  · geoip=True → 出口 IP 反查时区/语言并自动对齐指纹              │
│  · WebRTC 出口 IP 伪装（--fingerprint-webrtc-ip=auto）           │
└────────────────────────────────────────────────────────────────┘
```

### 数据模型

```sql
-- init_db.py 新增
CREATE TABLE IF NOT EXISTS proxy_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,               -- 备注名，如「青 network-家宽-沪01」
    protocol TEXT NOT NULL,           -- http / https / socks5
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    username TEXT DEFAULT '',
    password TEXT DEFAULT '',
    region TEXT DEFAULT '',           -- checker 写入：出口城市/运营商
    exit_ip TEXT DEFAULT '',          -- checker 写入：出口 IP
    latency_ms INTEGER DEFAULT 0,     -- 最近一次测活延迟
    status TEXT DEFAULT 'unknown',    -- ok / dead / unknown
    fail_count INTEGER DEFAULT 0,     -- 连续失败次数（jhao104 淘汰思路）
    last_check_at TIMESTAMP,
    source TEXT DEFAULT 'manual',     -- manual / provider:<名> / free:<源名>
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- user_info 加列（迁移：ALTER TABLE，老库无损）
ALTER TABLE user_info ADD COLUMN proxy_id INTEGER DEFAULT NULL;
```

凭证与 cookies 文件同安全边界（单机桌面应用，SQLite 本就在用户机器上），不做额外加密。

### 后端模块

**`backend/impl/proxy_pool/manager.py`** — 核心取用接口：

```python
def resolve_proxy_for_account(user_info_id: int) -> str | None:
    """账号 → 绑定代理 → 健康代理 的解析链。

    返回 "protocol://user:pass@host:port" 或 None（无绑定/池关闭）。
    绑定代理 status=dead 时的降级：同 region 备用代理 → None + 显式告警日志。
    绝不静默回落本机 IP（会造成账号 IP 跳变，比不用代理更危险）。
    """
```

**`backend/impl/proxy_pool/checker.py`** — 测活后台线程：

- 间隔 5 分钟批量测活（`api.ip.sb/geoip` 拿出口 IP + 地域 + 延迟，
  参考 jhao104 `DoValidator.regionGetter` 设计）；
- `fail_count` 连续 N 次（默认 3）失败 → `status=dead`；
- 线程模型参考现有「视频号保活线程」（app.py 启动时拉起，daemon）。

**浏览器注入**（唯一的平台层改动，所有 11+ 平台自动生效）：

```python
# _browser.py
async def create_browser(..., proxy: str | None = None):
    browser = await launch_async(
        headless=headless,
        args=["--start-maximized"],
        proxy=proxy,
        geoip=proxy is not None,   # 走代理时自动对齐时区/语言/WebRTC
        humanize=humanize, human_preset=human_preset,
    )

# BasePlatform.create_browser(..., proxy=None) 同步透传
```

各平台调用点把 `manager.resolve_proxy_for_account(self.user_info_id)` 的结果传入。
login（扫码）**必须与发布走同一代理**——扫码时的 IP 会成为账号的「常用登录地」，
登录走本机、发布走代理 = 平台立刻判定异地登录。

**API（新 Blueprint `backend/proxy_api/`，遵循「新路由放 Blueprint」约定）**：

- `GET/POST/PUT/DELETE /api/proxies`（CRUD + 启停）
- `POST /api/proxies/<id>/check`（手动测活）
- `POST /api/accounts/<id>/bind_proxy` / `unbind`
- settings 新增 key：`proxyMode`（`off` 默认 / `pool`）——`off` 时全部行为与现状完全一致

### 前端

1. `Settings.vue` 新增「代理池」卡片：表格（名称/协议/出口地区/延迟/状态/绑定账号数）、
   添加/编辑弹窗、手动测速按钮、总开关（`proxyMode`）。
2. `AccountManagement.vue` 账号卡片：显示绑定代理徽标（如 `沪-家宽01`），
   下拉换绑/解绑；绑定的代理 dead 时红色告警。

### 分期实施

| 阶段 | 内容 | 价值 |
|---|---|---|
| **P1（本期）** | 池表 + 手动录入 + 测活线程 + 账号绑定 + `_browser.py` 注入 + API + 前端两个页面 | 最小可用：自购代理立刻产生账号隔离价值 |
| P2（下期） | 付费代理商「API 提取链接」支持：填提取 URL → 定时拉取入池自动绑定 | 免手动录入，适配隧道/短效代理 |
| P3（可选，默认关） | 移植 jhao104 fetcher 免费源采集，`source=free:*`，UI 强警示仅限测试用途 | 低成本体验池能力；明确不用于登录态账号 |

### 不在范围内

- 不引入 Redis / 新进程 / Docker（见选型理由）
- 不做代理链/二级代理
- 不做 IP 自动更换调度（账号绑定 sticky，不轮换）
- P3 免费源默认关闭且不用于 login/publish 路径

## 风险与对策

| 风险 | 对策 |
|---|---|
| 代理死掉导致发布失败 | 降级链：重试 → 同 region 备用 → 任务失败并在日志/UI 显式标注（绝不静默走本机 IP） |
| 用户误用免费代理挂登录账号 | P3 免费源 UI 强警示 + 文档说明；`source=free:*` 的代理在 login/publish 解析时直接拒绝（check 类操作可用） |
| geoip 反查接口（ip.sb）不可用 | CloakBrowser 的 geoip 失败时自动跳过（不阻塞启动），仅指纹对齐降级 |
| 打包体积/依赖变化 | P1 零新增 pip 依赖（测活用 httpx，cloakbrowser 已带） |

## 附录：代理商选型参考（2026-09 行情，采购前以官网实时报价为准）

### 国内平台账号（抖音/小红书/视频号/B站/微博等）→ 国内静态独享住宅 IP

| 服务商 | 产品 | 参考价 | 备注 |
|---|---|---|---|
| 巨量HTTP | 静态独享纯净住宅 IP | 13 元/天，245 元/月（3 条起 9 折） | 官方明确「账号矩阵运营」场景；按时续费保留 IP；HTTP+SOCKS5 |
| 快代理 | 独享静态 | ~112 元/月（独享） | 老牌，隧道产品线为主；区县定向收费 |
| 青果网络 | 独享静态 | ~98 元/月（独享） | 产品线全（短效/长效/独享/隧道） |
| 站大爷 | 独享静态 | ~118 元/月（独享） | 300+ 城市覆盖 |
| 91HTTP | 独享静态 | ~92 元/月（独享） | 基础白名单免费 |

注：85~118 元/月档多为「机房/普通静态独享」，巨量 245 元/月档为「纯净家庭住宅」——
社媒账号场景优先确认是真住宅（家宽）属性，机房 IP 在社媒平台风控里折损明显。
多家横评文章为厂商软文（有代理/独享云等自比自夸），数据仅取量级参考。

### 海外平台账号（TikTok/YouTube）→ 静态 ISP/住宅代理

| 服务商 | 参考价 | 备注 |
|---|---|---|
| IPRoyal | 静态住宅 ~$2.00/IP/月 起 | 一线厂商里价格最低，性价比首选 |
| Decodo (原 Smartproxy) | 静态 ISP ~$2.5-3.5/IP/月 | 套餐形态多，中文支持一般 |
| Proxy-Seller | 静态 ISP ~$2-3/IP/月 | 可选国家多 |
| Bright Data | 企业级，价格最高 | 合规与稳定性最好，预算充足再考虑 |

### 采购要点（与 P2 集成相关）

1. **必须支持「用户名密码认证」**：桌面应用用户没有固定服务器公网 IP，
   「白名单绑定服务器 IP」的认证模式对桌面分发不友好（家宽 IP 会变）。
2. **必须支持 API 提取**：P2 的「提取链接自动入池」依赖标准 API 拉取格式。
3. **禁止用动态短效/隧道挂账号**：IP 轮换 = 异地登录风控信号，
   巨量官方采购指南原话「账号运营业务禁止使用动态隧道」。
4. 先买**包天/小额套餐**实测目标平台兼容性（验证码率、登录稳定性）再批量采购。
5. 共享静态（9~16 元/月）便宜但有连带风控风险，不建议用于账号资产。
