# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests

from patchright.async_api import Page
from patchright.async_api import Playwright
from patchright.async_api import async_playwright

from conf import DEBUG_MODE, LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from uploader.base_video import BaseVideoUploader
from utils.base_social_media import set_init_script
from utils.constant import VideoZoneTypes
from utils.log import bilibili_logger

BILIBILI_UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"
BILIBILI_MANAGE_URL = "https://member.bilibili.com/platform/upload-manager/article"
BILIBILI_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
BILIBILI_PUBLISH_STRATEGY_SCHEDULED = "scheduled"
BILIBILI_DEFAULT_TID = VideoZoneTypes.MUSIC.value if hasattr(VideoZoneTypes, 'MUSIC') else 3  # 音乐


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


async def cookie_auth(account_file: str) -> bool:
    """校验 B站 cookie 是否有效"""
    from conf import LOGIN_HEADLESS
    async with async_playwright() as playwright:
        if LOCAL_CHROME_PATH:
            browser = await playwright.chromium.launch(
                headless=LOGIN_HEADLESS, executable_path=LOCAL_CHROME_PATH,
            )
        else:
            browser = await playwright.chromium.launch(
                headless=LOGIN_HEADLESS, channel="chrome",
            )
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto(BILIBILI_UPLOAD_URL)
            if "passport.bilibili.com" in page.url:
                bilibili_logger.info(_msg("❌", "B站 cookie 已失效，需要重新登录"))
                return False
            bilibili_logger.success(_msg("✅", "B站 cookie 有效"))
            return True
        except Exception as exc:
            bilibili_logger.warning(_msg("⚠️", f"B站 cookie 校验时出错: {exc}"))
            return False
        finally:
            await browser.close()


async def bilibili_setup(account_file: str, handle=False, return_detail=False, headless=True) -> bool:
    """检查 B站 cookie 是否就绪（和其他平台 setup 函数接口对齐）"""
    return await cookie_auth(account_file)


