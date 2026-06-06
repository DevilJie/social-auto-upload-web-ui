# 一键反馈菜单 + 反馈系统对接 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在桌面应用内新增「一键反馈」菜单，以卡片形式展示 `https://feedback.cjxch.com` 的反馈数据，支持 Tab 切换（活跃/非活跃）、分页、详情抽屉、+1 投票、提交新反馈；同步调整侧边栏菜单顺序为用户指定的新顺序。

**Architecture:** Flask 后端用 HMAC-SHA256 签名代理转发到 feedback.cjxch.com（前端永不接触 `app_secret`）。Vue 前端新增 `Feedback.vue`，通过 `/api/feedback/*` 调用后端。后端单文件追加 3 个路由 + 1 个签名工具，前端新增 1 个 API 模块 + 1 个视图 + 菜单/路由接入 + Settings 加一个邮箱字段。

**Tech Stack:** Python 3 + Flask（已有 `requests==2.32.3`）、Vue 3 + Element Plus（已有 axios + `@/utils/request`）、pytest（项目已有 `backend/test_*.py` 使用模式）

---

## 文件结构

```
backend/
├── conf.py                                          # 修改：追加 3 个配置项
├── app.py                                           # 修改：末尾追加 3 路由 + _feedback_sign
└── tests/
    ├── __init__.py                                  # 新建（空文件）
    └── test_feedback.py                             # 新建：签名 + 3 路由的 pytest

frontend/src/
├── api/
│   ├── index.js                                     # 修改：export * from './feedback'
│   └── feedback.js                                  # 新建：3 个 API 函数
├── views/
│   ├── Feedback.vue                                 # 新建：主页面（Tab + 卡片 + 抽屉 + 提交对话框）
│   └── Settings.vue                                 # 修改：末尾追加「反馈系统」section
├── App.vue                                          # 修改：navItems 调整顺序 + 新增第 10 项
└── router/
    └── index.js                                     # 修改：加 /feedback 路由
```

总计：1 个修改 + 3 个新建（后端），4 个修改 + 1 个新建（前端）。

---

## Task 1: 后端配置项（conf.py）

**Files:**
- Modify: `backend/conf.py:1-14`

- [ ] **Step 1: 在 conf.py 末尾追加配置项**

文件末尾（`FEEDBACK_API_TIMEOUT` 之前已存在的最后一个 import 之后）追加：

```python
# 反馈系统对接（密钥可暴露，不影响业务；用户已确认）
FEEDBACK_API_BASE_URL = os.environ.get('FEEDBACK_API_BASE_URL', 'https://feedback.cjxch.com')
FEEDBACK_APP_KEY = os.environ.get('FEEDBACK_APP_KEY', 'ak_6de413b0f08587a92df5314806920dbde2f4193b076f7431bacec657')
FEEDBACK_APP_SECRET = os.environ.get('FEEDBACK_APP_SECRET', 'sk_7aa34a39ad547ec2ccd0fc61f23825b197dbbd3bec565461615961f6ca7c113b52937e19c8f372d39c756ae0b5d9bd1f6514e5895e92d4e5')
FEEDBACK_API_TIMEOUT = int(os.environ.get('FEEDBACK_API_TIMEOUT', '10'))
```

- [ ] **Step 2: 验证导入不报错**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -c "from conf import FEEDBACK_API_BASE_URL, FEEDBACK_APP_KEY, FEEDBACK_APP_SECRET, FEEDBACK_API_TIMEOUT; print(FEEDBACK_API_BASE_URL); print(len(FEEDBACK_APP_KEY)); print(len(FEEDBACK_APP_SECRET)); print(FEEDBACK_API_TIMEOUT)"
```

Expected: 输出 `https://feedback.cjxch.com`、两个非零长度、`10`，无 ImportError。

- [ ] **Step 3: 提交**

```bash
git add backend/conf.py
git commit -m "feat(backend): 新增反馈系统对接配置项"
```

---

## Task 2: 后端签名工具函数 `_feedback_sign`（TDD）

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_feedback.py`

- [ ] **Step 1: 写失败测试 — 签名输出**

`backend/tests/test_feedback.py`:

```python
"""反馈系统代理的单元测试。"""
import hmac
import hashlib
import sys
from pathlib import Path

# 让 app.py / conf.py 可被 import
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def test_feedback_sign_known_vector():
    """固定输入产生已知 hex（与文档 §3.3 算法对齐）。"""
    from app import _feedback_sign

    app_key = "ak_test"
    app_secret = "sk_test"
    timestamp = "1717555800000"

    # 期望 = HMAC-SHA256(secret, key+timestamp+secret) hex
    expected_msg = f"{app_key}{timestamp}{app_secret}".encode('utf-8')
    expected_sig = hmac.new(app_secret.encode('utf-8'), expected_msg, hashlib.sha256).hexdigest()

    actual = _feedback_sign(timestamp, app_key=app_key, app_secret=app_secret)
    assert actual == expected_sig
    # 长度为 64（小写 hex）
    assert len(actual) == 64
    assert actual == actual.lower()
