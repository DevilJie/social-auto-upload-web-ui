"""淘宝光合「关联商品/店铺」选择面板 API。

前端弹窗生命周期与浏览器会话绑定:
- 打开弹窗 → POST /picker/open 创建会话(常驻无头浏览器,进入选择面板)
- 用户在弹窗内操作 → POST /picker/{switch_type,tab,filter,search,load_more}
- 关闭弹窗 → POST /picker/close 释放浏览器

关键实现:
- 全局 picker event loop(后台 daemon 线程),所有 session 的协程都跑在这个 loop,
  playwright 的 browser/page 对象因此能跨 HTTP 请求复用
- session_id = account_id,同一账号同时只能开一个 picker
"""

import asyncio
import sqlite3
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl.taobao_guanghe.picker import (
    GuanghePickerSession,
    _get_cookie_path_by_account_id,
    _resolve_cookie_path,
    pool,
)

logger = get_channel_logger("taobao_guanghe")

taobao_guanghe_bp = Blueprint('taobao_guanghe', __name__, url_prefix='/api/taobao_guanghe')


# ----------------------------------------------------------------------
# 持久 event loop:所有 picker 协程都在这个 loop 中跑
# ----------------------------------------------------------------------

_picker_loop = None
_picker_loop_lock = threading.Lock()
_picker_thread = None


def _ensure_picker_loop():
    """惰性启动后台 event loop 线程(全局单例)。"""
    global _picker_loop, _picker_thread
    with _picker_loop_lock:
        if _picker_loop is None:
            _picker_loop = asyncio.new_event_loop()

            def _run():
                asyncio.set_event_loop(_picker_loop)
                _picker_loop.run_forever()

            _picker_thread = threading.Thread(target=_run, daemon=True, name="taobao-guanghe-picker-loop")
            _picker_thread.start()
            logger.info("[Picker] event loop 已启动")
    return _picker_loop


def run_picker_async(coro, timeout: float = 180.0):
    """提交协程到 picker event loop 并同步等结果。"""
    loop = _ensure_picker_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _ok(data: dict):
    return jsonify({"code": 200, "data": data})


def _err(msg: str, code: int = 500, http: int = 500):
    return jsonify({"code": code, "msg": msg}), http


def _resolve_session_or_404(session_id: str):
    """从池中取 session,不存在返回 (None, error_response)。"""
    if not session_id:
        return None, _err("session_id 不能为空", 400, 400)
    session = pool.get(session_id)
    if session is None:
        return None, _err("会话不存在或已关闭,请重新打开弹窗", 404, 404)
    return session, None


# ----------------------------------------------------------------------
# API: 打开/初始化
# ----------------------------------------------------------------------

@taobao_guanghe_bp.route('/picker/open', methods=['POST'])
def picker_open():
    """打开弹窗 → 启动浏览器并进入选择面板。

    Body:
        account_id (str): 账号 id
        type (str): 'product' / 'shop'

    Returns:
        {"code":200,"data":{"session_id":"...","items":[...],"has_more":bool,"type":...}}
    """
    body = request.get_json(silent=True) or {}
    account_id = (body.get("account_id") or "").strip()
    type_ = (body.get("type") or "").strip()
    if not account_id:
        return _err("account_id 不能为空", 400, 400)
    if type_ not in ("product", "shop"):
        return _err("type 必须是 product 或 shop", 400, 400)

    cookie_file = _get_cookie_path_by_account_id(account_id)
    if not cookie_file:
        return _err("账号不存在或未登录", 404, 404)
    cookie_path = _resolve_cookie_path(cookie_file)

    logger.info(f"[Picker API] open account_id={account_id} type={type_}")
    try:
        # 同账号已有 session 的话先销毁(创建新 session 时 pool.create 内部会清理)
        session = pool.create(account_id, cookie_path)
        result = run_picker_async(session.open(type_), timeout=180)
        return _ok({"session_id": session.session_id, **result})
    except Exception as e:
        logger.error(f"[Picker API] open 失败: {e}", exc_info=True)
        # 失败时确保 session 已从池中移除(避免脏数据)
        pool.remove(account_id)
        return _err(f"打开选择面板失败: {e}")


