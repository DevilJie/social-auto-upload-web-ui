# -*- coding: utf-8 -*-
"""验证: 浏览器关闭后 _wait_article_publish_done 立即判失败(不等 900s)。"""
import asyncio
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl.registry import get_platform  # noqa: E402


async def main() -> None:
    platform = get_platform(17)
    browser = await platform.create_browser(headless=True)
    try:
        ctx = await platform.create_context(browser)
        page = await ctx.new_page()
        # 模拟用户扫码时直接关浏览器
        await page.close()
        await ctx.close()
        t0 = time.monotonic()
        try:
            await platform._wait_article_publish_done(page, timeout_s=900)
            print("FAIL: 未抛异常(误报等待)")
        except RuntimeError as e:
            elapsed = time.monotonic() - t0
            print(f"✓ 已判失败,耗时 {elapsed:.1f}s")
            print(f"  原因: {e}")
            print("PASS" if elapsed < 5 else "FAIL: 耗时过长")
    finally:
        try:
            await platform.close_browser(browser, is_close_by_code=True)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