```

为了让测试可独立传入 key/secret，需要让 `_feedback_sign` 接受可选参数。`app.py` 中定义时把这两个值作为默认参数从 conf 读取。

- [ ] **Step 2: 运行测试，确认失败（因为函数还没定义）**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -m pytest tests/test_feedback.py::test_feedback_sign_known_vector -v
```

Expected: `FAILED` with `ImportError: cannot import name '_feedback_sign' from 'app'`。

- [ ] **Step 3: 在 app.py 末尾（最后一个 `@app.route` 之后）追加签名工具 + HMAC import**

`backend/app.py` 顶部 import 区追加：

```python
import hmac
import hashlib
```

并在文件末尾（最后一个 route 之后）追加：

```python
# ── 反馈系统代理（HMAC 签名由后端完成，前端永不接触 app_secret）──
def _feedback_sign(timestamp_ms: str, app_key: str = None, app_secret: str = None) -> str:
    if app_key is None:
        app_key = FEEDBACK_APP_KEY
    if app_secret is None:
        app_secret = FEEDBACK_APP_SECRET
    msg = f"{app_key}{timestamp_ms}{app_secret}".encode('utf-8')
    return hmac.new(app_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()
```

注：app.py 顶部目前是 `from conf import BASE_DIR`。要把新增的 4 个常量也带进来，**整行替换**为：

```python
from conf import (
    BASE_DIR,
    FEEDBACK_API_BASE_URL,
    FEEDBACK_APP_KEY,
    FEEDBACK_APP_SECRET,
    FEEDBACK_API_TIMEOUT,
)
```

后续 Task 3-5 的代码使用 `FEEDBACK_API_BASE_URL` 等（不带 `conf.` 前缀）。

- [ ] **Step 4: 运行测试，确认通过**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -m pytest tests/test_feedback.py::test_feedback_sign_known_vector -v
```

Expected: `PASSED`。

- [ ] **Step 5: 提交**

```bash
git add backend/app.py backend/tests/test_feedback.py backend/tests/__init__.py
git commit -m "feat(backend): 新增 _feedback_sign 签名工具及单元测试"
```

---

## Task 3: 后端路由 `GET /api/feedback/list`（TDD）

**Files:**
- Modify: `backend/app.py`（追加路由）
- Modify: `backend/tests/test_feedback.py`（追加测试）

- [ ] **Step 1: 追加失败测试 — list 路由转发逻辑**

在 `backend/tests/test_feedback.py` 末尾追加：

```python
from unittest.mock import patch, MagicMock


def test_feedback_list_active_tab(monkeypatch):
    """tab=active 时不传 include_all；原样透传上游响应。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "code": 200,
        "data": {
            "list": [
                {"id": 1, "status": 1, "vote_count": 5, "created_at": "2026-06-05T10:00:00+08:00",
                 "attachments": [{"file_url": "/uploads/x.png"}]}
            ],
            "total": 1, "page": 1, "page_size": 20
        }
    }
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return fake_resp

    with patch("app._requests.get", side_effect=fake_get):
        client = app.test_client()
        r = client.get("/api/feedback/list?tab=active&page=1&page_size=20")
        assert r.status_code == 200
        body = r.get_json()
        # 透传
        assert body["data"]["total"] == 1
        # 不应包含 include_all
        assert "include_all" not in captured["params"]
        # URL 指向反馈系统
        assert captured["url"].startswith("https://feedback.cjxch.com/api/v1/feedback")
        # 签名头齐
        assert "X-App-Key" in captured["headers"]
        assert "X-Timestamp" in captured["headers"]
        assert "X-Sign" in captured["headers"]
        assert len(captured["headers"]["X-Sign"]) == 64
        # file_url 被改写为绝对 URL
        assert body["data"]["list"][0]["attachments"][0]["file_url"] == "https://feedback.cjxch.com/uploads/x.png"


def test_feedback_list_inactive_tab_filters(monkeypatch):
    """tab=inactive 时带 include_all=true 并过滤 status 3/4。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "code": 200,
        "data": {
            "list": [
                {"id": 1, "status": 1, "vote_count": 5},  # 活跃 - 应被过滤
                {"id": 2, "status": 3, "vote_count": 2},  # 已完成 - 保留
                {"id": 3, "status": 4, "vote_count": 1},  # 已拒绝 - 保留
                {"id": 4, "status": 2, "vote_count": 0},  # 处理中 - 应被过滤
            ],
            "total": 4
        }
    }
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        return fake_resp

    with patch("app._requests.get", side_effect=fake_get):
        client = app.test_client()
        r = client.get("/api/feedback/list?tab=inactive")
        assert r.status_code == 200
        body = r.get_json()
        # 只剩 status 3/4
        assert body["data"]["total"] == 2
        ids = [x["id"] for x in body["data"]["list"]]
        assert ids == [2, 3]
        # 带 include_all=true
        assert captured["params"].get("include_all") == "true"


