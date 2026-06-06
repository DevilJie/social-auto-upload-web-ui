"""反馈系统代理的单元测试。"""
import sys
from pathlib import Path

# 让 app.py / conf.py 可被 import
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def test_feedback_sign_known_vector():
    """硬编码已知 hex（用 Python 一次性算好写死的，不是运行公式）。"""
    from app import _feedback_sign

    # 已知向量：HMAC-SHA256("sk_test", "ak_test1717555800000sk_test")
    # 上述公式算出的 hex 是 64 字符小写：
    expected = "54875963021a1bb4640e2c87ad7e90125d9ee4ca0e4e797bc8abd80e13cd281f"

    actual = _feedback_sign("1717555800000", app_key="ak_test", app_secret="sk_test")
    assert actual == expected
    assert len(actual) == 64
    assert actual == actual.lower()


def test_feedback_sign_different_vector():
    """不同输入应产生不同签名（防止常量被硬编码）。"""
    from app import _feedback_sign
    sig1 = _feedback_sign("1000", app_key="k1", app_secret="s1")
    sig2 = _feedback_sign("2000", app_key="k1", app_secret="s1")
    sig3 = _feedback_sign("1000", app_key="k2", app_secret="s1")
    assert sig1 != sig2
    assert sig1 != sig3
    assert sig2 != sig3


from unittest.mock import patch, MagicMock


def test_feedback_list_no_filter_returns_active():
    """不传 status/include_all 时原样透传上游响应；自动带上 settings 里的 email。"""
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

    with patch("app.read_settings", return_value={"feedbackEmail": "viewer@example.com"}):
        with patch("app._requests.get", side_effect=fake_get):
            client = app.test_client()
            r = client.get("/api/feedback/list?page=1&page_size=20")
            assert r.status_code == 200
            body = r.get_json()
            assert body["data"]["total"] == 1
            # 不应包含 include_all 或 status
            assert "include_all" not in captured["params"]
            assert "status" not in captured["params"]
            # settings 里的 email 自动透传给上游
            assert captured["params"].get("email") == "viewer@example.com"
            # URL 指向反馈系统
            assert captured["url"].startswith("https://feedback.cjxch.com/api/v1/feedback")
            # 签名头齐
            assert "X-App-Key" in captured["headers"]
            assert "X-Timestamp" in captured["headers"]
            assert "X-Sign" in captured["headers"]
            assert len(captured["headers"]["X-Sign"]) == 64
            # file_url 被改写为绝对 URL
            assert body["data"]["list"][0]["attachments"][0]["file_url"] == "https://feedback.cjxch.com/uploads/x.png"


def test_feedback_list_no_email_in_settings():
    """settings 没 email 时不传 email 给上游（仍能正常返回）。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"code": 200, "data": {"list": [], "total": 0}}
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        return fake_resp

    with patch("app.read_settings", return_value={}):
        with patch("app._requests.get", side_effect=fake_get):
            client = app.test_client()
            r = client.get("/api/feedback/list")
            assert r.status_code == 200
            assert "email" not in captured["params"]


def test_feedback_list_status_filter():
    """status=2 只传 status 给上游。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "code": 200,
        "data": {
            "list": [
                {"id": 2, "status": 2, "vote_count": 3},
            ],
            "total": 1
        }
    }
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        return fake_resp

    with patch("app._requests.get", side_effect=fake_get):
        client = app.test_client()
        r = client.get("/api/feedback/list?status=2")
        assert r.status_code == 200
        assert captured["params"].get("status") == 2
        assert "include_all" not in captured["params"]


