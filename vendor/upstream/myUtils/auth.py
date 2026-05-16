import asyncio
import configparser
import os

from patchright.async_api import async_playwright
from xhs import XhsClient

from conf import BASE_DIR, LOCAL_CHROME_HEADLESS
from myUtils.browser import create_browser, create_context
from utils.log import tencent_logger, kuaishou_logger, douyin_logger
from pathlib import Path
from uploader.xhs_uploader.main import sign_local




async def cookie_auth_douyin(account_file):
    async with async_playwright() as playwright:
        browser = await create_browser(playwright)
        context = await create_context(browser, storage_state=account_file)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.douyin.com/creator-micro/content/upload")
        try:
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload", timeout=5000)
            # 2024.06.17 抖音创作者中心改版
            # 判断
            # 等待"扫码登录"元素出现，超时 5 秒（如果 5 秒没出现，说明 cookie 有效）
            try:
                await page.get_by_text("扫码登录").wait_for(timeout=5000)
                douyin_logger.error("[+] cookie 失效，需要扫码登录")
                return False
            except:
                douyin_logger.success("[+]  cookie 有效")
                return True
        except:
            douyin_logger.error("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False


async def cookie_auth_tencent(account_file):
    async with async_playwright() as playwright:
        browser = await create_browser(playwright)
        context = await create_context(browser, storage_state=account_file)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        try:
            await page.wait_for_selector('div.title-name:has-text("微信小店")', timeout=5000)  # 等待5秒
            tencent_logger.error("[+] 等待5秒 cookie 失效")
            return False
        except:
            tencent_logger.success("[+] cookie 有效")
            return True


async def cookie_auth_ks(account_file):
    async with async_playwright() as playwright:
        browser = await create_browser(playwright)
        context = await create_context(browser, storage_state=account_file)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://cp.kuaishou.com/article/publish/video")
        try:
            await page.wait_for_selector("div.names div.container div.name:text('机构服务')", timeout=5000)  # 等待5秒

            kuaishou_logger.info("[+] 等待5秒 cookie 失效")
            return False
        except:
            kuaishou_logger.success("[+] cookie 有效")
            return True


async def cookie_auth_xhs(account_file):
    async with async_playwright() as playwright:
        browser = await create_browser(playwright)
        context = await create_context(browser, storage_state=account_file)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.xiaohongshu.com/creator-micro/content/upload")
        try:
            await page.wait_for_url("https://creator.xiaohongshu.com/creator-micro/content/upload", timeout=5000)
        except:
            print("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
        # 2024.06.17 抖音创作者中心改版
        if await page.get_by_text('手机号登录').count() or await page.get_by_text('扫码登录').count():
            print("[+] 等待5秒 cookie 失效")
            return False
        else:
            print("[+] cookie 有效")
            return True


async def check_cookie(type, file_path):
    match type:
        # 小红书
        case 1:
            return await cookie_auth_xhs(Path(BASE_DIR / "cookiesFile" / file_path))
        # 视频号
        case 2:
            return await cookie_auth_tencent(Path(BASE_DIR / "cookiesFile" / file_path))
        # 抖音
        case 3:
            return await cookie_auth_douyin(Path(BASE_DIR / "cookiesFile" / file_path))
        # 快手
        case 4:
            return await cookie_auth_ks(Path(BASE_DIR / "cookiesFile" / file_path))
        # B站
        case 5:
            return await cookie_auth_bilibili(Path(BASE_DIR / "cookiesFile" / file_path))
        # 百家号
        case 6:
            from uploader.baijiahao_uploader.main import cookie_auth as baijiahao_cookie_auth
            return await baijiahao_cookie_auth(Path(BASE_DIR / "cookiesFile" / file_path))
        # YouTube
        case 8:
            from uploader.youtube_uploader.main import cookie_auth as youtube_cookie_auth
            return await youtube_cookie_auth(str(Path(BASE_DIR / "cookiesFile" / file_path)))
        # TikTok
        case 7:
            from uploader.tk_uploader.main_chrome import cookie_auth as tiktok_cookie_auth
            return await tiktok_cookie_auth(Path(BASE_DIR / "cookiesFile" / file_path))
        case _:
            return False


async def cookie_auth_bilibili(account_file):
    async with async_playwright() as playwright:
        browser = await create_browser(playwright)
        context = await create_context(browser, storage_state=account_file)
        page = await context.new_page()
        await page.goto("https://member.bilibili.com/platform/upload-manager/article")
        try:
            await page.wait_for_url("**/platform/**", timeout=5000)
            # 如果被重定向到登录页，说明cookie失效
            if "passport.bilibili.com" in page.url:
                print("[+] B站 cookie 失效，需要重新登录")
                return False
            print("[+] B站 cookie 有效")
            return True
        except:
            print("[+] B站等待5秒 cookie 检查超时")
            await context.close()
            await browser.close()
            return False
        finally:
            try:
                await context.close()
                await browser.close()
            except:
                pass
