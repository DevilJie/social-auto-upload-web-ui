"""京东关联商品 picker session — 后台 headless browser。

按 account_id 单例复用:
- 同账号同时只能开一个 picker(避免资源竞争)
- picker 与 platform 共享 _jd_link_ops(同一份 DOM 操作)

浏览器策略:headless=True(无头模式,关联挂件自动化不打扰用户)
"""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from .._browser import create_browser, create_context, close_browser
from . import _jd_link_ops as link_ops
from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("jingmai")


# cookie 失效的 URL 特征:goto 后若被重定向到这些域名,说明登录态没了。
# (参考淘宝光合 picker.py 的 _COOKIE_INVALID_MARKERS 模式)
_COOKIE_INVALID_MARKERS = (
    "login.jd.com",
    "passport.jd.com",
    "sso.jd.com",
    "auth.jd.com",
)


def _get_cookie_path_by_account_id(account_id: str) -> str | None:
    """根据 user_info.id 取 cookiesFile 路径(参考淘宝光合 picker)。"""
    if not account_id:
        return None
    db_path = str(Path(BASE_DIR / "db" / "database.db"))
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _resolve_cookie_path(cookie_filename: str) -> Path:
    return Path(BASE_DIR / "cookiesFile") / cookie_filename


class JdPickerSession:
    """单账号单 headless browser session。"""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.browser = None
        self.page = None
        # 京东微前端架构:发布表单在 iframe 里(self.frame),不在 top frame(self.page)。
        # 所有 link_ops 操作必须传 self.frame,否则永远找不到 .addgoods-upload 等元素。
        self.frame = None

    async def _wait_publish_frame(self, timeout: float = 20):
        """等发布表单 iframe(委托给 link_ops.wait_publish_frame 公共函数)。"""
        return await link_ops.wait_publish_frame(self.page, timeout=timeout)

    async def _init_browser_and_frame(self):
        """启动浏览器 + goto 发布页 + 进 iframe。

        只负责建立 self.browser / self.page / self.frame,不切 radio、不开抽屉。
        具体 UI 操作由 open()(商品) / novel_search()(小说) 各自做。
        """
        if self.browser is not None:
            raise RuntimeError(f"picker session 已存在: {self.account_id}")

        cookie_filename = _get_cookie_path_by_account_id(self.account_id)
        cookie_path = _resolve_cookie_path(cookie_filename) if cookie_filename else None
        storage_state = str(cookie_path) if cookie_path and cookie_path.exists() else None
        logger.info(f"[JdPicker][{self.account_id}] init cookie={'有' if storage_state else '无'}")

        # 无头模式:关联挂件浏览器自动化不打扰用户
        self.browser = await create_browser(headless=True)
        if storage_state:
            ctx = await create_context(self.browser, storage_state=storage_state)
            self.page = await ctx.new_page()
        else:
            ctx = await self.browser.new_context()
            self.page = await ctx.new_page()

        # goto 发布页 —— 用 domcontentloaded 而不是 networkidle:
        # networkidle 要等 500ms 内零网络活动,但京东 SPA 有持续 polling/上报,
        # 实测会吃满 30s 超时再走降级。domcontentloaded 只要 HTML 解析完就返回,
        # 后续靠 _wait_publish_frame polling(0.3s 周期)等 iframe,快几秒。
        logger.info("[JdPicker] goto 京东发布页")
        await self.page.goto(
            "https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop",
            wait_until="domcontentloaded",
            timeout=30000,
        )

        # cookie 失效检测:goto 后若被重定向到登录/SSO 页,直接抛错而不是傻等 iframe 超时
        current_url = self.page.url or ""
        if any(m in current_url for m in _COOKIE_INVALID_MARKERS):
            raise RuntimeError("cookie 失效,请重新登录京东")

        # 京东 dr.jd.com 是微前端架构:top frame (self.page) 只渲染"猜你想问"等 FAQ
        # 引导内容,真正的发布表单在 iframe (self.frame) 里。所有表单操作都在 iframe 上做。
        logger.info("[JdPicker] 等发布表单 iframe 出现(最长 20s)")
        try:
            self.frame = await self._wait_publish_frame(timeout=20)
            logger.info(f"[JdPicker] ✓ iframe={self.frame.url}")
        except Exception:
            # 失败时 dump 整页状态帮助定位
            page_state = await self.page.evaluate(
                """() => {
                    const out = {url: location.href, title: document.title, texts: '', classes: [], radio_count: 0, drawer_count: 0};
                    out.texts = (document.body && document.body.innerText || '').slice(0, 800);
                    const interesting = new Set();
                    document.querySelectorAll('[class*="addgoods"], [class*="publish"], [class*="video-upload"], [class*="jd-radio"], [class*="jd-drawer"]').forEach(el => {
                        interesting.add(el.className.toString().slice(0, 200));
                    });
                    out.classes = Array.from(interesting).slice(0, 30);
                    out.radio_count = document.querySelectorAll('.jd-radio-wrapper, [class*="radio"]').length;
                    out.drawer_count = document.querySelectorAll('.jd-drawer-wrapper-body, [class*="drawer"]').length;
                    out.file_inputs = document.querySelectorAll('input[type="file"]').length;
                    return out;
                }"""
            )
            logger.error(
                f"[JdPicker] 页面状态 dump: url={page_state.get('url')} "
                f"title={page_state.get('title')} "
                f"radio_count={page_state.get('radio_count')} "
                f"drawer_count={page_state.get('drawer_count')} "
                f"file_inputs={page_state.get('file_inputs')}"
            )
            logger.error(
                f"[JdPicker] 页面可见文本前800字:\n{page_state.get('texts', '')}"
            )
            logger.error(
                f"[JdPicker] 关键 class:\n" + "\n".join(page_state.get('classes', []))
            )

            # iframe 等待失败时的诊断:遍历所有 frame,确认 iframe 是否存在、
            # URL pattern 是否变了(JD 改路由会让 _wait_publish_frame 匹配不到)。
            all_frames = self.page.frames
            logger.error(
                f"[JdPicker] === frame tree dump (共 {len(all_frames)} 个 frame) ==="
            )
            for i, f in enumerate(all_frames):
                try:
                    f_state = await f.evaluate(
                        """() => ({
                            url: location.href,
                            radio_count: document.querySelectorAll('[class*="radio"], .jd-radio-wrapper').length,
                            file_inputs: document.querySelectorAll('input[type="file"]').length,
                            addgoods_count: document.querySelectorAll('[class*="addgoods"]').length,
                            text_head: (document.body && document.body.innerText || '').slice(0, 200).replace(/\\s+/g, ' '),
                        })"""
                    )
                    logger.error(
                        f"[JdPicker] frame[{i}] url={f_state.get('url')} "
                        f"radio={f_state.get('radio_count')} "
                        f"file_inputs={f_state.get('file_inputs')} "
                        f"addgoods={f_state.get('addgoods_count')} "
                        f"text='{f_state.get('text_head')}'"
                    )
                except Exception as fe:
                    logger.error(
                        f"[JdPicker] frame[{i}] url={f.url} evaluate 失败: {fe}"
                    )

            raise RuntimeError(
                f"未找到发布表单 iframe。URL={self.page.url or ''}"
            )

    async def open(self) -> dict:
        """启动浏览器进入商品选择面板,返回首屏 {products, total}。"""
        await self._init_browser_and_frame()

        # 等 .addgoods-upload 在 iframe 里出现(attached 即可,不要求 visible,
        # 因为可能有残留浮层遮挡,但 JS click 可以绕过)
        logger.info("[JdPicker] 等 .addgoods-upload 在 iframe 里出现(最长 20s)")
        await self.frame.wait_for_selector(
            ".addgoods-upload",
            timeout=20_000,
            state="attached",
        )

        # 切商品 radio(默认已是商品,但保险起见)
        logger.info("[JdPicker] 切商品 radio")
        await link_ops.switch_radio(self.frame, "product")
        logger.info("[JdPicker] ✓ 商品 radio 已选")

        # 点'添加商品'卡片,打开抽屉
        logger.info("[JdPicker] 点击 .addgoods-upload 卡片")
        await link_ops.click_add_card(self.frame)
        logger.info("[JdPicker] ✓ 已点击添加商品卡片")

        # 等抽屉就绪
        logger.info("[JdPicker] 等抽屉 .jd-drawer-wrapper-body 就绪")
        await link_ops.wait_panel_ready(self.frame)
        logger.info("[JdPicker] ✓ 抽屉已就绪")

        # 返回首屏商品 + 总条数
        products = await link_ops.scrape_products(self.frame)
        total = await link_ops.scrape_total(self.frame)
        logger.info(f"[JdPicker] ✓ 首屏抓到 {len(products)} 个商品,共 {total} 条")
        return {"products": products, "total": total}

    async def novel_search(self, keyword: str) -> dict:
        """搜索小说关键词,返回 {novels: [...]}。

        不依赖 open()(那是 product-specific 的)。第一次调用时自建浏览器 + iframe,
        之后复用 session(切 radio 从 product 切回 novel 会自动关商品抽屉)。
        """
        if self.frame is None:
            await self._init_browser_and_frame()

        # 切到 novel radio(从 product 切过来会自动关抽屉)
        await link_ops.switch_radio(self.frame, "novel")
        await asyncio.sleep(0.5)

        novels = await link_ops.search_novels(self.frame, keyword)
        logger.info(f"[JdPicker] ✓ 小说搜到 {len(novels)} 个候选")
        return {"novels": novels}

    async def _dismiss_help_dialog(self) -> None:
        """关闭京东发布页首屏的'猜你想问'帮助浮层。

        浮层会挡住主表单,导致 Playwright visible 检查失败。
        策略(按优先级尝试):
        1. 找含'猜你想问'/'我知道了'/'关闭'文案的可点元素 → 点击
        2. 找 .jd-modal-close / [aria-label='Close'] 关闭按钮 → 点击
        3. 兜底:按 Esc 键
        """
        try:
            dismissed = await self.page.evaluate(
                """() => {
                    // 1. 找含"我知道了"/"关闭"/"不再提示"等文案的按钮
                    const candidates = Array.from(document.querySelectorAll(
                        'button, .jd-btn, .jd-modal-close, [aria-label="Close"], .close'
                    ));
                    const targetTexts = ['我知道了', '关闭', '不再提示', '取消', '×'];
                    for (const el of candidates) {
                        const t = (el.textContent || '').trim();
                        if (targetTexts.includes(t)) {
                            el.click();
                            return t;
                        }
                    }
                    // 2. 找含"猜你想问"的容器,看里面有没有可点的关闭按钮
                    const faq = Array.from(document.querySelectorAll('div, span'))
                        .find(el => (el.textContent || '').trim().startsWith('猜你想问'));
                    if (faq) {
                        // 向上找父容器内的关闭按钮
                        let parent = faq;
                        for (let i = 0; i < 8 && parent; i++) {
                            const closeBtn = parent.querySelector(
                                '.jd-modal-close, [aria-label="Close"], .close, .jd-icon-close'
                            );
                            if (closeBtn) { closeBtn.click(); return 'close-icon'; }
                            parent = parent.parentElement;
                        }
                    }
                    return null;
                }"""
            )
            if dismissed:
                logger.info(f"[JdPicker] ✓ 关闭帮助浮层: {dismissed}")
                await asyncio.sleep(0.8)
                return
            # 3. 兜底:按 Esc
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
            logger.info("[JdPicker] 按 Esc 尝试关闭浮层")
        except Exception as e:
            logger.info(f"[JdPicker] 关闭浮层异常(忽略): {e}")

    async def search(self, keyword: str) -> dict:
        """搜索并返回 {products, total}。

        keyword 为空也会触发搜索(清空 input + Enter),让京东恢复"全部商品"。
        """
        if self.frame is None:
            raise RuntimeError("picker 未打开,请先调用 open()")
        # link_ops.search 内部已包含:清空 + 填 keyword(if 非空) + Enter + wait
        await link_ops.search(self.frame, keyword)
        products = await link_ops.scrape_products(self.frame)
        total = await link_ops.scrape_total(self.frame)
        return {"products": products, "total": total}

    async def go_page(self, page: int) -> dict:
        """翻页并返回 {products, total}。"""
        if self.frame is None:
            raise RuntimeError("picker 未打开")
        await link_ops.go_page(self.frame, page)
        products = await link_ops.scrape_products(self.frame)
        total = await link_ops.scrape_total(self.frame)
        return {"products": products, "total": total}

    async def close(self):
        """释放浏览器资源(必须在 finally 中调用)。"""
        try:
            if self.browser is not None:
                await close_browser(self.browser, is_close_by_code=True)
        except Exception as e:
            logger.warning(f"关闭 picker 浏览器失败: {e}")
        finally:
            self.browser = None
            self.page = None
            self.frame = None