def test_feedback_list_upstream_5xx_returns_502(monkeypatch):
    """上游 5xx 时后端返回 502。"""
    from app import app
    import requests as _requests

    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = _requests.HTTPError("500 Server Error")

    with patch("app._requests.get", return_value=fake_resp):
        client = app.test_client()
        r = client.get("/api/feedback/list?tab=active")
        assert r.status_code == 502
        assert "反馈系统不可达" in r.get_json()["message"]
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -m pytest tests/test_feedback.py -v -k "list"
```

Expected: 3 个 `FAILED`（路由未定义 → 404）。

- [ ] **Step 3: 实现 list 路由**

在 `backend/app.py` 末尾（紧跟 `_feedback_sign` 之后）追加：

```python
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
        params['include_all'] = 'true'

    ts = str(int(time.time() * 1000))
    headers = {
        'X-App-Key': FEEDBACK_APP_KEY,
        'X-Timestamp': ts,
        'X-Sign': _feedback_sign(ts),
    }

    try:
        r = _requests.get(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback",
            params=params,
            headers=headers,
            timeout=FEEDBACK_API_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502

    if tab == 'inactive':
        items = [x for x in data.get('data', {}).get('list', []) if x.get('status') in (3, 4)]
        data['data']['list'] = items
        data['data']['total'] = len(items)

    # attachment.file_url 从相对路径改写为绝对 URL
    for item in data.get('data', {}).get('list', []):
        for att in item.get('attachments') or []:
            if att.get('file_url', '').startswith('/'):
                att['file_url'] = FEEDBACK_API_BASE_URL + att['file_url']

    return jsonify(data)
```

确认 `time` 已在 app.py 顶部 import（看 app.py 第 6-15 行，已在 Task 2 时确认存在 `import time`）。如未存在则补：`import time`。

- [ ] **Step 4: 运行测试，确认通过**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -m pytest tests/test_feedback.py -v -k "list"
```

Expected: 3 个 `PASSED`。

- [ ] **Step 5: 提交**

```bash
git add backend/app.py backend/tests/test_feedback.py
git commit -m "feat(backend): 实现 GET /api/feedback/list 路由及测试"
```

---

## Task 4: 后端路由 `POST /api/feedback/submit`（TDD）

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_feedback.py`

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_feedback.py` 末尾追加：

```python
def test_feedback_submit_missing_fields():
    """缺 email 或 content 返 400。"""
    from app import app

    client = app.test_client()
    r = client.post("/api/feedback/submit", data={"email": "a@b.com"})
    assert r.status_code == 400
    assert "必填" in r.get_json()["message"]

    r = client.post("/api/feedback/submit", data={"content": "hello"})
    assert r.status_code == 400


def test_feedback_submit_forwards_files(monkeypatch):
    """multipart 字段和文件都正确转发。"""
    from app import app
    import io

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"code": 200, "data": {"id": 99}}
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_post(url, data, files, headers, timeout):
        captured["url"] = url
        captured["data"] = data
        captured["files"] = files
        captured["headers"] = headers
        return fake_resp

    with patch("app._requests.post", side_effect=fake_post):
        client = app.test_client()
        r = client.post(
            "/api/feedback/submit",
            data={
                "email": "user@example.com",
                "content": "应用启动后白屏",
            },
            content_type="multipart/form-data",
            buffered=True,
        )
        # Flask test client 不直接接受 files+data 一起传，单独走上传
        # 走上传路径
        r2 = client.post(
            "/api/feedback/submit",
            data={
                "email": "user@example.com",
                "content": "应用启动后白屏",
                "files": (io.BytesIO(b"fake-image-bytes"), "screen.png"),
            },
            content_type="multipart/form-data",
            buffered=True,
        )
        assert r2.status_code == 200
        assert captured["data"]["email"] == "user@example.com"
        assert captured["data"]["content"] == "应用启动后白屏"
        # 至少 1 个文件被转发
        assert len(captured["files"]) >= 1
        # 签名头齐
        assert "X-Sign" in captured["headers"]
        # URL 正确
        assert captured["url"].startswith("https://feedback.cjxch.com/api/v1/feedback")
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -m pytest tests/test_feedback.py -v -k "submit"
```

Expected: 2 个 `FAILED`（路由未注册 → 405 或 404）。

- [ ] **Step 3: 实现 submit 路由**

在 `backend/app.py` 末尾追加：

```python
@app.route('/api/feedback/submit', methods=['POST'])
def feedback_submit():
    email = request.form.get('email', '').strip()
    content = request.form.get('content', '').strip()
    if not email or not content:
        return jsonify({'code': 400, 'message': '邮箱和内容必填', 'data': None}), 400

    files = []
    for f in request.files.getlist('files'):
        files.append(('files', (f.filename, f.stream, f.mimetype)))

    ts = str(int(time.time() * 1000))
    headers = {
        'X-App-Key': FEEDBACK_APP_KEY,
        'X-Timestamp': ts,
        'X-Sign': _feedback_sign(ts),
    }

    try:
        r = _requests.post(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback",
            data={'email': email, 'content': content},
            files=files,
            headers=headers,
            timeout=FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502
```

- [ ] **Step 4: 运行测试，确认通过**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -m pytest tests/test_feedback.py -v -k "submit"
```

Expected: 2 个 `PASSED`。

- [ ] **Step 5: 提交**

```bash
git add backend/app.py backend/tests/test_feedback.py
git commit -m "feat(backend): 实现 POST /api/feedback/submit 路由及测试"
```

---

## Task 5: 后端路由 `POST /api/feedback/vote`（TDD）

**Files:**
- Modify: `backend/app.py`
- Modify: `backend/tests/test_feedback.py`

- [ ] **Step 1: 追加失败测试**

在 `backend/tests/test_feedback.py` 末尾追加：

```python
def test_feedback_vote_missing_fields():
    """缺 id 或 email 返 400。"""
    from app import app

    client = app.test_client()
    r = client.post("/api/feedback/vote", json={"id": 1})
    assert r.status_code == 400
    r = client.post("/api/feedback/vote", json={"email": "a@b.com"})
    assert r.status_code == 400
    r = client.post("/api/feedback/vote", json={})
    assert r.status_code == 400


def test_feedback_vote_forwards(monkeypatch):
    """正常请求正确转发到 /<id>/vote。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"code": 200, "data": None}
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return fake_resp

    with patch("app._requests.post", side_effect=fake_post):
        client = app.test_client()
        r = client.post("/api/feedback/vote", json={"id": 42, "email": "voter@example.com"})
        assert r.status_code == 200
        assert captured["url"] == "https://feedback.cjxch.com/api/v1/feedback/42/vote"
        assert captured["json"] == {"email": "voter@example.com"}
        assert "X-Sign" in captured["headers"]


def test_feedback_vote_passes_through_400(monkeypatch):
    """上游 4xx（如 already voted）原样透传。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"code": 400, "message": "already voted", "data": None}
    fake_resp.status_code = 400
    fake_resp.raise_for_status = MagicMock()

    with patch("app._requests.post", return_value=fake_resp):
        client = app.test_client()
        r = client.post("/api/feedback/vote", json={"id": 1, "email": "a@b.com"})
        assert r.status_code == 400
        assert r.get_json()["message"] == "already voted"
