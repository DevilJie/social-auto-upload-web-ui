"""小红书发布前置校验单元测试:话题总数 ≤ 10(描述 #xxx + 标签)。

只测纯函数 ``_count_hashtags``,并间接覆盖 ``publish_video`` 的前置拦截逻辑。
不触发浏览器/CloakBrowser 流程。
"""
import sys
from pathlib import Path

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl.xiaohongshu.platform import _count_hashtags, _XHS_MAX_TOPICS  # noqa: E402


# ----- _count_hashtags: 描述文本里独立 #xxx 计数 -----

def test_count_hashtags_empty():
    assert _count_hashtags("") == 0
    assert _count_hashtags(None) == 0


def test_count_hashtags_basic():
    assert _count_hashtags("你好 #话题1 #话题2") == 2


def test_count_hashtags_leading_hash():
    """行首的 # 也算话题"""
    assert _count_hashtags("#话题1 描述 #话题2") == 2


def test_count_hashtags_inline_not_counted():
    """a#b 这种粘连的不算独立话题"""
    assert _count_hashtags("a#b c#d") == 0


def test_count_hashtags_url_anchor_not_counted():
    """http://x#anchor 这种 # 前面不是空白,不算"""
    assert _count_hashtags("http://example.com#section 看这个") == 0


def test_count_hashtags_double_hash_not_counted():
    """## 开头(# 后紧跟 #)不算"""
    assert _count_hashtags("## 标题 #正常") == 1


def test_count_hashtags_isolated_hash_not_counted():
    """孤立 # 不算"""
    assert _count_hashtags("单独 # 一个") == 0


def test_count_hashtags_multiline():
    """多行:每行行首的 # 都算"""
    text = "#第一行\n#第二行\n普通文字 #第三行"
    assert _count_hashtags(text) == 3


def test_max_topics_constant():
    """上限常量为 10"""
    assert _XHS_MAX_TOPICS == 10


# ----- 话题总数 ≤ 10 边界(模拟 publish_video 前置校验的判定) -----

def _total(desc, tags):
    """复刻 publish_video 里的合并计数逻辑"""
    return _count_hashtags(desc) + len(tags or [])


def test_tags_only_10_ok():
    """纯标签 10 个 = 10,刚好通过"""
    assert _total("", ["t%d" % i for i in range(10)]) == 10


def test_tags_only_11_fail():
    """纯标签 11 个 = 11,超出"""
    assert _total("", ["t%d" % i for i in range(11)]) == 11
    assert _total("", ["t%d" % i for i in range(11)]) > _XHS_MAX_TOPICS


def test_desc2_tags8_ok():
    """描述 2 + 标签 8 = 10,刚好通过"""
    assert _total("#a #b", ["t%d" % i for i in range(8)]) == 10


def test_desc2_tags9_fail():
    """描述 2 + 标签 9 = 11,超出"""
    assert _total("#a #b", ["t%d" % i for i in range(9)]) == 11
    assert _total("#a #b", ["t%d" % i for i in range(9)]) > _XHS_MAX_TOPICS


def test_desc10_tags0_ok():
    """描述里 10 个 #xxx,无标签 = 10,刚好通过"""
    assert _total("#a #b #c #d #e #f #g #h #i #j", []) == 10


def test_desc11_fail():
    """描述里 11 个 #xxx,超出"""
    text = "#a #b #c #d #e #f #g #h #i #j #k"
    assert _total(text, []) == 11
    assert _total(text, []) > _XHS_MAX_TOPICS


def test_inline_hash_in_desc_not_counted():
    """描述里 a#b 不计入,只有独立的 #xxx 算"""
    # a#b#c#d 全部粘连 = 0 个独立话题
    assert _total("a#b#c#d 文案", ["t%d" % i for i in range(10)]) == 10
