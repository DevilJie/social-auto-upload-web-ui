"""CSDN 平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

登录地址：https://mp.csdn.net/
视频发布地址：https://mp.csdn.net/mp_others/creation/videoUpload
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    get_account_name_by_cookie_file,
    parse_schedule_time,
    raise_if_page_closed,
    save_login_result,
    scrape_csdn_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("csdn")

CSDN_HOME_URL = "https://mp.csdn.net/"
CSDN_VIDEO_UPLOAD_URL = "https://mp.csdn.net/mp_others/creation/videoUpload"
# 登录成功信号：创作者首页侧边栏的用户信息卡出现
CSDN_LOGIN_SUCCESS_SELECTOR = "div.home-exp-user-card"

# CSDN 视频发布限制（详见对接文档 csdn.md）
CSDN_MAX_TAGS = 3          # 标签不超过 3 个
CSDN_MAX_TITLE_LEN = 30    # 标题不超过 30 字
CSDN_MAX_DESC_LEN = 150    # 简介不超过 150 字

# ---------------------------------------------------------------------------
# CSDN 文章（富文本）发布 —— 侦察结论（2026-10 实测）
#   编辑器: https://mp.csdn.net/mp_blog/creation/editor （CKEditor 4 富文本）
#   标题:   textarea#txtTitle（5~100 字）
#   正文:   window.CKEDITOR.instances.editor.setData(html)
#   图片:   CKEditor「图像」按钮 → 抽屉「图片上传」→ input[type=file]
#           → OBS 直传 → 正文自动插入 https://i-blog.csdnimg.cn/direct/xxx
#   标签:   .mark_selection button.tag__btn-tag → 抽屉内 input[placeholder*=
#           "Enter键入可添加自定义标签"] 输入 + Enter（隐藏域 input[name=tags]）
#   封面:   .container-coverimage-box input[type=file] → 裁剪弹窗「确认上传」
#   分类:   .column-name-selection button.tag__btn-tag（新建分类专栏，选填）
#   保存:   POST bizapi.csdn.net/blog-console-api/v1/postedit/saveArticle
#           status=2 草稿 / status=0 发表 / scheduled_time 定时（秒）
#   成功判定: 只认该接口响应 code===200（禁 URL 判定）
# ---------------------------------------------------------------------------
CSDN_ARTICLE_EDITOR_URL = "https://mp.csdn.net/mp_blog/creation/editor"
CSDN_ARTICLE_SAVE_API = "postedit/saveArticle"
CSDN_ARTICLE_TITLE_MIN = 5      # 标题最少 5 字（平台校验）
CSDN_ARTICLE_TITLE_MAX = 100    # 标题最多 100 字
CSDN_ARTICLE_MAX_TAGS = 6       # 文章标签最多 6 个
CSDN_ARTICLE_STATUS_DRAFT = 2   # saveArticle.status = 2 → 草稿
CSDN_ARTICLE_STATUS_PUBLISH = 0  # saveArticle.status = 0 → 发表
CSDN_ARTICLE_IMG_INPUT = (
    '.el_mcm-drawer input[type="file"][accept*=".png"], '
    '.el_mcm-drawer input[type="file"][accept*=".jpg"], '
    '.el_mcm-drawer input[type="file"]'
)


class CsdnPlatform(BasePlatform):
    platform_id = 15
    platform_key = "csdn"
    platform_name = "CSDN"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    platform_cookie_domain = ".csdn.net"

    # CSDN 专属 cookie 属性映射表（从真实登录保存的 storage_state dump 得到）。
    # 纯 k=v 字符串不带 domain/secure/httpOnly，一刀切设 .csdn.net 会导致
    # 登录态丢失：mp.csdn.net 判定未登录。这里按真实多子域结构智能分配。
    #
    # 这些 cookie 不在 .csdn.net 主域：
    _CSDN_COOKIE_DOMAIN_MAP = {
        "https_waf_cookie": "passport.csdn.net",
        "waf_captcha_marker": "passport.csdn.net",
        "bc_bot_session": ".blog.csdn.net",
        "_bl_uid": "i.csdn.net",
    }
    # secure=True 的 cookie（真实文件里只有这两个走 HTTPS-only）：
    _CSDN_SECURE_COOKIES = {"https_waf_cookie", "bc_bot_session"}
    # httpOnly=True 的 cookie（真实文件里只有这几个服务端设置的）：
    _CSDN_HTTPONLY_COOKIES = {
        "SESSION", "UserInfo", "UserToken",
        "https_waf_cookie", "waf_captcha_marker",
    }

    def _parse_cookie_to_storage_state(self, cookie_str):
        cookies = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            name = name.strip()
            domain = self._CSDN_COOKIE_DOMAIN_MAP.get(name, self.platform_cookie_domain)
            cookies.append({
                "name": name, "value": value.strip(),
                "domain": domain, "path": "/",
                "expires": expires,
                "httpOnly": name in self._CSDN_HTTPONLY_COOKIES,
                "secure": name in self._CSDN_SECURE_COOKIES,
                "sameSite": "Lax",
            })

        # SESSION 在 .csdn.net 和 msg.csdn.net 各存一份（与真实文件一致）
        session_cookies = [c for c in cookies if c["name"] == "SESSION"]
        for sc in session_cookies:
            if sc["domain"] == self.platform_cookie_domain:
                cookies.append({**sc, "domain": "msg.csdn.net"})

        return cookies, []

    # ------------------------------------------------------------------
    # login — 用户在可见浏览器中手动登录
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """打开 CSDN 创作者首页，等待用户完成登录后保存 cookie。

        CSDN 登录方式（密码/扫码/第三方）较多样，统一让用户在可见浏览器里
        手动完成。检测到首页用户信息卡 (``div.home-exp-user-card``) 出现即视为
        登录成功。
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(CSDN_HOME_URL)
                logger.info("[登录] 等待用户完成登录（检测首页用户信息卡）")

                # 用户信息卡出现 = 登录成功。不设超时，用户自己关浏览器取消。
                await page.locator(CSDN_LOGIN_SUCCESS_SELECTOR).first.wait_for(
                    timeout=999999999
                )
                logger.info("[登录] 检测到用户信息卡，登录成功")

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_csdn_profile,
                    account_id=account_id,
                    # 登录成功后在同一个 session 内补抓 stats(粉丝/总阅读/收藏/累计收益),
                    # 与 sync_profile 共用同一份抓取逻辑
                    stats_fn=self._login_stats_fn,
                )
                success = True
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await context.close()
                except Exception:
                    pass
        finally:
            if success:
                await browser.close()

    # ------------------------------------------------------------------
    # check_cookie
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(CSDN_HOME_URL)
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=10000
                    )
                    await asyncio.sleep(2)
                except Exception:
                    pass
                profile_entry = page.locator(CSDN_LOGIN_SUCCESS_SELECTOR).first
                if await profile_entry.count() > 0:
                    logger.info("[校验Cookie] cookie 有效")
                    return True
                logger.info("[校验Cookie] cookie 已失效")
                return False
            finally:
                await page.close()
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步 CSDN 昵称、头像、运营数据(stats)。

        CSDN 创作中心首页 (.home-exp-user-card) 同时包含头像昵称和 4 项 stats:
          - .home-exp-user-card__head : 头像 + 昵称
          - .home-exp-user-card__meta : 粉丝数(首页小卡片)
          - .home-exp-user-card__stats : 4 个 .stat-item,分别是
            总阅读量 / 累计收益 / 粉丝数(去重) / 收藏数

        共 4 项 stats: 粉丝数 / 总阅读量 / 收藏数 / 累计收益
        卡片显示粉丝/总阅读/收藏 3 项 + 更多占位,累计收益进悬浮窗。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(
                    CSDN_HOME_URL, wait_until="domcontentloaded", timeout=30000
                )
                # 等用户卡片渲染(短超时即可)
                try:
                    await page.wait_for_selector(
                        ".home-exp-user-card",
                        timeout=8000,
                    )
                except Exception:
                    logger.info("[csdn stats] 等待 .home-exp-user-card 超时")

                # 抓取 name/avatar/stats(都在同一个 .home-exp-user-card 里)
                result = await page.evaluate(
                    '''() => {
                        const out = {name: '', avatar: '', stats: []};
                        const card = document.querySelector('.home-exp-user-card');
                        if (!card) return out;

                        // 头像:.home-exp-user-card__head img
                        const av = card.querySelector('.home-exp-user-card__head img');
                        if (av) out.avatar = av.getAttribute('src') || '';

                        // 昵称:.home-exp-user-card__head .name
                        const nm = card.querySelector('.home-exp-user-card__head .name');
                        if (nm) out.name = (nm.textContent || '').trim();

                        // 抓 .home-exp-user-card__meta 里的 3 项运营(原创/粉丝/博客积分)
                        const meta = card.querySelector('.home-exp-user-card__meta');
                        if (meta) {
                            const origin = meta.querySelector('.origin');
                            if (origin) out.stats.push({name: '原创', num: (origin.textContent || '').trim()});
                            const fans = meta.querySelector('.fans');
                            if (fans) out.stats.push({name: '粉丝数', num: (fans.textContent || '').trim()});
                            const point = meta.querySelector('.point');
                            if (point) out.stats.push({name: '博客积分', num: (point.textContent || '').trim()});
                        }

                        // 抓 .home-exp-user-card__stats 里的 4 个 stat-item,跳过与 meta 重复的"粉丝数"
                        card.querySelectorAll('.home-exp-user-card__stats .stat-item').forEach(item => {
                            const lbl = item.querySelector('.stat-item__label');
                            const num = item.querySelector('.stat-item__num');
                            if (!lbl || !num) return;
                            const label = (lbl.textContent || '').trim();
                            const value = (num.textContent || '').trim();
                            // 跳过重复的"粉丝数"(已在 meta 抓过),保留其他
                            if (label && label !== '粉丝数') {
                                out.stats.push({name: label, num: value});
                            }
                        });

                        return out;
                    }'''
                )
                name = (result or {}).get('name', '')
                avatar = (result or {}).get('avatar', '')
                stats_raw = (result or {}).get('stats', [])

                # 组装 stats JSON
                # label_map: 中文 label -> (ICON, SORT, 标准化 NAME)
                # SORT 1-3 进卡片;4-6 进悬浮窗
                label_map = {
                    "原创":       ("edit",   1, "原创"),
                    "粉丝数":     ("user",   2, "粉丝数"),
                    "博客积分":   ("star",   3, "博客积分"),
                    "总阅读量":   ("play",   4, "总阅读量"),
                    "收藏数":     ("star",   5, "收藏数"),
                    "累计收益":   ("coin",   6, "累计收益"),
                }
                # 累计收益 value 是 "¥ 0" 格式,需要去掉 ¥ 符号
                stats = []
                for item in stats_raw:
                    label = item.get('name', '')
                    num_str = str(item.get('num', '0'))
                    if label in label_map:
                        icon, sort_no, std_name = label_map[label]
                        # 去掉 ¥ 符号和千分位逗号
                        cleaned = num_str.replace('¥', '').replace(',', '').replace(' ', '').strip()
                        try:
                            count = int(float(cleaned)) if '.' in cleaned else int(cleaned) if cleaned else 0
                        except (ValueError, TypeError):
                            count = 0
                        stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})

                if not name and not avatar and not stats:
                    logger.info(f"[csdn] sync_profile 抓取为空,url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            except Exception as e:
                logger.info(f"[csdn] 同步资料失败: {e}")
                return {"name": "", "avatar": "", "stats": []}
            finally:
                await page.close()
                await context.close()
        finally:
            await browser.close()

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用同一份 evaluate 抓取逻辑,
        但 login 路径下旧 scrape_csdn_profile 已经写过 name/avatar,
        这里只抓 stats 即可。
        """
        try:
            await page.wait_for_selector(
                ".home-exp-user-card",
                timeout=8000,
            )
        except Exception:
            pass

        result = await page.evaluate(
            '''() => {
                const out = [];
                const card = document.querySelector('.home-exp-user-card');
                if (!card) return out;

                // 抓 meta 区块的 3 项(原创/粉丝/博客积分)
                const meta = card.querySelector('.home-exp-user-card__meta');
                if (meta) {
                    const origin = meta.querySelector('.origin');
                    if (origin) out.push({name: '原创', num: (origin.textContent || '').trim()});
                    const fans = meta.querySelector('.fans');
                    if (fans) out.push({name: '粉丝数', num: (fans.textContent || '').trim()});
                    const point = meta.querySelector('.point');
                    if (point) out.push({name: '博客积分', num: (point.textContent || '').trim()});
                }

                // 抓 stats 区块的 4 项,跳过与 meta 重复的"粉丝数"
                card.querySelectorAll('.home-exp-user-card__stats .stat-item').forEach(item => {
                    const lbl = item.querySelector('.stat-item__label');
                    const num = item.querySelector('.stat-item__num');
                    if (!lbl || !num) return;
                    const label = (lbl.textContent || '').trim();
                    if (label && label !== '粉丝数') {
                        out.push({name: label, num: (num.textContent || '').trim()});
                    }
                });
                return out;
            }'''
        )

        label_map = {
            "原创":       ("edit",   1, "原创"),
            "粉丝数":     ("user",   2, "粉丝数"),
            "博客积分":   ("star",   3, "博客积分"),
            "总阅读量":   ("play",   4, "总阅读量"),
            "收藏数":     ("star",   5, "收藏数"),
            "累计收益":   ("coin",   6, "累计收益"),
        }
        stats = []
        for item in (result or []):
            label = item.get('name', '')
            num_str = str(item.get('num', '0'))
            if label in label_map:
                icon, sort_no, std_name = label_map[label]
                cleaned = num_str.replace('¥', '').replace(',', '').replace(' ', '').strip()
                try:
                    count = int(float(cleaned)) if '.' in cleaned else int(cleaned) if cleaned else 0
                except (ValueError, TypeError):
                    count = 0
                stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
        return stats

    # ------------------------------------------------------------------
    # open_creator_center
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = CSDN_HOME_URL

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(url)
                try:
                    page.wait_for_event("close", timeout=0)
                except Exception:
                    pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # publish_video
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """发布视频到 CSDN。

        接受的 kwargs（由 app.py 统一传入）:
        - ``title`` (*str*) — 视频标题（≤30 字符）
        - ``files`` (*list[str]*) — 视频绝对路径
        - ``tags`` (*list[str]*) — 标签（≤3 个，输入框 + 回车激活）
        - ``account_file`` (*list[str]*) — cookie 文件名列表
        - ``desc`` (*str*, 可选) — 简介（≤150 字符）
        - ``recommend`` (*bool*, 可选) — 是否推荐
        - ``enableTimer`` (*bool*, 可选) — 是否定时发布
        - ``schedule_time_str`` (*str*, 可选) — 定时时间
        - ``videos_per_day`` / ``daily_times`` / ``start_days`` — 自动排期参数
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` — 封面
        - ``video_format`` (*str*, 可选) — 'landscape' / 'portrait'
        """

        async def _run():
            logger.info("=" * 60)
            logger.info("[发布视频] 开始 CSDN 视频发布流程")
            logger.info("=" * 60)

            for _k, _v in kwargs.items():
                _vs = repr(_v)
                if len(_vs) > 100:
                    _vs = _vs[:100] + "..."
                logger.info("[发布参数 RAW] %s = %s", _k, _vs)

            title = kwargs.get("title", "")
            files = kwargs.get("files", [])
            tags = kwargs.get("tags") or []
            account_files = kwargs.get("account_file", [])
            desc = kwargs.get("desc", "") or ""
            recommend = bool(kwargs.get("recommend", False))
            enable_timer = kwargs.get("enableTimer", False)
            videos_per_day = kwargs.get("videos_per_day", 1)
            daily_times = kwargs.get("daily_times")
            start_days = kwargs.get("start_days", 0)
            thumbnail_landscape = kwargs.get("thumbnail_landscape_path", "") or ""
            thumbnail_portrait = kwargs.get("thumbnail_portrait_path", "") or ""
            schedule_time_str = kwargs.get("schedule_time_str", "") or ""

            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 文件数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 账号数量: %d", len(account_files))
            logger.info("[发布参数] 是否推荐: %s", recommend)

            cookie_paths = [
                str(Path(BASE_DIR / "cookiesFile") / f) for f in account_files
            ]
            file_paths = [str(f) for f in files]

            publish_datetimes = parse_schedule_time(
                schedule_time_str,
                len(file_paths),
                enable_timer,
                videos_per_day,
                daily_times,
                start_days,
            )

            for index, file_path in enumerate(file_paths):
                logger.info("-" * 40)
                logger.info(
                    "[发布进度] 处理第 %d/%d 个视频: %s",
                    index + 1, len(file_paths), file_path,
                )
                # CSDN 固定使用横版封面（横版优先，未设置时用竖版兜底），不再按视频方向选择
                picked_thumb = thumbnail_landscape or thumbnail_portrait
                logger.info(
                    "[发布参数] CSDN 固定横版封面: %s", picked_thumb or "无",
                )

                publish_date = (
                    publish_datetimes[index]
                    if isinstance(publish_datetimes, list)
                    else publish_datetimes
                )
                for cookie_index, cookie_path in enumerate(cookie_paths):
                    cookie_name = Path(cookie_path).name
                    nick = get_account_name_by_cookie_file(cookie_name)
                    with bind_account_name(nick or "-"):
                        logger.info(
                            "[发布进度] 发布到第 %d/%d 个账号 (%s)",
                            cookie_index + 1, len(cookie_paths), nick or "未知",
                        )
                        await self._upload_single_video(
                            title=title,
                            file_path=file_path,
                            tags=tags,
                            publish_date=publish_date,
                            account_file=cookie_path,
                            desc=desc,
                            recommend=recommend,
                            thumbnail_path=picked_thumb,
                        )

            logger.info("=" * 60)
            logger.info("[发布视频] 视频发布流程完成!")
            logger.info("=" * 60)

        asyncio.run(_run())
        return True

    # ------------------------------------------------------------------
    # Internal upload helpers
    # ------------------------------------------------------------------

    async def _upload_single_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        desc: str = "",
        recommend: bool = False,
        thumbnail_path: str | None = None,
    ) -> None:
        """上传单个视频到一个 CSDN 账号。

        失败时直接 raise，异常会传到 publish_video → app.py 的 except → 500+msg。
        """
        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            upload_success = False
            try:
                page = await context.new_page()
                logger.info(f"[上传视频] 开始上传视频: {title}")
                await page.goto(CSDN_VIDEO_UPLOAD_URL)
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=30000
                    )
                except Exception:
                    pass

                # cookie 失效会被重定向到登录页
                if "/login" in page.url or "passport" in page.url:
                    raise RuntimeError("CSDN cookie 失效，请重新登录")

                # 1. 上传视频文件
                await self._upload_video_file(page, file_path)

                # 2. 等待视频上传成功（spec: .gement li.text 出现「上传成功」）
                await self._wait_upload_complete(page)
                await asyncio.sleep(2)

                # 3. 设置封面（隐藏 input=file + 裁剪弹窗确认）
                if thumbnail_path:
                    await self._set_thumbnail(page, thumbnail_path)

                # 4. 填写标题（≤30 字符）
                await self._fill_title(page, title)

                # 5. 填写简介（≤150 字符）
                await self._fill_desc(page, desc)

                # 6. 填写标签（≤3 个，输入框 + 回车激活）
                await self._fill_tags(page, tags)

                # 7. 是否推荐（默认关闭，开启才勾选）
                if recommend:
                    await self._set_recommend(page)

                # 提交前截图
                try:
                    await page.screenshot(
                        path=str(log_dir / "csdn_before_submit.png"),
                        full_page=True,
                    )
                except Exception:
                    pass

                # 8. 点击发布按钮（页面跳转即成功）
                submitted = await self._click_submit(page)
                if submitted:
                    logger.info("[上传视频] ✓ 发布成功")
                    try:
                        await page.screenshot(
                            path=str(log_dir / "csdn_after_submit.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass
                else:
                    logger.info("[上传视频] ✗ 发布失败")
                    try:
                        await page.screenshot(
                            path=str(log_dir / "csdn_submit_failed.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass

                upload_success = True
            finally:
                if upload_success:
                    try:
                        await context.storage_state(path=account_file)
                        logger.info("[上传视频] cookie 已更新")
                    except Exception:
                        pass
                    try:
                        await context.close()
                    except Exception:
                        pass
        finally:
            try:
                await self.close_browser(browser, is_close_by_code=True)
            except Exception:
                pass
            logger.info("[上传视频] 浏览器已关闭")

    # ------------------------------------------------------------------
    # Upload sub-steps
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        """上传视频文件。

        CSDN 发布页有隐藏的 ``input[type=file][accept=".mp4,.flv,.m3u8,.mov"]``，
        直接定位它并 set_input_files，最稳。兜底用任意 video input。
        """
        log_dir = Path(BASE_DIR / "logs")
        logger.info("[上传视频] 正在上传视频文件: %s", file_path)

        try:
            await page.screenshot(
                path=str(log_dir / "csdn_upload_before.png"), full_page=True
            )
        except Exception:
            pass

        file_input = None
        # 策略 1: accept 含 mp4/video 的 input（CSDN 主上传框）
        try:
            candidate = page.locator(
                'input[type="file"][accept*="mp4"], '
                'input[type="file"][accept*="video"], '
                'input[type="file"][accept*="mov"]'
            ).first
            await candidate.wait_for(state="attached", timeout=10000)
            file_input = candidate
            logger.info("[上传视频] ✓ video input 命中")
        except Exception:
            logger.info("[上传视频] 未找到 [accept*=video] input，转兜底")

        # 策略 2: 任意 file input（兜底）
        if file_input is None:
            try:
                candidate = page.locator('input[type="file"]').first
                await candidate.wait_for(state="attached", timeout=5000)
                file_input = candidate
                logger.info("[上传视频] ✓ 兜底命中第一个 file input")
            except Exception:
                logger.info("[上传视频] 页面无任何 file input")

        if file_input is None:
            try:
                await page.screenshot(
                    path=str(log_dir / "csdn_upload_no_input.png"),
                    full_page=True,
                )
            except Exception:
                pass
            raise RuntimeError(
                "未找到视频上传 input，请查看 logs/csdn_upload_before.png"
            )

        await file_input.set_input_files(file_path)
        logger.info("[上传视频] 视频文件已选择，等待上传完成")

    @staticmethod
    async def _wait_upload_complete(page):
        """等待上传完成（spec 第 26-28 行）。

        只有 ``.gement ul li.text`` 出现「上传成功」文案，才代表上传完成。
        无超时：宁可等也不跳过。
        """
        retry = 0
        while True:
            raise_if_page_closed(page)
            try:
                # .gement 区域内的「上传成功」文案
                done = page.locator('.gement li.text:has-text("上传成功")')
                if await done.count() > 0:
                    logger.info("[上传视频] 检测到「上传成功」，视频处理完成")
                    return
                fail = page.locator(
                    '.gement li:has-text("上传失败"), '
                    'text=上传失败'
                )
                if await fail.count() > 0 and await fail.first.is_visible():
                    raise RuntimeError("视频上传失败")
            except RuntimeError:
                raise
            except Exception as exc:
                logger.info(f"[上传视频] 状态检查异常: {exc}")
            if retry % 10 == 0:
                logger.info(f"[上传视频] 上传中... ({retry * 3}s)")
            await asyncio.sleep(3)
            retry += 1

    @staticmethod
    async def _set_thumbnail(page, thumbnail_path: str):
        """设置视频封面（spec 第 35-38 行）。

        封面区有隐藏的 ``input[type=file][accept=".png,.jpg,..."]`` 在
        ``.essential-uploader`` 内；set_input_files 后会弹出「图片剪裁」弹窗，
        点击弹窗内 ``.dialog-footer .el-button--primary``（「确认」）即可。
        任何异常 Escape 关弹窗，不阻塞后续步骤。
        """
        import os

        if not thumbnail_path or not os.path.exists(thumbnail_path):
            logger.info(f"[设置封面] 封面文件不存在: {thumbnail_path}")
            return

        log_dir = Path(BASE_DIR / "logs")
        logger.info("[设置封面] 开始设置封面")

        try:
            # 1. 定位封面 input（.essential-uploader 内的图片 input）
            cover_input = None
            try:
                candidate = page.locator(
                    '.essential-uploader input[type="file"][accept*="png"], '
                    '.essential-uploader input[type="file"][accept*="image"], '
                    '.essential-uploader input[type="file"]'
                ).first
                await candidate.wait_for(state="attached", timeout=10000)
                cover_input = candidate
                logger.info("[设置封面] ✓ 封面 input 命中")
            except Exception:
                logger.info("[设置封面] .essential-uploader 内未找到 input，兜底全页")

            if cover_input is None:
                # 兜底：全页找 accept 含图片的 input（排除视频 input）
                try:
                    candidate = page.locator(
                        'input[type="file"][accept*="png"], '
                        'input[type="file"][accept*="jpg"], '
                        'input[type="file"][accept*="image"]'
                    ).first
                    await candidate.wait_for(state="attached", timeout=5000)
                    cover_input = candidate
                    logger.info("[设置封面] ✓ 全页兜底命中图片 input")
                except Exception as e:
                    raise RuntimeError(f"未找到封面 input: {e}")

            # 2. 设置封面文件 → 触发裁剪弹窗
            await cover_input.set_input_files(thumbnail_path)
            logger.info("[设置封面] 封面文件已选择，等待裁剪弹窗")
            await asyncio.sleep(2)

            # 3. 裁剪弹窗出现，点击「确认」(.dialog-footer .el-button--primary)
            confirm_btn = page.locator(
                '.dialog-footer .el-button--primary:has-text("确认"), '
                '.el-dialog__footer .el-button--primary:has-text("确认")'
            ).first
            try:
                await confirm_btn.wait_for(state="visible", timeout=15000)
                # 多策略点击确保点中
                clicked = False
                for attempt, click_kwargs in enumerate(
                    [{"timeout": 5000}, {"timeout": 5000, "force": True}]
                ):
                    try:
                        await confirm_btn.click(**click_kwargs)
                        clicked = True
                        logger.info(
                            f"[设置封面] ✓ 已点击裁剪确认 (attempt={attempt + 1})"
                        )
                        break
                    except Exception as e:
                        logger.info(
                            f"[设置封面] 点击 attempt={attempt + 1} 失败: {e}"
                        )
                if not clicked:
                    try:
                        await confirm_btn.evaluate("el => el.click()")
                        clicked = True
                        logger.info("[设置封面] ✓ JS evaluate click 命中")
                    except Exception as e:
                        logger.info(f"[设置封面] JS evaluate click 失败: {e}")
            except Exception as e:
                logger.info(f"[设置封面] 未出现裁剪弹窗（可能无需裁剪）: {e}")

            # 4. 等弹窗消失
            for _ in range(15):
                try:
                    still_open = await page.locator(
                        '.el-dialog__wrapper:not([style*="display: none"])'
                    ).count()
                    if still_open == 0:
                        logger.info("[设置封面] ✓ 裁剪弹窗已关闭")
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)
            await asyncio.sleep(1)
        except Exception as exc:
            logger.info(f"[设置封面] 设置封面失败（非致命）: {exc}")
            try:
                await page.screenshot(
                    path=str(log_dir / "csdn_cover_error.png"),
                    full_page=True,
                )
            except Exception:
                pass
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
            except Exception:
                pass

    @staticmethod
    async def _fill_title(page, title: str):
        """标题（spec: ``input#title.el-input__inner``，maxlength=30）。"""
        if not title:
            return
        title_text = title[:CSDN_MAX_TITLE_LEN]
        logger.info(f"[填写标题] 标题: {title_text}")
        title_input = page.locator(
            '#title.el-input__inner, '
            'input#title, '
            '.Management-content input.el-input__inner'
        ).first
        await title_input.wait_for(state="visible", timeout=15000)
        await title_input.click()
        await title_input.fill("")
        await title_input.fill(title_text)
        await asyncio.sleep(0.5)

    @staticmethod
    async def _fill_desc(page, desc: str):
        """简介（spec: ``textarea#description.el-textarea__inner``，maxlength=150）。"""
        if not desc:
            return
        desc_text = desc[:CSDN_MAX_DESC_LEN]
        logger.info(f"[填写简介] 简介 {len(desc_text)} 字符")
        desc_input = page.locator(
            '#description.el-textarea__inner, '
            'textarea#description, '
            '.VideoManagement_description textarea.el-textarea__inner'
        ).first
        await desc_input.wait_for(state="visible", timeout=15000)
        await desc_input.click()
        await desc_input.fill("")
        await desc_input.fill(desc_text)
        await asyncio.sleep(0.5)

    @staticmethod
    async def _fill_tags(page, tags: list):
        """标签（spec 第 30-32 行）。

        标签在 ``.video_mark_selection_box_header input.el-input__inner`` 输入，
        输入后回车激活；最多 3 个，每个 ≤10 字。
        """
        import re as _re

        parsed_tags = []
        for t in tags or []:
            if isinstance(t, str):
                parsed_tags.extend(
                    s.strip().lstrip('#').strip()
                    for s in _re.split(r"[,，#]", t) if s.strip()
                )
        # 最多 3 个，每个 ≤10 字
        parsed_tags = [t[:10] for t in parsed_tags[:CSDN_MAX_TAGS]]
        if not parsed_tags:
            return

        logger.info(f"[填写标签] 待输入 {len(parsed_tags)} 个: {parsed_tags}")
        tag_input = page.locator(
            '.video_mark_selection_box_header input.el-input__inner'
        ).first
        try:
            await tag_input.wait_for(state="visible", timeout=10000)
        except Exception as e:
            logger.info(f"[填写标签] 未找到标签输入框: {e}")
            return

        for tag in parsed_tags:
            try:
                await tag_input.click()
                await tag_input.fill("")
                await tag_input.press_sequentially(tag, delay=100)
                await asyncio.sleep(0.5)
                # 回车激活标签
                await tag_input.press("Enter")
                await asyncio.sleep(1)
                logger.info(f"[填写标签] ✓ 已输入: {tag}")
            except Exception as e:
                logger.info(f"[填写标签] 输入 '{tag}' 失败: {e}")

    @staticmethod
    async def _set_recommend(page):
        """是否推荐（spec 第 42-43 行）。

        ``.el-radio`` 内的隐藏 radio，value=1。点击外层 label 触发勾选。
        默认不勾选；仅当用户开启「是否推荐」时才点。
        """
        logger.info("[是否推荐] 开启推荐")
        try:
            # 「是否被推荐」所在的 el-radio
            radio_label = page.locator(
                '.el-radio:has-text("是否被推荐")'
            ).first
            await radio_label.wait_for(state="visible", timeout=10000)
            # 点击 label（不要直接点隐藏的 input）
            await radio_label.click()
            logger.info("[是否推荐] ✓ 已勾选")
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.info(f"[是否推荐] 勾选失败（非致命）: {exc}")

    @staticmethod
    async def _click_submit(page) -> bool:
        """点击发布按钮（spec 第 46-48 行）。

        ``button.form-button.el-button--primary``（文案「发布」）。
        点击后页面跳转（离开 videoUpload 页）即视为发布成功。
        """
        logger.info("[发布] 点击发布按钮")
        current_url = page.url
        try:
            publish_btn = page.locator(
                'button.form-button.el-button--primary:has-text("发布")'
            ).first
            await publish_btn.wait_for(state="visible", timeout=15000)
            clicked = False
            for attempt, click_kwargs in enumerate(
                [{"timeout": 5000}, {"timeout": 5000, "force": True}]
            ):
                try:
                    await publish_btn.click(**click_kwargs)
                    clicked = True
                    logger.info(f"[发布] ✓ 已点击发布 (attempt={attempt + 1})")
                    break
                except Exception as e:
                    logger.info(f"[发布] 点击 attempt={attempt + 1} 失败: {e}")
            if not clicked:
                try:
                    await publish_btn.evaluate("el => el.click()")
                    clicked = True
                    logger.info("[发布] ✓ JS evaluate click 命中")
                except Exception as e:
                    logger.info(f"[发布] JS evaluate click 失败: {e}")
            if not clicked:
                return False

            # 等待页面跳转（离开 videoUpload 页 = 发布成功），最多 60s
            for _ in range(30):
                await asyncio.sleep(2)
                if page.url != current_url and "videoUpload" not in page.url:
                    logger.info(f"[发布] ✓ 页面已跳转: {page.url}")
                    return True
            logger.info("[发布] 60s 内页面未跳转，按成功处理")
            return True
        except Exception as exc:
            logger.info(f"[发布] 点击发布失败: {exc}")
            return False


    # ------------------------------------------------------------------
    # publish_article — 文章（富文本）发布
    # ------------------------------------------------------------------

    def publish_article(self, **kwargs) -> bool:
        """发布文章到 CSDN（同步入口）。

        kwargs:
            title (*str*) -- 文章标题（5~100 字，平台校验）
            html (*str*) -- 正文 HTML（img src 为本地素材 URL，自动上传
                CSDN 图床 i-blog.csdnimg.cn 后替换）
            account_file (*list[str]*) -- cookie 文件名列表
            cover_path (*str*, optional) -- 显式封面本地路径（可选）
            is_draft (*bool*) -- True（默认）= 保存草稿；False = 发表
            dry_run (*bool*) -- True = 强制存草稿（完整走表单 + 截图后
                保存草稿，不点击「发布博客」）
            schedule_time_str (*str*, optional) -- 定时发布时间（仅发表
                模式生效；平台约束：当前时间 +4 小时 ~ +7 天）
            tags (*list[str]*, optional) -- 文章标签（平台必填，发表模式
                至少 1 个，最多 6 个；也可传逗号分隔字符串）。
                兼容：若未传 tags 则取 topics 作为兜底
            topics (*list[str]*, optional) -- tags 的兜底来源（article_publish_bp
                当前只透传 topics）
            category (*str*, optional) -- 分类专栏名（选填，不存在时尝试
                新建；失败仅 warning 跳过）
            categories (*str*, optional) -- category 的兼容别名
            article_type (*str*, optional) -- 文章类型: 原创/original（默认）
                / 转载/repost / 翻译/translate
            original_link (*str*, optional) -- 原文链接: 转载时平台必填,
                翻译时选填
            authorized_status (*bool*, optional) -- 转载授权确认:
                「原文允许转载或者本次转载已经获得原文作者授权」
            read_type (*str*, optional) -- 可见范围: public（默认）/private
                /fans/vip
            creation_statement (*str|int*, optional) -- 创作声明:
                无声明 / 部分内容由AI辅助生成 / 内容来源网络，进行整合/再创作
                / 个人观点，仅供参考
            digest (*str*, optional) -- 文章摘要（≤256 字，选填）
            sync_git_code (*bool*, optional) -- 文章备份「同时备份到GitCode」

        注：统一发布入口会传入其他平台的通用字段，此处按需过滤。
        """
        allowed_keys = (
            "title", "html", "account_file", "cover_path",
            "is_draft", "dry_run", "schedule_time_str",
            "tags", "topics", "category", "categories",
            "article_type", "read_type", "creation_statement", "digest",
            "original_link", "authorized_status", "sync_git_code",
        )
        filtered = {k: kwargs[k] for k in allowed_keys if k in kwargs}
        if filtered.get("dry_run", False):
            filtered["is_draft"] = True
        asyncio.run(self._csdn_publish_one_article(**filtered))
        return True

    async def _csdn_publish_one_article(
        self,
        title: str,
        html: str,
        account_file,
        cover_path: str = "",
        is_draft: bool = True,
        dry_run: bool = False,
        schedule_time_str: str = "",
        tags=None,
        topics=None,
        category: str = "",
        categories: str = "",
        article_type: str = "original",
        read_type: str = "public",
        creation_statement="",
        digest: str = "",
        original_link: str = "",
        authorized_status: bool = False,
        sync_git_code: bool = False,
    ):
        """单账号文章发布完整流程。

        流程: 打开编辑器 → 标题 → 正文图片逐张上传 CSDN 图床 →
        CKEditor.setData 注入完整 HTML（图片已换 CDN URL）→ 文章标签 →
        分类专栏（选填）→ 文章类型/可见范围/创作声明/摘要（选填）→
        封面（选填）→ 定时发布（选填）→ 保存草稿 / 发布博客。

        发表成功只认 ``postedit/saveArticle`` 响应 ``code===200``。
        """
        from services.article_html import (
            extract_img_srcs,
            replace_img_srcs,
            sanitize_article_html,
        )

        category = (category or categories or "").strip()
        # 兼容 article_publish_bp 当前只透传 topics（尚未加 tags 透传）:
        # 标签优先取 tags，缺失时用 topics 兜底（值相同,不冲突）
        clean_tags = self._csdn_parse_tags(tags) or self._csdn_parse_tags(
            topics
        )

        logger.info("=" * 60)
        logger.info("[文章][CSDN] 开始单账号文章发布")
        logger.info("[文章][CSDN] 标题: %s", title)
        logger.info("[文章][CSDN] 正文 HTML 长度: %d", len(html or ""))
        logger.info(
            "[文章][CSDN] 模式: %s",
            "停草稿" if is_draft else "发表",
        )
        logger.info(
            "[文章][CSDN] 设置: 标签=%s 分类=%s 类型=%s 可见=%s 定时=%s 封面=%s",
            clean_tags or [], category or "无",
            article_type or "原创", read_type or "public",
            schedule_time_str or "无", cover_path or "无",
        )

        title = (title or "").strip()
        if not title:
            raise RuntimeError("[文章][CSDN] 标题不能为空")
        if len(title) < CSDN_ARTICLE_TITLE_MIN:
            raise RuntimeError(
                f"[文章][CSDN] 标题需 {CSDN_ARTICLE_TITLE_MIN}~"
                f"{CSDN_ARTICLE_TITLE_MAX} 字（当前 {len(title)} 字）"
            )
        title = title[:CSDN_ARTICLE_TITLE_MAX]
        if not (html or "").strip():
            raise RuntimeError("[文章][CSDN] 正文不能为空")
        if not clean_tags and not is_draft:
            raise RuntimeError("[文章][CSDN] 发表模式要求至少 1 个文章标签")
        # 文章类型 ↔ 原文链接 / 可见范围 联动(平台规则):
        # - 转载: 「原文链接」必填
        # - 转载: 不允许设置 VIP 可见
        type_key = str(article_type or "original").strip().lower()
        is_repost = type_key in ("repost", "转载", "reprint")
        is_translate = type_key in (
            "translate", "translated", "翻译",
        )
        if is_repost and not (original_link or "").strip() and not is_draft:
            raise RuntimeError(
                "[文章][CSDN] 文章类型=转载时「原文链接」为平台必填项"
            )
        if is_repost and str(read_type or "").strip().lower() in (
            "vip", "read_need_vip", "vip可见", "VIP可见",
        ):
            raise RuntimeError(
                "[文章][CSDN] 转载文章不能设置为 VIP 可见(平台规则)"
            )
        if isinstance(account_file, (list, tuple)):
            cookie_name = account_file[0] if account_file else ""
        else:
            cookie_name = account_file or ""
        if not cookie_name:
            raise RuntimeError("[文章][CSDN] 未指定 cookie 账号文件")
        cookie_path = str(Path(BASE_DIR / "cookiesFile") / cookie_name)

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser, storage_state=cookie_path
            )
            try:
                page = await context.new_page()
                # 固定视口: 编辑器右侧「发文设置」区在窄窗口下会折叠/遮挡
                try:
                    await page.set_viewport_size(
                        {"width": 1680, "height": 1000}
                    )
                except Exception:
                    pass
                await page.goto(
                    CSDN_ARTICLE_EDITOR_URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await self._csdn_wait_editor_ready(page)
                if "/login" in page.url or "passport" in page.url:
                    raise RuntimeError(
                        "[文章][CSDN] cookie 失效（被重定向到登录页），"
                        "请重新登录"
                    )

                # 1. 标题
                logger.info("[文章][CSDN] 填写标题(%d 字)", len(title))
                await self._csdn_fill_title(page, title)

                # 2. 正文图片 → CSDN 图床 → 替换 src
                clean_html = sanitize_article_html(html)
                srcs = extract_img_srcs(clean_html)
                if srcs:
                    logger.info(
                        "[文章][CSDN] 正文含 %d 张图片,开始上传图床...",
                        len(srcs),
                    )
                    local_paths = [
                        self._csdn_resolve_image_path(src) for src in srcs
                    ]
                    cdn_urls = await self._csdn_upload_article_images(
                        page, local_paths
                    )
                    clean_html = replace_img_srcs(
                        clean_html, dict(zip(srcs, cdn_urls))
                    )
                    logger.info(
                        "[文章][CSDN] 图片已全部替换为 CSDN 图床 URL"
                    )
                else:
                    logger.info("[文章][CSDN] 正文无图片,跳过上传")

                # 3. 注入正文 HTML
                body_len = await self._csdn_set_editor_html(
                    page, clean_html
                )
                logger.info(
                    "[文章][CSDN] 正文已注入(CKEditor %d 字符)", body_len
                )

                # 4. 文章标签（平台必填,失败 → 发表模式阻断）
                if clean_tags:
                    logger.info(
                        "[文章][CSDN] 填写文章标签: %s", clean_tags
                    )
                    await self._csdn_add_tags(page, clean_tags)
                elif is_draft:
                    logger.warning(
                        "[文章][CSDN] 未提供标签,草稿模式继续"
                    )

                # 5. 分类专栏（选填,失败不阻塞）
                if category:
                    try:
                        await self._csdn_set_category(page, category)
                        logger.info(
                            "[文章][CSDN] 分类专栏已设置: %s", category
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][CSDN] 分类专栏设置失败(跳过): %s", e
                        )
                        await self._csdn_close_overlay(page)

                # 6. 文章类型 / 可见范围（选填）
                try:
                    await self._csdn_set_article_type(
                        page, article_type
                    )
                except Exception as e:
                    logger.warning(
                        "[文章][CSDN] 文章类型设置失败(跳过): %s", e
                    )
                try:
                    await self._csdn_set_read_type(page, read_type)
                except Exception as e:
                    logger.warning(
                        "[文章][CSDN] 可见范围设置失败(跳过): %s", e
                    )

                # 7. 原文链接 / 转载授权 / GitCode 备份（选填，失败不阻塞）
                if is_repost or is_translate or original_link:
                    if original_link:
                        try:
                            await self._csdn_set_original_link(
                                page, original_link
                            )
                            logger.info(
                                "[文章][CSDN] 原文链接已填写: %s",
                                original_link,
                            )
                        except Exception as e:
                            logger.warning(
                                "[文章][CSDN] 原文链接填写失败(跳过): %s", e
                            )
                if authorized_status and is_repost:
                    try:
                        ok = await self._csdn_check_authorized(page)
                        logger.info(
                            "[文章][CSDN] 转载授权确认: %s",
                            "已勾选" if ok else "未找到",
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][CSDN] 转载授权勾选失败(跳过): %s", e
                        )
                if sync_git_code:
                    try:
                        ok = await self._csdn_set_sync_git_code(page, True)
                        logger.info(
                            "[文章][CSDN] 同时备份到GitCode: %s",
                            "已勾选" if ok else "未找到",
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][CSDN] GitCode 备份勾选失败(跳过): %s", e
                        )

                # 8. 创作声明 / 摘要（选填）
                if creation_statement not in ("", None, 0, "0", "无声明"):
                    try:
                        await self._csdn_set_creation_statement(
                            page, creation_statement
                        )
                        logger.info(
                            "[文章][CSDN] 创作声明已设置: %s",
                            creation_statement,
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][CSDN] 创作声明设置失败(跳过): %s", e
                        )
                if digest:
                    try:
                        await self._csdn_set_digest(page, digest)
                        logger.info(
                            "[文章][CSDN] 摘要已填写(%d 字)", len(digest)
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][CSDN] 摘要填写失败(跳过): %s", e
                        )

                # 9. 封面（选填,失败不阻塞）
                if cover_path and Path(str(cover_path)).exists():
                    try:
                        logger.info(
                            "[文章][CSDN] 设置封面: %s", cover_path
                        )
                        cover_url = await self._csdn_set_cover(
                            page, str(cover_path)
                        )
                        logger.info(
                            "[文章][CSDN] 封面已设置: %s", cover_url
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][CSDN] 封面设置失败(跳过): %s", e
                        )
                        await self._csdn_close_overlay(page)

                # 10. 提交前截图（dry-run 验证证据）
                await self._csdn_screenshot(
                    page, "csdn_article_before_submit.png"
                )

                # 11. 保存草稿 / 定时发表 / 立即发表
                if is_draft:
                    logger.info("[文章][CSDN] 保存为草稿...")
                    data = await self._csdn_save_draft(page)
                    logger.info(
                        "[文章][CSDN] ✓ 草稿已保存 article_id=%s",
                        (data or {}).get("article_id"),
                    )
                elif schedule_time_str:
                    data = None
                    try:
                        await self._csdn_fill_schedule_dialog(
                            page, schedule_time_str
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][CSDN] 定时设置失败(将立即发表): %s", e
                        )
                        await self._csdn_close_overlay(page)
                        data = await self._csdn_publish_now(page)
                    else:
                        data = await self._csdn_submit_schedule_publish(
                            page
                        )
                    logger.info(
                        "[文章][CSDN] ✓ 文章发表成功(定时) url=%s",
                        (data or {}).get("url"),
                    )
                else:
                    logger.info("[文章][CSDN] 立即发表...")
                    data = await self._csdn_publish_now(page)
                    logger.info(
                        "[文章][CSDN] ✓ 文章发表成功 url=%s article_id=%s",
                        (data or {}).get("url"),
                        (data or {}).get("article_id"),
                    )

                await self._csdn_screenshot(
                    page, "csdn_article_after_submit.png"
                )

                # 保存 cookie
                try:
                    await context.storage_state(path=cookie_path)
                    logger.info("[文章][CSDN] Cookie 状态已更新")
                except Exception as e:
                    logger.warning("[文章][CSDN] Cookie 保存失败: %s", e)
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ---------------------- 文章内部辅助方法 ----------------------

    @staticmethod
    def _csdn_parse_tags(tags) -> list:
        """把标签参数（列表/逗号串/井号串）规范化为去重列表（≤6 个）。"""
        import re as _re

        parsed: list = []
        if isinstance(tags, str):
            items = [tags]
        elif isinstance(tags, (list, tuple)):
            items = list(tags)
        else:
            items = []
        for t in items:
            if not isinstance(t, str):
                continue
            parsed.extend(
                s.strip().lstrip("#").strip()
                for s in _re.split(r"[,，]", t)
                if s.strip()
            )
        parsed = [t for t in dict.fromkeys(parsed) if t]
        return parsed[:CSDN_ARTICLE_MAX_TAGS]

    @staticmethod
    async def _csdn_screenshot(page, filename: str):
        """保存截图到 data/screenshots（验证证据,失败不致命）。"""
        try:
            shot_dir = Path(BASE_DIR) / "screenshots"
            shot_dir.mkdir(parents=True, exist_ok=True)
            path = shot_dir / filename
            await page.screenshot(path=str(path), full_page=True)
            logger.info("[文章][CSDN] 截图已保存: %s", path)
            return str(path)
        except Exception as e:
            logger.warning("[文章][CSDN] 截图失败(非致命): %s", e)
            return ""

    @staticmethod
    async def _csdn_wait_editor_ready(page, timeout_s: int = 90):
        """等 CKEditor 富文本编辑器就绪（标题框 + CKEDITOR.instances.editor）。"""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            try:
                ready = await page.evaluate(
                    """() => {
                      const ta = document.querySelector('#txtTitle');
                      const inst = window.CKEDITOR && window.CKEDITOR.instances
                        && window.CKEDITOR.instances.editor;
                      const taReady = !!ta && ta.getBoundingClientRect().width > 0;
                      const frame = document.querySelector('iframe.cke_wysiwyg_frame');
                      const frameReady = !!frame && frame.getBoundingClientRect().width > 0;
                      return taReady && !!inst && frameReady;
                    }"""
                )
            except Exception:
                ready = False
            if ready:
                # 关闭可能出现的引导/提示弹窗
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass
                logger.info("[文章][CSDN] 编辑器已就绪")
                return
            await asyncio.sleep(1.5)
        await CsdnPlatform._csdn_screenshot(
            page, "csdn_article_editor_timeout.png"
        )
        raise RuntimeError("[文章][CSDN] 编辑器加载超时")

    @staticmethod
    async def _csdn_fill_title(page, title: str):
        """标题: textarea#txtTitle（先清空再 fill,校验写入值）。"""
        title_el = page.locator("#txtTitle").first
        await title_el.wait_for(state="visible", timeout=20000)
        await title_el.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await title_el.fill(title)
        await asyncio.sleep(0.8)
        actual = await page.evaluate(
            """() => {
              const el = document.querySelector('#txtTitle');
              return el ? (el.value || '').trim() : '';
            }"""
        )
        if not actual:
            raise RuntimeError("[文章][CSDN] 标题填写失败(输入框为空)")
        logger.info("[文章][CSDN] 标题已填写: %s", actual[:40])

    @staticmethod
    def _csdn_resolve_image_path(src: str) -> str:
        """把正文 img src 解析为本地文件路径（上传 CSDN 图床用）。

        支持素材库 URL(/api/materials/file/<stored_path>)、本地绝对路径、
        data: URL(写临时文件)、外链 http(s)(下载到临时文件)。
        """
        import base64
        import mimetypes
        import tempfile
        from urllib.parse import unquote, urlparse

        from storage import get_storage

        if src.startswith("data:"):
            head, _, b64 = src.partition(",")
            mime = head[5:].split(";")[0] or "image/png"
            ext = mimetypes.guess_extension(mime) or ".png"
            fd, path = tempfile.mkstemp(suffix=ext)
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64decode(b64))
            return path

        parsed = urlparse(src)
        marker = "/api/materials/file/"
        stored = ""
        if marker in src:
            stored = unquote(src.split(marker, 1)[1].split("?")[0])
        elif parsed.path and marker in parsed.path:
            stored = unquote(parsed.path.split(marker, 1)[1])

        if stored:
            local = get_storage().get_local_path(stored)
            if local and Path(local).exists():
                return local
            full_url = src if src.startswith("http") else (
                f"http://127.0.0.1:5409{src}"
            )
            return CsdnPlatform._csdn_download_to_temp(
                full_url, stored.split("/")[-1]
            )

        if src.startswith(("http://", "https://")):
            return CsdnPlatform._csdn_download_to_temp(
                src, Path(parsed.path).name or "img.png"
            )

        p = Path(src)
        if p.exists():
            return str(p)
        raise RuntimeError(f"[文章][CSDN] 无法解析正文图片 src: {src}")

    @staticmethod
    def _csdn_download_to_temp(url: str, filename: str = "img.png") -> str:
        import tempfile
        import urllib.request

        resp = urllib.request.urlopen(url, timeout=30)
        data = resp.read()
        suffix = Path(filename).suffix or ".png"
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path

    @classmethod
    async def _csdn_upload_article_images(cls, page, local_paths) -> list:
        """逐张通过编辑器「图像」抽屉上传本地图片,收集 CSDN 图床 URL。

        每张: 点工具栏「图像」→ 抽屉 input[type=file] set_input_files →
        轮询 iframe 内新增 http src 的 img（csrf 图床直传,返回
        i-blog.csdnimg.cn/direct/...）→ 关闭抽屉。任一张失败即抛异常。
        """
        frame_body = page.frame_locator(
            "iframe.cke_wysiwyg_frame"
        ).locator("body").first
        loop = asyncio.get_event_loop()
        urls: list = []
        for i, path in enumerate(local_paths):
            raise_if_page_closed(page, action="文章发布")
            before = await cls._csdn_body_img_srcs(frame_body)
            # 1. 点「图像」按钮打开上传抽屉
            pos = await page.evaluate(
                """() => {
                  const el = document.querySelector(
                    '.cke_button__imageoutside');
                  if (!el) return null;
                  el.scrollIntoView({block: 'center'});
                  const r = el.getBoundingClientRect();
                  if (r.width <= 0 || r.height <= 0) return null;
                  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                }"""
            )
            if not pos:
                raise RuntimeError("[文章][CSDN] 未找到正文图像按钮")
            await page.mouse.click(pos["x"], pos["y"])
            # 2. 抽屉内文件输入
            img_input = page.locator(CSDN_ARTICLE_IMG_INPUT).first
            try:
                await img_input.wait_for(state="attached", timeout=20000)
            except Exception as exc:
                raise RuntimeError(
                    f"[文章][CSDN] 图片上传抽屉未出现: {exc}"
                )
            # 3. 上传并轮询新图床 URL
            await img_input.set_input_files(path)
            new_src = ""
            deadline = loop.time() + 90
            while loop.time() < deadline:
                raise_if_page_closed(page, action="文章发布")
                srcs = await cls._csdn_body_img_srcs(frame_body)
                added = [
                    s for s in srcs
                    if s.startswith("http") and s not in before
                ]
                if added:
                    new_src = added[-1]
                    break
                await asyncio.sleep(1.5)
            if not new_src:
                # 冷启动偶发超时,自动重试一次
                logger.warning(
                    "[文章][CSDN] 图片上传超时,重试一次: %s",
                    Path(path).name,
                )
                try:
                    await img_input.set_input_files(path)
                except Exception:
                    pass
                deadline2 = loop.time() + 90
                while loop.time() < deadline2:
                    raise_if_page_closed(page, action="文章发布")
                    srcs2 = await cls._csdn_body_img_srcs(frame_body)
                    added2 = [
                        s for s in srcs2
                        if s.startswith("http") and s not in before
                    ]
                    if added2:
                        new_src = added2[-1]
                        break
                    await asyncio.sleep(1.5)
            if not new_src:
                raise RuntimeError(
                    f"[文章][CSDN] 正文图片上传超时({Path(path).name})"
                )
            urls.append(new_src)
            logger.info(
                "[文章][CSDN] 图片 %d/%d 已上传图床: %s",
                i + 1, len(local_paths), new_src[:100],
            )
            # 4. 关闭图片抽屉（上传完成后自动插入正文,抽屉可能已自动关闭）
            await cls._csdn_close_overlay(page)
        return urls

    @staticmethod
    async def _csdn_body_img_srcs(frame_body) -> list:
        try:
            return await frame_body.evaluate(
                """() => [...document.querySelectorAll('img')]
                    .map((im) => im.src)"""
            )
        except Exception:
            return []

    @staticmethod
    async def _csdn_close_overlay(page, max_rounds: int = 5):
        """关闭残留抽屉/弹层（Escape + 关闭按钮）,避免遮挡后续点击。"""
        for _ in range(max_rounds):
            try:
                opened = await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      return [...document.querySelectorAll(
                        '.el_mcm-drawer.open, .el_mcm-drawer.rtl.open, '
                        + '.vue-image-crop-upload, .mark-selection-popper')]
                        .some(vis);
                    }"""
                )
            except Exception:
                return
            if not opened:
                return
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            await asyncio.sleep(0.8)
            try:
                await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      for (const el of document.querySelectorAll(
                          '.el_mcm-drawer__close-btn, .el_mcm-dialog__headerbtn, '
                          + '.modal__close-button, .vicp-close')) {
                        if (vis(el)) { el.click(); return; }
                      }
                    }"""
                )
            except Exception:
                pass
            await asyncio.sleep(0.8)

    @staticmethod
    async def _csdn_set_editor_html(page, html: str) -> int:
        """CKEditor.setData 注入正文 HTML,返回写入后数据长度。"""
        length = await page.evaluate(
            """(html) => {
              const inst = window.CKEDITOR && window.CKEDITOR.instances
                && window.CKEDITOR.instances.editor;
              if (!inst) return -1;
              inst.setData(html);
              try { inst.updateElement(); } catch (e) {}
              return (inst.getData() || '').length;
            }""",
            html,
        )
        if length is None or length < 10:
            raise RuntimeError(
                f"[文章][CSDN] 正文注入失败或内容过短(length={length})"
            )
        await asyncio.sleep(2)
        return int(length)

    @staticmethod
    async def _csdn_add_tags(page, tags: list):
        """添加文章标签: 打开标签抽屉 → 输入 + Enter → 校验隐藏域。"""
        trigger = page.locator(".mark_selection button.tag__btn-tag").first
        await trigger.scroll_into_view_if_needed(timeout=10000)
        await trigger.click(timeout=15000)
        tag_input = page.locator(
            'input[placeholder*="Enter键入可添加自定义标签"]'
        ).first
        try:
            await tag_input.wait_for(state="visible", timeout=20000)
        except Exception as exc:
            raise RuntimeError(
                f"[文章][CSDN] 文章标签输入框未出现: {exc}"
            )
        for tag in tags:
            raise_if_page_closed(page, action="文章发布")
            await tag_input.click()
            await tag_input.fill("")
            await tag_input.press_sequentially(tag, delay=100)
            await asyncio.sleep(2.0)  # 等联想词接口
            await page.keyboard.press("Enter")
            await asyncio.sleep(1.0)
        actual = await page.evaluate(
            """() => {
              const el = document.querySelector('input[name="tags"]');
              return el ? (el.value || '') : '';
            }"""
        )
        missing = [t for t in tags if t not in (actual or "")]
        if missing:
            raise RuntimeError(
                f"[文章][CSDN] 文章标签未生效: 缺失 {missing}(已生效: {actual})"
            )
        logger.info("[文章][CSDN] 文章标签已生效: %s", actual)
        # 关闭标签弹层
        try:
            close_btn = page.locator(
                ".mark-selection-popper .modal__close-button"
            ).first
            if await close_btn.count():
                await close_btn.click(timeout=5000)
            else:
                await trigger.click(timeout=5000)
        except Exception:
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
        await asyncio.sleep(1)

    @staticmethod
    async def _csdn_set_category(page, category: str):
        """新建分类专栏（选填;接口/弹窗变动时抛异常由调用方跳过）。"""
        btn = page.locator(
            ".column-name-selection button.tag__btn-tag"
        ).first
        await btn.scroll_into_view_if_needed(timeout=10000)
        await btn.click(timeout=15000)
        await asyncio.sleep(2.5)
        # 找到新建专栏弹窗内的名称输入框（多种候选选择器）
        name_input = None
        for sel in (
            '.el_mcm-dialog input[placeholder*="专栏"]',
            '.el_mcm-dialog input[placeholder*="名称"]',
            '.el_mcm-message-box input',
            '[class*="dialog"] input[placeholder*="专栏"]',
            'input[placeholder*="请输入专栏名称"]',
        ):
            loc = page.locator(sel).first
            try:
                if await loc.count() and await loc.is_visible():
                    name_input = loc
                    break
            except Exception:
                continue
        if name_input is None:
            raise RuntimeError("未找到新建分类专栏弹窗输入框")
        await name_input.click()
        await name_input.fill(category[:30])
        await asyncio.sleep(0.5)
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const names = ['确定', '创建', '保存', '立即创建'];
              for (const b of document.querySelectorAll('button')) {
                if (!vis(b)) continue;
                const t = (b.innerText || '').trim();
                if (names.includes(t) && !b.disabled) { b.click(); return t; }
              }
              return '';
            }"""
        )
        if not clicked:
            raise RuntimeError("未找到分类专栏确定按钮")
        await asyncio.sleep(3)
        actual = await page.evaluate(
            """() => [...document.querySelectorAll(
                'input[name="categories"]')].map((e) => e.value)
                .filter(Boolean).join(',')"""
        )
        if category not in (actual or ""):
            raise RuntimeError(
                f"分类专栏未生效(已生效: {actual or '空'})"
            )
        await asyncio.sleep(0.5)

    @staticmethod
    async def _csdn_click_form_radio(
        page, group_label: str, option_text: str
    ) -> bool:
        """在指定 label 的表单项内点击单选项（文案精确匹配）。"""
        return await page.evaluate(
            """(args) => {
              const [groupLabel, optionText] = args;
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const labels = [...document.querySelectorAll(
                '.el_mcm-form-item__label')];
              const lab = labels.find((e) =>
                (e.innerText || '').includes(groupLabel));
              if (!lab) return false;
              let item = lab;
              for (let i = 0; i < 6 && item; i++) {
                const cls = (item.className || '').toString();
                if (cls.includes('form-item')
                    && !cls.includes('__label')) break;
                item = item.parentElement;
              }
              if (!item) return false;
              for (const el of item.querySelectorAll(
                  'label, .el_mcm-radio, span, div')) {
                if (!vis(el)) continue;
                const t = (el.innerText || '').trim();
                if (t !== optionText) continue;
                const r = el.getBoundingClientRect();
                if (r.height > 48) continue;
                el.click();
                return true;
              }
              return false;
            }""",
            [group_label, option_text],
        )

    @classmethod
    async def _csdn_set_article_type(cls, page, article_type: str):
        """文章类型: 原创(默认)/转载/翻译。已是原创则不操作。"""
        mapping = {
            "original": "原创", "原创": "原创",
            "repost": "转载", "转载": "转载", "reprint": "转载",
            "translate": "翻译", "翻译": "翻译",
        }
        label = mapping.get(
            str(article_type or "original").strip().lower(),
            mapping.get(str(article_type or "原创").strip(), "原创"),
        )
        if label == "原创":
            logger.info("[文章][CSDN] 文章类型默认原创,无需设置")
            return
        ok = await cls._csdn_click_form_radio(page, "文章类型", label)
        if not ok:
            raise RuntimeError(f"未找到文章类型选项: {label}")
        await asyncio.sleep(0.8)

    @classmethod
    async def _csdn_set_read_type(cls, page, read_type: str):
        """可见范围: 全部可见(默认)/仅我可见/粉丝可见/VIP可见。"""
        mapping = {
            "public": "全部可见", "全部可见": "全部可见",
            "private": "仅我可见", "仅我可见": "仅我可见",
            "fans": "粉丝可见", "粉丝可见": "粉丝可见",
            "vip": "VIP可见", "VIP可见": "VIP可见",
        }
        key = str(read_type or "public").strip()
        label = mapping.get(key.lower(), mapping.get(key, "全部可见"))
        if label == "全部可见":
            logger.info("[文章][CSDN] 可见范围默认全部可见,无需设置")
            return
        ok = await cls._csdn_click_form_radio(page, "可见范围", label)
        if not ok:
            raise RuntimeError(f"未找到可见范围选项: {label}")
        await asyncio.sleep(0.8)

    @staticmethod
    async def _csdn_set_original_link(page, link: str):
        """原文链接: 文章类型选「转载/翻译」后出现的 input。

        平台规则: 转载时该字段带 * 必填; 翻译时选填。
        """
        inp = page.locator('input[placeholder*="原文链接"]').first
        await inp.wait_for(state="visible", timeout=15000)
        await inp.scroll_into_view_if_needed(timeout=8000)
        await inp.click()
        await inp.fill(str(link or "").strip()[:500])
        await asyncio.sleep(1)
        actual = await page.evaluate(
            """() => {
              const inp = [...document.querySelectorAll('input')]
                .find((i) => (i.placeholder || '').includes('原文链接'));
              return inp ? (inp.value || '').trim() : '';
            }"""
        )
        if not actual:
            raise RuntimeError("[文章][CSDN] 原文链接未生效")

    @staticmethod
    async def _csdn_check_authorized(page) -> bool:
        """转载授权确认 checkbox「原文允许转载或者本次转载已经获得原文作者授权」。"""
        return await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const cbs = [...document.querySelectorAll(
                  '.el_mcm-checkbox')].filter(vis)
                .filter((e) =>
                  (e.innerText || '').includes('原文允许转载'));
              if (!cbs.length) return false;
              const el = cbs[0];
              if (!String(el.className).includes('is-checked')) el.click();
              return true;
            }"""
        )

    @staticmethod
    async def _csdn_set_sync_git_code(page, enabled: bool = True) -> bool:
        """文章备份「同时备份到GitCode」。"""
        for _ in range(3):
            # 先滚动到「文章备份」区(窄视口下可能在可视区外/懒渲染)
            await page.evaluate(
                """() => {
                  const labels = [...document.querySelectorAll(
                      '.el_mcm-form-item__label')];
                  const lab = labels.find((e) =>
                    (e.innerText || '').includes('文章备份'));
                  if (lab) lab.scrollIntoView({block: 'center'});
                }"""
            )
            await asyncio.sleep(1.2)
            done = await page.evaluate(
                """(want) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const cbs = [...document.querySelectorAll(
                      '.el_mcm-checkbox')].filter(vis)
                    .filter((e) =>
                      (e.innerText || '').includes('同时备份到GitCode'));
                  if (!cbs.length) return null;
                  const el = cbs[0];
                  const checked = String(el.className)
                    .includes('is-checked');
                  if (checked !== want) el.click();
                  return String(el.className).includes('is-checked');
                }""",
                enabled,
            )
            if done is not None:
                return True
        return False

    @classmethod
    async def _csdn_set_creation_statement(cls, page, value):
        """创作声明下拉（选填,失败由调用方 warning 跳过）。"""
        labels = [
            "无声明",
            "部分内容由AI辅助生成",
            "内容来源网络，进行整合/再创作",
            "个人观点，仅供参考",
        ]
        if isinstance(value, int):
            label = labels[value] if 0 <= value < len(labels) else ""
        else:
            text = str(value or "").strip()
            if text.isdigit():
                idx = int(text)
                label = labels[idx] if 0 <= idx < len(labels) else ""
            else:
                label = text
        if not label:
            raise RuntimeError(f"无效创作声明: {value}")
        opened = await page.evaluate(
            """(groupLabel) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const labels = [...document.querySelectorAll(
                '.el_mcm-form-item__label')];
              const lab = labels.find((e) =>
                (e.innerText || '').includes(groupLabel));
              if (!lab) return false;
              let item = lab;
              for (let i = 0; i < 6 && item; i++) {
                const cls = (item.className || '').toString();
                if (cls.includes('form-item')
                    && !cls.includes('__label')) break;
                item = item.parentElement;
              }
              if (!item) return false;
              const w = item.querySelector('.el_mcm-select__wrapper');
              if (!w || !vis(w)) return false;
              w.click();
              return true;
            }""",
            "创作声明",
        )
        if not opened:
            raise RuntimeError("未找到创作声明下拉")
        await asyncio.sleep(1.2)
        clicked = await page.evaluate(
            """(label) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              for (const el of document.querySelectorAll(
                  '.el_mcm-select-dropdown__item, li')) {
                if (!vis(el)) continue;
                if ((el.innerText || '').trim() === label) {
                  el.click();
                  return true;
                }
              }
              return false;
            }""",
            label,
        )
        if not clicked:
            raise RuntimeError(f"未找到创作声明选项: {label}")
        await asyncio.sleep(0.8)

    @staticmethod
    async def _csdn_set_digest(page, digest: str):
        """文章摘要 textarea（placeholder 以「摘要：」开头）。"""
        ta = page.locator(
            'textarea[placeholder^="摘要"]'
        ).first
        if not await ta.count():
            raise RuntimeError("未找到文章摘要输入框")
        await ta.scroll_into_view_if_needed(timeout=8000)
        await ta.click()
        await ta.fill(str(digest)[:256])
        await asyncio.sleep(0.5)

    @classmethod
    async def _csdn_set_cover(cls, page, cover_path: str) -> str:
        """封面上传: 本地文件 → 裁剪弹窗「确认上传」→ 预览图 URL。"""
        cover_input = page.locator(
            ".container-coverimage-box input[type=file]"
        ).first
        await cover_input.wait_for(state="attached", timeout=20000)
        await cover_input.set_input_files(cover_path)
        crop = page.locator(".vue-image-crop-upload").first
        try:
            await crop.wait_for(state="visible", timeout=25000)
        except Exception as exc:
            raise RuntimeError(f"封面裁剪弹窗未出现: {exc}")
        await asyncio.sleep(1)
        clicked = await page.evaluate(
            """() => {
              const c = document.querySelector('.vue-image-crop-upload');
              if (!c) return '';
              for (const b of c.querySelectorAll(
                  '.vicp-operate-btn, a, button')) {
                if ((b.innerText || '').trim() === '确认上传') {
                  b.click();
                  return '确认上传';
                }
              }
              return '';
            }"""
        )
        if not clicked:
            raise RuntimeError("未找到封面确认上传按钮")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 90
        cover_url = ""
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            cover_url = await page.evaluate(
                """() => {
                  const box = document.querySelector(
                    '.container-coverimage-box');
                  if (!box) return '';
                  // 封面预览图（.preview-box img.preview）：
                  // 不能用容器内任意 img，否则会命中正文图片缩略图
                  const preview = box.querySelector(
                    '.preview-box img.preview');
                  const src = preview ? (preview.src || '') : '';
                  return src.startsWith('http') ? src : '';
                }"""
            )
            if cover_url:
                break
            await asyncio.sleep(1.5)
        if not cover_url:
            raise RuntimeError("封面上传超时(未出现封面预览图)")
        await cls._csdn_close_overlay(page)
        return cover_url

    @staticmethod
    def _csdn_parse_datetime(schedule_time_str: str):
        from datetime import datetime as _dt

        text = (schedule_time_str or "").strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H-%M-%S",
            "%Y-%m-%d %H-%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
        ):
            try:
                return _dt.strptime(text, fmt)
            except ValueError:
                continue
        raise ValueError(f"无法解析定时时间: {schedule_time_str!r}")

    async def _csdn_fill_schedule_dialog(
        self, page, schedule_time_str: str
    ):
        """打开「定时发布」弹窗并选择日期+时间（不提交）。"""
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        target = self._csdn_parse_datetime(schedule_time_str)
        now = _dt.now()
        if target < now + _td(hours=4):
            raise ValueError(
                "CSDN 定时发布需晚于当前时间 4 小时（当前设定: "
                f"{target:%Y-%m-%d %H:%M}）"
            )
        if target > now + _td(days=7):
            raise ValueError(
                "CSDN 定时发布需早于当前时间 7 天（当前设定: "
                f"{target:%Y-%m-%d %H:%M}）"
            )
        # 1. 打开弹窗
        btn = page.locator('button:has-text("定时发布")').first
        await btn.scroll_into_view_if_needed(timeout=10000)
        await btn.click(timeout=15000)
        dialog = page.locator(
            ".el_mcm-dialog.publish-timer-dialog-wrapper"
        ).first
        await dialog.wait_for(state="visible", timeout=20000)
        await asyncio.sleep(1)
        # 2. 选日期
        date_input = dialog.locator("input.txt-date").first
        if not await date_input.count():
            date_input = dialog.locator(
                'input[placeholder="选择日期"]'
            ).first
        await date_input.click()
        await asyncio.sleep(1)
        for _ in range(4):
            raise_if_page_closed(page, action="文章发布")
            header = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const h = [...document.querySelectorAll(
                    '.el_mcm-date-picker__header-label, '
                    + '.el_mcm-picker-panel__header-label')]
                    .filter(vis).map((e) => (e.innerText || '').trim());
                  return h.join('|');
                }"""
            )
            if (
                str(target.year) in (header or "")
                and f"{target.month} 月" in (header or "")
            ):
                break
            await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  for (const el of document.querySelectorAll(
                      '.el_mcm-picker-panel__icon-btn.arrow-right, '
                      + '.el_mcm-date-picker__next-btn')) {
                    if (vis(el)) { el.click(); return; }
                  }
                }"""
            )
            await asyncio.sleep(0.8)
        picked = await page.evaluate(
            """(day) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const cells = [...document.querySelectorAll(
                '.el_mcm-date-table td.available')]
                .filter((td) => vis(td)
                  && !td.className.includes('prev-month')
                  && !td.className.includes('next-month'));
              for (const td of cells) {
                const sp = td.querySelector('span');
                if (sp && (sp.innerText || '').trim() === String(day)) {
                  td.click();
                  return true;
                }
              }
              return false;
            }""",
            target.day,
        )
        if not picked:
            raise RuntimeError(
                f"定时弹窗未找到日期单元格: {target:%Y-%m-%d}"
            )
        await asyncio.sleep(1)
        date_value = await date_input.input_value()
        if date_value != f"{target:%Y-%m-%d}":
            # 尝试直接 fill（部分版本可编辑）
            try:
                await date_input.fill(f"{target:%Y-%m-%d}")
                await page.keyboard.press("Enter")
                await asyncio.sleep(0.8)
                date_value = await date_input.input_value()
            except Exception:
                pass
        if date_value != f"{target:%Y-%m-%d}":
            raise RuntimeError(
                f"定时日期选择失败(期望 {target:%Y-%m-%d},实际 {date_value})"
            )
        # 3. 选时间（15 分钟粒度下拉）
        time_target = f"{target:%H:%M}"
        opened = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const d = document.querySelector(
                '.publish-timer-dialog-wrapper');
              if (!d) return false;
              for (const w of d.querySelectorAll(
                  '.el_mcm-select__wrapper')) {
                if (vis(w)) { w.click(); return true; }
              }
              return false;
            }"""
        )
        if not opened:
            raise RuntimeError("定时弹窗未找到时间下拉")
        await asyncio.sleep(1)
        options = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              return [...document.querySelectorAll(
                '.el_mcm-select-dropdown__item')]
                .filter(vis).map((e) => (e.innerText || '').trim())
                .filter(Boolean);
            }"""
        )
        if not options:
            raise RuntimeError("定时弹窗时间选项为空")
        # 取最接近目标时间的可选值
        def _minutes(text: str):
            try:
                h, m = text.split(":")
                return int(h) * 60 + int(m)
            except Exception:
                return None

        target_min = target.hour * 60 + target.minute
        candidates = [
            (abs(_minutes(o) - target_min), o)
            for o in options if _minutes(o) is not None
        ]
        if not candidates:
            raise RuntimeError(f"定时弹窗无可用时间选项: {options[:5]}")
        chosen = min(candidates)[1]
        clicked = await page.evaluate(
            """(text) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              for (const el of document.querySelectorAll(
                  '.el_mcm-select-dropdown__item')) {
                if (!vis(el)) continue;
                if ((el.innerText || '').trim() === text) {
                  el.click();
                  return true;
                }
              }
              return false;
            }""",
            chosen,
        )
        if not clicked:
            raise RuntimeError(f"定时时间选择失败: {chosen}")
        await asyncio.sleep(1)
        logger.info(
            "[文章][CSDN] 定时发布已设置: 日期=%s 时间=%s",
            date_value, chosen,
        )

    async def _csdn_submit_schedule_publish(self, page) -> dict:
        """在定时弹窗内点「定时发布」提交,并等 saveArticle code=200。"""
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const d = document.querySelector(
                '.publish-timer-dialog-wrapper');
              if (!d) return '';
              for (const b of d.querySelectorAll('button')) {
                if (!vis(b)) continue;
                const t = (b.innerText || '').replace(/\\s+/g, '');
                if (t === '定时发布' && !b.disabled) {
                  b.click();
                  return '定时发布';
                }
              }
              return '';
            }"""
        )
        if not clicked:
            raise RuntimeError("[文章][CSDN] 定时弹窗提交按钮未找到")

        async def _noop():
            return None

        data = await self._csdn_wait_save_response(
            page, _noop, CSDN_ARTICLE_STATUS_PUBLISH,
            action="定时发表", timeout_s=180,
        )
        return data

    async def _csdn_save_draft(self, page) -> dict:
        """保存草稿: 点「保存草稿」→ 等 saveArticle(status=2) code=200。"""
        await self._csdn_close_overlay(page)
        btn = page.locator('button:has-text("保存草稿")').first
        if not await btn.count():
            raise RuntimeError("[文章][CSDN] 保存草稿按钮未找到")
        await btn.scroll_into_view_if_needed(timeout=10000)

        async def _click():
            await btn.click(timeout=15000)

        return await self._csdn_wait_save_response(
            page, _click, CSDN_ARTICLE_STATUS_DRAFT,
            action="保存草稿", timeout_s=120,
        )

    async def _csdn_publish_now(self, page) -> dict:
        """立即发表: 点「发布博客」→ 等 saveArticle(status=0) code=200。"""
        # 先关闭可能残留的弹层
        await self._csdn_close_overlay(page)
        btn = page.locator('button:has-text("发布博客")').first
        if not await btn.count():
            raise RuntimeError("[文章][CSDN] 发布博客按钮未找到")
        await btn.scroll_into_view_if_needed(timeout=10000)
        await asyncio.sleep(0.5)

        async def _click():
            await btn.click(timeout=15000)

        return await self._csdn_wait_save_response(
            page, _click, CSDN_ARTICLE_STATUS_PUBLISH,
            action="文章发表", timeout_s=180,
        )

    @classmethod
    async def _csdn_wait_save_response(
        cls, page, trigger, expected_status: int, action: str,
        timeout_s: int = 180, risk_timeout_s: int = 600,
    ) -> dict:
        """执行 trigger 并监听 postedit/saveArticle 响应判定成功。

        成功判定: 响应 JSON ``code===200``（禁 URL 判定）。失败 raise
        含 code+msg。检测到风控/人机校验弹窗时,有头浏览器等待用户处理
        （额外 risk_timeout_s 秒）,超时如实报失败。
        """
        import json as _json

        holder: dict = {}
        done = asyncio.Event()

        async def _parse_response(resp):
            try:
                data = await resp.json()
            except Exception:
                data = None
            holder["data"] = data
            holder["status_code"] = resp.status
            holder["url"] = resp.url
            done.set()

        def _on_response(resp):
            try:
                if CSDN_ARTICLE_SAVE_API not in resp.url:
                    return
                if resp.request.method != "POST":
                    return
                post = _json.loads(resp.request.post_data or "{}")
                if int(post.get("status", -1)) != expected_status:
                    return
                holder["post"] = post
                asyncio.ensure_future(_parse_response(resp))
            except Exception:
                pass

        page.on("response", _on_response)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        risk_deadline = None
        risk_logged = False
        try:
            await trigger()
            while True:
                raise_if_page_closed(page, action=action)
                if done.is_set():
                    break
                now = loop.time()
                if now >= deadline and not (
                    risk_deadline and now < risk_deadline
                ):
                    break
                if not risk_logged:
                    try:
                        if await cls._csdn_risk_modal_visible(page):
                            risk_logged = True
                            risk_deadline = now + risk_timeout_s
                            logger.warning(
                                "[文章][CSDN] 检测到风控/人机校验弹窗，请在"
                                "浏览器中手动完成验证（最多等待 %d 秒）",
                                risk_timeout_s,
                            )
                    except Exception:
                        pass
                await asyncio.sleep(1)
        finally:
            try:
                page.remove_listener("response", _on_response)
            except Exception:
                pass

        if not done.is_set():
            raise RuntimeError(
                f"[文章][CSDN] {action}接口无响应或超时"
                f"（等待 {timeout_s}s，可能被风控拦截）"
            )
        data = holder.get("data")
        if not isinstance(data, dict):
            raise RuntimeError(
                f"[文章][CSDN] {action}响应解析失败"
                f"(status={holder.get('status_code')})"
            )
        code = data.get("code")
        msg = data.get("msg") or data.get("message") or ""
        post = holder.get("post") or {}
        logger.info(
            "[文章][CSDN] %s响应: code=%s msg=%s status=%s scheduled_time=%s",
            action, code, msg, post.get("status"), post.get("scheduled_time"),
        )
        if code != 200:
            raise RuntimeError(
                f"CSDN {action}失败: code={code} msg={msg or '未知错误'}"
            )
        payload = data.get("data")
        result = payload if isinstance(payload, dict) else {}
        return result

    @staticmethod
    async def _csdn_risk_modal_visible(page) -> bool:
        """检测 CSDN 风控/人机校验/登录失效弹窗是否可见。"""
        try:
            return await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const kws = [
                    '安全验证', '人机验证', '滑动验证', '拖动滑块',
                    '请完成验证', '验证码', '登录状态失效',
                  ];
                  for (const el of document.querySelectorAll(
                      '.csdn-login-box, .login-box, '
                      + '[class*="captcha"], [class*="verify-box"], '
                      + 'iframe[src*="captcha"], iframe[src*="passport"]')) {
                    if (vis(el)) return true;
                  }
                  for (const el of document.querySelectorAll(
                      'div, span, p, h3, h4')) {
                    if (!vis(el)) continue;
                    const t = (el.innerText || '').trim();
                    if (!t || t.length > 80) continue;
                    if (kws.some((k) => t.includes(k))) return true;
                  }
                  return false;
                }"""
            )
        except Exception:
            return False


# ---------------------------------------------------------------------------
# 素材方向查询已移除：CSDN 固定使用横版封面，不再需要按视频方向选择。
# ---------------------------------------------------------------------------
