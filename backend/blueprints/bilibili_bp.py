"""B 站创作者平台相关 API 代理(纯 HTTP 轻量方案)。

合集列表 / 参与话题列表均直连 B站创作中心接口:
从 cookie 文件解析登录态 → requests 带 Cookie/UA/Referer 请求 → 毫秒级返回。
两个接口均经投稿页抓包确认无需 wbi 签名(2026-10)。

历史:合集列表旧实现走浏览器 UI 解析(开上传页→传测试视频→点「请选择合集」
→解析浮层 DOM),单次请求 30-60s、每次都向 B 站上传一个测试视频,且 B 站
改版后「请选择合集」入口文案变化导致接口必挂;前端下拉每次展开都调一次,
体验极差。2026-10 重构为纯 HTTP 直连(实测 108ms)。
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("bilibili")

bilibili_bp = Blueprint('bilibili', __name__, url_prefix='/api/bilibili')

# B 站创作中心投稿页(接口 Referer 来源)
_BILI_UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"
# 合集接口(2026-10 投稿页侦察:GET 无 wbi 签名,登录 cookie 即可)
_BILI_SEASONS_API = "https://member.bilibili.com/x2/creative/web/seasons"
# 参与话题接口(同上,按标题相关性推荐)
_BILI_TOPIC_API = "https://member.bilibili.com/x/vupre/web/topic/type/v2"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
)


def _get_cookie_path(cookie_file: str) -> str:
    """获取 cookie 文件的完整路径。"""
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    """从数据库按账号 id 取 cookie 文件名;account_id 为空则取任一 B 站账号。"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        # type=5 为 B 站
        cursor.execute("SELECT filePath FROM user_info WHERE type = 5 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def _bili_api_get(url: str, cookie_path: str) -> dict:
    """带登录态请求 B站创作中心接口,返回响应 JSON。

    cookie_path 指向 Playwright storage_state JSON,解析出 bilibili 域的
    cookie 拼 Cookie 头;实测(cookie+UA+Referer)可通过风控。
    网络/HTTP 层失败抛异常,由调用方转 500。
    """
    state = json.loads(Path(cookie_path).read_text(encoding="utf-8"))
    cookie_str = "; ".join(
        f"{c['name']}={c['value']}"
        for c in state.get("cookies", [])
        if "bilibili" in c.get("domain", "")
    )
    headers = {
        "Cookie": cookie_str,
        "User-Agent": _UA,
        "Referer": _BILI_UPLOAD_URL,
        "Origin": "https://member.bilibili.com",
    }
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


@bilibili_bp.route('/collections', methods=['GET'])
def list_collections():
    """获取账号的合集列表(投稿表单「选择合集」数据源)。

    Query params:
        account_id: 账号 id(用于取 cookie)

    Returns:
        {"code": 200, "data": {"list": [{"name": 合集名, "id": 合集id,
         "total": 稿件数}...], "total": N, "tip": B站提示(可为空)}}
    """
    account_id = request.args.get('account_id')
    logger.info(f"[合集列表] 收到请求: account_id={account_id}")

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[合集列表] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的 B 站账号"}), 404

        cookie_path = _get_cookie_path(cookie_file)
        url = (
            f"{_BILI_SEASONS_API}?pn=1&ps=50&order=desc&sort=mtime"
            f"&filter=1&t={int(time.time() * 1000)}"
        )
        body = _bili_api_get(url, cookie_path)
        if body.get("code") != 0:
            msg = f"B站接口返回异常: code={body.get('code')} {body.get('message', '')}"
            logger.error(f"[合集列表] {msg}")
            return jsonify({"code": 500, "msg": msg}), 500

        data = body.get("data") or {}
        seasons = data.get("seasons") or []
        items = []
        for s in seasons:
            if not isinstance(s, dict):
                continue
            # seasons 元素字段名未固化(无合集账号无法实测有合集结构),
            # 合集名按 title/name/season_name 宽兼容取值
            name = (s.get("title") or s.get("name") or s.get("season_name") or "").strip()
            if not name:
                continue
            items.append({
                "name": name,
                "id": s.get("season_id") or s.get("id") or "",
                "total": s.get("total", ""),
            })
        tip = (data.get("tip") or {}).get("title") or ""
        logger.info(f"[合集列表] 成功,共 {len(items)} 个合集")
        return jsonify({
            "code": 200,
            "data": {"list": items, "total": len(items), "tip": tip},
        })
    except Exception as e:
        logger.error(f"[合集列表] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


@bilibili_bp.route('/topics', methods=['GET'])
def list_topics():
    """获取 B 站参与话题列表(投稿表单「参与话题」数据源)。

    Query params:
        account_id: 账号 id(用于取 cookie)
        title: 视频标题(可选,B 站按标题相关性推荐话题)

    Returns:
        {"code": 200, "data": {"list": [{"topicId","name","activityText",
         "activityDescription","playVv"}...], "total": N}}
    """
    account_id = request.args.get('account_id')
    title = request.args.get('title', '')
    logger.info(f"[话题列表] 收到请求: account_id={account_id} title={title!r}")

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[话题列表] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的 B 站账号"}), 404

        cookie_path = _get_cookie_path(cookie_file)
        params = {
            "pn": "0",
            "ps": "20",
            "title": title or "视频投稿",
            "platform": "pc",
            "t": str(int(time.time() * 1000)),
        }
        query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
        body = _bili_api_get(f"{_BILI_TOPIC_API}?{query}", cookie_path)
        if body.get("code") != 0:
            msg = f"B站接口返回异常: code={body.get('code')} {body.get('message', '')}"
            logger.error(f"[话题列表] {msg}")
            return jsonify({"code": 500, "msg": msg}), 500

        topics = (body.get("data") or {}).get("topics") or []
        items = [
            {
                "topicId": t.get("topic_id"),
                "name": t.get("topic_name", ""),
                "activityText": t.get("activity_text") or "",
                "activityDescription": t.get("topic_description") or "",
                "playVv": t.get("arc_play_vv", 0),
            }
            for t in topics
            if t.get("topic_name")
        ]
        logger.info(f"[话题列表] 成功,共 {len(items)} 个话题")
        return jsonify({"code": 200, "data": {"list": items, "total": len(items)}})
    except Exception as e:
        logger.error(f"[话题列表] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500
