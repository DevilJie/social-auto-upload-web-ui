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
