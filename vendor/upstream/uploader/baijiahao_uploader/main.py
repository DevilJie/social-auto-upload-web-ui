# -*- coding: utf-8 -*-
import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path

from patchright.async_api import Playwright, async_playwright, Page
import os
import time
import asyncio

from conf import LOCAL_CHROME_HEADLESS
from myUtils.browser import create_browser, create_context
from utils.log import baijiahao_logger
from utils.network import async_retry


async def baijiahao_cookie_gen_wrapper(id, status_queue):
    """百家号登录包装函数 — 适配 sau_backend.run_async_function 接口"""
    print(f"[BAIJIAHAO DEBUG] wrapper called with id={id}, status_queue={status_queue}")
    baijiahao_logger.info(f"百家号登录开始... id={id}")
    from conf import BASE_DIR
    import uuid

    uuid_v1 = str(uuid.uuid1())
    cookies_dir = Path(BASE_DIR / "cookiesFile")
    cookies_dir.mkdir(exist_ok=True)
    account_file = str(cookies_dir / f"{uuid_v1}.json")
    print(f"[BAIJIAHAO DEBUG] account_file={account_file}")

    print(f"[BAIJIAHAO DEBUG] 调用 baijiahao_cookie_gen...")
    user_name, avatar_url = await baijiahao_cookie_gen(account_file)
    if not user_name:
        user_name = "百家号用户"
    print(f"[BAIJIAHAO DEBUG] baijiahao_cookie_gen 返回 name={user_name}")

    # 登录成功后保存到数据库
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO user_info (type, filePath, userName, status, avatar)
                       VALUES (?, ?, ?, ?, ?)
                       ''', (6, f"{uuid_v1}.json", user_name, 1, avatar_url))
        conn.commit()
    print(f"[BAIJIAHAO DEBUG] 数据库插入完成")

    # 发送成功消息
    status_queue.put(json.dumps({"status": "200", "name": user_name, "avatar": avatar_url}))


async def baijiahao_cookie_gen(account_file):
    """百家号登录 - 检测登录完成并自动保存 cookie，返回 (name, avatar)"""
    import asyncio
    print(f"[BAIJIAHAO DEBUG] baijiahao_cookie_gen ENTRY, account_file={account_file}")

    async with async_playwright() as playwright:
        print(f"[BAIJIAHAO DEBUG] launching browser (patchright)")
        browser = await create_browser(playwright, headless=False, login_mode=True)
        context = await create_context(browser)
        page = await context.new_page()
        print(f"[BAIJIAHAO DEBUG] navigating to login page...")
        await page.goto("https://baijiahao.baidu.com/builder/theme/bjh/login", timeout=45000)
        print(f"[BAIJIAHAO DEBUG] page loaded, url={page.url}")
        baijiahao_logger.info("百家号登录页面已打开，请完成扫码登录...")

        # 等待登录完成 - 百家号登录后通常会跳转到 home 页面
        try:
            await page.wait_for_url("**/builder/rc/home**", timeout=120000)
            baijiahao_logger.info("检测到登录成功，正在保存 cookie...")
        except Exception:
            baijiahao_logger.warning("未检测到登录完成，将在 120 秒后保存当前状态")
            await asyncio.sleep(120)

        # 抓取用户资料
        name, avatar = await _scrape_baijiahao_profile(page)

        await context.storage_state(path=account_file)
        baijiahao_logger.success("百家号 cookie 已保存")
        await page.close()
        await context.close()
        await browser.close()
        return name, avatar


async def _scrape_baijiahao_profile(page):
    """从百家号账号设置页抓取用户昵称和头像"""
    name = ""
    avatar = ""
    try:
        # 导航到账号设置页，这里头像和昵称直接渲染在页面上
        await page.goto("https://baijiahao.baidu.com/builder/rc/settings/accountSet", timeout=15000)
        await page.wait_for_load_state('domcontentloaded', timeout=10000)
        await asyncio.sleep(2)

        # 头像: img 含 userImg 的 class
        avatar_el = page.locator('img[class*="userImg"]').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()

        # 昵称: div 含 userName 的 class
        name_el = page.locator('div[class*="userName"]').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()

        print(f"[BAIJIAHAO] 抓取结果 - name={name!r} avatar={avatar[:50] if avatar else 'None'}", flush=True)
    except Exception as e:
        print(f"[BAIJIAHAO] 抓取用户资料失败: {e}", flush=True)
    return name, avatar


async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await create_browser(playwright)
        context = await create_context(browser, storage_state=account_file)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://baijiahao.baidu.com/builder/rc/home")
        await page.wait_for_timeout(timeout=5000)

        if await page.get_by_text('注册/登录百家号').count():
            baijiahao_logger.error("等待5秒 cookie 失效")
            return False
        else:
            baijiahao_logger.success("[+] cookie 有效")
            return True


async def baijiahao_setup(account_file, handle=False):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            return False
        baijiahao_logger.error("cookie文件不存在或已失效，即将自动打开浏览器，请扫码登录，登陆后会自动生成cookie文件")
        await baijiahao_cookie_gen(account_file)
    return True

class BaiJiaHaoVideo(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file,
                 proxy_setting=None, desc=None,
                 thumbnail_landscape_path=None, thumbnail_portrait_path=None,
                 creation_declaration='', supplementary_declaration='',
                 ai_content=False, headless=None):
        self.title = title  # 视频标题
        self.file_path = file_path
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.headless = headless if headless is not None else LOCAL_CHROME_HEADLESS
        self.proxy_setting = proxy_setting
        self.desc = desc
        self.thumbnail_landscape_path = thumbnail_landscape_path
        self.thumbnail_portrait_path = thumbnail_portrait_path
        self.creation_declaration = creation_declaration or ''
        self.supplementary_declaration = supplementary_declaration or ''
        self.ai_content = ai_content

    async def set_schedule_time(self, page, publish_date):
        """
        todo 时间选择，日后在处理 百家号的时间选择不准确，目前是随机
        """
        publish_date_day = f"{publish_date.month}月{publish_date.day}日" if publish_date.day >9  else f"{publish_date.month}月0{publish_date.day}日"
        publish_date_hour = f"{publish_date.hour}点"
        publish_date_min = f"{publish_date.minute}分"
        await page.wait_for_selector('div.select-wrap', timeout=5000)
        for _ in range(3):
            try:
                await page.locator('div.select-wrap').nth(0).click()
                await page.wait_for_selector('div.rc-virtual-list  div.cheetah-select-item', timeout=5000)
                break
            except:
                await page.locator('div.select-wrap').nth(0).click()
        # page.locator(f'div.rc-virtual-list-holder-inner >> text={publish_date_day}').click()
        await page.wait_for_timeout(2000)
        await page.locator(f'div.rc-virtual-list  div.cheetah-select-item >> text={publish_date_day}').click()
        await page.wait_for_timeout(2000)

        # 改为随机点击一个 hour
        for _ in range(3):
            try:
                await page.locator('div.select-wrap').nth(1).click()
                await page.wait_for_selector('div.rc-virtual-list div.rc-virtual-list-holder-inner:visible', timeout=5000)
                break
            except:
                await page.locator('div.select-wrap').nth(1).click()
        await page.wait_for_timeout(2000)
        current_choice_hour = await page.locator('div.rc-virtual-list:visible div.cheetah-select-item-option').count()
        await page.wait_for_timeout(2000)
        await page.locator('div.rc-virtual-list:visible div.cheetah-select-item-option').nth(
            random.randint(1, current_choice_hour-3)).click()
        # 2024.08.05 current_choice_hour的获取可能有问题，页面有7，这里获取了10，暂时硬编码至6

        await page.wait_for_timeout(2000)
        await page.locator("button >> text=定时发布").click()


    async def handle_upload_error(self, page):
        # 日后实现，目前没遇到
        return
        print("视频出错了，重新上传中")

    async def upload(self, playwright: Playwright) -> None:
        # 使用 Chromium 浏览器启动一个浏览器实例
        browser = await create_browser(playwright, headless=self.headless, proxy=self.proxy_setting)
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await create_context(
            browser,
            storage_state=f"{self.account_file}",
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.4324.150 Safari/537.36',
        )
        await context.grant_permissions(['geolocation'])

        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://baijiahao.baidu.com/builder/rc/edit?type=videoV2", timeout=60000)
        baijiahao_logger.info(f"正在上传-------{self.title}.mp4")
        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        baijiahao_logger.info('正在打开主页...')
        await page.wait_for_url("https://baijiahao.baidu.com/builder/rc/edit?type=videoV2", timeout=60000)

        # 上传视频文件 — 选择器适配百家号新 DOM（class 名为动态 hash）
        video_input = page.locator("input[type='file'][accept*='.mp4']")
        if await video_input.count() == 0:
            video_input = page.locator("input[type='file']").first
        await video_input.set_input_files(self.file_path)

        # 等待页面跳转到指定的 URL
        while True:
            # 判断是是否进入视频发布页面，没进入，则自动等待到超时
            try:
                await page.wait_for_selector("div#formMain:visible")
                break
            except:
                baijiahao_logger.info("正在等待进入视频发布页面...")
                await asyncio.sleep(0.1)

        # 填充标题和话题
        # 这里为了避免页面变化，故使用相对位置定位：作品标题父级右侧第一个元素的input子元素
        await asyncio.sleep(1)
        baijiahao_logger.info("正在填充标题和话题...")
        await self.add_title_tags(page)

        upload_status = await self.uploading_video(page)
        if not upload_status:
            baijiahao_logger.error(f"发现上传出错了... 文件:{self.file_path}")
            raise

        # 判断封面区域是否就绪（等 coverWrap 内至少 2 个 cover-container 出现）
        while True:
            container_count = await page.locator("div[class*='coverWrap'] > div[class*='cover-container']").count()
            if container_count >= 2:
                baijiahao_logger.info(f"封面区域已就绪（找到 {container_count} 个 cover-container）")
                break
            else:
                baijiahao_logger.info(f"等待封面区域就绪（当前 {container_count} 个 cover-container）...")
                await asyncio.sleep(3)

        # 设置自定义封面
        await self._set_cover(page)

        # 设置创作声明
        await self._set_creation_declaration(page)

        await self.publish_video(page, self.publish_date)
        await page.wait_for_timeout(2000)

        # 人机校验处理：如果出现百度安全验证，等待用户手动完成
        captcha_dialog = page.locator('div.passMod_dialog-container:visible')
        if await captcha_dialog.count():
            baijiahao_logger.warning("出现人机校验，请在浏览器中手动完成验证...")
            try:
                await captcha_dialog.wait_for(state="hidden", timeout=120000)
                baijiahao_logger.info("人机校验已完成")
                await asyncio.sleep(3)
            except Exception:
                baijiahao_logger.error("人机校验等待超时（120秒），退出")
                raise Exception("人机校验等待超时")

        # 等待发布成功跳转
        try:
            await page.wait_for_url("https://baijiahao.baidu.com/builder/rc/clue**", timeout=30000)
            baijiahao_logger.success("视频发布成功")
        except Exception:
            current_url = page.url
            baijiahao_logger.error(f"发布后未跳转到成功页面, 当前URL: {current_url}")
            raise Exception(f"视频发布后未成功跳转, 当前URL: {current_url}")

        await context.storage_state(path=self.account_file)  # 保存cookie
        baijiahao_logger.info('cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()


    @async_retry(timeout=300)  # 例如，最多重试3次，超时时间为180秒
    async def uploading_video(self, page):
        while True:
            upload_failed = await page.locator('div .cover-overlay:has-text("上传失败")').count()
            if upload_failed:
                baijiahao_logger.error("发现上传出错了...")
                # await self.handle_upload_error(page)  # 假设这是处理上传错误的函数
                return False

            uploading = await page.locator('div .cover-overlay:has-text("上传中")').count()
            if uploading:
                baijiahao_logger.info("正在上传视频中...")
                await asyncio.sleep(2)  # 等待2秒再次检查
                continue

            # 检查上传是否成功
            if not uploading and not upload_failed:
                baijiahao_logger.success("视频上传完毕")
                return True

    async def set_schedule_publish(self, page, publish_date):
        while True:
            schedule_element = page.locator("div.op-btn-outter-content >> text=定时发布").locator("..").locator(
                'button')
            try:
                await schedule_element.click()
                await page.wait_for_selector('div.select-wrap:visible', timeout=3000)
                await page.wait_for_timeout(timeout=2000)
                baijiahao_logger.info("开始点击发布定时...")
                await self.set_schedule_time(page, publish_date)
                break
            except Exception as e:
                baijiahao_logger.error(f"定时发布失败: {e}")
                raise  # 重新抛出异常，让重试装饰器捕获

    @async_retry(timeout=300)  # 例如，最多重试3次，超时时间为180秒
    async def publish_video(self, page: Page, publish_date):
        if publish_date != 0:
            # 定时发布
            await self.set_schedule_publish(page, publish_date)
        else:
            # 立即发布
            await self.direct_publish(page)

    async def direct_publish(self, page):
        try:
            # 用 data-testid 精确定位发布按钮，避免 strict mode
            publish_button = page.locator("button[data-testid='publish-btn']")
            if await publish_button.count():
                await publish_button.click()
            else:
                # 回退：文字匹配
                publish_button = page.locator("button.cheetah-btn-primary:has-text('发布')")
                if await publish_button.count():
                    await publish_button.first.click()
        except Exception as e:
            baijiahao_logger.error(f"直接发布视频失败: {e}")
            raise  # 重新抛出异常，让重试装饰器捕获

    async def add_title_tags(self, page):
        """填充作品描述 — 百家号发布页只有"作品描述"字段（Lexical 编辑器），没有独立标题"""
        # 百家号用描述字段，优先 desc，回退 title
        desc_text = (self.desc or self.title or "").strip()
        if not desc_text:
            baijiahao_logger.warning("无描述内容，跳过填充")
            return
        desc_text = desc_text[:50]

        # Lexical contenteditable 编辑器（作品描述字段）
        lexical_editor = page.locator('[data-lexical-editor="true"]')
        if await lexical_editor.count():
            editor = lexical_editor.first
            await editor.click()
            await asyncio.sleep(0.3)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await page.keyboard.type(desc_text, delay=50)
            baijiahao_logger.info(f"已填充作品描述: {desc_text}")
            return

        # 旧版回退：placeholder 方式
        title_container = page.get_by_placeholder('添加标题获得更多推荐')
        if await title_container.count():
            await title_container.fill(desc_text)
            baijiahao_logger.info(f"已通过 placeholder 填充描述: {desc_text}")
            return

        baijiahao_logger.warning("未找到描述输入框，跳过填充")

    async def _set_cover(self, page):
        """上传自定义封面（横屏 + 竖屏）
        用 cover-container 定位，第1个=横版，第2个=竖版。
        流程：点击封面区域 → 弹窗打开 → 上传图片 → 点确定
        """
        import os as _os

        containers = page.locator("div[class*='coverWrap'] > div[class*='cover-container']")
        total = await containers.count()
        baijiahao_logger.info(f"[封面] 找到 {total} 个 cover-container，开始逐个设置")

        for idx, (cover_type, cover_path) in enumerate([
            ("横屏封面", self.thumbnail_landscape_path),
            ("竖屏封面", self.thumbnail_portrait_path),
        ]):
            baijiahao_logger.info(f"[封面] === 处理第 {idx+1} 个: {cover_type} ===")

            if not cover_path or not _os.path.exists(cover_path):
                baijiahao_logger.info(f"[封面] {cover_type} 无图片文件，跳过")
                continue
            if idx >= total:
                baijiahao_logger.warning(f"[封面] cover-container 不足（{total}），跳过{cover_type}")
                continue

            baijiahao_logger.info(f"[封面] {cover_type} 图片: {_os.path.basename(cover_path)}")
            try:
                container = containers.nth(idx)

                # 1. 点击封面区域（"选择封面" 或 "编辑封面"），打开弹窗
                baijiahao_logger.info(f"[封面] 点击第 {idx+1} 个 cover-container ...")
                await container.click()
                baijiahao_logger.info(f"[封面] 已点击{cover_type}，等待弹窗打开...")

                # 等待弹窗出现
                await page.wait_for_selector("div.cheetah-modal:visible", timeout=10000)
                baijiahao_logger.info(f"[封面] {cover_type}弹窗已出现")
                await asyncio.sleep(1)

                # 2. 在弹窗中找到 file input，上传图片
                file_input_count = await page.locator("div.cheetah-modal:visible input[type='file']").count()
                baijiahao_logger.info(f"[封面] 弹窗中找到 {file_input_count} 个 file input")

                dialog_input = page.locator("div.cheetah-modal:visible input[type='file']").first
                await dialog_input.set_input_files(cover_path)
                baijiahao_logger.info(f"[封面] 已上传{cover_type}文件")
                await asyncio.sleep(2)

                # 3. 点击弹窗中的确定按钮
                confirm_btn = page.locator("div.cheetah-modal:visible button.cheetah-btn-primary:has-text('确定')")
                confirm_count = await confirm_btn.count()
                baijiahao_logger.info(f"[封面] 弹窗中找到 {confirm_count} 个确定按钮")

                if confirm_count:
                    await confirm_btn.first.click()
                    baijiahao_logger.info(f"[封面] 已点击确定提交{cover_type}")
                else:
                    baijiahao_logger.warning(f"[封面] {cover_type}弹窗未找到确定按钮")

                await asyncio.sleep(2)
                baijiahao_logger.success(f"[封面] {cover_type}设置完成")

            except Exception as e:
                baijiahao_logger.error(f"[封面] 设置{cover_type}失败: {e}")

    async def _set_creation_declaration(self, page):
        """设置创作声明（必选声明 + 补充声明）"""
        if not self.creation_declaration and not self.supplementary_declaration:
            return

        baijiahao_logger.info(f"设置创作声明 - 必选: {self.creation_declaration}, 补充: {self.supplementary_declaration}")
        try:
            # 点击创作声明输入框
            declaration_input = page.locator("input[placeholder='请选择创作声明']")
            if not await declaration_input.count():
                baijiahao_logger.info("未找到创作声明输入框，跳过")
                return

            await declaration_input.click()
            baijiahao_logger.info("已点击创作声明输入框")
            await asyncio.sleep(1)

            # 用 role=dialog 精确定位创作声明弹窗
            modal = page.get_by_role("dialog", name="创作声明")
            await modal.wait_for(state="visible", timeout=5000)
            baijiahao_logger.info("创作声明弹窗已出现")

            # 选择必选声明 — 遍历 flex 行找匹配文字
            if self.creation_declaration:
                target_text = self.creation_declaration.strip()
                count = await modal.locator("div.flex.items-center.cursor-pointer").count()
                clicked = False
                for i in range(count):
                    row = modal.locator("div.flex.items-center.cursor-pointer").nth(i)
                    row_text = (await row.inner_text() or "").strip()
                    if row_text == target_text:
                        await row.locator("input.cheetah-radio-input").click(force=True)
                        baijiahao_logger.success(f"已选择必选声明: {row_text}")
                        clicked = True
                        break
                if not clicked:
                    baijiahao_logger.warning(f"未找到匹配的必选声明: {target_text}")
                await asyncio.sleep(0.5)

            # 选择补充声明
            if self.supplementary_declaration:
                target_text = self.supplementary_declaration.strip()
                count = await modal.locator("div.flex.items-center.cursor-pointer").count()
                clicked = False
                for i in range(count):
                    row = modal.locator("div.flex.items-center.cursor-pointer").nth(i)
                    row_text = (await row.inner_text() or "").strip()
                    if row_text == target_text:
                        await row.locator("input.cheetah-radio-input").click(force=True)
                        baijiahao_logger.success(f"已选择补充声明: {row_text}")
                        clicked = True
                        break
                if not clicked:
                    baijiahao_logger.warning(f"未找到匹配的补充声明: {target_text}")
                await asyncio.sleep(0.5)

            # 点击弹窗中的确定按钮
            confirm_btn = modal.locator("button.cheetah-btn-primary:has-text('确定')")
            if await confirm_btn.count():
                await confirm_btn.click()
                baijiahao_logger.info("已点击创作声明确定按钮")
            else:
                baijiahao_logger.warning("未找到创作声明确定按钮")

            await asyncio.sleep(1)
            baijiahao_logger.success("创作声明设置完成")

        except Exception as e:
            baijiahao_logger.warning(f"设置创作声明失败（不影响上传）: {e}")

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)



    # 使用 AI成片 功能
    async def ai2video(self, playwright: Playwright) -> None:
        # 使用 Chromium 浏览器启动一个浏览器实例
        browser = await create_browser(playwright, headless=self.headless, proxy=self.proxy_setting)
        # 创建一个浏览器上下文，使用指定的 cookie 文件
        context = await create_context(
            browser,
            storage_state=f"{self.account_file}",
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.4324.150 Safari/537.36',
            viewport={"width": 1600, "height": 900},
        )
        await context.grant_permissions(['geolocation'])

        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://aigc.baidu.com/make", timeout=60000)
        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        baijiahao_logger.info('正在打开主页...')
        await page.wait_for_url("https://aigc.baidu.com/make", timeout=60000)

        # 点击"全网"标签
        await page.locator('div.rounded-lg.border:has-text("全网")').click()
        await asyncio.sleep(1)  # 这里延迟是为了方便眼睛直观的观看

        # 点击 "上传视频" 按钮
        # await page.locator("div[class^='video-main-container'] input").set_input_files(self.file_path)

        # region 操作处

        # 生成日期时间键名（格式：ai2video_YYYYMMDDHHMM）
        now = datetime.now()
        datetime_str = now.strftime("%Y%m%d%H%M")
        processed_key = "ai2video_processed_titles"
        batch_key = f"ai2video_{datetime_str}"

        # 初始化LocalStorage
        await page.evaluate(f"""
                   if (!localStorage.getItem("{processed_key}")) {{
                       localStorage.setItem("{processed_key}", JSON.stringify([]));                   
                   }}
                   if (!localStorage.getItem("{batch_key}")) {{
                       localStorage.setItem("{batch_key}", JSON.stringify([]));                   
                   }}
               """)

        # 定位新闻列表容器（转义特殊CSS字符）
        container_selector = '.overflow-auto.flex-grow.h-0.saas-scrollbar.mt\-\[-4px\].pl\-\[24px\].pr\-\[10px\].pb\-\[18px\]'
        news_items = await page.locator(container_selector).locator('div.py\-\[6px\].group.cursor-pointer').all()

        for item in news_items:
            try:
                # 获取新闻标题
                title_elem = item.locator('div.flex.text-gray-darker.items-center.relative.pr\-\[56px\] > span')
                title = await title_elem.text_content()
                if not title:
                    continue

                # 检查是否已处理过
                is_processed = await page.evaluate(
                    f"""title => {{
                               const processedList = JSON.parse(localStorage.getItem("{processed_key}") || "[]");
                               return processedList.includes(title);
                           }}""",
                    title
                )

                if is_processed:
                    print(f"[跳过] {title}")
                    continue

                # 悬停显示按钮（根据HTML结构，按钮在悬停时显示）
                await item.hover()

                # 点击生成文案按钮
                button = item.locator('button:has-text("生成文案")')
                await button.click()
                print(f"[点击] {title}")

                # 等待30秒
                # await page.wait_for_timeout(30000)
                print(f"[等待完成] {title}")
                
                # 监听"一键成片"按钮
                print(f"[开始监听] 一键成片按钮")
                should_exit_while_loop = False  # 添加标志变量
                while True:
                    # 定位"一键成片"按钮
                    one_key_button = page.locator("button:has-text('一键成片')")
                    
                    # 检查按钮是否存在
                    if await one_key_button.count() > 0:
                        # 检查按钮是否有disabled属性
                        is_disabled = await one_key_button.get_attribute("disabled")
                        
                        if is_disabled is None:
                            # 按钮不再被禁用，点击它
                            print(f"[发现可点击按钮] 一键成片")
                            await one_key_button.click()  # 先点击一键成片按钮
                            
                            # 等待可能出现的"温馨提示"窗口
                            print(f"[检查] 是否出现温馨提示窗口")
                            await page.wait_for_timeout(2000)  # 等待2秒，让窗口有时间显示
                            
                            try:
                                # 检查是否存在"温馨提示"窗口，设置较短的超时时间
                                tip_window = page.locator("div:has-text('温馨提示') >> visible=true")
                                if await tip_window.count() > 0:
                                    print(f"[发现] 温馨提示窗口")
                                    
                                    # 定位并点击"知道了"按钮，设置较短的超时时间
                                    know_button = page.locator("button:has-text('知道了')")
                                    if await know_button.count() > 0:
                                        try:
                                            # 设置较短的超时时间进行点击
                                            await know_button.click(timeout=5000)
                                            print(f"[已点击] 知道了按钮")
                                        except Exception as e:
                                            print(f"[警告] 点击知道了按钮时出错: {str(e)}")
                                    else:
                                        print(f"[警告] 未找到知道了按钮")
                                else:
                                    print(f"[信息] 未出现温馨提示窗口，继续执行")
                            except Exception as e:
                                print(f"[警告] 处理温馨提示窗口时出错: {str(e)}")
                                # 继续执行，不要因为这个错误中断流程
                                
                            # 记录到LocalStorage前打印日志
                            print(f"[开始记录] 准备将标题 '{title}' 记录到LocalStorage")
                            
                            # 记录到LocalStorage
                            await page.evaluate(
                                f"""
                                        (title, processedKey, batchKey) => {{
                                            // 更新已处理列表
                                            const processedList = JSON.parse(localStorage.getItem(processedKey) || "[]");
                                            if (!processedList.includes(title)) {{
                                                processedList.push(title);
                                                localStorage.setItem(processedKey, JSON.stringify(processedList));
                                            }}

                                            // 更新当前批次记录
                                            const batchList = JSON.parse(localStorage.getItem(batchKey) || "[]");
                                            if (!batchList.includes(title)) {{
                                                batchList.push(title);
                                                localStorage.setItem(batchKey, JSON.stringify(batchList));
                                            }}
                                        }}
                                        """,
                                title, processed_key, batch_key
                            )
                            
                            # 记录完成后打印日志
                            print(f"[记录完成] 标题 '{title}' 已成功记录到LocalStorage")

                            print(f"[记录完成] {title}")
                            
                            # 监听新打开的标签页
                            print(f"[监听] 等待新标签页打开")
                            # 获取当前所有页面
                            current_pages = context.pages
                            current_page_count = len(current_pages)
                            
                            # 等待新标签页打开（最多等待10秒）
                            new_page = None
                            max_wait_time = 10  # 最大等待时间（秒）
                            start_time = time.time()
                            
                            while time.time() - start_time < max_wait_time:
                                # 获取最新的页面列表
                                pages = context.pages
                                # 如果页面数量增加，说明新标签页已打开
                                if len(pages) > current_page_count:
                                    # 获取最新打开的页面（通常是列表中的最后一个）
                                    new_page = pages[-1]
                                    print(f"[发现] 新标签页已打开")
                                    break
                                # 短暂等待后再次检查
                                await asyncio.sleep(0.5)
                            
                            # 如果找到新标签页，获取其标题和URL并保存
                            if new_page:
                                # 等待页面加载完成
                                try:
                                    await new_page.wait_for_load_state("domcontentloaded", timeout=5000)
                                    # 获取页面标题和URL
                                    page_title = await new_page.title()
                                    page_url = new_page.url
                                    
                                    print(f"[获取] 标题: {page_title}")
                                    print(f"[获取] URL: {page_url}")
                                    
                                    # 将标题和URL保存到url.txt文件
                                    with open("url.txt", "a", encoding="utf-8") as f:
                                        f.write(f"{page_title}\n{page_url}\n\n")
                                    
                                    print(f"[保存] 标题和URL已保存到url.txt")
                                    
                                    # 等待5秒后关闭新标签页
                                    print(f"[等待] 5秒后将关闭新标签页")
                                    await asyncio.sleep(5)
                                    await new_page.close()
                                    print(f"[关闭] 新标签页已关闭")
                                except Exception as e:
                                    print(f"[错误] 处理新标签页时出错: {str(e)}")
                                    try:
                                        # 尝试关闭页面，即使出错
                                        await new_page.close()
                                        print(f"[关闭] 新标签页已关闭（出错后）")
                                    except:
                                        pass
                            else:
                                print(f"[警告] 未检测到新标签页打开")
                            
                            # 跳出整个while循环
                            print(f"[操作] 跳出所有循环，不再处理其他新闻")
                            should_exit_while_loop = True  # 设置标志变量
                            break  # 跳出while循环
                    
                    # 检查是否需要跳出while循环
                    if should_exit_while_loop:
                        break
                        
                    # 每秒检查一次按钮状态
                    await page.wait_for_timeout(1000)
                
                # 检查是否需要跳出for循环
                if should_exit_while_loop:
                    print(f"[操作] 跳出for循环，完全结束处理")
                    break  # 跳出for循环
            except Exception as e:
                print(f"处理新闻时出错: {str(e)}")
                continue


        # endregion 操作处

        print(f"[循环完成] 准备关闭浏览器")

        # 暂停 1000s
        await asyncio.sleep(1000)  # 这里延迟是为了方便眼睛直观的观看

        # 退出前保存 storage 信息
        await context.storage_state(path=self.account_file)  # 保存cookie
        baijiahao_logger.info('cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文和浏览器实例
        await context.close()
        await browser.close()


    async def mainAi(self):
        async with async_playwright() as playwright:
            await self.ai2video(playwright)
