# -*- coding: utf-8 -*-
"""文章发布 Blueprint — 一键分发文章到多平台(首个平台:微信公众号)。

与图集发布(image_publish_bp)同一套交互模式:
  前端逐账号调 POST /publish(共用 batchId) → 后端写 publish_batches
  (type='article') + publish_details → 调 platform.publish_article。

正文为富文本 HTML(img src 指向本地素材库),图片上传与替换由各平台
publish_article 实现负责(公众号走 filetransfer → mmbiz CDN)。

草稿管理直接复用 /api/v2/drafts(type='article'),本文件不含草稿接口。
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from storage import resolve_material_path
from util._logger import get_channel_logger

logger = get_channel_logger("article_publish")

article_publish_bp = Blueprint(
    "article_publish", __name__, url_prefix="/api/article-publish"
)

DB_PATH = BASE_DIR / "db" / "database.db"

# 支持文章发布的平台(平台 key → platform_id),与前端 ARTICLE_PLATFORM_KEYS 对应
ARTICLE_PLATFORM_MAP = {
    "weixin_gzh": 17,
    "微信公众号": 17,
}

# 忽略字段:正文 HTML 单独接收,不进 account_configs 的通用拷贝
_ARTICLE_EXCLUDED = {"filePath"}


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _update_article_publish_detail(detail_id, status, error_message=""):
    """更新单条 publish_details 状态,并聚合到 publish_batches(同图集)。"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "UPDATE publish_details SET status=?, finished_at=?, error_message=? WHERE id=?",
                (status, datetime.now().isoformat(), error_message, detail_id),
            )
            row = conn.execute(
                "SELECT batch_id FROM publish_details WHERE id=?", (detail_id,)
            ).fetchone()
            if not row:
                return
            batch_id = row[0]
            counts = conn.execute(
                """SELECT COUNT(*),
                          SUM(CASE WHEN status='success' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)
                   FROM publish_details WHERE batch_id=?""",
                (batch_id,),
            ).fetchone()
            total, succ, fail = counts[0], counts[1] or 0, counts[2] or 0
            if total == 0:
                bs = "pending"
            elif fail == 0:
                bs = "success"
            elif succ == 0:
                bs = "failed"
            else:
                bs = "partial"
            conn.execute(
                """UPDATE publish_batches
                   SET status=?, success_count=?, failed_count=?, account_count=?,
                       finished_at=?, updated_at=?
                   WHERE id=?""",
                (bs, succ, fail, total, datetime.now().isoformat(),
                 datetime.now().isoformat(), batch_id),
            )
    except Exception as e:
        logger.info(f"[article_publish] 更新状态失败: {e}")


