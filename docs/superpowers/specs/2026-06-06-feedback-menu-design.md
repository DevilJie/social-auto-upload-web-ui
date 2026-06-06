# 一键反馈菜单 + 反馈系统对接 设计文档

## 概述

将反馈系统（`https://feedback.cjxch.com`）以「一键反馈」菜单的形式接入到本应用。菜单以卡片形式展示所有反馈数据，点击查看详情，支持 +1 投票、提交新反馈。同时按用户要求调整侧边栏菜单顺序。

**安全约束**：`app_secret` 写入 `conf.py`（用户明确表态：此密钥无关紧要，暴露可接受）。前端永远不接触 `app_secret`，所有请求经 Flask 后端签名代理。

## 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 签名位置 | Flask 后端 | 前端不可见 `app_secret`；前端任何代码改动都不影响密钥 |
| 后端集成 | 单文件追加到 `app.py` 末尾 | 项目现有 800 行单文件路由风格；3 个简单路由不值得拆 Blueprint |
| 菜单顺序 | 仪表盘→账号→素材→视频发布→图文发布→草稿箱→发布历史→更新日志→关于作者→一键反馈 | 用户指定 |
| 邮箱来源 | 设置页填一次，存 `localStorage` | 项目无账号体系；用户已选 |
| 状态分组 | 两个 Tab：活跃(1+2) / 非活跃(3+4) | 用户已选 |
| 列表分页 | `el-pagination` 经典分页 | 用户已选 |
| 提交反馈 | 支持附件 | 用户已选 |
| 「更新历史」 | 即现有的「更新日志」，不改名 | 用户确认 |
| 列表排序 | 前端按 `vote_count desc, created_at desc` | 用户指定 |

## 范围

### 在范围内

1. 后端 3 个代理路由（`/api/feedback/list`、`/api/feedback/submit`、`/api/feedback/vote`）
2. 后端 `_feedback_sign()` 工具函数 + `conf.py` 3 个配置项
3. 前端 `Feedback.vue` 页面（Tab + 卡片 + 抽屉 + 提交对话框）
4. 前端 `feedback.js` API 模块
5. `App.vue` 菜单顺序调整 + 新增第 10 项
6. `router/index.js` 加路由
7. `Settings.vue` 加「反馈系统邮箱」字段
8. 后端 pytest 测试

### 不在范围内

