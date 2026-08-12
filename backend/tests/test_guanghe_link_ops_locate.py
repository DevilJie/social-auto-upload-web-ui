"""locate_and_check 单测 — mock frame 验证匹配/勾选/disabled 逻辑。

同步测试风格(与现有 backend/tests/ 一致),async 函数用 asyncio.run 包一层。
不依赖 pytest-asyncio。
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "impl"))

from taobao_guanghe import _link_ops  # noqa: E402


def _patch(func_name, fake_coro):
    """把 _link_ops.<func_name> 临时替换为 fake_coro(async 函数)。"""
    original = getattr(_link_ops, func_name)
    setattr(_link_ops, func_name, fake_coro)
    return original


def test_all_targets_clicked():
    """三个目标都命中且 clicked。"""
    fake_items = [
        {"id": "111", "title": "A1", "disabled": False},
        {"id": "222", "title": "A2", "disabled": False},
        {"id": "333", "title": "A3", "disabled": False},
    ]

    async def fake_scrape(frame, type_):
        return (fake_items[:], False)
    orig_scrape = _patch("scrape", fake_scrape)

    async def fake_click(frame, type_, tid):
        return "clicked"
    orig_click = _patch("_click_item_by_id", fake_click)

    try:
        result = asyncio.run(_link_ops.locate_and_check(MagicMock(), "product", {"111", "222", "333"}))
    finally:
        _link_ops.scrape = orig_scrape
        _link_ops._click_item_by_id = orig_click

    assert set(result["checked"]) == {"111", "222", "333"}
    assert result["already"] == []
    assert result["disabled"] == []
    assert result["missing"] == []


def test_some_missing():
    """列表里只有 111/222,999 找不到。"""
    fake_items = [{"id": "111", "disabled": False}, {"id": "222", "disabled": False}]

    async def fake_scrape(frame, type_):
        return (fake_items[:], False)
    orig_scrape = _patch("scrape", fake_scrape)

    async def fake_click(frame, type_, tid):
        return "clicked" if tid in {"111", "222"} else "not_found"
    orig_click = _patch("_click_item_by_id", fake_click)

    try:
        result = asyncio.run(_link_ops.locate_and_check(MagicMock(), "product", {"111", "222", "999"}))
    finally:
        _link_ops.scrape = orig_scrape
        _link_ops._click_item_by_id = orig_click

    assert set(result["checked"]) == {"111", "222"}
    assert result["missing"] == ["999"]


def test_disabled_item_reported():
    """目标在列表里但 disabled=True → 进 disabled 桶,不调 click。"""
    fake_items = [{"id": "111", "disabled": True}]

    async def fake_scrape(frame, type_):
        return (fake_items[:], False)
    orig_scrape = _patch("scrape", fake_scrape)

    async def fake_click(frame, type_, tid):
        raise AssertionError("disabled item 不应该走到 click")
    orig_click = _patch("_click_item_by_id", fake_click)

    try:
        result = asyncio.run(_link_ops.locate_and_check(MagicMock(), "product", {"111"}))
    finally:
        _link_ops.scrape = orig_scrape
        _link_ops._click_item_by_id = orig_click

    assert result["disabled"] == ["111"]
    assert result["checked"] == []


def test_already_checked():
    """已勾选的算 already,不重复 click。"""
    fake_items = [{"id": "111", "disabled": False}]

    async def fake_scrape(frame, type_):
        return (fake_items[:], False)
    orig_scrape = _patch("scrape", fake_scrape)

    async def fake_click(frame, type_, tid):
        return "already"
    orig_click = _patch("_click_item_by_id", fake_click)

    try:
        result = asyncio.run(_link_ops.locate_and_check(MagicMock(), "product", {"111"}))
    finally:
        _link_ops.scrape = orig_scrape
        _link_ops._click_item_by_id = orig_click

    assert result["already"] == ["111"]
    assert result["checked"] == []