class BilibiliBaseUploader(BaseVideoUploader):
    def __init__(
        self,
        publish_date: datetime | int,
        account_file,
        publish_strategy: str | None = None,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        self.publish_date = publish_date
        self.account_file = str(account_file)
        self.publish_strategy = publish_strategy
        self.debug = debug
        self.headless = headless
        self.local_executable_path = LOCAL_CHROME_PATH

    async def validate_base_args(self):
        if not os.path.exists(self.account_file):
            raise RuntimeError(
                f"B站 cookie 文件不存在，请先完成登录: {self.account_file}"
            )
        if not await cookie_auth(self.account_file):
            raise RuntimeError(
                f"B站 cookie 已失效，请先完成登录: {self.account_file}"
            )

        if self.publish_strategy is None:
            self.publish_strategy = (
                BILIBILI_PUBLISH_STRATEGY_SCHEDULED
                if self.publish_date != 0
                else BILIBILI_PUBLISH_STRATEGY_IMMEDIATE
            )

        if self.publish_strategy not in {
            BILIBILI_PUBLISH_STRATEGY_IMMEDIATE,
            BILIBILI_PUBLISH_STRATEGY_SCHEDULED,
        }:
            raise ValueError(f"不支持的发布策略: {self.publish_strategy}")

        if self.publish_strategy == BILIBILI_PUBLISH_STRATEGY_SCHEDULED:
            self.publish_date = self.validate_publish_date(self.publish_date)
        else:
            self.publish_date = 0


class BilibiliVideo(BilibiliBaseUploader):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime | int,
        account_file,
        category: int | None = None,
        thumbnail_path=None,
        desc: str | None = None,
        publish_strategy: str | None = None,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
        )
        self.title = title
        self.file_path = file_path
        self.tags = tags or []
        self.category = category or BILIBILI_DEFAULT_TID
        self.thumbnail_path = thumbnail_path
        self.desc = desc or ""

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("B站视频上传时，title 是必须的")
        self.file_path = str(self.validate_video_file(self.file_path))
        if self.thumbnail_path:
            self.thumbnail_path = str(self.validate_image_file(self.thumbnail_path))

    async def _upload_video_file(self, page: Page):
        """上传视频文件到 B站"""
        bilibili_logger.info(_msg("📤", "正在上传视频文件"))

        # B站上传页可能使用 iframe 也可能直接在主页面上
        # 先尝试 iframe，再尝试主页面
        file_input = None
        try:
            upload_frame = page.frame_locator('iframe[name="videoUpload"]')
            input_in_frame = upload_frame.locator(
                'input[type="file"]'
            )
            await input_in_frame.wait_for(state="attached", timeout=5000)
            file_input = input_in_frame
        except Exception:
            bilibili_logger.info(_msg("ℹ️", "未检测到上传 iframe，尝试主页面"))

        if file_input is None:
            # 备选：直接在主页面查找 file input
            file_input = page.locator('input[type="file"][accept*="video"], input[type="file"]').first
            await file_input.wait_for(state="attached", timeout=10000)

        await file_input.set_input_files(self.file_path)
        bilibili_logger.info(_msg("✅", "视频文件已选择，等待上传完成"))

    async def _wait_upload_complete(self, page: Page):
        """等待视频上传完成"""
        max_retries = 120
        retry_count = 0
        while retry_count < max_retries:
            try:
                # 检查上传完成标志
                # 尝试 iframe 内
                try:
                    upload_frame = page.frame_locator('iframe[name="videoUpload"]')
                    done_text = upload_frame.locator("text=上传完成")
                    if await done_text.count() > 0 and await done_text.first.is_visible():
                        bilibili_logger.success(_msg("✅", "视频上传完成"))
                        return
                except Exception:
                    pass

                # 备选：主页面检查
                done_text_main = page.locator("text=上传完成")
                if await done_text_main.count() > 0 and await done_text_main.first.is_visible():
                    bilibili_logger.success(_msg("✅", "视频上传完成"))
                    return

                # 检查上传失败
                fail_text = page.locator("text=上传失败")
                if await fail_text.count() > 0:
                    bilibili_logger.warning(_msg("⚠️", "视频上传失败，尝试重新上传"))
                    await self._upload_video_file(page)

                if retry_count % 10 == 0:
                    bilibili_logger.info(_msg("⏳", f"视频上传中... ({retry_count * 3}s)"))

                await asyncio.sleep(3)
            except Exception as exc:
                bilibili_logger.warning(_msg("⚠️", f"检查上传状态出错: {exc}"))
                await asyncio.sleep(3)
            retry_count += 1

        if retry_count == max_retries:
            bilibili_logger.warning(_msg("⚠️", "视频上传超时，可能未完成"))

    async def _fill_title(self, page: Page):
        """填写视频标题"""
        bilibili_logger.info(_msg("✍️", f"填写标题: {self.title[:30]}"))
        title_input = page.locator(
            'input[placeholder*="标题"], input[placeholder*="Title"], '
            '.video-title input, [class*="title"] input[type="text"]'
        ).first
        await title_input.wait_for(state="visible", timeout=15000)
        await title_input.click()
        await title_input.fill("")
        await title_input.fill(self.title[:80])

    # tid -> 中文名映射（B站页面上显示的是中文）
    _TID_CN_NAME = {
        # 主分区
        1: "动画", 13: "番剧", 23: "电影", 167: "国创", 11: "电视剧",
        177: "纪录片", 4: "游戏", 119: "鬼畜", 3: "音乐", 129: "舞蹈",
        181: "影视", 5: "娱乐", 36: "知识", 188: "科技", 202: "资讯",
        211: "美食", 160: "生活", 223: "汽车", 155: "时尚", 234: "运动",
        217: "动物圈", 19: "VLOG",
        # 常用子分区
        21: "日常", 28: "原创音乐", 31: "翻唱", 33: "连载动画",
        32: "完结动画", 95: "数码", 96: "星海", 122: "野生技术协会",
        207: "资讯", 251: "三农", 76: "游戏人物", 75: "单机游戏",
        65: "网络游戏", 163: "手机游戏", 164: "桌游棋牌",
        171: "电子竞技", 172: "MAD·AMV", 173: "MMD·3D",
    }

    async def _set_category(self, page: Page):
        """设置视频分区（容错：失败不阻塞上传）"""
        if not self.category:
            return

        cn_name = self._TID_CN_NAME.get(self.category, None)
        bilibili_logger.info(_msg("📂", f"设置分区 tid={self.category} 中文名={cn_name}"))
        try:
            log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            if not cn_name:
                bilibili_logger.warning(_msg("⚠️", f"未知的 tid: {self.category}，跳过分区设置"))
                return

            # 用 JS 点击分区下拉框并选择目标分区
            result = await page.evaluate("""(cnName) => {
                // 找到分区下拉框（通常是当前显示分区名的可点击元素）
                const allElements = document.querySelectorAll(
                    '[class*="select"], [class*="category"], [class*="zone"], [class*="partition"]'
                );
                for (const el of allElements) {
                    // 找到看起来像分区选择器的元素
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 10 && rect.height < 80
                        && el.textContent.trim().length < 20) {
                        el.click();
                        return {action: 'clicked_selector', text: el.textContent.trim()};
                    }
                }
                return null;
            }""", cn_name)
            await asyncio.sleep(1)

            await page.screenshot(path=str(log_dir / "bilibili_partition_open.png"), full_page=True)

            if result:
                bilibili_logger.info(_msg("📂", f"分区选择器已点击: {result}"))
            else:
                bilibili_logger.warning(_msg("⚠️", "未找到分区选择器"))
                return

            # 在展开的下拉菜单中点击目标分区
            clicked = await page.evaluate("""(cnName) => {
                const items = document.querySelectorAll(
                    '[class*="option"], [class*="item"], [class*="select"] li, '
                    + '[class*="category"] div, [class*="partition"] div'
                );
                for (const el of items) {
                    const text = el.textContent.trim();
                    if (text === cnName) {
                        el.click();
                        return text;
                    }
                }
                return null;
            }""", cn_name)

            if clicked:
                bilibili_logger.success(_msg("✅", f"分区已设置: {clicked}"))
            else:
                bilibili_logger.warning(_msg("⚠️", f"未找到分区: {cn_name}，将使用默认分区"))
            await asyncio.sleep(1)
        except Exception as exc:
            bilibili_logger.warning(_msg("⚠️", f"设置分区失败（不影响上传）: {exc}"))

    async def _fill_tags(self, page: Page):
        """填写视频标签"""
        if not self.tags:
            return

        bilibili_logger.info(_msg("🏷️", f"添加 {len(self.tags)} 个标签"))
        tag_input = page.locator(
            'input[placeholder*="回车键Enter创建标签"], '
            'input[placeholder*="Enter创建标签"], '
            'input[placeholder*="标签"]'
        ).first
        await tag_input.wait_for(state="visible", timeout=10000)
        for tag in self.tags[:10]:
            await tag_input.fill("")
            await tag_input.fill(str(tag))
            await asyncio.sleep(0.3)
            await tag_input.press("Enter")
            await asyncio.sleep(0.5)
            bilibili_logger.info(_msg("🏷️", f"已添加标签: {tag}"))

    async def _fill_desc(self, page: Page):
        """填写视频简介"""
        if not self.desc:
            return

        bilibili_logger.info(_msg("📝", "填写视频简介"))
        # B站简介编辑器可能是 contenteditable div 或 textarea
        desc_editor = page.locator(
            '[contenteditable="true"][class*="editor"], '
            '.ql-editor, '
            '[class*="desc"] textarea, '
            '[class*="desc"] [contenteditable="true"]'
        ).first
        if await desc_editor.count() > 0 and await desc_editor.is_visible():
            await desc_editor.click()
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(self.desc, delay=10)
        else:
            bilibili_logger.warning(_msg("⚠️", "未找到简介编辑器"))

    async def _set_thumbnail(self, page: Page):
        """通过浏览器自动化方式上传封面"""
        if not self.thumbnail_path:
            return

        import os
        if not os.path.exists(self.thumbnail_path):
            bilibili_logger.error(_msg("❌", f"封面文件不存在: {self.thumbnail_path}"))
            return

        log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
        bilibili_logger.info(_msg("🖼️", "开始设置B站封面"))

        try:
            # 截图调试
            await page.screenshot(path=str(log_dir / "bilibili_before_cover.png"), full_page=True)
            bilibili_logger.info(_msg("📸", "封面设置前截图已保存"))

            # 根据用户提供的DOM，点击封面区域会打开上传界面
            # 先点击封面上传区域，激活文件选择
            click_selectors = [
                ".cover-editor-panel-canvas-empty.ratio_16_9 .empty-uploader-wrap",
                ".ratio_16_9 .empty-uploader-wrap",
                ".cover-editor-panel-canvas-empty .empty-uploader-wrap",
                "[class*='empty-uploader-wrap']",
            ]

            click_target = None
            for sel in click_selectors:
                count = await page.locator(sel).count()
                bilibili_logger.info(_msg("🔍", f"查找封面上传点击区域，使用选择器 '{sel}'，数量: {count}"))
                if count > 0:
                    click_target = page.locator(sel).first
                    break

            if not click_target:
                bilibili_logger.error(_msg("❌", "未找到封面上传点击区域"))
                return

            bilibili_logger.info(_msg("🖱", "点击封面上传区域"))
            await click_target.click()
            await asyncio.sleep(1)

            # 点击后截图，查看弹窗情况
            await page.screenshot(path=str(log_dir / "bilibili_after_cover_click.png"), full_page=True)
            bilibili_logger.info(_msg("📸", "点击后截图已保存"))

            # 查找文件输入框（可能是隐藏的）
            file_input_selectors = [
                "input[type='file'][accept*='image']",
                "input[type='file']",
            ]

            file_input = None
            for sel in file_input_selectors:
                count = await page.locator(sel).count()
                bilibili_logger.info(_msg("🔍", f"查找文件 input，使用选择器 '{sel}'，数量: {count}"))
                if count > 0:
                    file_input = page.locator(sel).first
                    break

            if not file_input:
                bilibili_logger.error(_msg("❌", "未找到文件 input"))
                return

            await file_input.set_input_files(self.thumbnail_path)
            bilibili_logger.info(_msg("📤", f"已选择封面文件: {os.path.basename(self.thumbnail_path)}"))

            # 等待封面上传处理
            await asyncio.sleep(2)

            # 查找并点击确定按钮
            confirm_selectors = [
                "button:has-text('确定')",
                "[class*='confirm']",
                "[class*='submit']",
            ]
            confirm_button = None
            for sel in confirm_selectors:
                count = await page.locator(sel).count()
                if count > 0:
                    confirm_button = page.locator(sel).first
                    bilibili_logger.info(_msg("🔘", f"找到确定按钮: {sel}"))
                    break

            if confirm_button:
                await confirm_button.click()
                bilibili_logger.info(_msg("✅", "已点击确定按钮"))
            else:
                bilibili_logger.warning(_msg("⚠️", "未找到确定按钮"))

            bilibili_logger.success(_msg("🥳", "B站封面设置完成"))

        except Exception as exc:
            bilibili_logger.error(_msg("❌", f"封面设置失败: {exc}"))
            raise RuntimeError(f"封面设置失败: {exc}")

    async def upload(self, playwright: Playwright) -> None:
        bilibili_logger.info(_msg("🔍", "上传前检查 cookie、视频文件和发布时间"))
        await self.validate_upload_args()
        bilibili_logger.info(_msg("✅", "上传前检查通过"))

        log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        if self.local_executable_path:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                executable_path=self.local_executable_path,
            )
        else:
            browser = await playwright.chromium.launch(
                headless=self.headless,
                channel="chrome",
            )
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)

        upload_success = False
        try:
            page = await context.new_page()
            bilibili_logger.info(_msg("🎬", f"开始上传视频: {self.title}"))
            await page.goto(BILIBILI_UPLOAD_URL)
            bilibili_logger.info(_msg("🧭", "正在等待B站上传页面加载"))
            await page.wait_for_url("**/platform/upload/**", timeout=30000)

            # 检查是否被重定向到登录页
            if "passport.bilibili.com" in page.url:
                raise RuntimeError("B站 cookie 已失效，请重新登录")

            # 1. 上传视频文件
            await self._upload_video_file(page)

            # 2. 等待上传完成
            await self._wait_upload_complete(page)
            await asyncio.sleep(3)

            # 表单填写前截图
            await page.screenshot(path=str(log_dir / "bilibili_before_form.png"), full_page=True)

            # 3. 填写标题
            await self._fill_title(page)

            # 4. 设置分区
            await self._set_category(page)

            # 5. 填写标签
            await self._fill_tags(page)

            # 6. 填写简介
            await self._fill_desc(page)

            # 7. 设置封面
            await self._set_thumbnail(page)

            # 8. 设置定时发布
            if self.publish_strategy == BILIBILI_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
                await self._set_schedule_time(page, self.publish_date)

            # 提交前截图
            await page.screenshot(path=str(log_dir / "bilibili_before_submit.png"), full_page=True)

            # 9. 提交投稿
            bilibili_logger.info(_msg("📤", "正在提交投稿"))

            # 先滚动到页面底部，确保投稿按钮可见
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)

            submitted = False
            for attempt in range(10):
                try:
                    # 用 JS 直接查找并点击"立即投稿"按钮
                    # 只匹配精确文字"立即投稿"，避免匹配左侧导航栏的"投稿"
                    clicked = await page.evaluate("""() => {
                        // 优先找"立即投稿"，其次找底部区域的投稿按钮
                        const candidates = document.querySelectorAll(
                            'button, [role="button"], [class*="submit"], [class*="publish"]'
                        );
                        // 第一轮：精确匹配"立即投稿"
                        for (const el of candidates) {
                            const text = el.textContent.trim();
                            if (text === '立即投稿') {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    el.scrollIntoView({behavior: 'instant', block: 'center'});
                                    el.click();
                                    return text;
                                }
                            }
                        }
                        // 第二轮：放宽到 button 和 role=button，匹配包含"投稿"的
                        const buttons = document.querySelectorAll('button, [role="button"]');
                        for (const el of buttons) {
                            const text = el.textContent.trim();
                            if (text === '立即投稿') {
                                el.click();
                                return text;
                            }
                        }
                        return null;
                    }""")

                    if clicked:
                        bilibili_logger.info(_msg("✅", f"已通过 JS 点击投稿按钮: {clicked}"))
                        await asyncio.sleep(3)
                    else:
                        bilibili_logger.info(_msg("🔍", f"JS 未找到投稿按钮，重试 {attempt + 1}/10"))
                        await asyncio.sleep(3)
                        continue

                    # 等待页面变化：URL 跳转 OR 按钮消失 OR 成功提示
                    current_url = page.url
                    for wait_i in range(10):
                        await asyncio.sleep(2)
                        new_url = page.url
                        # URL 变了 = 投稿成功跳转
                        if new_url != current_url:
                            bilibili_logger.success(
                                _msg("🎉", f"B站视频投稿成功，已跳转到: {new_url}")
                            )
                            submitted = True
                            break
                        # 按钮消失了 = 页面已变化（SPA 内部跳转）
                        btn_still_exists = await page.evaluate("""() => {
                            const els = document.querySelectorAll('button, [role="button"]');
                            for (const el of els) {
                                if (el.textContent.trim() === '立即投稿') return true;
                            }
                            return false;
                        }""")
                        if not btn_still_exists:
                            bilibili_logger.success(_msg("🎉", "B站视频投稿成功（投稿按钮已消失）"))
                            submitted = True
                            break
                        # 检查是否出现成功提示
                        success_el = page.locator(
                            'text=发布成功, text=投稿成功, text=提交成功'
                        ).first
                        if await success_el.count() > 0 and await success_el.is_visible():
                            bilibili_logger.success(_msg("🎉", "B站视频投稿成功"))
                            submitted = True
                            break

                    if submitted:
                        break

                    # 页面没变化，截图记录
                    bilibili_logger.info(_msg("🔄", f"点击后页面未变化，重试 {attempt + 1}/10"))
                    await page.screenshot(
                        path=str(log_dir / f"bilibili_submit_{attempt}.png"),
                        full_page=True,
                    )

                except Exception as exc:
                    bilibili_logger.info(_msg("🔄", f"提交重试 {attempt + 1}/10: {exc}"))
                    await page.screenshot(
                        path=str(log_dir / f"bilibili_submit_{attempt}.png"),
                        full_page=True,
                    )
                    await asyncio.sleep(2)

            if not submitted:
                bilibili_logger.warning(_msg("⚠️", "投稿提交未能确认成功，但可能已经提交"))

            upload_success = True
        finally:
            if upload_success:
                try:
                    await context.storage_state(path=self.account_file)
                    bilibili_logger.success(_msg("✅", "B站 cookie 已更新"))
                except Exception:
                    pass
            await context.close()
            await browser.close()
            bilibili_logger.info(_msg("✅", "浏览器已关闭"))

    async def _set_schedule_time(self, page: Page, publish_date: datetime):
        """设置定时发布（容错）"""
        bilibili_logger.info(
            _msg("⏰", f"设置定时发布: {publish_date.strftime('%Y-%m-%d %H:%M')}")
        )
        try:
            schedule_radio = page.locator(
                'label:has-text("定时发布"), '
                '[class*="radio"]:has-text("定时发布"), '
                '[class*="schedule"]'
            ).first
            await schedule_radio.wait_for(state="visible", timeout=10000)
            await schedule_radio.click()
            await asyncio.sleep(1)

            date_input = page.locator(
                'input[placeholder*="日期"], input[placeholder*="时间"], '
                '.ant-calendar-picker input, [class*="datepicker"] input'
            ).first
            if await date_input.count() > 0:
                await date_input.click()
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.type(publish_date.strftime("%Y-%m-%d %H:%M"))
                await page.keyboard.press("Enter")
        except Exception as exc:
            bilibili_logger.warning(_msg("⚠️", f"设置定时发布失败: {exc}"))

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
