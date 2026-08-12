"""京东关联商品 picker 路由蓝图。

参考 backend/blueprints/taobao_guanghe_bp.py:
- 全局 picker event loop(后台 daemon 线程)
- 4 个路由:open / search / go_page / close
- session_id = account_id
"""

import asyncio
import logging
import threading
from typing import Optional

from flask import Blueprint, request, jsonify

from impl.jd.picker import pool, JdPickerSession

logger = logging.getLogger(__name__)

bp = Blueprint("jd_picker", __name__)

# ---------- 后台 event loop ----------

_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_loop_lock = threading.Lock()
_loop_ready = threading.Event()


def _start_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _loop_ready.set()
    _loop.run_forever()


def _ensure_loop():
    global _loop_thread
    if _loop_thread is None or not _loop_thread.is_alive():
        with _loop_lock:
            # 双重检查:拿锁后再次判定,避免并发请求各起一个 event loop
            if _loop_thread is None or not _loop_thread.is_alive():
                _loop_ready.clear()
                _loop_thread = threading.Thread(target=_start_loop, daemon=True)
                _loop_thread.start()
                _loop_ready.wait(timeout=5)
    return _loop


def run_picker_async(coro, timeout: float = 60):
    """跨线程提交协程到 picker event loop,等待结果返回。"""
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# ---------- 路由 ----------

@bp.route("/api/jd/picker/open", methods=["POST"])
def picker_open():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    if not account_id:
        return jsonify({"ok": False, "error": "accountId required"}), 400

    if pool.has(account_id):
        return jsonify({"ok": False, "error": f"账号 {account_id} 已有 picker 在运行"}), 400

    session = pool.get_or_create(account_id)
    try:
        products = run_picker_async(session.open(), timeout=60)
        return jsonify({"ok": True, "products": products, "sessionId": account_id})
    except Exception as e:
        pool.release(account_id)
        logger.exception("picker open failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/jd/picker/search", methods=["POST"])
def picker_search():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    keyword = data.get("keyword", "")
    if not account_id:
        return jsonify({"ok": False, "error": "accountId required"}), 400

    session = pool.get(account_id)
    if session is None:
        return jsonify({"ok": False, "error": "picker 未打开"}), 400

    try:
        products = run_picker_async(session.search(keyword), timeout=30)
        return jsonify({"ok": True, "products": products})
    except Exception as e:
        logger.exception("picker search failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/jd/picker/go_page", methods=["POST"])
def picker_go_page():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    page = data.get("page", 1)
    if not account_id:
        return jsonify({"ok": False, "error": "accountId required"}), 400

    session = pool.get(account_id)
    if session is None:
        return jsonify({"ok": False, "error": "picker 未打开"}), 400

    try:
        products = run_picker_async(session.go_page(page), timeout=30)
        return jsonify({"ok": True, "products": products})
    except Exception as e:
        logger.exception("picker go_page failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/api/jd/picker/close", methods=["POST"])
def picker_close():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    if not account_id:
        return jsonify({"ok": False, "error": "accountId required"}), 400

    pool.release(account_id)
    return jsonify({"ok": True})