def test_feedback_list_include_all():
    """include_all=true 不传 status。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {
        "code": 200,
        "data": {"list": [], "total": 0}
    }
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_get(url, params, headers, timeout):
        captured["params"] = params
        return fake_resp

    with patch("app._requests.get", side_effect=fake_get):
        client = app.test_client()
        r = client.get("/api/feedback/list?include_all=true")
        assert r.status_code == 200
        assert captured["params"].get("include_all") == "true"
        assert "status" not in captured["params"]


def test_feedback_list_invalid_status():
    """status 非整数返 400。"""
    from app import app

    client = app.test_client()
    r = client.get("/api/feedback/list?status=abc")
    assert r.status_code == 400
    assert "status" in r.get_json()["message"]


def test_feedback_list_upstream_5xx_returns_502():
    """上游 5xx 时后端返回 502。"""
    from app import app
    import requests as _requests

    fake_resp = MagicMock()
    fake_resp.raise_for_status.side_effect = _requests.HTTPError("500 Server Error")

    with patch("app._requests.get", return_value=fake_resp):
        client = app.test_client()
        r = client.get("/api/feedback/list")
        assert r.status_code == 502
        assert "反馈系统不可达" in r.get_json()["message"]


def test_feedback_submit_missing_fields():
    """缺 email（form + settings 都没有）和 content 返 400。"""
    from app import app

    # 模拟 settings 表里也没 email
    with patch("app.read_settings", return_value={}):
        client = app.test_client()
        r = client.post("/api/feedback/submit", data={"email": "a@b.com"})
        assert r.status_code == 400
        assert "必填" in r.get_json()["message"]

        r = client.post("/api/feedback/submit", data={"content": "hello"})
        assert r.status_code == 400


def test_feedback_submit_uses_settings_email_when_form_empty():
    """form 没传 email 时，从 settings 表读。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"code": 200, "data": {"id": 99}}
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_post(url, data, files, headers, timeout):
        captured["data"] = data
        return fake_resp

    with patch("app.read_settings", return_value={"feedbackEmail": "settings@example.com"}):
        with patch("app._requests.post", side_effect=fake_post):
            client = app.test_client()
            r = client.post("/api/feedback/submit", data={"content": "hello"})
            assert r.status_code == 200
            assert captured["data"]["email"] == "settings@example.com"
            assert captured["data"]["content"] == "hello"


def test_feedback_submit_form_email_overrides_settings():
    """form 显式传 email 时覆盖 settings（支持一身份多用场景）。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"code": 200, "data": {"id": 99}}
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_post(url, data, files, headers, timeout):
        captured["data"] = data
        return fake_resp

    with patch("app.read_settings", return_value={"feedbackEmail": "settings@example.com"}):
        with patch("app._requests.post", side_effect=fake_post):
            client = app.test_client()
            r = client.post(
                "/api/feedback/submit",
                data={"email": "override@example.com", "content": "hi"},
            )
            assert r.status_code == 200
            assert captured["data"]["email"] == "override@example.com"


def test_feedback_submit_forwards_files():
    """multipart 文件被转发到上游。"""
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

    with patch("app.read_settings", return_value={"feedbackEmail": "user@example.com"}):
        with patch("app._requests.post", side_effect=fake_post):
            client = app.test_client()
            r = client.post(
                "/api/feedback/submit",
                data={
                    "content": "应用启动后白屏",
                    "files": (io.BytesIO(b"fake-image-bytes"), "screen.png"),
                },
                content_type="multipart/form-data",
                buffered=True,
            )
            assert r.status_code == 200
            assert captured["data"]["email"] == "user@example.com"
            assert captured["data"]["content"] == "应用启动后白屏"
            assert len(captured["files"]) >= 1
            assert "X-Sign" in captured["headers"]
            assert captured["url"].startswith("https://feedback.cjxch.com/api/v1/feedback")


def test_feedback_vote_uses_settings_email():
    """vote 不传 email 时从 settings 读。"""
    from app import app

    fake_resp = MagicMock()
    fake_resp.json.return_value = {"code": 200, "data": None}
    fake_resp.status_code = 200
    fake_resp.raise_for_status = MagicMock()

    captured = {}
    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        return fake_resp

    with patch("app.read_settings", return_value={"feedbackEmail": "settings@example.com"}):
        with patch("app._requests.post", side_effect=fake_post):
            client = app.test_client()
            r = client.post("/api/feedback/vote", json={"id": 42})
            assert r.status_code == 200
            assert captured["url"] == "https://feedback.cjxch.com/api/v1/feedback/42/vote"
            assert captured["json"] == {"email": "settings@example.com"}


def test_feedback_vote_no_email_anywhere_returns_400():
    """settings 没 email + body 也没 email → 400。"""
    from app import app

    with patch("app.read_settings", return_value={}):
        client = app.test_client()
        r = client.post("/api/feedback/vote", json={"id": 1})
        assert r.status_code == 400
        r = client.post("/api/feedback/vote", json={"id": 1, "email": ""})
        assert r.status_code == 400


def test_feedback_vote_forwards():
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

    with patch("app.read_settings", return_value={"feedbackEmail": "settings@example.com"}):
        with patch("app._requests.post", side_effect=fake_post):
            client = app.test_client()
            r = client.post("/api/feedback/vote", json={"id": 42, "email": "voter@example.com"})
            assert r.status_code == 200
            assert captured["url"] == "https://feedback.cjxch.com/api/v1/feedback/42/vote"
            assert captured["json"] == {"email": "voter@example.com"}
            assert "X-Sign" in captured["headers"]


def test_feedback_vote_passes_through_400():
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
