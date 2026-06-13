"""草稿合并/校验/payload 适配模块。

所有函数独立、纯 Python，不导入任何前端代码、不依赖任何 publish-page 内部。
字段集与 PublishCenter.vue:592-637 保持同步。
"""

import os
import sqlite3
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from conf import BASE_DIR

DB_PATH = BASE_DIR / "db" / "database.db"


def _get_account_by_id(account_id):
    """查 user_info 表，返回 account 对象（id/platform/file_path）或不存在的 None。

    user_info schema: (id, type INTEGER, filePath TEXT, userName TEXT, status, avatar)
    `type` 是数字平台 id（1-10），需要映射到字符串 key。
    """
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT id, type, filePath FROM user_info WHERE id = ?",
                (account_id,),
            ).fetchone()
        if not row:
            return None
        # 复用 app.py 里的 PLATFORM_ID_TO_KEY 映射（导入而非重复定义）
        from app import PLATFORM_ID_TO_KEY
        platform_key = PLATFORM_ID_TO_KEY.get(row[1], '')
        account = type('Account', (), {})()
        account.id = row[0]
        account.platform = platform_key
        account.file_path = row[2]
        return account
    except sqlite3.Error:
        return None


# 平台声明字段映射（与 PublishCenter.vue:1329-1338 一致）
DECLARATION_PLATFORMS = {
    'xiaohongshu': 'aiContent',
    'douyin': 'aiContent',
    'kuaishou': 'aiContent',
    'bilibili': 'creationDeclaration',
    'baijiahao': 'creationDeclaration',
    'tencent_video': 'creationDeclaration',
    'iqiyi': 'creationDeclaration',
    'youtube': ['audience', 'alteredContent'],
    # channels / tiktok 不在此表（不校验声明字段）
}


def _first_truthy(*values):
    """返回第一个真值；布尔用 is None 检查除外。"""
    for v in values:
        if v is not None and v != '' and v != []:
            return v
    return values[-1] if values else None


def _first_list(*values):
    """返回第一个非空 list；都是空则返回最后一个。"""
    for v in values:
        if isinstance(v, list) and len(v) > 0:
            return v
    return values[-1] if values else []


def _first_bool(*values):
    """布尔合并：用 is None 判定 None 表示"未设置"，False/True 都是有效值。"""
    for v in values:
        if v is not None:
            return v
    return False


def merge_config(common, platform_default, platform_ov, account_ov):
    """合并 4 层。3 级字段（大多数）：accountOv > platformOv > platformDefault。
    4 级字段（cover*/video*）：accountOv > platformOv > common（跳过 platformDefault）。"""
    common = common or {}
    platform_default = platform_default or {}
    platform_ov = platform_ov or {}
    account_ov = account_ov or {}

    # 4 级字段（common 兜底）
    cover_landscape = _first_truthy(account_ov.get('coverLandscape'), platform_ov.get('coverLandscape'), common.get('coverLandscape'))
    cover_portrait = _first_truthy(account_ov.get('coverPortrait'), platform_ov.get('coverPortrait'), common.get('coverPortrait'))
    video_landscape = _first_truthy(account_ov.get('videoLandscape'), platform_ov.get('videoLandscape'), common.get('videoLandscape'))
    video_portrait = _first_truthy(account_ov.get('videoPortrait'), platform_ov.get('videoPortrait'), common.get('videoPortrait'))

    # 3 级文本字段
    title = _first_truthy(account_ov.get('title'), platform_ov.get('title'), platform_default.get('title'), '')
    description = _first_truthy(account_ov.get('description'), platform_ov.get('description'), platform_default.get('description'), '')
    tags = _first_list(account_ov.get('tags'), platform_ov.get('tags'), platform_default.get('tags', []))

    # 3 级平台常见字段
    video_format = _first_truthy(account_ov.get('videoFormat'), platform_ov.get('videoFormat'), platform_default.get('videoFormat', ''), '')
    enable_timer = _first_truthy(account_ov.get('enableTimer'), platform_ov.get('enableTimer'), platform_default.get('enableTimer', 0), 0)
    schedule_time = _first_truthy(account_ov.get('scheduleTime'), platform_ov.get('scheduleTime'), platform_default.get('scheduleTime', ''), '')
    ai_content = _first_truthy(account_ov.get('aiContent'), platform_ov.get('aiContent'), platform_default.get('aiContent', ''), '')
    is_original = _first_bool(account_ov.get('isOriginal'), platform_ov.get('isOriginal'), platform_default.get('isOriginal', False))

    # 3 级平台特定字段
    platform_specific = {}
    for field in [
        'creationDeclaration', 'riskWarning', 'enableCashActivity',
        'supplementaryDeclaration', 'audience', 'alteredContent',
        'zone', 'activityId', 'hotspotId', 'hotspotData', 'selectedTag',
        'tagType', 'tagValue', 'mixId', 'mixData', 'topic', 'isDraft',
        'location', 'collection', 'groupChat',
    ]:
        platform_specific[field] = _first_truthy(
            account_ov.get(field), platform_ov.get(field), platform_default.get(field)
        )

    return {
        'title': title,
        'description': description,
        'tags': tags,
        'coverLandscape': cover_landscape,
        'coverPortrait': cover_portrait,
        'videoLandscape': video_landscape,
        'videoPortrait': video_portrait,
        'videoFormat': video_format,
        'enableTimer': enable_timer,
        'scheduleTime': schedule_time,
        'aiContent': ai_content,
        'isOriginal': is_original,
        **platform_specific,
    }


