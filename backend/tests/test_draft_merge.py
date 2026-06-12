"""merge_config / validate / build_platform_kwargs 单元测试。"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.draft_merge import (
    DECLARATION_PLATFORMS,
    merge_config,
    validate_draft_for_publish,
    validate_image_draft_for_publish,
    build_platform_kwargs,
)


# ===== DECLARATION_PLATFORMS =====

def test_declaration_platforms_keys():
    """8 个平台：xiaohongshu/douyin/kuaishou/bilibili/baijiahao/tencent_video/iqiyi + youtube。"""
    assert set(DECLARATION_PLATFORMS.keys()) == {
        'xiaohongshu', 'douyin', 'kuaishou',
        'bilibili', 'baijiahao', 'tencent_video', 'iqiyi',
        'youtube',
    }


def test_declaration_platforms_youtube_has_two_fields():
    assert DECLARATION_PLATFORMS['youtube'] == ['audience', 'alteredContent']


# ===== merge_config: 3 级 vs 4 级 =====

def test_merge_text_3_level_priority():
    """title/description/tags 是 3 级：accountOv > platformOv > platformDefault，不走 common。"""
    common = {'title': 'C', 'description': 'C', 'tags': ['c']}
    pd = {'title': 'P', 'description': 'P', 'tags': ['p']}
    po = {'title': 'O', 'description': 'O', 'tags': ['o']}
    ao = {'title': 'A', 'description': 'A', 'tags': ['a']}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == 'A'
    assert m['description'] == 'A'
    assert m['tags'] == ['a']


def test_merge_text_3_level_falls_to_platform_default():
    """accountOv/platformOv 都缺时，走 platformDefault。"""
    common = {'title': 'C', 'description': 'C', 'tags': ['c']}
    pd = {'title': 'P', 'description': 'P', 'tags': ['p']}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == 'P'
    assert m['description'] == 'P'
    assert m['tags'] == ['p']


def test_merge_text_does_not_fall_to_common():
    """3 级字段不会回退到 common。"""
    common = {'title': 'C'}
    pd = {}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == ''   # 兜底空字符串


def test_merge_cover_video_4_level_falls_to_common():
    """cover*/video* 4 级：accountOv > platformOv > common，跳过 platformDefault。"""
    common = {'coverLandscape': {'id': 'c'}, 'videoLandscape': {'id': 'vc'}}
    pd = {'coverLandscape': {'id': 'p'}, 'videoLandscape': {'id': 'vp'}}   # 平台默认
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    # platformDefault 不参与 cover*/video* 的兜底
    assert m['coverLandscape'] == {'id': 'c'}
    assert m['videoLandscape'] == {'id': 'vc'}


def test_merge_cover_video_4_level_platform_ov_beats_common():
    common = {'coverLandscape': {'id': 'c'}}
    pd = {}
    po = {'coverLandscape': {'id': 'o'}}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['coverLandscape'] == {'id': 'o'}


def test_merge_boolean_uses_is_none():
    """布尔字段：False ≠ None。accountOv.isOriginal=False 应当胜出。"""
    common = {}
    pd = {'isOriginal': True}
    po = {}
    ao = {'isOriginal': False}
    m = merge_config(common, pd, po, ao)
    assert m['isOriginal'] is False


def test_merge_list_falls_through_to_first_non_empty():
    """列表字段：第一个非空列表胜出。"""
    common = {}
    pd = {'tags': ['p']}
    po = {'tags': []}     # 空列表算 falsy
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['tags'] == ['p']


def test_merge_ai_content_platform_specific():
    """aiContent: 3 级合并（不走 common 兜底）。"""
    common = {'aiContent': 'COMMON'}
    pd = {'aiContent': 'PD'}
    po = {'aiContent': 'OV'}
    ao = {'aiContent': 'ACC'}
    m = merge_config(common, pd, po, ao)
    assert m['aiContent'] == 'ACC'


def test_merge_creation_declaration_no_common_fallback():
    """creationDeclaration: 3 级（不参考 common）。"""
    common = {'creationDeclaration': 'COMMON'}
    pd = {}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['creationDeclaration'] is None or m['creationDeclaration'] == ''


# ===== validate_draft_for_publish =====

class FakeAccount:
    def __init__(self, id, platform, file_path):
        self.id = id
        self.platform = platform
        self.file_path = file_path


def _user_info_lookup_patch(monkeypatch, accounts):
    """monkeypatch services.draft_merge._get_account_by_id 返回 accounts 列表。"""
    def _lookup(account_id):
        for a in accounts:
            if a.id == account_id:
                return a
        return None
    monkeypatch.setattr('services.draft_merge._get_account_by_id', _lookup)


def _video_draft(draft_data, draft_id=1):
    return {'id': draft_id, 'type': 'video', 'draft_data': draft_data}


def test_validate_draft_missing_video():
    """commonConfig 视频文件都没有 → 报错。"""
    draft = _video_draft({
        'commonConfig': {'videoLandscape': None, 'videoPortrait': None,
                         'coverLandscape': {'id': 'c'}, 'coverPortrait': None},
        'platformConfigs': {'bilibili': {'title': 'T', 'videoFormat': 'portrait',
                                          'creationDeclaration': 'cd'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('视频' in e for e in errs)


def test_validate_draft_missing_publish_account_ids():
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {},
        'platformOverrides': {},
        'accountOverrides': {},
        'publishAccountIds': [],
    })
    errs = validate_draft_for_publish(draft)
    assert any('账号' in e or 'publishAccountIds' in e or '未选择' in e for e in errs)


def test_validate_draft_account_not_found(monkeypatch):
    _user_info_lookup_patch(monkeypatch, [])  # 账号表为空
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'bilibili': {}},
        'platformOverrides': {},
        'accountOverrides': {},
        'publishAccountIds': [999],
    })
    errs = validate_draft_for_publish(draft)
    assert any('999' in e and ('不存在' in e or '账号' in e) for e in errs)


def test_validate_draft_bilibili_missing_creation_declaration(monkeypatch):
    """B 站账号层缺 creationDeclaration → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'bilibili', '/cookies/b1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'bilibili': {'title': 'T', 'videoFormat': 'portrait'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},  # 没填 creationDeclaration
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('creationDeclaration' in e for e in errs)


