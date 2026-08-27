"""草稿合并/校验/payload 适配模块。

所有函数独立、纯 Python，不导入任何前端代码、不依赖任何 publish-page 内部。
字段集与 PublishCenter.vue:592-637 保持同步。
"""

import os
import re
import sqlite3
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from conf import BASE_DIR

DB_PATH = BASE_DIR / "db" / "database.db"

# 描述里独立 #xxx 话题计数正则(与 douyin/platform.py、xiaohongshu/platform.py 同语义)
_HASHTAG_PATTERN = re.compile(r"(?:^|\s)#[^\s#]+", re.MULTILINE)
DOUYIN_HASHTAG_RE = _HASHTAG_PATTERN
XHS_HASHTAG_RE = _HASHTAG_PATTERN


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
    cover_landscape_169 = _first_truthy(account_ov.get('coverLandscape169'), platform_ov.get('coverLandscape169'), common.get('coverLandscape169'))
    cover_portrait_916 = _first_truthy(account_ov.get('coverPortrait916'), platform_ov.get('coverPortrait916'), common.get('coverPortrait916'))
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
        # 批量发布补齐：与 PublishCenter mergeConfig / /postVideo 字段集对齐
        'category', 'biliRepostSource', 'biliCollectionName', 'biliCollectionData',
        'weiboCategory', 'videoType', 'contentStatement', 'contentStatement2',
        'contentStatement2Optional', 'weiboCollectionName',
        'authorStatement', 'reprintUrl', 'compilation', 'compilationData',
        'enableGenerateImage', 'extendLinkUrl',
        'recommend',
        'vivoLocationName', 'vivoLocationData', 'vivoDeclaration',
        'vivoPrivacy', 'vivoDownloadPermission',
        'gzhClaimSource', 'gzhCollectionName', 'gzhCollectionData',
        'guangheClaim', 'guangheLinkType', 'guangheProducts', 'guangheShops',
        'jdRelatedType', 'jdProducts', 'jdNovelData', 'jdDeclaration',
        'channelsCollectionName', 'channelsLocationName',
        'channelsActivityName', 'channelsActivityData', 'channelsMarkTag',
        'channelsShootDate', 'channelsShootRegion', 'channelsRepostSource',
        'collectionId', 'collectionName', 'collectionData',
        'xhsSourceType', 'xhsShootLocation', 'xhsShootDate', 'xhsRepostSource',
    ]:
        platform_specific[field] = _first_truthy(
            account_ov.get(field), platform_ov.get(field), platform_default.get(field)
        )

    # 布尔字段单独用 _first_bool（False 是有效值，不能用 _first_truthy 跳过）
    for field in ['extendLink', 'vivoDistribution']:
        platform_specific[field] = _first_bool(
            account_ov.get(field), platform_ov.get(field), platform_default.get(field)
        )

    return {
        'title': title,
        'description': description,
        'tags': tags,
        'coverLandscape': cover_landscape,
        'coverPortrait': cover_portrait,
        'coverLandscape169': cover_landscape_169,
        'coverPortrait916': cover_portrait_916,
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

        # 抖音话题总数 ≤ 5(描述 #xxx + 官方活动 + 标签)
        # 与 douyin/platform.py 的 _validate_publish_params、前端 PublishCenter 同语义
        if platform == 'douyin':
            desc_text = merged.get('description') or ''
            dh_len = len(DOUYIN_HASHTAG_RE.findall(desc_text))
            ac_len = len(merged.get('activityId') or [])
            tg_len = len(merged.get('tags') or [])
            if dh_len + ac_len + tg_len > 5:
                errors.append(
                    f'账号 {account_id}(douyin) 话题({dh_len + ac_len + tg_len})超过 5'
                    f'(描述#{dh_len} + 活动{ac_len} + 标签{tg_len})'
                )

        # 小红书话题总数 ≤ 10(描述 #xxx + 标签)
        # 与 xiaohongshu/platform.py 的前置校验、前端 PublishCenter 同语义
        if platform == 'xiaohongshu':
            desc_text = merged.get('description') or ''
            dh_len = len(XHS_HASHTAG_RE.findall(desc_text))
            tg_len = len(merged.get('tags') or [])
            if dh_len + tg_len > 10:
                errors.append(
                    f'账号 {account_id}(xiaohongshu) 话题({dh_len + tg_len})超过 10'
                    f'(描述#{dh_len} + 标签{tg_len})'
                )

    return errors


# 图集平台声明字段映射（与视频版相同）
_IMAGE_DECLARATION_PLATFORMS = DECLARATION_PLATFORMS


def validate_image_draft_for_publish(draft):
    """dry-run 校验图集草稿。返回错误消息列表。"""
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
                errors.append(f'图集草稿({platform}) 缺 {"+".join(missing)}')
        else:
            if not config.get(decl_field):
                errors.append(f'图集草稿({platform}) 缺 {decl_field}')

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

    # 视频文件路径:横版优先,无则竖版(不再区分横竖,上传了即可发;
    # 实际方向由素材表 materials.orientation 决定,各平台 impl 自行读取)
    selected_video = _resolve_stored_path(merged.get('videoLandscape')) \
        or _resolve_stored_path(common.get('videoLandscape')) \
        or _resolve_stored_path(merged.get('videoPortrait')) \
        or _resolve_stored_path(common.get('videoPortrait'))

    # 封面路径
    cover_landscape = _resolve_stored_path(merged.get('coverLandscape')) \
        or _resolve_stored_path(common.get('coverLandscape'))
    cover_portrait = _resolve_stored_path(merged.get('coverPortrait')) \
        or _resolve_stored_path(common.get('coverPortrait'))
    cover_landscape_169 = _resolve_stored_path(merged.get('coverLandscape169')) \
        or _resolve_stored_path(common.get('coverLandscape169'))
    cover_portrait_916 = _resolve_stored_path(merged.get('coverPortrait916')) \
        or _resolve_stored_path(common.get('coverPortrait916'))

    # 兜底：只上传了横版或竖版之一时，另一个用同图（与 /postVideo 一致）
    if cover_landscape and not cover_portrait:
        cover_portrait = cover_landscape
    elif cover_portrait and not cover_landscape:
        cover_landscape = cover_portrait

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

    # category: 微博级联数组 > zhihu 等字符串 category > B站 zone > 原创/转载数值
    weibo_cat = merged.get('weiboCategory')
    if isinstance(weibo_cat, list) and weibo_cat:
        category = weibo_cat
    elif merged.get('category'):
        category = merged.get('category')
    else:
        zone = merged.get('zone') or ''
        is_original = merged.get('isOriginal')
        if zone:
            category = zone
        else:
            category = 1 if is_original else 0

    # aiContent: 微博的「类型」(原创/二创/转载)走 videoType 字段透传（与 /postVideo 一致）
    platform_key = getattr(account, 'platform', '') if account else ''
    if platform_key == 'weibo':
        ai_content = merged.get('videoType', '') or ''
    else:
        ai_content = merged.get('aiContent', '') or ''

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
        'thumbnail_landscape_169_path': cover_landscape_169,
        'thumbnail_portrait_916_path': cover_portrait_916,
        'productLink': merged.get('productLink', '') or '',
        'productTitle': merged.get('productTitle', '') or '',
        'schedule_time_str': schedule_time_str,
        'ai_content': ai_content,
        'creation_declaration': creation_declaration,
        # B 站转载来源(创作声明=转载 时必填)
        'bili_repost_source': merged.get('biliRepostSource', '') or '',
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
        # 微博特有参数（类型走 ai_content，内容声明/合集单独透传）
        'content_statement': merged.get('contentStatement', '') or '',
        'content_statement2': merged.get('contentStatement2', '') or '',
        'content_statement2_optional': merged.get('contentStatement2Optional', '') or '',
        'weibo_collection': merged.get('weiboCollectionName', '') or '',
        # 支付宝特有参数（作者声明/转载来源/合集）
        'author_statement': merged.get('authorStatement', '') or '',
        'compilation': merged.get('compilation', '') or '',
        'reprint_url': merged.get('reprintUrl', '') or '',
        # 今日头条特有参数
        'enable_generate_image': merged.get('enableGenerateImage') if merged.get('enableGenerateImage') is not None else True,
        'collection_id': merged.get('collection', '') or '',
        'extend_link': bool(merged.get('extendLink')),
        'extend_link_url': merged.get('extendLinkUrl', '') or '',
        # CSDN 是否推荐
        'recommend': bool(merged.get('recommend')),
        # VIVO 平台特有参数
        'vivo_location_name': merged.get('vivoLocationName', '') or '',
        'vivo_distribution': bool(merged.get('vivoDistribution')),
        'vivo_declaration': merged.get('vivoDeclaration', '') or '',
        'vivo_privacy': merged.get('vivoPrivacy') or '公开',
        'vivo_download_permission': merged.get('vivoDownloadPermission') or '允许',
        # 微信公众号特有参数
        'is_original': bool(merged.get('isOriginal')),
        'gzh_collection_name': merged.get('gzhCollectionName', '') or '',
        'gzh_claim_source': merged.get('gzhClaimSource', '') or '',
        # 淘宝光合创作者声明 + 关联商品/店铺
        'guanghe_claim': merged.get('guangheClaim', '') or '',
        'guangheLinkType': merged.get('guangheLinkType', '') or '',
        'guangheProducts': merged.get('guangheProducts') or [],
        'guangheShops': merged.get('guangheShops') or [],
        # 京东平台特有参数
        'jd_related_type': merged.get('jdRelatedType', '') or '',
        'jd_products': merged.get('jdProducts') or [],
        'jd_novel': merged.get('jdNovelData') or (
            {'title': merged['jdNovel']} if merged.get('jdNovel') else ''),
        'jd_declaration': merged.get('jdDeclaration', '') or '',
        # 视频号合集/位置/活动/标注/拍摄信息
        'channels_activity_name': merged.get('channelsActivityName', '') or '',
        'channels_activity_id': (merged.get('channelsActivityData') or {}).get('activity_id', ''),
        'channels_mark_tag': merged.get('channelsMarkTag') or '无需标注',
        'channels_shoot_date': merged.get('channelsShootDate', '') or '',
        'channels_shoot_region': merged.get('channelsShootRegion') or [],
        'channels_repost_source': merged.get('channelsRepostSource', '') or '',
        'schedule_time': schedule_time_str,
        # 小红书合集(账号级):用 xhs_ 前缀避免与头条 collection_id 冲突
        'xhs_collection_id': merged.get('collectionId', '') or '',
        'xhs_collection_name': merged.get('collectionName', '') or '',
        # 小红书内容来源声明(平台级)
        'xhs_source_type': merged.get('xhsSourceType', '') or '',
        'xhs_shoot_location': merged.get('xhsShootLocation', '') or '',
        'xhs_shoot_date': merged.get('xhsShootDate', '') or '',
        'xhs_repost_source': merged.get('xhsRepostSource', '') or '',
        # B 站合集(账号级)
        'bili_collection_name': merged.get('biliCollectionName', '') or '',
        # 视频号合集(账号级)
        'channels_collection_name': merged.get('channelsCollectionName', '') or '',
        # 视频号位置(平台级,空=不显示位置)
        'channels_location_name': merged.get('channelsLocationName', '') or '',
    }
