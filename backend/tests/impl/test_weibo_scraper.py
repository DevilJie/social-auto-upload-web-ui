"""Unit tests for `scrape_weibo_profile` in backend.impl._utils."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl._utils import scrape_weibo_profile  # noqa: E402


def _make_page(evaluate_result=None, evaluate_raises=False):
    """构造一个最小 mock page，scrape_weibo_profile 只需用到 wait_for_load_state / sleep / evaluate。"""
    page = MagicMock()
    page.wait_for_load_state = AsyncMock()
    if evaluate_raises:
        page.evaluate = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        page.evaluate = AsyncMock(return_value=evaluate_result or {})
    return page


def test_scraper_returns_empty_on_evaluate_exception():
    """evaluate 抛异常时返回空字符串。"""
    page = _make_page(evaluate_raises=True)
    name, avatar = asyncio.run(scrape_weibo_profile(page))
    assert name == ""
    assert avatar == ""


def test_scraper_extracts_sinaimg_avatar():
    """evaluate 返回含 sinaimg.cn 的 img 信息时，avatar 被正确抓出。"""
    page = _make_page(evaluate_result={
        "name": "",
        "avatar": "https://tvax2.sinaimg.cn/crop.0.0.512.512.180/abc123.jpg",
        "debug": [],
    })
    name, avatar = asyncio.run(scrape_weibo_profile(page))
    assert avatar == "https://tvax2.sinaimg.cn/crop.0.0.512.512.180/abc123.jpg"