def test_validate_draft_xiaohongshu_missing_ai_content(monkeypatch):
    """小红书账号层缺 aiContent → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'xiaohongshu', '/cookies/x1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},  # 没 aiContent
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('aiContent' in e for e in errs)


def test_validate_draft_youtube_missing_audience_or_altered(monkeypatch):
    """YouTube 缺 audience 或 alteredContent → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'youtube', '/cookies/y1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'youtube': {'title': 'T', 'videoFormat': 'portrait'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},  # 缺 audience/alteredContent
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('audience' in e or 'alteredContent' in e for e in errs)


def test_validate_draft_portrait_without_portrait_cover(monkeypatch):
    """videoFormat=portrait 但缺竖版封面 → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'xiaohongshu', '/cookies/x1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': {'id': 'cl'}, 'coverPortrait': None},  # 只横版
        'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait',
                                            'aiContent': '内容由AI生成'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait',
                                    'aiContent': '内容由AI生成'}},
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('竖版封面' in e or 'portrait' in e.lower() or 'cover' in e.lower() for e in errs)


def test_validate_draft_douyin_activity_tags_cap(monkeypatch):
    """抖音活动+标签 > 5 → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'douyin', '/cookies/d1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': None, 'videoPortrait': {'id': 'v'},
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'douyin': {'title': 'T', 'videoFormat': 'portrait',
                                        'aiContent': '内容由AI生成'}},
        'platformOverrides': {},
        'accountOverrides': {
            '1': {'title': 'T', 'videoFormat': 'portrait', 'aiContent': '内容由AI生成',
                  'activityId': ['a', 'b', 'c'], 'tags': ['t1', 't2', 't3']},  # 3+3=6 > 5
        },
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('5' in e or '活动' in e or '标签' in e for e in errs)


def test_validate_draft_happy_path(monkeypatch):
    """完整合法草稿 → 错误列表为空。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'xiaohongshu', '/cookies/x1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': None, 'videoPortrait': {'id': 'v'},
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait',
                                            'aiContent': '内容由AI生成'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait',
                                    'aiContent': '内容由AI生成'}},
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert errs == []
