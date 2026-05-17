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
from myUtils.browser import create_browser, create_context
from uploader.base_video import BaseVideoUploader
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
        browser = await create_browser(playwright, headless=LOGIN_HEADLESS)
        try:
            context = await create_context(browser, storage_state=account_file)
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
        category: int | str | None = None,
        thumbnail_path=None,
        desc: str | None = None,
        publish_strategy: str | None = None,
        ai_content: str | None = None,
        creation_declaration: str | None = None,
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
        # 解析标签：支持 "#标签1 #标签2" 或 "标签1,标签2" 或混合格式
        if isinstance(tags, str) and tags.strip():
            import re
            self.tags = [t.strip() for t in re.split(r'[,，#]', tags) if t.strip()]
        elif isinstance(tags, list):
            self.tags = tags
        else:
            self.tags = []
        self.category = category or BILIBILI_DEFAULT_TID  # int(tid) or str(中文名)
        self.thumbnail_path = thumbnail_path
        self.desc = desc or ""
        self.ai_content = ai_content or ""
        self.creation_declaration = creation_declaration or ""

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
        """设置视频分区（新版B站上传页面）"""
        if not self.category:
            return

        # 解析分区名称：支持 int(tid) 或 str(中文名)
        if isinstance(self.category, int):
            cn_name = self._TID_CN_NAME.get(self.category, None)
        else:
            cn_name = str(self.category).strip()

        bilibili_logger.info(_msg("📂", f"设置分区: category={self.category}, 中文名={cn_name}"))
        try:
            log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            if not cn_name:
                bilibili_logger.warning(_msg("⚠️", f"未知的分区: {self.category}，跳过分区设置"))
                return

            # Step 1: 点击 .select-controller 打开分区下拉框
            select_controller = page.locator('.select-controller').first
            await select_controller.wait_for(state="visible", timeout=10000)
            await select_controller.click()
            bilibili_logger.info(_msg("📂", "已点击 select-controller 打开分区下拉框"))
            await asyncio.sleep(1)

            # Step 2: 在下拉列表中点击目标分区
            # 下拉项格式: <div title="分区名" class="drop-list-v2-item">
            target_item = page.locator(f'.drop-list-v2-item[title="{cn_name}"]')
            if await target_item.count() > 0:
                await target_item.first.click()
                bilibili_logger.success(_msg("✅", f"分区已设置: {cn_name}"))
            else:
                bilibili_logger.warning(_msg("⚠️", f"下拉列表中未找到分区: {cn_name}"))
                await page.screenshot(path=str(log_dir / "bilibili_partition_not_found.png"), full_page=True)

            await asyncio.sleep(1)
            await page.screenshot(path=str(log_dir / "bilibili_partition_selected.png"), full_page=True)
        except Exception as exc:
            bilibili_logger.warning(_msg("⚠️", f"设置分区失败（不影响上传）: {exc}"))

    async def _fill_tags(self, page: Page):
        """填写视频标签"""
        if not self.tags:
            return

        bilibili_logger.info(_msg("🏷️", f"添加 {len(self.tags)} 个标签"))

        log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # 尝试多种选择器定位标签输入框
        tag_input = None
        selectors = [
            'input[placeholder*="回车键Enter创建标签"]',
            'input[placeholder*="Enter创建标签"]',
            'input[placeholder*="按回车"]',
            'input[placeholder*="标签"]',
            '.tag-input input',
            '[class*="tag"] input[type="text"]',
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    tag_input = loc
                    bilibili_logger.info(_msg("🏷️", f"找到标签输入框: {sel}"))
                    break
            except Exception:
                continue

        if tag_input is None:
            bilibili_logger.warning(_msg("⚠️", "未找到标签输入框，尝试截图调试"))
            await page.screenshot(path=str(log_dir / "bilibili_tag_input_not_found.png"), full_page=True)
            return

        for i, tag in enumerate(self.tags[:10]):
            try:
                # 每次重新定位输入框（添加标签后DOM可能变化）
                tag_input = None
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            tag_input = loc
                            break
                    except Exception:
                        continue
                if tag_input is None:
                    bilibili_logger.warning(_msg("⚠️", f"标签输入框丢失，停止添加"))
                    break

                await tag_input.click()
                await asyncio.sleep(0.3)
                await tag_input.type(str(tag), delay=50)
                await asyncio.sleep(0.3)
                await tag_input.press("Enter")
                await asyncio.sleep(0.5)
                bilibili_logger.info(_msg("🏷️", f"已添加标签 ({i+1}/{min(len(self.tags), 10)}): {tag}"))
            except Exception as exc:
                bilibili_logger.warning(_msg("⚠️", f"添加标签失败 '{tag}': {exc}"))

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

    async def _set_declaration(self, page: Page):
        """设置创作声明（如AI生成内容声明等）"""
        if not self.ai_content:
            return

        bilibili_logger.info(_msg("📋", f"设置声明与权益: {self.ai_content}"))
        try:
            log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: 点击"更多设置"展开面板
            more_settings = page.locator('span.label:has-text("更多设置")')
            if await more_settings.count() > 0 and await more_settings.first.is_visible():
                try:
                    await more_settings.first.click(timeout=5000)
                except Exception:
                    # 可能有 popover 遮挡，先按 Escape 关闭再重试
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.5)
                    await more_settings.first.click(force=True)
                bilibili_logger.info(_msg("📋", "已点击'更多设置'"))
                await asyncio.sleep(2)
            else:
                bilibili_logger.warning(_msg("⚠️", "未找到'更多设置'按钮"))
                return

            # Step 2: 点击"创作声明"选择器区域
            # 找到包含"请选择符合您视频内容的创作声明"的元素
            declaration_selector = page.locator('p.select-item-cont:has-text("请选择符合您视频内容的创作声明")')
            if await declaration_selector.count() > 0 and await declaration_selector.first.is_visible():
                await declaration_selector.first.click()
                bilibili_logger.info(_msg("📋", "已点击'创作声明'选择器"))
                await asyncio.sleep(1)
            else:
                bilibili_logger.warning(_msg("⚠️", "未找到'创作声明'选择器"))
                await page.screenshot(path=str(log_dir / "bilibili_declaration_not_found.png"), full_page=True)
                return

            # Step 3: 在展开的声明列表中，选择匹配的声明
            # 声明项的格式: "作者声明：xxx"
            # 前端传来的 ai_content 值不含"作者声明："前缀，需要匹配
            target_text = self.ai_content.strip()
            mark_items = page.locator('.mark-item')
            count = await mark_items.count()
            clicked = False
            for i in range(count):
                item = mark_items.nth(i)
                item_text = (await item.text_content() or "").strip()
                # 匹配：item_text 是 "作者声明：xxx"，target_text 是 "xxx"
                if target_text in item_text:
                    await item.click()
                    bilibili_logger.success(_msg("✅", f"已选择创作声明: {item_text}"))
                    clicked = True
                    break

            if not clicked:
                bilibili_logger.warning(_msg("⚠️", f"未找到匹配的声明: {target_text}"))
                await page.screenshot(path=str(log_dir / "bilibili_declaration_not_matched.png"), full_page=True)

            await asyncio.sleep(1)
        except Exception as exc:
            bilibili_logger.warning(_msg("⚠️", f"设置创作声明失败（不影响上传）: {exc}"))

    async def _set_creation_declaration(self, page: Page):
        """设置创作声明（bcc-select 下拉框：含AI生成内容等）
        仅部分账号会显示此下拉框，未找到时静默跳过。
        DOM: input.bcc-select-input-inner[placeholder*="创作声明"] -> li.bcc-option > span
        """
        if not self.creation_declaration:
            return

        bilibili_logger.info(_msg("📋", f"设置创作声明: {self.creation_declaration}"))
        try:
            # 先关闭可能遮挡的 popover
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            # 尝试查找创作声明下拉框（可能在主表单或"更多设置"面板内）
            select_input = page.locator('input.bcc-select-input-inner[placeholder*="创作声明"]')
            if await select_input.count() == 0:
                bilibili_logger.info(_msg("📋", "当前账号无创作声明下拉框，跳过"))
                return

            await select_input.first.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await select_input.first.click(force=True)
            bilibili_logger.info(_msg("📋", "已点击创作声明下拉框"))
            await asyncio.sleep(1)

            # 等待下拉选项出现，用 :visible 过滤隐藏的下拉列表
            await page.wait_for_selector('li.bcc-option:visible', timeout=3000)
            options = page.locator('li.bcc-option:visible')
            count = await options.count()
            bilibili_logger.info(_msg("📋", f"下拉选项数量: {count}"))

            # 在展开的下拉列表中点击匹配的 bcc-option
            target_text = self.creation_declaration.strip()
            clicked = False
            for i in range(count):
                opt = options.nth(i)
                span = opt.locator('span').first
                opt_text = (await span.text_content() or "").strip()
                if opt_text == target_text:
                    await opt.click()
                    bilibili_logger.success(_msg("✅", f"已选择创作声明: {opt_text}"))
                    clicked = True
                    break

            if not clicked:
                bilibili_logger.warning(_msg("⚠️", f"未找到匹配的创作声明选项: {target_text}"))

            await asyncio.sleep(1)
        except Exception as exc:
            bilibili_logger.warning(_msg("⚠️", f"设置创作声明失败（不影响上传）: {exc}"))

    async def _set_thumbnail(self, page: Page):
        """通过封面编辑器对话框上传封面 — 匹配B站封面编辑器 DOM"""
        if not self.thumbnail_path:
            return

        import os
        if not os.path.exists(self.thumbnail_path):
            bilibili_logger.error(_msg("❌", f"封面文件不存在: {self.thumbnail_path}"))
            return

        log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
        bilibili_logger.info(_msg("🖼️", "开始设置B站封面"))

        try:
            # Step 0: 截图记录当前页面状态
            await page.screenshot(path=str(log_dir / "bilibili_cover_before.png"), full_page=True)

            # Step 1: 打开封面编辑器弹窗 — 多种触发器尝试
            dialog_opened = False
            trigger_selectors = [
                'div.cover-item',
                '.cover-item',
                '.video-cover-container',
                '.cover-wrap',
                '.cover-add',
                '[data-reporter-id="112"]',
                '.upload-video-cover',
                'div[class*="cover"] >> text=选择封面',
                'div[class*="cover"] >> text=封面',
            ]
            for sel in trigger_selectors:
                count = await page.locator(sel).count()
                bilibili_logger.info(_msg("🔍", f"封面触发器 '{sel}': {count} 个"))
                if count > 0:
                    try:
                        await page.locator(sel).first.click(timeout=3000)
                        bilibili_logger.info(_msg("🖱️", f"已点击封面触发器: {sel}"))
                        dialog_opened = True
                        break
                    except Exception as e:
                        bilibili_logger.info(_msg("ℹ️", f"点击 '{sel}' 失败: {e}"))
                        continue

            if not dialog_opened:
                bilibili_logger.warning(_msg("⚠️", "所有封面触发器均未成功，跳过封面设置"))
                return

            # 等待封面编辑器弹窗出现（B站弹窗 DOM: div.bcc-dialog）
            dialog = page.locator('div.bcc-dialog:has-text("封面制作")').first
            await dialog.wait_for(state="visible", timeout=15000)
            bilibili_logger.info(_msg("✅", "封面编辑器弹窗已打开"))
            await asyncio.sleep(1)

            # 截图查看弹窗状态
            await page.screenshot(path=str(log_dir / "bilibili_cover_editor.png"), full_page=True)

            # Step 2: 点击4:3区域选中它（首页推荐封面）
            editor_4_3 = page.locator('div.cover-editor-panel-canvas-image.editor_4_3').first
            if await editor_4_3.count() > 0:
                await editor_4_3.click()
                bilibili_logger.info(_msg("🖼️", "已点击选中4:3封面区域"))
                await asyncio.sleep(0.5)
            else:
                bilibili_logger.warning(_msg("⚠️", "未找到4:3封面区域，继续后续步骤"))

            # Step 3: 勾选"双比例同步改动"复选框
            sync_checkbox = page.locator('.sync-checkbox input[type="checkbox"]').first
            if await sync_checkbox.count() > 0:
                is_checked = await sync_checkbox.is_checked()
                if not is_checked:
                    # 点击 label 或 checkbox 的父级来切换状态
                    sync_label = page.locator('.sync-checkbox').first
                    await sync_label.click()
                    bilibili_logger.info(_msg("✅", "已勾选'双比例同步改动'"))
                else:
                    bilibili_logger.info(_msg("✅", "'双比例同步改动'已经是勾选状态"))
                await asyncio.sleep(0.5)
            else:
                bilibili_logger.warning(_msg("⚠️", "未找到'双比例同步改动'复选框"))

            # 截图确认选择状态
            await page.screenshot(path=str(log_dir / "bilibili_cover_sync_checked.png"), full_page=True)

            # Step 4: 上传封面文件（隐藏 input 在弹窗内）
            # .cover-upload .bcc-upload-wrapper > input[type="file"]
            file_input = page.locator('.cover-upload input[type="file"]').first
            file_count = await file_input.count()
            bilibili_logger.info(_msg("🔍", f"封面文件 input: {file_count} 个"))

            if file_count > 0:
                await file_input.set_input_files(self.thumbnail_path)
                bilibili_logger.info(_msg("📤", f"已选择封面文件: {os.path.basename(self.thumbnail_path)}"))
            else:
                # 备用：查找任意 image input
                fallback_input = page.locator('input[accept*="image"]').first
                if await fallback_input.count() > 0:
                    await fallback_input.set_input_files(self.thumbnail_path)
                    bilibili_logger.info(_msg("📤", f"通过备用 input 选择封面文件"))
                else:
                    bilibili_logger.error(_msg("❌", "未找到封面文件上传 input"))
                    return

            # 等待图片上传和处理
            bilibili_logger.info(_msg("⏳", "等待封面图片上传处理..."))
            await asyncio.sleep(3)

            # Step 5: 点击弹窗内"完成"按钮
            submit_btn = page.locator('div.button.submit').first
            submit_count = await submit_btn.count()
            bilibili_logger.info(_msg("🔍", f"完成按钮: {submit_count} 个"))
            if submit_count > 0:
                await submit_btn.click()
                bilibili_logger.info(_msg("✅", "已点击完成按钮"))
            else:
                bilibili_logger.warning(_msg("⚠️", "未找到完成按钮"))
            await asyncio.sleep(1)

            # Step 6: 点击弹窗外层"确定"按钮
            confirm_btn = page.locator('button.bcc-button--primary').first
            confirm_count = await confirm_btn.count()
            bilibili_logger.info(_msg("🔍", f"确定按钮: {confirm_count} 个"))
            if confirm_count > 0:
                await confirm_btn.click()
                bilibili_logger.info(_msg("✅", "已点击确定按钮"))
            else:
                bilibili_logger.warning(_msg("⚠️", "未找到确定按钮"))
            await asyncio.sleep(1)

            # 等待弹窗关闭
            await asyncio.sleep(1)
            bilibili_logger.success(_msg("🥳", "B站封面设置完成"))

        except Exception as exc:
            # 截图用于排查
            try:
                await page.screenshot(path=str(log_dir / "bilibili_cover_error.png"), full_page=True)
            except Exception:
                pass
            bilibili_logger.error(_msg("❌", f"封面设置失败: {exc}"))
            raise RuntimeError(f"封面设置失败: {exc}")

    async def upload(self, playwright: Playwright) -> None:
        bilibili_logger.info(_msg("🔍", "上传前检查 cookie、视频文件和发布时间"))
        await self.validate_upload_args()
        bilibili_logger.info(_msg("✅", "上传前检查通过"))

        log_dir = Path(__file__).parent.parent.parent.parent / "data" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        browser = await create_browser(playwright, headless=self.headless)
        context = await create_context(browser, storage_state=self.account_file)

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

            # 8. 设置声明与权益
            await self._set_declaration(page)

            # 8.5 设置创作声明（bcc-select 下拉框）
            await self._set_creation_declaration(page)

            # 9. 设置定时发布
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
                    # 点击 <span class="submit-add" data-reporter-id="81">立即投稿</span>
                    submit_span = page.locator('span.submit-add')
                    if await submit_span.count() > 0:
                        await submit_span.first.scroll_into_view_if_needed()
                        await submit_span.first.click()
                        bilibili_logger.info(_msg("✅", "已点击立即投稿按钮"))
                    else:
                        bilibili_logger.info(_msg("🔍", f"未找到投稿按钮，重试 {attempt + 1}/10"))
                        await asyncio.sleep(3)
                        continue

                    # 等待投稿结果：检查"立即投稿"按钮是否消失
                    await asyncio.sleep(3)
                    for wait_i in range(15):
                        await asyncio.sleep(2)
                        # 检查立即投稿按钮是否已消失
                        btn_exists = await page.locator('span.submit-add').count() > 0
                        if not btn_exists:
                            bilibili_logger.success(_msg("🎉", "B站视频投稿成功（立即投稿按钮已消失）"))
                            submitted = True
                            break

                        # 同时检查URL是否已跳转
                        if page.url != BILIBILI_UPLOAD_URL and "/platform/upload/" not in page.url:
                            bilibili_logger.success(_msg("🎉", f"B站视频投稿成功，已跳转到: {page.url}"))
                            submitted = True
                            break

                    if submitted:
                        break

                    # 按钮仍在，截图记录
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

            # 提交成功后等待页面完全处理，避免过早关闭浏览器
            if submitted:
                bilibili_logger.info(_msg("⏳", "等待B站处理投稿（10秒）"))
                await asyncio.sleep(10)
                # 截图记录最终状态
                try:
                    await page.screenshot(path=str(log_dir / "bilibili_after_submit.png"), full_page=True)
                    bilibili_logger.info(_msg("📸", "投稿后截图已保存"))
                except Exception:
                    pass

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
        """设置定时发布 — 通过日历网格和时间选择面板交互"""
        bilibili_logger.info(
            _msg("⏰", f"设置定时发布: {publish_date.strftime('%Y-%m-%d %H:%M')}")
        )
        try:
            # Step 1: 点击 switch-container 开关，启用定时发布
            switch = page.locator('.switch-container').first
            await switch.wait_for(state="visible", timeout=10000)
            await switch.click()
            bilibili_logger.info(_msg("⏰", "已点击定时发布开关"))
            await asyncio.sleep(1)

            # Step 2: 打开日期选择器并选择日期
            target_day = publish_date.day
            date_trigger = page.locator('div.date-picker-date').first
            await date_trigger.wait_for(state="visible", timeout=10000)
            await date_trigger.click()
            bilibili_logger.info(_msg("📅", f"已打开日期选择器，目标日期: {target_day}号"))
            await asyncio.sleep(1)

            # 在日历网格中找到并点击目标日期（排除禁用的）
            # 可用日期: div.date-picker-body-item.date-item（不含 date-item-disabled）
            target_date_el = page.locator(
                'div.date-picker-body-item.date-item'
            ).filter(has_text=str(target_day))
            # 精确匹配：文本内容就是日期数字
            date_set = False
            count = await target_date_el.count()
            bilibili_logger.info(_msg("🔍", f"日历中找到 {count} 个匹配 '{target_day}' 的日期元素"))
            for i in range(count):
                el = target_date_el.nth(i)
                classes = await el.get_attribute("class") or ""
                if "date-item-disabled" in classes:
                    continue
                # 确认文本精确匹配（避免 "1" 匹配到 "12"）
                text = (await el.text_content() or "").strip()
                if text == str(target_day):
                    await el.click()
                    date_set = True
                    bilibili_logger.info(_msg("📅", f"已选择日期: {target_day}号"))
                    break
            if not date_set:
                bilibili_logger.warning(_msg("⚠️", f"日历中未找到可点击的日期: {target_day}号"))
            await asyncio.sleep(0.5)

            # Step 3: 打开时间选择器并选择小时和分钟
            target_hour = publish_date.strftime("%H")  # "00"-"23"
            target_minute = publish_date.strftime("%M")  # "00","05","10",...
            time_trigger = page.locator('div.date-picker-timer').first
            await time_trigger.wait_for(state="visible", timeout=10000)
            await time_trigger.click()
            bilibili_logger.info(_msg("🕐", f"已打开时间选择器，目标: {target_hour}:{target_minute}"))
            await asyncio.sleep(1)

            # 选择小时 — 第一个 .time-picker-panel-select-wrp 面板
            hour_panels = page.locator('.time-picker-panel-select-wrp')
            hour_panel = hour_panels.nth(0)
            hour_item = hour_panel.locator('span.time-picker-panel-select-item').filter(has_text=target_hour)
            hour_count = await hour_item.count()
            bilibili_logger.info(_msg("🔍", f"小时面板中找到 {hour_count} 个匹配 '{target_hour}' 的元素"))
            if hour_count > 0:
                await hour_item.first.click()
                bilibili_logger.info(_msg("🕐", f"已选择小时: {target_hour}"))
            else:
                bilibili_logger.warning(_msg("⚠️", f"未找到小时选项: {target_hour}"))
            await asyncio.sleep(0.3)

            # 选择分钟 — 第二个 .time-picker-panel-select-wrp 面板
            minute_panel = hour_panels.nth(1)
            minute_item = minute_panel.locator('span.time-picker-panel-select-item').filter(has_text=target_minute)
            minute_count = await minute_item.count()
            bilibili_logger.info(_msg("🔍", f"分钟面板中找到 {minute_count} 个匹配 '{target_minute}' 的元素"))
            if minute_count > 0:
                await minute_item.first.click()
                bilibili_logger.info(_msg("🕐", f"已选择分钟: {target_minute}"))
            else:
                bilibili_logger.warning(_msg("⚠️", f"未找到分钟选项: {target_minute}"))
            await asyncio.sleep(0.3)

            # 点击其他区域关闭时间选择器
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            bilibili_logger.success(_msg("✅", "定时发布设置完成"))
        except Exception as exc:
            bilibili_logger.warning(_msg("⚠️", f"设置定时发布失败: {exc}"))

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
