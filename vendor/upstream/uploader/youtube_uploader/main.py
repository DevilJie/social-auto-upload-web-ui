# -*- coding: utf-8 -*-
"""
YouTube Video Uploader

基于 Patchright 浏览器自动化 + Cookie 认证的 YouTube 视频上传器

上传地址: https://studio.youtube.com/channel/{channel_id}/videos/upload

YouTube Studio 使用 Polymer Shadow DOM，所有输入框均为 contenteditable div，
需要使用 Playwright locator 穿透 Shadow DOM 进行操作。

上传流程（4个步骤）：
  1. 详细信息 — 填写标题、描述、封面、观众（是否面向儿童）、展开高级设置（加工内容、标签）
  2. 视频元素 — 直接跳过
  3. 检查 — 直接跳过
  4. 公开范围 — 选择公开或定时发布
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

from patchright.async_api import Page
from patchright.async_api import Playwright
from patchright.async_api import async_playwright

from conf import DEBUG_MODE, LOCAL_CHROME_HEADLESS, _load_proxy_url
from myUtils.browser import create_browser, create_context, create_persistent_context
from uploader.base_video import BaseVideoUploader
from utils.log import youtube_logger

YOUTUBE_STUDIO_URL = "https://studio.youtube.com"


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


async def _scrape_youtube_profile(page):
    """从 YouTube Studio 页面抓取频道名称和头像（需有头模式，无头会被拦截）"""
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state('networkidle', timeout=15000)
        await asyncio.sleep(5)

        # Playwright locator 能穿透 Shadow DOM
        # 昵称: div#entity-name
        name_el = page.locator('div#entity-name').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()

        # 头像: img 含 ggpht.com
        all_imgs = page.locator('img')
        count = await all_imgs.count()
        for i in range(count):
            img = all_imgs.nth(i)
            src = (await img.get_attribute('src') or '')
            alt = (await img.get_attribute('alt') or '')
            if 'ggpht.com' in src or 'googleusercontent' in src:
                avatar = src
                if not name and alt and len(alt) < 50:
                    name = alt
                break

        # 备选：从页面标题获取
        if not name:
            title = await page.title()
            if ' - ' in title:
                candidate = title.split(' - ')[0].strip()
                if candidate and candidate != 'YouTube':
                    name = candidate

        print(f"[YOUTUBE] 抓取结果 - name={name!r} avatar={avatar[:50] if avatar else 'None'}", flush=True)
    except Exception as e:
        print(f"[YOUTUBE] 抓取用户资料失败: {e}", flush=True)
    return name, avatar


async def cookie_auth(account_file: str) -> bool:
    """校验 YouTube cookie 是否有效（无头模式）"""
    from conf import _load_proxy_url
    async with async_playwright() as playwright:
        _proxy = _load_proxy_url()
        browser = await create_browser(playwright, headless=True, proxy={"server": _proxy} if _proxy else None)
        try:
            context = await create_context(browser, storage_state=account_file)
            page = await context.new_page()
            await page.goto(YOUTUBE_STUDIO_URL)
            # 如果跳转到登录页面则 cookie 无效
            if "accounts.google.com" in page.url or "signin" in page.url.lower():
                youtube_logger.info(_msg("❌", "YouTube cookie 已失效，需要重新登录"))
                return False
            youtube_logger.success(_msg("✅", "YouTube cookie 有效"))
            return True
        except Exception as exc:
            youtube_logger.warning(_msg("⚠️", f"YouTube cookie 校验时出错: {exc}"))
            return False
        finally:
            await browser.close()


async def youtube_cookie_gen(id, status_queue):
    """生成 YouTube cookie（供 sau_backend login 接口调用）
    使用 patchright（反检测）+ launch_persistent_context（代理在有头模式下生效）
    """
    import json
    import uuid
    import os
    import tempfile
    from conf import BASE_DIR, _load_proxy_url

    # 代理：海外平台需要代理才能连接（每次动态读取，支持前端即时修改）
    proxy_url = _load_proxy_url()

    print(f"[YOUTUBE DEBUG] Launching browser... proxy={proxy_url}")

    context = None
    try:
        async with async_playwright() as playwright:
            # launch_persistent_context：patchright 有头模式下代理的唯一可靠方式
            # 注意：不加载 stealth.js，patchright 自身已有反检测能力
            tmp_dir = tempfile.mkdtemp(prefix="yt-login-")
            context = await create_persistent_context(
                playwright,
                user_data_dir=tmp_dir,
                headless=False,
                proxy={"server": proxy_url} if proxy_url else None,
            )
            page = context.pages[0] if context.pages else await context.new_page()
            print(f"[YOUTUBE DEBUG] Navigating to accounts.google.com...")
            await page.goto("https://accounts.google.com/", timeout=30000)
            print(f"[YOUTUBE DEBUG] Page loaded, title: {await page.title()}")
            youtube_logger.info("YouTube登录页面已打开，请完成扫码登录...")

            # 等待登录完成 - 检测 URL 离开登录页即可
            try:
                while True:
                    current_url = page.url
                    # 还在登录页面，继续等
                    if "accounts.google.com" in current_url and ("signin" in current_url or current_url.endswith("accounts.google.com/")):
                        await asyncio.sleep(1)
                        continue
                    # 已经离开登录页，说明登录成功
                    youtube_logger.info(f"检测到登录成功，当前页面: {current_url}")
                    break
                # 尝试导航到 YouTube Studio 确认 cookie 有效
                try:
                    await page.goto("https://studio.youtube.com", timeout=15000)
                    youtube_logger.info("YouTube Studio 页面已打开")
                except Exception:
                    youtube_logger.warning("导航到 YouTube Studio 失败，但 cookie 可能已保存")
            except Exception:
                youtube_logger.warning("登录检测异常")

            # 抓取用户资料
            user_name, avatar_url = await _scrape_youtube_profile(page)
            if not user_name:
                user_name = "YouTube用户"

            # 保存 cookie
            uuid_v1 = str(uuid.uuid1())
            cookies_dir = Path(BASE_DIR / "cookiesFile")
            cookies_dir.mkdir(exist_ok=True)
            await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
            youtube_logger.success("YouTube cookie saved")
            await context.close()
            context = None

            # 保存到数据库
            import sqlite3
            with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                               INSERT INTO user_info (type, filePath, userName, status, avatar)
                               VALUES (?, ?, ?, ?, ?)
                               ''', (8, f"{uuid_v1}.json", user_name, 1, avatar_url))
                conn.commit()

            # 发送成功消息
            status_queue.put(json.dumps({"status": "200", "name": user_name, "avatar": avatar_url}))
    except Exception as e:
        print(f"[YOUTUBE ERROR] {type(e).__name__}: {e}")
        youtube_logger.error(f"YouTube 登录失败: {e}")
        status_queue.put(json.dumps({"status": "500", "msg": f"YouTube 登录失败: {e}"}))
        if context:
            try:
                await context.close()
            except Exception:
                pass


async def youtube_setup(account_file: str, handle=False, return_detail=False, headless=True) -> bool:
    """检查 YouTube cookie 是否就绪"""
    return await cookie_auth(account_file)


class YouTubeBaseUploader(BaseVideoUploader):
    def __init__(
        self,
        publish_date: datetime | int,
        account_file,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        self.publish_date = publish_date
        self.account_file = str(account_file)
        self.debug = debug
        self.headless = headless

    async def validate_base_args(self):
        if not os.path.exists(self.account_file):
            raise RuntimeError(
                f"YouTube cookie 文件不存在，请先完成登录: {self.account_file}"
            )
        if not await cookie_auth(self.account_file):
            raise RuntimeError(
                f"YouTube cookie 已失效，请先完成登录: {self.account_file}"
            )

        if self.publish_date != 0:
            self.publish_date = self.validate_publish_date(self.publish_date)


class YouTubeVideo(YouTubeBaseUploader):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime | int,
        account_file,
        desc: str | None = None,
        thumbnail_path=None,
        headless: bool = LOCAL_CHROME_HEADLESS,
        audience: str = 'not_kids',  # 'kids' or 'not_kids'
        altered_content: bool = False,  # 是否包含加工内容
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            headless=headless,
        )
        self.title = title
        self.file_path = file_path
        # 解析标签：支持 "#标签1 #标签2" 或 "标签1,标签2" 或混合格式
        if isinstance(tags, str) and tags.strip():
            import re
            self.tags = [t.strip() for t in re.split(r'[,，#]', tags) if t.strip()]
        elif isinstance(tags, list):
            self.tags = tags
        else:
            self.tags = []
        self.desc = desc or ""
        self.thumbnail_path = thumbnail_path
        self.audience = audience
        self.altered_content = altered_content

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("YouTube 视频上传时，title 是必须的")
        self.file_path = str(self.validate_video_file(self.file_path))
        if self.thumbnail_path:
            self.thumbnail_path = str(self.validate_image_file(self.thumbnail_path))

    async def _open_upload_dialog(self, page: Page):
        """在 YouTube Studio 首页点击上传按钮，打开上传对话框"""
        youtube_logger.info(_msg("🖱️", "点击上传按钮"))

        # 等待页面完全渲染（Polymer 组件需要时间）
        await asyncio.sleep(5)

        # 尝试多种方式找到上传按钮
        upload_btn = page.locator('#upload-icon, [aria-label="上传视频"], ytcp-icon-button[aria-label="Upload videos"]').first
        await upload_btn.wait_for(state="visible", timeout=20000)
        youtube_logger.info(_msg("✅", "找到上传按钮，准备点击"))

        # 强制点击（穿透 Shadow DOM）
        await upload_btn.click(force=True)
        youtube_logger.info(_msg("✅", "已点击上传按钮，等待对话框出现"))

        # 等待上传对话框出现（确认文件选择器区域可见）
        file_picker = page.locator('#select-files-button, ytcp-uploads-file-picker').first
        await file_picker.wait_for(state="visible", timeout=15000)
        youtube_logger.info(_msg("✅", "上传对话框已打开"))

    async def _upload_video_file(self, page: Page):
        """在弹出的上传对话框中选择视频文件"""
        youtube_logger.info(_msg("📤", "正在上传视频文件"))

        # 上传对话框内的文件 input
        file_input = page.locator('input[name="Filedata"]').first
        await file_input.wait_for(state="attached", timeout=10000)
        await file_input.set_input_files(self.file_path)
        youtube_logger.info(_msg("✅", "视频文件已选择，等待上传处理"))

    async def _wait_upload_complete(self, page: Page):
        """等待视频上传完成，直到详细信息表单和封面组件出现"""
        youtube_logger.info(_msg("⏳", "等待视频上传完成..."))

        # 等待标题输入框出现（contenteditable div）— 说明上传完成进入编辑界面
        title_box = page.locator('#title-textarea #textbox').first
        await title_box.wait_for(state="visible", timeout=300000)  # 最多等5分钟
        youtube_logger.success(_msg("✅", "标题输入框已出现"))

        # 等待封面上传组件出现 — 确保页面完全加载
        try:
            thumbnail_input = page.locator('ytcp-thumbnail-uploader input#file-loader').first
            await thumbnail_input.wait_for(state="attached", timeout=60000)
            youtube_logger.success(_msg("✅", "封面上传组件已就绪"))
        except Exception:
            youtube_logger.warning(_msg("⚠️", "封面上传组件未出现，继续执行"))

        youtube_logger.success(_msg("✅", "视频上传完成，编辑界面已加载"))

        # 检查是否有上传失败的提示
        fail_text = page.locator("text=上传失败")
        if await fail_text.count() > 0:
            youtube_logger.error(_msg("❌", "视频上传失败"))
            return False

        return True

    async def _clear_and_type_contenteditable(self, page: Page, selector: str, text: str):
        """向 contenteditable div 输入文本"""
        el = page.locator(selector).first
        await el.wait_for(state="visible", timeout=10000)
        await el.click()
        await asyncio.sleep(0.3)
        # 全选清空
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        await asyncio.sleep(0.2)
        # 输入新文本
        await el.press_sequentially(text, delay=30)

    async def _fill_title(self, page: Page):
        """填写视频标题（contenteditable div）"""
        youtube_logger.info(_msg("✍️", f"填写标题: {self.title[:30]}"))
        await self._clear_and_type_contenteditable(page, '#title-textarea #textbox', self.title[:100])

    async def _fill_desc(self, page: Page):
        """填写视频描述（contenteditable div）"""
        if not self.desc:
            return
        youtube_logger.info(_msg("📝", "填写视频描述"))
        await self._clear_and_type_contenteditable(page, '#description-textarea #textbox', self.desc)

    async def _set_thumbnail(self, page: Page):
        """上传视频封面"""
        if not self.thumbnail_path:
            return
        if not os.path.exists(self.thumbnail_path):
            youtube_logger.error(_msg("❌", f"封面文件不存在: {self.thumbnail_path}"))
            return

        youtube_logger.info(_msg("🖼️", "开始设置 YouTube 封面"))
        try:
            # 封面上传的隐藏 file input（id="file-loader"）
            file_input = page.locator('ytcp-thumbnail-uploader input#file-loader').first
            await file_input.wait_for(state="attached", timeout=10000)
            await file_input.set_input_files(self.thumbnail_path)
            youtube_logger.success(_msg("✅", "封面已上传"))
            # 等待封面上传完成
            await asyncio.sleep(3)
        except Exception as exc:
            youtube_logger.warning(_msg("⚠️", f"封面设置失败: {exc}"))

    async def _set_audience(self, page: Page):
        """设置观众（是否面向儿童）"""
        youtube_logger.info(_msg("👥", f"设置观众: {'面向儿童' if self.audience == 'kids' else '不是面向儿童'}"))
        try:
            if self.audience == 'kids':
                radio = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_MFK"]').first
            else:
                radio = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').first

            await radio.wait_for(state="visible", timeout=10000)
            # 检查是否已经选中
            is_checked = await radio.get_attribute("aria-checked")
            if is_checked == "true":
                youtube_logger.info(_msg("✅", "观众设置已是目标值，跳过"))
                return
            # force=True 穿透 Shadow DOM 点击
            await radio.click(force=True)
            await asyncio.sleep(1)
            # 验证是否选中成功
            is_checked_after = await radio.get_attribute("aria-checked")
            if is_checked_after == "true":
                youtube_logger.success(_msg("✅", "观众设置完成"))
            else:
                youtube_logger.warning(_msg("⚠️", "观众设置可能未生效，再次点击"))
                await radio.click(force=True)
                await asyncio.sleep(0.5)
                youtube_logger.success(_msg("✅", "观众设置重试完成"))
        except Exception as exc:
            youtube_logger.warning(_msg("⚠️", f"观众设置失败: {exc}"))

    async def _expand_advanced_settings(self, page: Page):
        """展开高级设置"""
        youtube_logger.info(_msg("⚙️", "展开高级设置"))
        try:
            # 找到"展开"按钮（toggle-button 的 aria-label 为 "显示高级设置"）
            toggle_btn = page.locator('#toggle-button').first
            await toggle_btn.wait_for(state="visible", timeout=10000)

            # 检查是否已经展开（如果按钮 aria-label 包含 "隐藏" 则已展开）
            aria_label = await toggle_btn.get_attribute("aria-label") or ""
            if "隐藏" not in aria_label and "Collapse" not in aria_label:
                await toggle_btn.click(force=True)
                await asyncio.sleep(2)
                youtube_logger.info(_msg("✅", "高级设置已展开"))
            else:
                youtube_logger.info(_msg("✅", "高级设置已处于展开状态"))
        except Exception as exc:
            youtube_logger.warning(_msg("⚠️", f"展开高级设置失败: {exc}"))

    async def _set_altered_content(self, page: Page):
        """设置加工内容声明"""
        youtube_logger.info(_msg("🔧", f"设置加工内容: {'是' if self.altered_content else '否'}"))
        try:
            if self.altered_content:
                radio = page.locator('tp-yt-paper-radio-button[name="VIDEO_HAS_ALTERED_CONTENT_YES"]').first
            else:
                radio = page.locator('tp-yt-paper-radio-button[name="VIDEO_HAS_ALTERED_CONTENT_NO"]').first

            await radio.wait_for(state="visible", timeout=10000)
            is_checked = await radio.get_attribute("aria-checked")
            if is_checked == "true":
                youtube_logger.info(_msg("✅", "加工内容已是目标值，跳过"))
                return
            # force=True 穿透 Shadow DOM
            await radio.click(force=True)
            await asyncio.sleep(1)
            # 验证
            is_checked_after = await radio.get_attribute("aria-checked")
            if is_checked_after == "true":
                youtube_logger.success(_msg("✅", "加工内容设置完成"))
            else:
                youtube_logger.warning(_msg("⚠️", "加工内容可能未生效，再次点击"))
                await radio.click(force=True)
                await asyncio.sleep(0.5)
                youtube_logger.success(_msg("✅", "加工内容重试完成"))
        except Exception as exc:
            youtube_logger.warning(_msg("⚠️", f"加工内容设置失败: {exc}"))

    async def _fill_tags(self, page: Page):
        """填写视频标签（在高级设置的标签输入框中）"""
        if not self.tags:
            return

        youtube_logger.info(_msg("🏷️", f"添加 {len(self.tags)} 个标签"))
        try:
            tag_input = page.locator('#tags-container input#text-input').first
            await tag_input.wait_for(state="visible", timeout=10000)

            for tag in self.tags[:15]:
                try:
                    await tag_input.click()
                    await asyncio.sleep(0.2)
                    await tag_input.press_sequentially(str(tag), delay=30)
                    await asyncio.sleep(0.3)
                    await tag_input.press("Enter")
                    await asyncio.sleep(0.3)
                    youtube_logger.info(_msg("🏷️", f"已添加标签: {tag}"))
                except Exception as exc:
                    youtube_logger.warning(_msg("⚠️", f"添加标签失败 '{tag}': {exc}"))
        except Exception as exc:
            youtube_logger.warning(_msg("⚠️", f"标签输入框未找到: {exc}"))

    async def _click_next(self, page: Page):
        """点击"继续"按钮"""
        next_btn = page.locator('#next-button').first
        await next_btn.wait_for(state="visible", timeout=10000)
        await next_btn.click()
        await asyncio.sleep(2)

    async def _click_public_radio(self, page: Page):
        """点击 PUBLIC radio button（无论是否定时，都需要先选中公开）"""
        youtube_logger.info(_msg("🖱️", "开始点击 PUBLIC radio"))

        # 等待 radio group 出现
        privacy_radios = page.locator('#privacy-radios').first
        await privacy_radios.wait_for(state="visible", timeout=15000)
        youtube_logger.info(_msg("📋", "privacy-radios 已可见"))

        # 定位 PUBLIC radio
        public_radio = page.locator('tp-yt-paper-radio-button[name="PUBLIC"]').first
        await public_radio.wait_for(state="visible", timeout=10000)

        # 检查是否已选中
        is_checked = await public_radio.get_attribute("aria-checked")
        youtube_logger.info(_msg("📋", f"PUBLIC radio aria-checked={is_checked}"))
        if is_checked == "true":
            youtube_logger.info(_msg("✅", "公开已是选中状态"))
            return

        # 先滚动到元素可见
        await public_radio.scroll_into_view_if_needed()
        await asyncio.sleep(0.5)

        # 方法1: evaluate 直接触发 DOM click
        youtube_logger.info(_msg("🖱️", "方法1: evaluate click"))
        await public_radio.evaluate('el => el.click()')
        await asyncio.sleep(1.5)

        is_checked_after = await public_radio.get_attribute("aria-checked")
        youtube_logger.info(_msg("📋", f"evaluate 后 aria-checked={is_checked_after}"))
        if is_checked_after == "true":
            youtube_logger.success(_msg("✅", "已选择公开（evaluate）"))
            return

        # 方法2: Playwright click + force
        youtube_logger.info(_msg("🖱️", "方法2: playwright force click"))
        await public_radio.click(force=True)
        await asyncio.sleep(1.5)

        is_checked_after = await public_radio.get_attribute("aria-checked")
        youtube_logger.info(_msg("📋", f"force click 后 aria-checked={is_checked_after}"))
        if is_checked_after == "true":
            youtube_logger.success(_msg("✅", "已选择公开（force click）"))
            return

        # 方法3: 点击 radioContainer 内的 offRadio 圆圈
        youtube_logger.info(_msg("🖱️", "方法3: 点击 offRadio"))
        try:
            off_radio = public_radio.locator('#offRadio').first
            await off_radio.click(force=True)
            await asyncio.sleep(1)
            is_checked_after = await public_radio.get_attribute("aria-checked")
            if is_checked_after == "true":
                youtube_logger.success(_msg("✅", "已选择公开（offRadio）"))
                return
        except Exception as e:
            youtube_logger.warning(_msg("⚠️", f"offRadio click 失败: {e}"))

        # 方法4: 用 page.evaluate 全局查找并点击
        youtube_logger.info(_msg("🖱️", "方法4: page.evaluate 全局查找"))
        try:
            result = await page.evaluate('''() => {
                const radios = document.querySelectorAll('tp-yt-paper-radio-button[name="PUBLIC"]');
                if (radios.length > 0) {
                    radios[0].click();
                    return radios[0].getAttribute('aria-checked');
                }
                return 'not_found';
            }''')
            youtube_logger.info(_msg("📋", f"全局 evaluate 后 aria-checked={result}"))
        except Exception as e:
            youtube_logger.warning(_msg("⚠️", f"全局 evaluate 失败: {e}"))

        youtube_logger.success(_msg("✅", "公开 radio 点击流程结束"))

    async def _set_visibility(self, page: Page):
        """设置公开范围 — 先选公开，再按需设置定时"""
        # 等待公开范围步骤加载
        await asyncio.sleep(2)

        # 无论是否定时，都需要先选中"公开"
        await self._click_public_radio(page)

        is_scheduled = self.publish_date != 0 and self.publish_date is not None
        if is_scheduled:
            youtube_logger.info(_msg("📅", "设置定时发布"))
            await self._set_scheduled_publish(page)

    async def _set_public_publish(self, page: Page):
        """选择公开发布 — 已在 _set_visibility 中通过 _click_public_radio 处理"""
        pass

    async def _set_scheduled_publish(self, page: Page):
        """设置定时发布 — 日期直接输入、时间直接输入、时区下拉选择"""
        try:
            # 等待公开范围步骤加载
            await asyncio.sleep(2)

            # 准备日期/时间字符串
            if isinstance(self.publish_date, datetime):
                date_str = f"{self.publish_date.year}年{self.publish_date.month}月{self.publish_date.day}日"
                time_str = f"{self.publish_date.hour:02d}:{self.publish_date.minute:02d}"
            else:
                dt = datetime.fromtimestamp(int(self.publish_date))
                date_str = f"{dt.year}年{dt.month}月{dt.day}日"
                time_str = f"{dt.hour:02d}:{dt.minute:02d}"

            youtube_logger.info(_msg("📅", f"计划定时发布: {date_str} {time_str}"))

            # 1. 点击 second-container 展开"安排时间"选项
            second_container = page.locator('#second-container').first
            await second_container.wait_for(state="visible", timeout=10000)
            await second_container.click(force=True)
            await asyncio.sleep(1)

            # 尝试展开定时发布的详细信息
            expand_btn = page.locator('#second-container-expand-button').first
            try:
                if await expand_btn.is_visible():
                    await expand_btn.click(force=True)
                    await asyncio.sleep(1)
            except Exception:
                pass

            # 2. 设置日期 — 点击 datepicker-trigger 展开日期选择器，然后直接在输入框中输入日期
            youtube_logger.info(_msg("📅", f"设置日期: {date_str}"))
            date_trigger = page.locator('#datepicker-trigger').first
            await date_trigger.wait_for(state="visible", timeout=10000)

            # 点击展开日期选择器
            await date_trigger.click(force=True)
            await asyncio.sleep(1)

            # 找到日期输入框（在 datepicker 弹窗内的 tp-yt-iron-input input）
            date_input = page.locator(
                '#datepicker-trigger tp-yt-iron-input input, '
                'tp-yt-paper-dialog.ytcp-datepicker tp-yt-iron-input input'
            ).first

            try:
                await date_input.wait_for(state="visible", timeout=5000)
                await date_input.click()
                await asyncio.sleep(0.3)
                # 全选并输入新日期
                await page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
                await date_input.press_sequentially(date_str, delay=30)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)
                youtube_logger.success(_msg("✅", f"日期已输入: {date_str}"))
            except Exception as exc:
                # 备选方案：直接操作 datepicker trigger 内部的文本
                youtube_logger.warning(_msg("⚠️", f"日期输入框未找到，尝试备选方案: {exc}"))
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                # 点击 trigger 的下拉文本
                dropdown_text = date_trigger.locator('.dropdown-trigger-text').first
                await dropdown_text.click(force=True)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Control+a")
                await asyncio.sleep(0.1)
                await dropdown_text.press_sequentially(date_str, delay=30)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)

            # 3. 设置时间 — 在 time-of-day-container 的输入框中直接输入
            youtube_logger.info(_msg("⏰", f"设置时间: {time_str}"))
            time_input = page.locator(
                '#time-of-day-container tp-yt-iron-input input, '
                '#time-of-day-container input'
            ).first
            await time_input.wait_for(state="visible", timeout=10000)
            await time_input.click()
            await asyncio.sleep(0.3)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)
            await time_input.press_sequentially(time_str, delay=30)
            await asyncio.sleep(0.3)
            await page.keyboard.press("Enter")
            await asyncio.sleep(0.5)
            youtube_logger.success(_msg("✅", f"时间已输入: {time_str}"))

            # 4. 设置时区 — 点击时区按钮，从下拉列表选择 GMT+8 香港
            youtube_logger.info(_msg("🌐", "设置时区 GMT+8（香港）"))
            timezone_btn = page.locator('button[aria-label="时区"], #timezone-select-button').first
            try:
                await timezone_btn.wait_for(state="visible", timeout=5000)
                await timezone_btn.click(force=True)
                await asyncio.sleep(1)

                # 在时区下拉列表中选择 "(GMT+08:00) 香港"
                tz_option = page.locator('tp-yt-paper-item:has-text("（GMT+08:00）香港"), '
                                         'tp-yt-paper-item:has-text("(GMT+08:00) Hong Kong"), '
                                         'tp-yt-paper-item:has-text("GMT+08:00")').first
                await tz_option.wait_for(state="visible", timeout=5000)
                await tz_option.click()
                youtube_logger.success(_msg("✅", "时区已设置为 GMT+8（香港）"))
            except Exception as exc:
                youtube_logger.warning(_msg("⚠️", f"时区设置失败，使用默认时区: {exc}"))
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass

            await asyncio.sleep(1)
            youtube_logger.success(_msg("✅", "定时发布设置完成"))

        except Exception as exc:
            youtube_logger.warning(_msg("⚠️", f"设置定时发布失败: {exc}"))

    async def upload(self, playwright: Playwright) -> None:
        youtube_logger.info(_msg("🔍", "上传前检查 cookie、视频文件和发布时间"))
        await self.validate_upload_args()
        youtube_logger.info(_msg("✅", "上传前检查通过"))

        log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        browser = await create_browser(playwright, headless=self.headless, proxy={"server": _load_proxy_url()} if _load_proxy_url() else None)
        context = await create_context(browser, storage_state=self.account_file)

        upload_success = False
        try:
            page = await context.new_page()
            youtube_logger.info(_msg("🎬", f"开始上传视频: {self.title}"))
            # YouTube Studio 首页（不用 networkidle，YouTube Studio 有持续网络请求永远达不到）
            await page.goto(YOUTUBE_STUDIO_URL, wait_until='domcontentloaded', timeout=30000)
            youtube_logger.info(_msg("🧭", "YouTube Studio 页面已开始加载，等待渲染..."))
            await asyncio.sleep(5)

            # Step 1: 点击上传按钮，打开上传对话框
            await self._open_upload_dialog(page)

            # Step 2: 上传视频文件
            await self._upload_video_file(page)

            # Step 3: 等待上传完成
            upload_ok = await self._wait_upload_complete(page)
            if not upload_ok:
                raise RuntimeError("视频上传失败")

            await asyncio.sleep(2)

            # Step 4: 填写详细信息
            await self._fill_title(page)
            await self._fill_desc(page)
            await self._set_thumbnail(page)
            await self._set_audience(page)

            # Step 5: 展开高级设置
            await self._expand_advanced_settings(page)

            # Step 6: 设置加工内容
            await self._set_altered_content(page)

            # Step 7: 填写标签
            await self._fill_tags(page)

            # Step 8: 点击"继续" → 视频元素步骤
            youtube_logger.info(_msg("➡️", "点击继续 → 视频元素"))
            await self._click_next(page)

            # Step 9: 点击"继续" → 检查步骤
            youtube_logger.info(_msg("➡️", "点击继续 → 检查"))
            await self._click_next(page)

            # Step 10: 点击"继续" → 公开范围步骤
            youtube_logger.info(_msg("➡️", "点击继续 → 公开范围"))
            await self._click_next(page)

            # Step 11: 设置公开范围
            await self._set_visibility(page)

            await asyncio.sleep(1)

            # Step 12: 点击"保存"完成发布
            youtube_logger.info(_msg("📤", "点击保存完成发布"))
            done_btn = page.locator('#done-button').first
            await done_btn.wait_for(state="visible", timeout=10000)
            await done_btn.click()
            youtube_logger.info(_msg("⏳", "等待发布处理..."))

            await asyncio.sleep(5)

            upload_success = True
            youtube_logger.success(_msg("✅", "视频发布成功"))

        except Exception as exc:
            upload_success = False
            youtube_logger.error(_msg("❌", f"上传过程出错: {exc}"))
            # 尝试截图保存错误现场
            try:
                screenshot_path = log_dir / f"youtube_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=str(screenshot_path))
                youtube_logger.info(_msg("📸", f"错误截图已保存: {screenshot_path}"))
            except Exception:
                pass
            raise RuntimeError(f"YouTube 上传失败: {exc}")
        finally:
            if upload_success:
                try:
                    await context.storage_state(path=self.account_file)
                    youtube_logger.success(_msg("✅", "YouTube cookie 已更新"))
                except Exception:
                    pass
            await context.close()
            await browser.close()
            youtube_logger.info(_msg("✅", "浏览器已关闭"))

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