```

- [ ] **Step 2: 运行测试，确认失败**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -m pytest tests/test_feedback.py -v -k "vote"
```

Expected: 3 个 `FAILED`（路由未注册）。

- [ ] **Step 3: 实现 vote 路由**

在 `backend/app.py` 末尾追加：

```python
@app.route('/api/feedback/vote', methods=['POST'])
def feedback_vote():
    body = request.get_json(silent=True) or {}
    fb_id = body.get('id')
    email = (body.get('email') or '').strip()
    if not fb_id or not email:
        return jsonify({'code': 400, 'message': 'id 和 email 必填', 'data': None}), 400

    ts = str(int(time.time() * 1000))
    headers = {
        'X-App-Key': FEEDBACK_APP_KEY,
        'X-Timestamp': ts,
        'X-Sign': _feedback_sign(ts),
    }

    try:
        r = _requests.post(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback/{fb_id}/vote",
            json={'email': email},
            headers=headers,
            timeout=FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502
```

- [ ] **Step 4: 运行测试，确认通过**

Run:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python -m pytest tests/test_feedback.py -v
```

Expected: 所有测试（9 个：1 sign + 3 list + 2 submit + 3 vote）`PASSED`。

- [ ] **Step 5: 提交**

```bash
git add backend/app.py backend/tests/test_feedback.py
git commit -m "feat(backend): 实现 POST /api/feedback/vote 路由及测试"
```

---

## Task 6: 前端 API 模块 `frontend/src/api/feedback.js`

**Files:**
- Create: `frontend/src/api/feedback.js`

- [ ] **Step 1: 创建文件**

```javascript
import { http } from '@/utils/request'

export function listFeedback({ tab, page = 1, pageSize = 20 }) {
  return http.get('/api/feedback/list', {
    params: { tab, page, page_size: pageSize }
  })
}

export function submitFeedback(formData) {
  return http.upload('/api/feedback/submit', formData)
}

export function voteFeedback({ id, email }) {
  return http.post('/api/feedback/vote', { id, email })
}
```

注：`http.upload` 是 `@/utils/request.js` 已有的方法（`request.post(formData, { headers: { 'Content-Type': 'multipart/form-data' } })`），专门处理 multipart。

- [ ] **Step 2: 在 `frontend/src/api/index.js` 添加 export**

修改文件末尾（现有 3 个 `export *` 之后）追加：

```javascript
export * from './feedback'
```

- [ ] **Step 3: 验证不报错**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build --mode development 2>&1 | head -30
```