# ---------- session 池 ----------


class _SessionPool:
    """按 account_id 管理 picker session,同账号同时只能开一个。"""

    def __init__(self):
        self._sessions: dict[str, JdPickerSession] = {}

    def get_or_create(self, account_id: str) -> JdPickerSession:
        existing = self._sessions.get(account_id)
        if existing is not None:
            return existing
        new_session = JdPickerSession(account_id)
        self._sessions[account_id] = new_session
        return new_session

    def create(self, account_id: str) -> JdPickerSession:
        """强制为 account_id 创建新 session;若已存在旧 session,异步销毁。

        对齐淘宝光合 pool.create 模式:打开弹窗总是从干净状态开始,
        客户端 close 漏调也不会卡死 —— 旧 session 的浏览器通过
        asyncio.ensure_future 在 picker loop 里异步关闭,不阻塞当前请求。

        本方法从 jd_bp.py 的 Flask 请求线程调用,但 asyncio.ensure_future
        会把协程提交到当前运行中的 picker loop(由 run_picker_async 启动),
        所以旧 session.close() 能在正确的 loop 上跑。
        """
        existing = self._sessions.get(account_id)
        if existing is not None:
            logger.info(f"[Pool] 账号 {account_id} 已有 session,异步销毁后重建")
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(existing.close())
            except RuntimeError:
                pass  # 没运行中的 loop,跳过(GC 兜底)
        new_session = JdPickerSession(account_id)
        self._sessions[account_id] = new_session
        return new_session

    def get(self, account_id: str) -> Optional[JdPickerSession]:
        return self._sessions.get(account_id)

    def release(self, account_id: str):
        """从池中移除 session 并返回,不负责关闭浏览器。

        返回的 session 由调用方用 `run_picker_async(session.close(), ...)`
        提交到后台 picker loop 关闭 —— 之前在 release 内部用 asyncio.get_event_loop()
        试图关闭,但 Flask 请求线程没运行中的 loop,会抛 RuntimeError 后 pass,
        导致 session 出池但浏览器进程泄漏。
        """
        return self._sessions.pop(account_id, None)

    def has(self, account_id: str) -> bool:
        return account_id in self._sessions


pool = _SessionPool()