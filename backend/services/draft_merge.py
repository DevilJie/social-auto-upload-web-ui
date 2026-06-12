"""草稿合并/校验/payload 适配模块。

所有函数独立、纯 Python，不导入任何前端代码、不依赖任何 publish-page 内部。
字段集与 PublishCenter.vue:592-637 保持同步。
"""

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


def merge_config(common, platform_default, platform_ov, account_ov):
    """4 级合并：返回与 PublishCenter.mergeConfig 等价的 dict。"""
    raise NotImplementedError


def validate_draft_for_publish(draft):
    """dry-run 校验。返回错误消息列表（空 = 合法）。"""
    raise NotImplementedError


def validate_image_draft_for_publish(draft):
    """图文草稿 dry-run 校验。返回错误消息列表。"""
    raise NotImplementedError


def build_platform_kwargs(merged, common, account):
    """merged dict → platform.publish_video kwargs dict。"""
    raise NotImplementedError