Expected: 无模块解析错误。如果只想快速 lint 一下：`node -e "import('./src/api/feedback.js').then(()=>console.log('ok'))"` 不行（Vite/ESM 路径），直接走 build。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/feedback.js frontend/src/api/index.js
git commit -m "feat(frontend): 新增 feedback API 模块"
```

---

## Task 7: 前端 Settings 加「反馈系统邮箱」字段

**Files:**
- Modify: `frontend/src/views/Settings.vue`

- [ ] **Step 1: 在 Settings.vue 末尾的 `</template>` 之前插入反馈系统 section**

定位：在 `</div>` 关闭最后一个 `settings-card` 之后、`<div class="save-bar">` 之前，插入新 section。可以通过搜索 `<div class="save-bar">` 找到。

在 `<div class="save-bar">` 这一行**之前**插入：

```html
    <!-- 反馈系统 -->
    <div class="settings-card">
      <h3 class="card-title">
        <el-icon class="title-icon"><ChatDotRound /></el-icon>
        反馈系统
      </h3>
      <div class="setting-row">
        <div class="setting-info">
          <span class="setting-label">反馈邮箱</span>
          <span class="setting-desc">用于在「一键反馈」菜单提交反馈和投票。不填将无法使用这些功能</span>
        </div>
        <div class="setting-control">
          <el-input
            v-model="settings.feedbackEmail"
            placeholder="your@email.com"
            style="width: 300px"
            clearable
          />
        </div>
      </div>
    </div>
