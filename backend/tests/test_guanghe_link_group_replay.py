"""_replay_groups 分组重现 + 中断策略 单测。

同步测试风格,async 用 asyncio.run 包一层。mock _link_ops 模块级函数。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "impl"))

# platform 模块在导入时会初始化 logger,但不会启动浏览器
from impl.taobao_guanghe import platform as platform_mod
# 关键:用 platform_mod._link_ops 而非独立 import,否则会得到另一个模块实例,
# patch 不生效(platform_mod 内引用的是 impl.taobao_guanghe._link_ops)。
_link_ops = platform_mod._link_ops


def _patch_all(fake_scrape_items, click_results=None, load_more_returns=True):
    """统一 patch _link_ops 模块级函数,返回还原函数。"""
    click_results = click_results or {}

    async def fake_scrape(frame, type_):
        return fake_scrape_items[:], False

    async def fake_click_item(frame, type_, tid):
        return click_results.get(tid, "clicked")

    async def fake_load_more(frame):
        return load_more_returns

    async def fake_noop(*a, **kw):
        pass

    saved = {
        "scrape": _link_ops.scrape,
        "_click_item_by_id": _link_ops._click_item_by_id,
        "load_more": _link_ops.load_more,
        "switch_radio": _link_ops.switch_radio,
        "click_add_card": _link_ops.click_add_card,
        "wait_panel_ready": _link_ops.wait_panel_ready,
        "switch_tab": _link_ops.switch_tab,
        "click_filter": _link_ops.click_filter,
        "search": _link_ops.search,
    }
    _link_ops.scrape = fake_scrape
    _link_ops._click_item_by_id = fake_click_item
    _link_ops.load_more = fake_load_more
    _link_ops.switch_radio = fake_noop
    _link_ops.click_add_card = fake_noop
    _link_ops.wait_panel_ready = fake_noop
    _link_ops.switch_tab = fake_noop
    _link_ops.click_filter = fake_noop
    _link_ops.search = fake_noop

    def restore():
        for k, v in saved.items():
            setattr(_link_ops, k, v)

    return restore


def _make_confirm_visible_false():
    """mock frame,confirm 按钮 count=0(不进点击分支)。"""
    frame = MagicMock()
    confirm_btn = MagicMock()
    confirm_btn.count = MagicMock(return_value=0)
    frame.locator.return_value.first = confirm_btn
    return frame


def test_group_replay_basic():
    """两组 trace,所有 itemId 都命中即 clicked,不应 raise。"""
    fake_items = [
        {"id": "111", "disabled": False},
        {"id": "222", "disabled": False},
        {"id": "333", "disabled": False},
    ]
    link_items = [
        {"id": "111", "trace": {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}},
        {"id": "222", "trace": {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}},
        {"id": "333", "trace": {"tab": "preferred", "keyword": "手机壳", "rule": "", "category": ""}},
    ]
    restore = _patch_all(fake_items)
    frame = _make_confirm_visible_false()
    try:
        asyncio.run(platform_mod._replay_groups(frame, "product", link_items, max_load_more=5))
    finally:
        restore()


def test_raise_when_disabled():
    """目标商品 disabled → raise RuntimeError,消息含「不可选」。"""
    fake_items = [{"id": "111", "disabled": True}]
    link_items = [{"id": "111", "trace": {"tab": "preferred", "keyword": "x"}}]
    restore = _patch_all(fake_items)
    frame = _make_confirm_visible_false()
    try:
        try:
            asyncio.run(platform_mod._replay_groups(frame, "product", link_items, max_load_more=5))
            assert False, "应抛 RuntimeError"
        except RuntimeError as e:
            assert "不可选" in str(e)
    finally:
        restore()


def test_raise_when_not_found_after_max_load_more():
    """超过 max_load_more 仍未找到 → raise,消息含「未找到」。"""
    fake_items = []
    link_items = [{"id": "999", "trace": {"tab": "preferred", "keyword": "x"}}]
    restore = _patch_all(fake_items, load_more_returns=True)
    frame = _make_confirm_visible_false()
    try:
        try:
            asyncio.run(platform_mod._replay_groups(frame, "product", link_items, max_load_more=5))
            assert False, "应抛 RuntimeError"
        except RuntimeError as e:
            assert "未找到" in str(e)
            assert "999" in str(e)
    finally:
        restore()