def validate_draft_for_publish(draft):
    """dry-run 校验视频草稿。返回错误消息列表。"""
    errors = []
    draft_data = draft.get('draft_data') or {}
    common = draft_data.get('commonConfig') or {}
    platform_configs = draft_data.get('platformConfigs') or {}
    platform_overrides = draft_data.get('platformOverrides') or {}
    account_overrides = draft_data.get('accountOverrides') or {}
    publish_account_ids = draft_data.get('publishAccountIds') or []

    # 1. 视频文件
    if not (common.get('videoLandscape') or common.get('videoPortrait')):
        errors.append('缺少视频文件')

    # 2. 至少 1 张封面（来自 3 个源）
    has_cover = bool(common.get('coverLandscape') or common.get('coverPortrait'))
    if not has_cover:
        for ov in account_overrides.values():
            if ov and (ov.get('coverLandscape') or ov.get('coverPortrait')):
                has_cover = True
                break
    if not has_cover:
        for ov in platform_overrides.values():
            if ov and (ov.get('coverLandscape') or ov.get('coverPortrait')):
                has_cover = True
                break
    if not has_cover:
        errors.append('缺少封面')

    # 3. publishAccountIds 非空
    if not publish_account_ids:
        errors.append('草稿未选择发布账号（publishAccountIds 为空）')
        return errors   # 后续检查依赖账号

    # 4. 每个账号的检查
    for account_id in publish_account_ids:
        account = _get_account_by_id(account_id)
        if account is None:
            errors.append(f'账号 {account_id} 不存在')
            continue

        platform = account.platform
        platform_default = platform_configs.get(platform) or {}
        account_ov = account_overrides.get(str(account_id)) or {}

        merged = merge_config(common, platform_default, platform_overrides.get(platform), account_ov)

        # 标题
        if not merged.get('title') or not str(merged['title']).strip():
            errors.append(f'账号 {account_id}({platform}) 缺标题')

        # 视频格式
        vf = merged.get('videoFormat')
        if vf not in ('portrait', 'landscape'):
            errors.append(f'账号 {account_id}({platform}) 缺视频格式')

        # 封面 per-videoFormat
        if vf == 'portrait' and not merged.get('coverPortrait'):
            errors.append(f'账号 {account_id}({platform}) 缺竖版封面')
        if vf == 'landscape' and not merged.get('coverLandscape'):
            errors.append(f'账号 {account_id}({platform}) 缺横版封面')

        # 声明字段
        decl_field = DECLARATION_PLATFORMS.get(platform)
        if decl_field:
            if isinstance(decl_field, list):
                # YouTube: 多个字段
                missing = [f for f in decl_field if not merged.get(f)]
                if missing:
                    errors.append(f'账号 {account_id}({platform}) 缺 {"+".join(missing)}')
            else:
                if not merged.get(decl_field):
                    errors.append(f'账号 {account_id}({platform}) 缺 {decl_field}')

        # 抖音活动+标签 ≤ 5
        if platform == 'douyin':
            ac_len = len(merged.get('activityId') or [])
            tg_len = len(merged.get('tags') or [])
            if ac_len + tg_len > 5:
                errors.append(f'账号 {account_id}(douyin) 活动({ac_len})+标签({tg_len}) 超过 5')

    return errors


# 图文平台声明字段映射（与视频版相同）
_IMAGE_DECLARATION_PLATFORMS = DECLARATION_PLATFORMS


def validate_image_draft_for_publish(draft):
    """dry-run 校验图文草稿。返回错误消息列表。"""
    errors = []
    image_ids = draft.get('image_ids') or []
    config = draft.get('account_configs') or {}

    if not image_ids:
        errors.append('缺少 image_ids')

    if not config.get('title') or not str(config['title']).strip():
        errors.append('缺 title（标题）')

    platform = config.get('platform', '')
    decl_field = _IMAGE_DECLARATION_PLATFORMS.get(platform)
    if decl_field:
        if isinstance(decl_field, list):
            missing = [f for f in decl_field if not config.get(f)]
            if missing:
                errors.append(f'图文草稿({platform}) 缺 {"+".join(missing)}')
        else:
            if not config.get(decl_field):
                errors.append(f'图文草稿({platform}) 缺 {decl_field}')

    return errors