# ----------------------------------------------------------------------
# API: 切换商品/店铺
# ----------------------------------------------------------------------

@taobao_guanghe_bp.route('/picker/switch_type', methods=['POST'])
def picker_switch_type():
    """切换商品↔店铺。

    Body:
        session_id (str)
        type (str): 'product' / 'shop'
    """
    body = request.get_json(silent=True) or {}
    session, err = _resolve_session_or_404(body.get("session_id"))
    if err:
        return err
    type_ = (body.get("type") or "").strip()
    if type_ not in ("product", "shop"):
        return _err("type 必须是 product 或 shop", 400, 400)
    try:
        result = run_picker_async(session.switch_type(type_), timeout=60)
        return _ok(result)
    except Exception as e:
        logger.error(f"[Picker API] switch_type 失败: {e}", exc_info=True)
        return _err(str(e))


# ----------------------------------------------------------------------
# API: 切换 tab(已购商品/平台优选)
# ----------------------------------------------------------------------

@taobao_guanghe_bp.route('/picker/tab', methods=['POST'])
def picker_tab():
    body = request.get_json(silent=True) or {}
    session, err = _resolve_session_or_404(body.get("session_id"))
    if err:
        return err
    tab = (body.get("tab") or "").strip()
    if tab not in ("bought", "preferred"):
        return _err("tab 必须是 bought 或 preferred", 400, 400)
    try:
        result = run_picker_async(session.switch_tab(tab), timeout=30)
        return _ok(result)
    except Exception as e:
        logger.error(f"[Picker API] tab 失败: {e}", exc_info=True)
        return _err(str(e))


# ----------------------------------------------------------------------
# API: 切换筛选(推荐规则/品类)
# ----------------------------------------------------------------------

@taobao_guanghe_bp.route('/picker/filter', methods=['POST'])
def picker_filter():
    body = request.get_json(silent=True) or {}
    session, err = _resolve_session_or_404(body.get("session_id"))
    if err:
        return err
    rule = body.get("rule")
    category = body.get("category")
    if not rule and not category:
        return _err("rule 或 category 至少传一个", 400, 400)
    try:
        result = run_picker_async(session.apply_filter(rule=rule, category=category), timeout=30)
        return _ok(result)
    except Exception as e:
        logger.error(f"[Picker API] filter 失败: {e}", exc_info=True)
        return _err(str(e))


# ----------------------------------------------------------------------
# API: 搜索
# ----------------------------------------------------------------------

@taobao_guanghe_bp.route('/picker/search', methods=['POST'])
def picker_search():
    body = request.get_json(silent=True) or {}
    session, err = _resolve_session_or_404(body.get("session_id"))
    if err:
        return err
    keyword = (body.get("keyword") or "").strip()
    try:
        result = run_picker_async(session.search(keyword), timeout=30)
        return _ok(result)
    except Exception as e:
        logger.error(f"[Picker API] search 失败: {e}", exc_info=True)
        return _err(str(e))


# ----------------------------------------------------------------------
# API: 加载更多
# ----------------------------------------------------------------------

@taobao_guanghe_bp.route('/picker/load_more', methods=['POST'])
def picker_load_more():
    body = request.get_json(silent=True) or {}
    session, err = _resolve_session_or_404(body.get("session_id"))
    if err:
        return err
    try:
        result = run_picker_async(session.load_more(), timeout=30)
        return _ok(result)
    except Exception as e:
        logger.error(f"[Picker API] load_more 失败: {e}", exc_info=True)
        return _err(str(e))


# ----------------------------------------------------------------------
# API: 关闭(释放浏览器)
# ----------------------------------------------------------------------

@taobao_guanghe_bp.route('/picker/close', methods=['POST'])
def picker_close():
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "").strip()
    session = pool.remove(session_id)
    if session is None:
        # 幂等:再次关闭已不存在的 session 也算成功
        return _ok({"closed": True})
    try:
        run_picker_async(session.close(), timeout=20)
        return _ok({"closed": True})
    except Exception as e:
        logger.error(f"[Picker API] close 失败: {e}", exc_info=True)
        return _err(str(e))