@article_publish_bp.route("/publish", methods=["POST"])
def publish_article():
    """发布文章到单个账号(前端多账号循环调用,共用 batchId)。

    Body:
        batchId: 批次 id(可选,首次不传由后端生成)
        account_configs: 单账号配置 dict:
            platform: 'weixin_gzh'
            filePath: cookie 文件名
            account_id / account_name
            articleTitle: 标题(≤64 字)
            articleHtml: 正文 HTML(img src=本地素材 URL)
            articleAuthor / articleDigest: 作者/摘要(选填)
            gzhCollectionName / gzhClaimSource / gzhOriginalUrl: 公众号设置(选填)
            scheduleTime: 定时发表(空=按 isDraft/dryRun 语义)
            isDraft: True=保存草稿(默认),False=直接发表
            dryRun: True=完整表单+截图+存草稿(默认 True,安全)
    """
    import asyncio
    from impl.registry import get_platform

    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    config = data.get("account_configs")
    batch_id = data.get("batchId") or str(uuid.uuid4())
    detail_id = str(uuid.uuid4())

    if not config or not isinstance(config, dict):
        return jsonify({"code": 400, "msg": "account_configs 必须是单个账号配置 dict"}), 400

    title = (config.get("articleTitle") or "").strip()
    html = config.get("articleHtml") or ""
    if not title:
        return jsonify({"code": 400, "msg": "文章标题不能为空"}), 400
    if not html.strip():
        return jsonify({"code": 400, "msg": "文章正文不能为空"}), 400

    now = datetime.now().isoformat()
    platform_key = config.get("platform", "weixin_gzh")
    account_id = config.get("account_id")
    account_name = config.get("account_name") or Path(
        config.get("filePath", "")
    ).stem
    digest = (config.get("articleDigest") or "")[:200]

    # dry-run 安全默认:任何模式都不真发表,除非显式 dryRun=0 且 isDraft=0
    dry_run = config.get("dryRun", True) in (True, "true", "True", 1, "1")
    is_draft = True if dry_run else config.get("isDraft", True) in (True, "true", "True", 1, "1")

    excluded = set(_ARTICLE_EXCLUDED)
    account_configs = {k: v for k, v in config.items() if k not in excluded}

    try:
        conn = _get_db()
        conn.execute(
            """INSERT OR IGNORE INTO publish_batches
               (id, type, title, description, image_material_ids,
                landscape_cover_material_id, portrait_cover_material_id,
                account_count, status, source, created_at, updated_at)
               VALUES (?, 'article', ?, ?, '[]', '', '', 0, 'pending', 'article', ?, ?)""",
            (batch_id, title, digest, now, now),
        )
        conn.execute(
            """INSERT INTO publish_details
               (id, batch_id, account_id, account_name, platform, account_configs,
                status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'running', ?)""",
            (detail_id, batch_id, account_id, account_name, platform_key,
             json.dumps(account_configs, ensure_ascii=False), now),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({"code": 500, "msg": f"写入失败: {e}"}), 500

    # ---------- 实际发布执行 ----------
    success = False
    err = ""
    try:
        platform_id = ARTICLE_PLATFORM_MAP.get(platform_key)
        if not platform_id:
            raise ValueError(f"不支持文章发布的平台: {platform_key}")
        platform_obj = get_platform(platform_id)
        if not platform_obj:
            raise ValueError("无法获取平台实例")
        if not config.get("filePath"):
            raise ValueError("缺少账号 cookie 配置(filePath)")

        schedule_time = config.get("scheduleTime", "") or ""
        cover_stored = config.get("coverStoredPath", "") or ""
        publish_kwargs = dict(
                title=title,
                html=html,
                account_file=[config.get("filePath")],
                author=config.get("articleAuthor", "") or "",
                digest=digest,
                gzh_collection_name=config.get("gzhCollectionName", "") or "",
                gzh_claim_source=config.get("gzhClaimSource", "") or "",
                gzh_original_url=config.get("gzhOriginalUrl", "") or "",
                cover_path=resolve_material_path(cover_stored) if cover_stored else "",
                enableTimer=bool(schedule_time) and not is_draft,
                schedule_time_str=schedule_time,
                is_draft=is_draft,
                dry_run=dry_run,
            )
        logger.info(
            "[article_publish] 开始发布: account=%s platform=%s title=%s "
            "html_len=%d dry_run=%s is_draft=%s schedule=%s",
            account_name, platform_key, title, len(html), dry_run, is_draft,
            schedule_time or "无",
        )
        publish_fn = platform_obj.publish_article
        if asyncio.iscoroutinefunction(publish_fn):
            result = asyncio.run(publish_fn(**publish_kwargs))
        else:
            result = publish_fn(**publish_kwargs)
        success = bool(result)
    except Exception as e:
        logger.error(f"[article_publish] 发布失败: {e}", exc_info=True)
        err = str(e)
        success = False

    final_status = "success" if success else "failed"
    _update_article_publish_detail(detail_id, final_status, error_message=err)

    if success:
        return jsonify({
            "code": 200, "msg": "发布成功",
            "data": {"batch_id": batch_id, "detail_id": detail_id},
        })
    return jsonify({"code": 500, "msg": f"发布失败: {err}"}), 500


@article_publish_bp.route("/drafts/batch-publish", methods=["POST"])
def batch_publish_article_drafts():
    """文章草稿批量发布: 每篇逐账号推送到公众号草稿箱(同步执行)。

    Body: {"draft_ids": [int]} — 1-30 个文章草稿 id
    Response 200: {"code": 200, "succeeded": [id], "failed": [{draft_id, reason}]}
    Response 404: draft_ids 中存在不存在的草稿

    复用 /publish 单账号链路(test_request_context 内部调用),
    发布记录/发布历史与一键发布完全一致。
    """
    from flask import current_app
    from impl.registry import get_platform

    data = request.get_json() or {}
    draft_ids = data.get("draft_ids") or []
    if not isinstance(draft_ids, list) or not draft_ids or len(draft_ids) > 30:
        return jsonify({"code": 400, "msg": "draft_ids 数量必须 1-30"}), 400

    conn = _get_db()
    placeholders = ",".join("?" * len(draft_ids))
    rows = conn.execute(
        f"SELECT id, draft_data FROM drafts "
        f"WHERE id IN ({placeholders}) AND type = 'article'",
        draft_ids,
    ).fetchall()
    conn.close()

    found = {r["id"]: r["draft_data"] for r in rows}
    missing = [i for i in draft_ids if i not in found]
    if missing:
        return jsonify({
            "code": 404, "msg": "文章草稿不存在", "missing_ids": missing,
        }), 404

    succeeded = []
    failed = []
    for did in draft_ids:
        try:
            dd = json.loads(found[did] or "{}")
        except (json.JSONDecodeError, TypeError):
            failed.append({"draft_id": did, "reason": "草稿数据损坏"})
            continue

        common = dd.get("commonConfig") or {}
        title = (common.get("articleTitle") or "").strip()
        html = common.get("articleHtml") or ""
        account_ids = dd.get("publishAccountIds") or []
        pc = (dd.get("platformConfigs") or {}).get("weixin_gzh") or {}

        if not title:
            failed.append({"draft_id": did, "reason": "标题为空"})
            continue
        if not html.strip():
            failed.append({"draft_id": did, "reason": "正文为空"})
            continue
        if not account_ids:
            failed.append({"draft_id": did, "reason": "未选择发布账号"})
            continue
        if not get_platform(ARTICLE_PLATFORM_MAP["weixin_gzh"]):
            failed.append({"draft_id": did, "reason": "公众号平台未注册"})
            continue

        # 账号信息(cookie 文件)
        conn2 = _get_db()
        ph = ",".join("?" * len(account_ids))
        acc_rows = conn2.execute(
            f"SELECT id, filePath, userName FROM user_info WHERE id IN ({ph})",
            account_ids,
        ).fetchall()
        conn2.close()
        if not acc_rows:
            failed.append({"draft_id": did, "reason": "发布账号不存在或已删除"})
            continue

        batch_id = str(uuid.uuid4())
        all_ok = True
        errors = []
        for acc in acc_rows:
            account_configs = {
                "account_id": acc["id"],
                "account_name": acc["userName"] or Path(acc["filePath"]).stem,
                "platform": "weixin_gzh",
                "filePath": acc["filePath"],
                "articleTitle": title,
                "articleHtml": html,
                "articleAuthor": pc.get("articleAuthor", "") or "",
                "articleDigest": pc.get("articleDigest", "") or "",
                "gzhClaimSource": pc.get("gzhClaimSource", "") or "",
                "gzhCollectionName": pc.get("gzhCollectionName", "") or "",
                "gzhOriginalUrl": pc.get("gzhOriginalUrl", "") or "",
                "scheduleTime": pc.get("scheduleTime", "") or "",
                # 批量发布固定推送到公众号草稿箱(与一键发布一致,不群发)
                "dryRun": False,
                "isDraft": True,
            }
            try:
                with current_app.test_request_context(
                    "/api/article-publish/publish",
                    method="POST",
                    json={"batchId": batch_id, "account_configs": account_configs},
                ):
                    resp = publish_article()
                    if isinstance(resp, tuple):
                        body = resp[0].get_json() if hasattr(resp[0], "get_json") else {}
                        status = resp[1]
                    else:
                        body = resp.get_json() or {}
                        status = resp.status_code
                if status == 200 and body.get("code") == 200:
                    pass
                else:
                    all_ok = False
                    errors.append(
                        f"{account_configs['account_name']}: "
                        f"{body.get('msg') or f'HTTP {status}'}"
                    )
            except Exception as e:
                all_ok = False
                errors.append(f"{account_configs['account_name']}: {e}")

        if all_ok:
            succeeded.append(did)
        else:
            failed.append({
                "draft_id": did, "reason": "; ".join(errors) or "发布失败",
            })

    return jsonify({
        "code": 200, "succeeded": succeeded, "failed": failed,
    }), 200