def _resolve_stored_path(material):
    """从素材对象取 stored_path，再解析为本地绝对路径。

    相对路径（materials/2026/06/...）走 storage.resolve_material_path 解析；
    绝对路径原样返回（避免被 base_dir 拼接覆盖）。
    """
    if not material:
        return ''
    if isinstance(material, dict):
        stored = material.get('stored_path', '') or ''
        if not stored:
            return ''
        if os.path.isabs(stored):
            return stored
        try:
            from storage import resolve_material_path
            return resolve_material_path(stored) or stored
        except Exception:
            return stored
    return ''


def build_platform_kwargs(merged, common, account):
    """merged dict → platform.publish_video kwargs dict。
    common 兜底素材；account 提供 cookie 路径。"""
    merged = merged or {}
    common = common or {}

    video_format = merged.get('videoFormat') or ''

    # 视频文件路径（按 videoFormat 选）
    if video_format == 'portrait':
        selected_video = _resolve_stored_path(merged.get('videoPortrait')) \
            or _resolve_stored_path(common.get('videoPortrait'))
    elif video_format == 'landscape':
        selected_video = _resolve_stored_path(merged.get('videoLandscape')) \
            or _resolve_stored_path(common.get('videoLandscape'))
    else:
        # 无 videoFormat：先后再竖
        selected_video = _resolve_stored_path(merged.get('videoLandscape')) \
            or _resolve_stored_path(common.get('videoLandscape')) \
            or _resolve_stored_path(merged.get('videoPortrait')) \
            or _resolve_stored_path(common.get('videoPortrait'))

    # 封面路径
    cover_landscape = _resolve_stored_path(merged.get('coverLandscape')) \
        or _resolve_stored_path(common.get('coverLandscape'))
    cover_portrait = _resolve_stored_path(merged.get('coverPortrait')) \
        or _resolve_stored_path(common.get('coverPortrait'))

    # 通用 thumbnail（仅 portrait 缺时用 landscape 兜底，反之亦然；否则两者都有）
    generic_thumbnail = cover_portrait or cover_landscape

    # creationDeclaration list → 逗号 join；None → ''
    creation_decl = merged.get('creationDeclaration')
    if isinstance(creation_decl, list):
        creation_declaration = ','.join(creation_decl)
    elif creation_decl:
        creation_declaration = str(creation_decl)
    else:
        creation_declaration = ''

    # category: zone 优先（B 站），否则 isOriginal ? 1 : 0
    zone = merged.get('zone') or ''
    is_original = merged.get('isOriginal')
    if zone:
        category = zone
    else:
        category = 1 if is_original else 0

    # schedule_time
    schedule_time_str = merged.get('scheduleTime') or ''
    enable_timer = 1 if schedule_time_str else 0

    # mini_link: 仅 selectedTag.type === 'miniapp'
    selected_tag = merged.get('selectedTag') or {}
    if isinstance(selected_tag, dict) and selected_tag.get('type') == 'miniapp':
        mini_link = selected_tag.get('_searchKeyword') or ''
    else:
        mini_link = ''

    return {
        'title': merged.get('title', '') or '',
        'desc': merged.get('description', '') or '',
        'tags': merged.get('tags') or [],
        'activities': merged.get('activityId') or [],
        'files': [selected_video] if selected_video else [],
        'account_file': [account.file_path] if account and getattr(account, 'file_path', None) else [],
        'category': category,
        'enableTimer': enable_timer,
        'videos_per_day': 1,
        'daily_times': ['10:00'],
        'start_days': 0,
        'thumbnail_path': generic_thumbnail,
        'thumbnail_landscape_path': cover_landscape,
        'thumbnail_portrait_path': cover_portrait,
        'productLink': merged.get('productLink', '') or '',
        'productTitle': merged.get('productTitle', '') or '',
        'schedule_time_str': schedule_time_str,
        'ai_content': merged.get('aiContent', '') or '',
        'creation_declaration': creation_declaration,
        'risk_warning': merged.get('riskWarning', '') or '',
        'enable_cash_activity': bool(merged.get('enableCashActivity')),
        'supplementary_declaration': merged.get('supplementaryDeclaration', '') or '',
        'is_draft': bool(merged.get('isDraft')),
        'audience': merged.get('audience') or 'not_kids',
        'altered_content': bool(merged.get('alteredContent')),
        'hotspot': merged.get('hotspotId', '') or '',
        'tag_type': merged.get('tagType', '') or '',
        'tag_value': merged.get('tagValue', '') or '',
        'mini_link': mini_link,
        'mix_id': merged.get('mixId', '') or '',
    }