- 反馈搜索/筛选
- 反馈状态修改、回复、删除（Open API 不支持）
- 实时通知/轮询
- i18n
- 重命名「更新日志」
- 改动 Settings 已有字段
- 暗色模式适配

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  Vue 前端 (Feedback.vue)                                │
│    ├─ 顶部：标题 + 「+ 提交反馈」按钮                    │
│    ├─ 中部：2 个 Tab（活跃 / 非活跃）+ 卡片列表 + 分页  │
│    └─ 卡片点击 → el-drawer 详情（含 +1 按钮）            │
│         └─ 「+ 提交反馈」 → el-dialog                    │
└────────────────────┬────────────────────────────────────┘
                     │ fetch /api/feedback/*
                     ▼
┌─────────────────────────────────────────────────────────┐
│  Flask 后端 (backend/app.py 末尾)                        │
│    ├─ 3 个路由：list / submit / vote                    │
│    ├─ 工具函数：_feedback_sign(ts) → HMAC-SHA256 hex    │
│    └─ 读 conf.py: FEEDBACK_API_BASE_URL/APP_KEY/APP_SECRET│
└────────────────────┬────────────────────────────────────┘
                     │ X-App-Key / X-Timestamp / X-Sign
                     ▼
            https://feedback.cjxch.com
```

## 后端设计

### `backend/conf.py` 追加

```python
# 反馈系统对接（密钥可暴露，不影响业务）
FEEDBACK_API_BASE_URL = os.environ.get('FEEDBACK_API_BASE_URL', 'https://feedback.cjxch.com')
FEEDBACK_APP_KEY = os.environ.get('FEEDBACK_APP_KEY', 'ak_6de413b0f08587a92df5314806920dbde2f4193b076f7431bacec657')
FEEDBACK_APP_SECRET = os.environ.get('FEEDBACK_APP_SECRET', 'sk_7aa34a39ad547ec2ccd0fc61f23825b197dbbd3bec565461615961f6ca7c113b52937e19c8f372d39c756ae0b5d9bd1f6514e5895e92d4e5')
FEEDBACK_API_TIMEOUT = int(os.environ.get('FEEDBACK_API_TIMEOUT', '10'))
```

### `backend/app.py` 末尾追加

```python
# ── 反馈系统代理（HMAC 签名由后端完成，前端永不接触 app_secret）──
import hmac
import hashlib
import time
import requests as _requests
def _feedback_sign(timestamp_ms: str) -> str:
    msg = f"{conf.FEEDBACK_APP_KEY}{timestamp_ms}{conf.FEEDBACK_APP_SECRET}".encode('utf-8')
    return hmac.new(conf.FEEDBACK_APP_SECRET.encode('utf-8'), msg, hashlib.sha256).hexdigest()

def _feedback_headers() -> dict:
    ts = str(int(time.time() * 1000))
    return {
        'X-App-Key': conf.FEEDBACK_APP_KEY,
        'X-Timestamp': ts,
        'X-Sign': _feedback_sign(ts),
    }


@app.route('/api/feedback/list', methods=['GET'])
def feedback_list():
    tab = request.args.get('tab', 'active')  # 'active' or 'inactive'
    try:
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 20)), 100)
    except ValueError:
        return jsonify({'code': 400, 'message': 'page / page_size 必须是整数', 'data': None}), 400

    params = {'page': page, 'page_size': page_size}
    if tab == 'inactive':
        # 非活跃 = 已完成(3) + 已拒绝(4)，文档说多选需多次调用
        # 简化：拿全量前端过滤
        params['include_all'] = 'true'

    try:
        r = _requests.get(
            f"{conf.FEEDBACK_API_BASE_URL}/api/v1/feedback",
            params=params,
            headers=_feedback_headers(),
            timeout=conf.FEEDBACK_API_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502

    if tab == 'inactive':
        items = [x for x in data.get('data', {}).get('list', []) if x.get('status') in (3, 4)]
        data['data']['list'] = items
        data['data']['total'] = len(items)

    # 把 attachment.file_url 改写为绝对 URL，前端可直接使用
    for item in data.get('data', {}).get('list', []):
        for att in item.get('attachments', []) or []:
            if att.get('file_url', '').startswith('/'):
                att['file_url'] = conf.FEEDBACK_API_BASE_URL + att['file_url']

    return jsonify(data)


@app.route('/api/feedback/submit', methods=['POST'])
def feedback_submit():
    email = request.form.get('email', '').strip()
    content = request.form.get('content', '').strip()
    if not email or not content:
        return jsonify({'code': 400, 'message': '邮箱和内容必填', 'data': None}), 400

    files = []
    for f in request.files.getlist('files'):
        files.append(('files', (f.filename, f.stream, f.mimetype)))

    try:
        r = _requests.post(
            f"{conf.FEEDBACK_API_BASE_URL}/api/v1/feedback",
            data={'email': email, 'content': content},
            files=files,
            headers=_feedback_headers(),
            timeout=conf.FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502


@app.route('/api/feedback/vote', methods=['POST'])
def feedback_vote():
    body = request.get_json(silent=True) or {}
    fb_id = body.get('id')
    email = (body.get('email') or '').strip()
    if not fb_id or not email:
        return jsonify({'code': 400, 'message': 'id 和 email 必填', 'data': None}), 400

    try:
        r = _requests.post(
            f"{conf.FEEDBACK_API_BASE_URL}/api/v1/feedback/{fb_id}/vote",
            json={'email': email},
            headers=_feedback_headers(),
            timeout=conf.FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502
```

### 错误处理

| 上游情况 | 后端行为 |
|---------|---------|
| 2xx | 原样透传 body |
| 4xx（签名错、参数错） | 透传 status + body |
| 5xx | 透传 status + body（让前端展示） |
| 超时（10s） | 502 + 「反馈系统不可达」 |
| 网络异常 | 502 + 异常信息 |

## 前端设计

### `frontend/src/api/feedback.js`（新文件）

```javascript
import request from './index'

export function listFeedback({ tab, page = 1, pageSize = 20 }) {
  return request.get('/api/feedback/list', {
    params: { tab, page, page_size: pageSize }
  })
}

export function submitFeedback(formData) {
  return request.post('/api/feedback/submit', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export function voteFeedback({ id, email }) {
  return request.post('/api/feedback/vote', { id, email })
}
```

### `frontend/src/views/Feedback.vue`（新文件）

布局：

```
┌────────────────────────────────────────────────────┐
│  一键反馈                            [+ 提交反馈]   │
├────────────────────────────────────────────────────┤
│  [活跃反馈 (12)]   [非活跃反馈 (5)]                 │
├────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │ 状态徽章  │  │ 状态徽章  │  │ 状态徽章  │          │
│  │ 内容预览  │  │ 内容预览  │  │ 内容预览  │          │
│  │ ❤️ 5       │  │ ❤️ 3       │  │ ❤️ 1       │          │
│  │ 邮箱·时间  │  │ 邮箱·时间  │  │ 邮箱·时间  │          │
│  │ 📎 2 附件  │  │           │  │           │          │
│  └──────────┘  └──────────┘  └──────────┘          │
├────────────────────────────────────────────────────┤
│              < 1 2 3 ... >  el-pagination          │
└────────────────────────────────────────────────────┘
```

- **卡片**：3 列网格（响应式），每张含状态徽章、内容前 80 字、+1 数、邮箱（脱敏）、创建时间、附件数
- **点击卡片**：`el-drawer` 抽屉显示详情：完整内容、状态徽章、处理人（如有）、附件缩略图、+1 按钮、创建时间
  - 附件图片 URL 拼接规则：`fullUrl = ${conf.FEEDBACK_API_BASE_URL}${attachment.file_url}`，由后端在 `/api/feedback/list` 响应前把每条 attachment 的 `file_url` 改写为绝对 URL，避免前端处理跨域和拼接
- **+1 按钮**：已投过则禁用并显示「已支持」
- **「+ 提交反馈」**：`el-dialog`，email（默认填全局邮箱可编辑）+ content（textarea）+ 附件上传（1 个文件 5MB，accept 限定图片/PDF/Office）
- **邮箱引导**：`onMounted` 检查 `localStorage.getItem('global_user_email')`，空时弹 `el-message-box` 提示「请前往设置页填写邮箱」+ 跳转按钮
- **排序**：拉取后前端 `.sort()`：`vote_count desc, created_at desc`

### `frontend/src/App.vue`（修改）

调整 `navItems` 数组顺序 + 新增第 10 项：

```js
const navItems = [
  { path: '/', icon: HomeFilled, title: '仪表盘' },
  { path: '/account-management', icon: User, title: '账号管理' },
  { path: '/material-management', icon: Picture, title: '素材管理' },
  { path: '/publish-center', icon: Upload, title: '视频发布' },
  { path: '/image-publish', icon: Picture, title: '图文发布' },
  { path: '/drafts', icon: Document, title: '草稿箱' },
  { path: '/publish-history', icon: Clock, title: '发布历史' },
  { path: '/changelog', icon: Notebook, title: '更新日志' },
  { path: '/author', icon: UserFilled, title: '关于作者' },
  { path: '/feedback', icon: ChatDotRound, title: '一键反馈' }
]
```

新增 `ChatDotRound` 到 import 列表。

### `frontend/src/router/index.js`（修改）

```js
{ 
  path: '/feedback', 
  name: 'Feedback', 
  component: () => import('../views/Feedback.vue'), 
  meta: { icon: 'ChatDotRound', title: '一键反馈' } 
}
```

### `frontend/src/views/Settings.vue`（修改）

末尾追加一个「反馈系统」section：

- 表单项：邮箱（`v-model` 绑 `localStorage.getItem('global_user_email')`）
- 保存按钮：写入 `localStorage.setItem('global_user_email', email)`

不改动 Settings 已有任何字段/结构。

## 测试

### 后端 pytest（`backend/tests/test_feedback.py`）

1. **`_feedback_sign()`**：固定 key+ts+secret → 已知 hex
2. **`/api/feedback/list` tab=active**：mock `requests.get` 验证不带 `include_all`
3. **`/api/feedback/list` tab=inactive**：mock 验证带 `include_all=true` + 返回过滤
4. **`/api/feedback/list` 上游 5xx**：返 502
5. **`/api/feedback/submit` 缺字段**：返 400
6. **`/api/feedback/submit` 正常**：mock 验证 files 转发
7. **`/api/feedback/vote` 缺字段**：返 400
8. **`/api/feedback/vote` 正常**：mock 验证 URL 含 id

### 前端

不写组件测试（投入产出比低）。手动 end-to-end 验证清单：

- [ ] 列表加载（活跃 Tab 12 条）
- [ ] Tab 切换（活跃 / 非活跃）
- [ ] 分页（页码跳转、上一页/下一页）
- [ ] 卡片点击抽屉显示完整内容
- [ ] 投票成功 +1
- [ ] 重复投票显示「已支持」
- [ ] 提交反馈（带附件）成功，列表更新
- [ ] 未设置邮箱时进入页面弹提示
- [ ] 设置页填写邮箱后能正常提交/投票
- [ ] 上游报错（断网模拟）有友好提示

## 实施顺序

1. `conf.py` 加 3 个配置项
2. `app.py` 末尾追加 3 个路由 + `_feedback_sign` 工具
3. 后端 pytest 全过
4. `frontend/src/api/feedback.js`
5. `Settings.vue` 加邮箱字段
6. `Feedback.vue` 实现
7. `router/index.js` + `App.vue` 接入
8. 手动 e2e 验证清单全部通过

## 数据流

**读取：**
```
Feedback.vue mount
  → GET /api/feedback/list?tab=active&page=1&page_size=20
  → 后端 GET feedback.cjxch.com/api/v1/feedback?page=1&page_size=20 + X-Sign
  → 后端返回
  → 前端 .sort() by vote_count desc, created_at desc
  → 渲染
```

**投票：**
```
el-drawer 「+1」按钮 click
  → POST /api/feedback/vote {id, email}
  → 后端 POST feedback.cjxch.com/api/v1/feedback/<id>/vote {email} + X-Sign
  → 后端返回
  → 前端刷新抽屉中 vote_count
```

**提交：**
```
el-dialog 「提交」按钮 click
  → POST /api/feedback/submit (multipart: email, content, files)
  → 后端 POST feedback.cjxch.com/api/v1/feedback + X-Sign
  → 后端返回
  → 前端关闭对话框 + 刷新当前 Tab 列表
```

## 风险与权衡

| 风险 | 缓解 |
|------|------|
| `app_secret` 进 git 仓库 | 用户已知情并接受此风险；只用于本应用，且只暴露给阅读本仓库的人 |
| 上游反馈系统宕机 | 后端 502 + 友好提示；前端 `el-empty` 兜底 |
| 用户重复投票 | 后端 400 + 前端按钮变「已支持」（按接口 `already voted` 错误码） |
| 上游 8MB 附件缓冲 | 单文件 5MB 限制已在前端 `el-upload` 限制 |
| Settings 邮箱为空 | 进入菜单时弹提示并提供跳转 |
