"""派生字段 personalized 计算逻辑。
对比 account_configs 与 publish_batches 的公共值，任一非跳过字段不一致 → True。
数据库不存，仅在 /api/v2/history 响应中计算。"""
import json


def compute_personalized(account_configs: dict, batch_row: dict) -> bool:
    cfg = account_configs or {}
    batch = batch_row or {}

    # 文本字段 — 老数据 cfg 缺 key 时不视为个性化（视为未覆写）
    if 'title' in cfg and (cfg.get('title') or '') != (batch.get('title') or ''):
        return True
    if 'description' in cfg and (cfg.get('description') or '') != (batch.get('description') or ''):
        return True

    # 视频/封面（ID 比较）
    video_id = (cfg.get('videoLandscape') or {}).get('id') or (cfg.get('videoPortrait') or {}).get('id')
    if video_id and video_id != (batch.get('video_material_id') or ''):
        return True

    cover_l_id = (cfg.get('coverLandscape') or {}).get('id')
    if cover_l_id and cover_l_id != (batch.get('landscape_cover_material_id') or ''):
        return True

    cover_p_id = (cfg.get('coverPortrait') or {}).get('id')
    if cover_p_id and cover_p_id != (batch.get('portrait_cover_material_id') or ''):
        return True

    # 图文图片（ID 列表比较）
    cfg_image_ids = [img.get('id', '') for img in (cfg.get('images') or [])]
    if cfg_image_ids:
        try:
            batch_image_ids = json.loads(batch.get('image_material_ids') or '[]')
        except (json.JSONDecodeError, TypeError):
            batch_image_ids = []
        if cfg_image_ids != batch_image_ids:
            return True

    # 标签、平台特有字段：不存公共值，跳过
    return False
