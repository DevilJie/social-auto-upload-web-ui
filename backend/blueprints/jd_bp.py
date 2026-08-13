"""京东关联商品 picker 路由蓝图。

参考 backend/blueprints/taobao_guanghe_bp.py:
- 全局 picker event loop(后台 daemon 线程)
- 4 个路由:open / search / go_page / close
- session_id = account_id
- 统一响应格式 {code:200, data:{...}} / {code:4xx|5xx, msg:'...'},对齐前端 axios 拦截器
"""

import asyncio
import logging
import threading
from typing import Optional

from flask import Blueprint, request, jsonify

from impl.jd.picker import pool, JdPickerSession
from util._logger import get_channel_logger

logger = get_channel_logger("jingmai")

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


# ---------- 统一响应格式 (对齐前端 utils/request.js 拦截器) ----------

def _ok(data: dict):
    return jsonify({"code": 200, "data": data})


def _err(msg: str, code: int = 500, http: int = 500):
    return jsonify({"code": code, "msg": msg}), http


def _resolve_session_or_404(account_id: str):
    """从池中取 session,不存在返回 (None, error_response)。"""
    if not account_id:
        return None, _err("accountId 不能为空", 400, 400)
    session = pool.get(account_id)
    if session is None:
        return None, _err("picker 未打开或已关闭,请重新打开弹窗", 404, 404)
    return session, None


# ---------- 路由 ----------

@bp.route("/api/jd/picker/open", methods=["POST"])
def picker_open():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    if not account_id:
        return _err("accountId 不能为空", 400, 400)

    # pool.create:若同账号已有 session(前端 close 漏调、上次崩溃残留等),
    # 自动异步销毁旧的再建新的。不再返回"已有 picker 在运行" 409 ——
    # 客户端不需要为 session 生命周期负责。
    session = pool.create(account_id)
    try:
        result = run_picker_async(session.open(), timeout=60)
        return _ok({
            "products": result["products"],
            "total": result["total"],
            "sessionId": account_id,
        })
    except Exception as e:
        # 失败时清理 session:从池中移除 + 真正关闭浏览器
        logger.exception("picker open failed")
        released = pool.release(account_id)
        if released is not None:
            try:
                run_picker_async(released.close(), timeout=10)
            except Exception:
                pass  # 清理失败不阻塞错误返回
        return _err(f"打开选择面板失败: {e}")


@bp.route("/api/jd/picker/search", methods=["POST"])
def picker_search():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    keyword = data.get("keyword", "")
    session, err = _resolve_session_or_404(account_id)
    if err:
        return err

    try:
        result = run_picker_async(session.search(keyword), timeout=30)
        return _ok({"products": result["products"], "total": result["total"]})
    except Exception as e:
        logger.exception("picker search failed")
        return _err(str(e))


@bp.route("/api/jd/picker/go_page", methods=["POST"])
def picker_go_page():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    page = data.get("page", 1)
    session, err = _resolve_session_or_404(account_id)
    if err:
        return err

    try:
        result = run_picker_async(session.go_page(page), timeout=30)
        return _ok({"products": result["products"], "total": result["total"]})
    except Exception as e:
        logger.exception("picker go_page failed")
        return _err(str(e))


@bp.route("/api/jd/picker/close", methods=["POST"])
def picker_close():
    data = request.get_json() or {}
    account_id = data.get("accountId")
    if not account_id:
        return _err("accountId 不能为空", 400, 400)

    # pool.release 只 pop,真正关浏览器由这里跑在 picker loop 上
    session = pool.release(account_id)
    if session is None:
        # 幂等:再次关闭已不存在的 session 也算成功
        return _ok({"closed": True})
    try:
        run_picker_async(session.close(), timeout=20)
        return _ok({"closed": True})
    except Exception as e:
        logger.error(f"picker close 失败: {e}")
        return _err(str(e))