```

- [ ] **Step 2: 在 `<script setup>` 区顶部 import ChatDotRound**

定位 `import { ref, reactive, onMounted } from 'vue'` 附近的 icon 导入区（搜索 `from '@element-plus/icons-vue'`）。

在该行后追加 `ChatDotRound`：

```javascript
import { ChatDotRound } from '@element-plus/icons-vue'
```

- [ ] **Step 3: 在 reactive 的 `settings` 对象里加 `feedbackEmail` 字段**

定位 `const settings = reactive({` 块，在最后一个属性之后追加 `feedbackEmail: ''`。

- [ ] **Step 4: 在 onMounted 加载逻辑里加 localStorage 读取**

定位 `onMounted(() => {` 块。

在该函数内、所有 `if (res.data.xxx !== undefined) settings.xxx = res.data.xxx` 赋值行之后，追加 localStorage 兜底读取（后端 settings API 不返回此字段，靠前端 localStorage）：

```javascript
      const savedEmail = localStorage.getItem('global_user_email')
      if (savedEmail && !settings.feedbackEmail) {
        settings.feedbackEmail = savedEmail
      }
```

- [ ] **Step 5: 在 handleSave 函数里加 localStorage 写入**

定位 `handleSave`（搜索 `async function handleSave` 或 `:disabled="saving" @click="handleSave"`）。

在该函数最后一行（通常是 `ElMessage.success`）之前，加：

```javascript
      localStorage.setItem('global_user_email', settings.feedbackEmail || '')
```

- [ ] **Step 6: 验证 build 通过**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build --mode development 2>&1 | tail -10
```

Expected: 成功，无错误。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/Settings.vue
git commit -m "feat(frontend): Settings 加反馈系统邮箱字段"
```

---

## Task 8: 前端 `Feedback.vue` 主页面（核心 UI）

**Files:**
- Create: `frontend/src/views/Feedback.vue`

- [ ] **Step 1: 创建文件 — 模板区**

```vue
<template>
  <div class="feedback-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">一键反馈</h1>
        <p class="page-subtitle">查看、提交、投票反馈，与作者一起改进产品</p>
      </div>
      <el-button type="primary" :icon="Plus" @click="openSubmitDialog">提交反馈</el-button>
    </div>

    <el-tabs v-model="activeTab" @tab-change="handleTabChange">
      <el-tab-pane :label="`活跃反馈 (${tabCount.active})`" name="active" />
      <el-tab-pane :label="`非活跃反馈 (${tabCount.inactive})`" name="inactive" />
    </el-tabs>

    <div v-loading="loading" class="card-grid">
      <el-empty v-if="!loading && sortedList.length === 0" description="暂无反馈" />
      <div
        v-for="fb in sortedList"
        :key="fb.id"
        class="feedback-card"
        @click="openDrawer(fb)"
      >
        <div class="card-top">
          <el-tag :type="statusTagType(fb.status)" size="small">
            {{ statusLabel(fb.status) }}
          </el-tag>
          <span class="vote-count" @click.stop="handleVote(fb)">
            <el-icon><CaretTop /></el-icon>
            {{ fb.vote_count || 0 }}
          </span>
        </div>
        <div class="card-content">{{ truncate(fb.content, 80) }}</div>
        <div class="card-meta">
          <span class="meta-email">{{ maskEmail(fb.email) }}</span>
          <span class="meta-time">{{ formatTime(fb.created_at) }}</span>
        </div>
        <div v-if="fb.attachments && fb.attachments.length" class="card-attachments">
          <el-icon><Paperclip /></el-icon>
          {{ fb.attachments.length }} 个附件
        </div>
      </div>
    </div>

    <div v-if="total > 0" class="pagination-wrapper">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50]"
        :total="total"
        layout="total, sizes, prev, pager, next, jumper"
        @current-change="loadList"
        @size-change="onSizeChange"
      />
    </div>

    <!-- 详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      :title="`反馈 #${currentFb?.id || ''}`"
      size="500px"
      direction="rtl"
    >
      <div v-if="currentFb" class="drawer-content">
        <el-tag :type="statusTagType(currentFb.status)" size="small">
          {{ statusLabel(currentFb.status) }}
        </el-tag>
        <div v-if="currentFb.assignee" class="drawer-assignee">
          处理人：{{ currentFb.assignee }}
        </div>
        <div class="drawer-time">{{ formatTime(currentFb.created_at) }}</div>
        <div class="drawer-content-text">{{ currentFb.content }}</div>
        <div v-if="currentFb.attachments && currentFb.attachments.length" class="drawer-attachments">
          <h4>附件</h4>
          <el-image
            v-for="att in currentFb.attachments"
            :key="att.id"
            :src="att.file_url"
            :preview-src-list="currentFb.attachments.map(a => a.file_url)"
            :initial-index="0"
            fit="cover"
            class="attachment-img"
          />
        </div>
        <div class="drawer-vote">
          <el-button
            type="primary"
            :disabled="votedIds.has(currentFb.id)"
            @click="handleVote(currentFb)"
          >
            <el-icon><CaretTop /></el-icon>
            {{ votedIds.has(currentFb.id) ? '已支持' : '+1 支持' }}
            <span v-if="currentFb.vote_count" class="vote-num">{{ currentFb.vote_count }}</span>
          </el-button>
        </div>
      </div>
    </el-drawer>

    <!-- 提交反馈对话框 -->
    <el-dialog v-model="submitVisible" title="提交反馈" width="500px">
      <el-form :model="submitForm" label-width="80px">
        <el-form-item label="邮箱" required>
          <el-input v-model="submitForm.email" placeholder="your@email.com" />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="submitForm.content" type="textarea" :rows="5" placeholder="详细描述您遇到的问题或建议" />
        </el-form-item>
        <el-form-item label="附件">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-exceed="onExceed"
            :on-remove="onFileRemove"
            accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.pdf,.doc,.docx,.xlsx,.xls,.pptx,.ppt"
            list-type="picture"
          >
            <el-button :icon="Upload">选择文件 (≤5MB)</el-button>
            <template #tip>
              <div class="el-upload__tip">支持图片、PDF、Office 文档，单文件不超过 5MB</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>
```

- [ ] **Step 2: 添加 `<script setup>` 区**

接在 `</template>` 之后：

```vue
<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, CaretTop, Paperclip, Upload } from '@element-plus/icons-vue'
import { listFeedback, submitFeedback as apiSubmit, voteFeedback as apiVote } from '@/api/feedback'

const router = useRouter()

const activeTab = ref('active')
const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const tabCount = ref({ active: 0, inactive: 0 })

const drawerVisible = ref(false)
const currentFb = ref(null)

const submitVisible = ref(false)
const submitting = ref(false)
const submitForm = ref({ email: '', content: '' })
const submitFile = ref(null)

const votedIds = ref(new Set())

const sortedList = computed(() => {
  return [...list.value].sort((a, b) => {
    if ((b.vote_count || 0) !== (a.vote_count || 0)) {
      return (b.vote_count || 0) - (a.vote_count || 0)
    }
    return new Date(b.created_at) - new Date(a.created_at)
  })
})

function statusLabel(s) {
  return { 1: '待确认', 2: '处理中', 3: '已完成', 4: '已拒绝' }[s] || '未知'
}
function statusTagType(s) {
  return { 1: 'warning', 2: 'primary', 3: 'success', 4: 'info' }[s] || 'info'
}
function truncate(text, n) {
  if (!text) return ''
  return text.length > n ? text.slice(0, n) + '…' : text
}
function maskEmail(email) {
  if (!email) return ''
  const [user, domain] = email.split('@')
  if (!domain) return email
  return user.slice(0, 2) + '***@' + domain
}
function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function loadList() {
  loading.value = true
  try {
    const res = await listFeedback({
      tab: activeTab.value,
      page: page.value,
      pageSize: pageSize.value
    })
    list.value = res.data?.list || []
    total.value = res.data?.total || 0
  } catch (e) {
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadTabCounts() {
  // 活跃/非活跃总数都拉一次（小开销，page_size=1 只取 total）
  try {
    const [a, i] = await Promise.all([
      listFeedback({ tab: 'active', page: 1, pageSize: 1 }),
      listFeedback({ tab: 'inactive', page: 1, pageSize: 1 })
    ])
    tabCount.value = {
      active: a.data?.total || 0,
      inactive: i.data?.total || 0
    }
  } catch (e) {
    tabCount.value = { active: 0, inactive: 0 }
  }
}

function handleTabChange() {
  page.value = 1
  loadList()
}
function onSizeChange(s) {
  pageSize.value = s
  page.value = 1
  loadList()
}

function openDrawer(fb) {
  currentFb.value = fb
  drawerVisible.value = true
}

async function handleVote(fb) {
  const email = localStorage.getItem('global_user_email') || ''
  if (!email) {
    await promptForEmail()
    return
  }
  if (votedIds.value.has(fb.id)) return
  try {
    await apiVote({ id: fb.id, email })
    votedIds.value.add(fb.id)
    fb.vote_count = (fb.vote_count || 0) + 1
    ElMessage.success('+1 成功')
  } catch (e) {
    // 400 already voted - 加入集合
    if (e.message && e.message.includes('already voted')) {
      votedIds.value.add(fb.id)
      ElMessage.warning('您已为此反馈投过票')
    }
    // 其他错误已被 request.js 拦截器处理
  }
}

async function promptForEmail() {
  try {
    await ElMessageBox.confirm(
      '请前往设置页填写反馈邮箱',
      '需要邮箱',
      { confirmButtonText: '去设置', cancelButtonText: '取消', type: 'warning' }
    )
    router.push('/settings')
  } catch (_) {
    // 用户取消，不操作
  }
}

function openSubmitDialog() {
  submitForm.value = {
    email: localStorage.getItem('global_user_email') || '',
    content: ''
  }
  submitFile.value = null
  submitVisible.value = true
}
function onFileChange(file) {
  if (file.size > 5 * 1024 * 1024) {
    ElMessage.error('文件超过 5MB')
    submitFile.value = null
    return false
  }
  submitFile.value = file.raw
}
function onExceed() {
  ElMessage.warning('只能上传 1 个文件')
}
function onFileRemove() {
  submitFile.value = null
}

async function handleSubmit() {
  const email = submitForm.value.email.trim()
  const content = submitForm.value.content.trim()
  if (!email || !content) {
    ElMessage.error('邮箱和内容必填')
    return
  }
  // 邮箱不匹配全局设置时，自动更新
  const globalEmail = localStorage.getItem('global_user_email') || ''
  if (email !== globalEmail) {
    localStorage.setItem('global_user_email', email)
  }

  submitting.value = true
  try {
    const fd = new FormData()
    fd.append('email', email)
    fd.append('content', content)
    if (submitFile.value) {
      fd.append('files', submitFile.value)
    }
    await apiSubmit(fd)
    ElMessage.success('提交成功')
    submitVisible.value = false
    await loadList()
    await loadTabCounts()
  } catch (e) {
    // 错误已由 request.js 拦截器处理
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const email = localStorage.getItem('global_user_email')
  if (!email) {
    await promptForEmail()
  }
  await loadList()
  await loadTabCounts()
})
</script>
```

- [ ] **Step 3: 添加 `<style scoped>` 区**

```vue
<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.feedback-page {
  padding: 24px 32px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 700;
  color: $text-primary;
  margin-bottom: 4px;
}

.page-subtitle {
  font-size: 13px;
  color: $text-muted;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  min-height: 200px;
  margin-top: 16px;
}

.feedback-card {
  padding: 16px;
  border-radius: 12px;
  background: $bg-elevated;
  border: 1px solid $border;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: $brand-start;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  }
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.vote-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #ef4444;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 12px;
  transition: background 0.2s;

  &:hover {
    background: rgba(239, 68, 68, 0.1);
  }
}

.card-content {
  font-size: 14px;
  line-height: 1.6;
  color: $text-primary;
  margin-bottom: 12px;
  word-break: break-word;
}

.card-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: $text-muted;
  margin-bottom: 8px;
}

.card-attachments {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: $text-muted;
}

.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 24px 0;
}

.drawer-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.drawer-assignee {
  font-size: 13px;
  color: $text-secondary;
}

.drawer-time {
  font-size: 12px;
  color: $text-muted;
}

.drawer-content-text {
  padding: 12px;
  background: $bg-surface;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.6;
}

.drawer-attachments {
  h4 {
    font-size: 14px;
    margin-bottom: 8px;
    color: $text-primary;
  }
  .attachment-img {
    width: 100px;
    height: 100px;
    border-radius: 6px;
    margin-right: 8px;
    margin-bottom: 8px;
  }
}

.drawer-vote {
  padding-top: 12px;
  border-top: 1px solid $border;
}

.vote-num {
  margin-left: 6px;
  padding: 0 8px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 10px;
  font-size: 12px;
}

:deep(.el-tabs__item) {
  color: $text-secondary;
}
:deep(.el-tabs__item.is-active) {
  color: $brand-start;
}
</style>
```

> 注：样式中 `$text-primary`、`$bg-elevated` 等 SCSS 变量来自 `@/styles/variables.scss`（项目其他页面如 Dashboard.vue、AccountManagement.vue 已使用此模式）。

- [ ] **Step 4: 验证 build 通过**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build --mode development 2>&1 | tail -20
```

Expected: 成功，无错误。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/Feedback.vue
git commit -m "feat(frontend): 实现 Feedback.vue 主页面"
```

---

## Task 9: 前端 `App.vue` 调整菜单顺序 + 新增第 10 项

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: 调整 navItems 数组**

定位 `const navItems = [` 块。**完整替换**为：

```javascript
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

- [ ] **Step 2: 在 icon import 行追加 ChatDotRound**

定位 `import { ... } from '@element-plus/icons-vue'`。

在该行末尾 `UserFilled, Document, Notebook` 之后追加 `, ChatDotRound`：

```javascript
import {
  HomeFilled, User, Picture, Upload,
  Clock, Setting, Expand, Fold, UserFilled, Document, Notebook, ChatDotRound
} from '@element-plus/icons-vue'
```

- [ ] **Step 3: 验证 build 通过**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build --mode development 2>&1 | tail -5
```

Expected: 成功。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/App.vue
git commit -m "feat(frontend): 调整菜单顺序并新增一键反馈入口"
```

---

## Task 10: 前端 `router/index.js` 加路由

**Files:**
- Modify: `frontend/src/router/index.js`

- [ ] **Step 1: 在 routes 数组末尾追加**

定位 `const routes = [` 块的最后一个 `}` 元素（Author 路由）之后，逗号后追加：

```javascript
  { path: '/feedback', name: 'Feedback', component: () => import('../views/Feedback.vue'), meta: { icon: 'ChatDotRound', title: '一键反馈' } }
```

完整 routes 数组最后两行形如：

```javascript
  { path: '/author', name: 'Author', component: Author, meta: { icon: 'UserFilled', title: '关于作者', isBottom: true } },
  { path: '/feedback', name: 'Feedback', component: () => import('../views/Feedback.vue'), meta: { icon: 'ChatDotRound', title: '一键反馈' } }
```

- [ ] **Step 2: 验证 build 通过**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build --mode development 2>&1 | tail -5
```

Expected: 成功。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/router/index.js
git commit -m "feat(frontend): 加 /feedback 路由"
```

---

## Task 11: 手动 e2e 验证

**Files:** 无（仅验证）

- [ ] **Step 1: 启动后端**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python app.py
```

Expected: 端口 5409 监听中，无报错。如被占用：

```bash
lsof -i :5409 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
```

- [ ] **Step 2: 启动前端 dev server**

新开终端：

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run dev
```

Expected: Vite 启动，端口 5173 监听。

- [ ] **Step 3: 浏览器验证清单**

打开 `http://localhost:5173`，逐项打勾：

- [ ] 左侧菜单出现「一键反馈」在第 10 项（最底部）
- [ ] 菜单顺序：仪表盘、账号管理、素材管理、视频发布、图文发布、草稿箱、发布历史、更新日志、关于作者、一键反馈
- [ ] 点击「一键反馈」进入页面
- [ ] 若未在 Settings 填邮箱，弹出提示「请前往设置页填写反馈邮箱」并提供「去设置」按钮
- [ ] 去 Settings 填邮箱，保存
- [ ] 返回「一键反馈」页面
- [ ] 列表正常加载（活跃 Tab 显示待确认+处理中的反馈）
- [ ] 切换到「非活跃反馈」Tab，显示已完成+已拒绝的
- [ ] 每张卡片显示：状态徽章、内容预览、+1 数、邮箱（脱敏）、创建时间
- [ ] 卡片按 `vote_count desc, created_at desc` 排序
- [ ] 点击卡片，右侧抽屉显示完整内容
- [ ] 抽屉内点击「+1 支持」，按钮变「已支持」，+1 数字 +1
- [ ] 再次点不会重复 +1
- [ ] 页面右上角点「提交反馈」，弹对话框
- [ ] 邮箱已自动填充全局邮箱
- [ ] 填内容，可选附件，点「提交」
- [ ] 关闭对话框，列表自动刷新，新反馈出现在最前面
- [ ] Tab 标题里的数字自动更新
- [ ] 模拟上游 502：临时关掉后端，前端弹「反馈系统不可达」

- [ ] **Step 4: 最终提交（如有零散改动）**

```bash
git status
```

如有未提交改动：

```bash
git add -A && git commit -m "chore: 反馈菜单 e2e 验证后的微调"
```

否则跳过。

---

## 完成标准

✅ 9 个后端 pytest 全部通过
✅ 前端 `vite build` 成功无错误
✅ 浏览器 e2e 清单 16 项全部通过
✅ 所有改动已 commit（中文 message）
✅ Spec `docs/superpowers/specs/2026-06-06-feedback-menu-design.md` 和 Plan `docs/superpowers/plans/2026-06-06-feedback-menu.md` 都已落盘
