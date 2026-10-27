"""
大鱼号平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

创作中心地址：https://mp.dayu.com/dashboard/index
视频发布地址：https://mp.dayu.com/dashboard/video/write（首页悬停「发布内容」→「短视频」进入）
发布成功跳转：https://mp.dayu.com/dashboard/contents
"""

import asyncio
import base64
import json
import mimetypes
import threading
import time
from datetime import timedelta
from pathlib import Path
from queue import Queue
from urllib.parse import unquote, urlparse

from util._logger import bind_account_name, get_channel_logger

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    raise_if_page_closed,
    save_login_result,
    scrape_dayu_profile,
)
from ..base_platform import BasePlatform
from .._manual_review import manual_review_enabled, wait_for_manual_publish

logger = get_channel_logger("dayu")

HOME_URL = "https://mp.dayu.com/dashboard/index"
WRITE_URL = "https://mp.dayu.com/dashboard/video/write"
CONTENTS_URL = "https://mp.dayu.com/dashboard/contents"

# 大鱼号页面上规定的字数限制（发布表单实时显示 x/60、x/200）
MAX_TITLE_LENGTH = 60
MIN_TITLE_LENGTH = 5
MAX_DESC_LENGTH = 200
MAX_TAGS = 10

# ---------------------------------------------------------------------------
# 图文文章（article）相关常量与页面脚本
# ---------------------------------------------------------------------------
# 图文编辑器：Vue2 页面 + UEditor 富文本(iframe#ueditor_0)
ARTICLE_WRITE_URL = "https://mp.dayu.com/dashboard/article/write"
# 编辑器标题框提示 0/50、最少 5 个字
ARTICLE_MAX_TITLE_LENGTH = 50
ARTICLE_MIN_TITLE_LENGTH = 5
# UEditor 单图上限 5MB(imageMaxSize)、允许 png/jpg/jpeg/gif/bmp
ARTICLE_IMAGE_MAX_BYTES = 5 * 1024 * 1024
# 信息来源(作品声明)单选项 —— 与编辑器 radio 文案一一对应
ARTICLE_SOURCE_OPTIONS = (
    "无需标注", "AI生成", "虚构演绎", "营销信息",
    "转载", "个人观点", "不适宜未成年人",
)
# 图文定时发表: 平台实测「当前时间后 2 小时 ~ 7 天」, 只支持 5 分钟粒度
# (重新侦察 2026-10-23: 默认值=当前 +2h, 日期面板仅今天~+7 天可选,
#  分钟面板只列 00/05/10…55)
ARTICLE_SCHEDULE_MIN_HOURS = 2
ARTICLE_SCHEDULE_MAX_DAYS = 7
ARTICLE_SCHEDULE_SNAP_MINUTES = 5
# 图文「作者名称」输入上限 0/10
ARTICLE_AUTHOR_MAX_LEN = 10

# 正文/封面图片上传：UEditor 编辑器同款接口，页面内 fetch 带 cookie/referer。
# items: [{name,b64,mime}] → [{name,ok,cdn_url,ret,err_msg}]
# 成功响应: {"state":"SUCCESS","url":"https://mp.dayu.com/dayu/image?...","type":...}
_ARTICLE_UPLOAD_JS = """async (items) => {
  const out = [];
  for (const it of items) {
    try {
      const bin = atob(it.b64);
      const arr = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
      const fd = new FormData();
      fd.append('upfile', new File([arr], it.name || 'image.jpg',
                                  {type: it.mime || 'image/jpeg'}));
      const resp = await fetch('/ueditor/controller?action=uploadimage', {
        method: 'POST', body: fd, credentials: 'include',
      });
      const body = await resp.json();
      const ok = !!(body && body.state === 'SUCCESS' && body.url);
      out.push({
        name: it.name,
        ok: ok,
        cdn_url: (body && body.url) || '',
        ret: (body && body.state) || ('http ' + resp.status),
        err_msg: (body && (body.error || body.state)) || '',
      });
    } catch (e) {
      out.push({name: it.name, ok: false, cdn_url: '',
                ret: 'exception', err_msg: String(e)});
    }
  }
  return out;
}"""

# 粘贴 HTML 到 UEditor iframe(与知乎同样的 ClipboardEvent 通道，实测可解析
# h2/strong/em/ul/img；UEditor 会自动给图片补 data-md5/imagesize)。
# 返回 iframe body innerHTML 长度，调用方校验 >20 判定粘贴成功。
_ARTICLE_PASTE_JS = """(html) => {
  const ifr = document.querySelector('iframe#ueditor_0');
  if (!ifr || !ifr.contentDocument) return 0;
  const ed = ifr.contentDocument.body;
  ed.focus();
  const dt = new DataTransfer();
  dt.setData('text/html', html);
  dt.setData('text/plain', 'article');
  ed.dispatchEvent(new ClipboardEvent('paste', {
    bubbles: true, cancelable: true, clipboardData: dt,
  }));
  return ed.innerHTML.length;
}"""

# 读页面 Vue 实例的 formData 子集(封面/定时/草稿/信息来源状态校验用)
_ARTICLE_FORM_JS = """() => {
  const seen = new Set();
  const stack = [document.body];
  let vm = null;
  while (stack.length) {
    const el = stack.pop();
    if (!el || seen.has(el)) continue;
    seen.add(el);
    if (el.__vue__) {
      let v = el.__vue__;
      while (v) {
        if (v.formData && 'title' in v.formData) { vm = v; break; }
        v = v.$parent;
      }
      if (vm) break;
    }
    for (const c of el.children) stack.push(c);
  }
  if (!vm) return null;
  const fd = vm.formData;
  return {
    title: fd.title,
    draft_id: fd.draft_id,
    coverImg: fd.coverImg,
    cover_from: fd.cover_from,
    origin_cover_img: fd.origin_cover_img,
    vertical_cover_url: fd.vertical_cover_url,
    use_multi_cover: fd.use_multi_cover,
    is_timed_release: fd.is_timed_release,
    time_for_release: fd.time_for_release,
    source_remark_type: (fd.source_remark_detail || {}).type || '',
    source_remark_content: (fd.source_remark_detail || {}).content || [],
    author: fd.author,
    defaultAuthor: fd.defaultAuthor,
  };
}"""


# 保存/发表 API 响应钩子：注入到页面(XHR/fetch 双通道)，把
# /dashboard/save-draft 与 /dashboard/submit-article 的响应原文写入
# localStorage(同源跨页面跳转仍保留)，供后台进程判定成败。
# 背景: 两个接口成功后页面会立即跳转(草稿箱/内容管理)，Playwright 的
# response.text() 此时会报 Network.getResponseBody no resource，必须在
# 页面内先把 body 落袋。
_API_HOOK_JS = """
(() => {
  const KEYS = ['/dashboard/save-draft', '/dashboard/submit-article'];
  const STORE = '__dayu_api_log';
  const hit = (u) => KEYS.some((k) => String(u || '').includes(k));
  const save = (url, status, text) => {
    try {
      const arr = JSON.parse(localStorage.getItem(STORE) || '[]');
      arr.push({url: String(url || ''), status: status, text: String(text || '')});
      localStorage.setItem(STORE, JSON.stringify(arr));
    } catch (e) {}
  };
  try {
    const origFetch = window.fetch;
    if (origFetch) {
      window.fetch = function (...args) {
        const p = origFetch.apply(this, args);
        try {
          p.then((resp) => {
            try {
              const url = (resp && resp.url)
                || (args[0] && (args[0].url || args[0])) || '';
              if (hit(url)) {
                const clone = resp.clone();
                clone.text().then((t) => save(url, resp.status, t))
                  .catch(() => {});
              }
            } catch (e) {}
          });
        } catch (e) {}
        return p;
      };
    }
  } catch (e) {}
  try {
    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url, ...rest) {
      this.__dayu_url = url;
      return origOpen.call(this, method, url, ...rest);
    };
    XMLHttpRequest.prototype.send = function (...args) {
      try {
        this.addEventListener('load', () => {
          try {
            const url = this.__dayu_url || this.responseURL || '';
            if (hit(url)) save(url, this.status, this.responseText);
          } catch (e) {}
        });
      } catch (e) {}
      return origSend.apply(this, args);
    };
  } catch (e) {}
})();
"""


class _DayuApiCapture:
    """监听大鱼号保存/发表 API 响应(页面内钩子 + localStorage 落袋)。

    铁律:发表成功只能以 API 响应判定(禁止 URL 判定)。页面注入的钩子把
    ``POST /dashboard/save-draft`` 与 ``POST /dashboard/submit-article``
    的 status + JSON 原文写进 localStorage；调用方用 :meth:`wait` 取最新
    一条再解析 data._id / data.content_id。
    """

    async def install(self, page) -> None:
        """注入钩子(必须在页面导航前调用)。"""
        try:
            await page.add_init_script(_API_HOOK_JS)
        except Exception as e:
            logger.warning("[文章][大鱼号] 注入 API 钩子失败: %s", e)

    async def read(self, page) -> list:
        try:
            return await page.evaluate(
                """() => {
                  try {
                    return JSON.parse(
                      localStorage.getItem('__dayu_api_log') || '[]');
                  } catch (e) { return []; }
                }"""
            ) or []
        except Exception:
            return []

    async def wait(self, page, key: str, timeout_s: int = 120,
                   since: int = 0) -> dict:
        """等待包含 *key* 的响应并返回(带 json body 与下标 _index)。"""
        deadline = asyncio.get_event_loop().time() + timeout_s
        loop = asyncio.get_event_loop()
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            entries = await self.read(page)
            for idx in range(since, len(entries)):
                item = entries[idx]
                if key not in item.get("url", ""):
                    continue
                text = item.get("text") or ""
                parsed = None
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None
                return {
                    "url": item.get("url", ""),
                    "status": item.get("status"),
                    "text": text,
                    "json": parsed,
                    "_index": idx,
                }
            await asyncio.sleep(0.5)
        raise RuntimeError(
            f"[文章][大鱼号] 等待 {key} 响应超时({timeout_s}s)"
        )


class DayuPlatform(BasePlatform):
    platform_id = 21
    platform_key = "dayu"
    platform_name = "大鱼号"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # 大鱼号 cookie 由 mp.dayu.com 下发，通配 .dayu.com 后对创作中心生效
    platform_cookie_domain = ".dayu.com"

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        - 全部 cookie 归属 ``platform_cookie_domain`` (.dayu.com)
        - expires 给 7 天保守占位，sync_profile 跑完后 storage_state 会被
          回写为真实的 cookie（含真实 expires + localStorage）
        - localStorage 留空，由 sync_profile 自然补全
        """
        cookies: list[dict] = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": self.platform_cookie_domain,
                "path": "/",
                "expires": expires,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            })
        logger.info(
            f"[dayu] cookie 解析: {len(cookies)} 条, domain={self.platform_cookie_domain}"
        )
        return cookies, []

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """大鱼号扫码登录。登录成功后跳转创作中心首页 dashboard/index。"""
        logger.info("=" * 60)
        logger.info("[登录] 开始大鱼号登录流程")
        logger.info("=" * 60)

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                logger.info("[登录] 正在打开大鱼号创作中心...")
                await page.goto(HOME_URL)
                await asyncio.sleep(3)

                # 已登录直接进入首页；未登录会停在登录页
                if await self._is_logged_in(page):
                    logger.info("[登录] 检测到已有登录态，直接保存")
                else:
                    # Extract QR code image
                    src = None
                    qr_selectors = [
                        'img[class*="qrcode"]',
                        'img[class*="qr-code"]',
                        'img[class*="QRCode"]',
                        'img[class*="scan-code"]',
                        'div[class*="qrcode"] img',
                        'div[class*="login"] img',
                    ]
                    for selector in qr_selectors:
                        try:
                            img_locator = page.locator(selector).first
                            if await img_locator.count():
                                src = await img_locator.get_attribute("src")
                                if src and (src.startswith("http") or src.startswith("data:")):
                                    logger.info("[登录] 找到二维码图片，选择器: %s", selector)
                                    break
                                src = None
                        except Exception:
                            continue

                    if src:
                        logger.info("[登录] 二维码图片已发送到前端")
                        status_queue.put(src)
                    else:
                        logger.warning("[登录] 未找到二维码图片，请手动在弹出的浏览器中登录")
                        status_queue.put(json.dumps({"error": "无法找到登录二维码，请在浏览器中手动登录"}))

                    # Wait for login (5 minutes)
                    logger.info("[登录] 等待用户扫码...")
                    max_wait = 300
                    start_time = asyncio.get_event_loop().time()
                    while (asyncio.get_event_loop().time() - start_time) < max_wait:
                        raise_if_page_closed(page, action="登录")
                        try:
                            if await self._is_logged_in(page):
                                logger.info("[登录] 检测到页面跳转到创作中心，登录成功!")
                                break
                        except Exception:
                            pass
                        await asyncio.sleep(1)

                # Scrape profile & save
                logger.info("[登录] 正在获取用户信息...")
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_dayu_profile,
                    account_id=account_id,
                    # 登录成功后在同一个 session 内补抓 stats(昨日播放/本月收益/粉丝数)
                    stats_fn=self._login_stats_fn,
                )
                logger.info("[登录] 登录流程完成!")
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await browser.close()

    @staticmethod
    async def _is_logged_in(page) -> bool:
        """登录成功的标志：顶栏出现用户头像区(.header-user)。"""
        try:
            if await page.locator(".header-user").count():
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid."""
        logger.info("[Cookie检查] 开始检查cookie有效性: %s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)

                if await page.locator(".header-user").count():
                    logger.info("[Cookie检查] Cookie有效，顶栏用户区存在")
                    return True

                logger.warning("[Cookie检查] Cookie无效，未找到顶栏用户区")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — refresh user name / avatar / stats
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步大鱼号昵称、头像、运营数据(stats)。

        创作中心首页 (https://mp.dayu.com/dashboard/index) 顶部条:
          - 头像: .header-user img
          - 昵称: .header-info .name

        运营数据在 .index2-summary 区块,每个 .index2-summary_data 含
        标题(.index2-summary_data_header)和数值(.index2-summary_data_body)。
        无数据时页面显示 "--",按 0 处理。
        """
        logger.info("[同步资料] 开始同步用户资料: %s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                try:
                    await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(3)

                name, avatar = await scrape_dayu_profile(page)
                stats = await self._scrape_stats(page)
                logger.info(
                    "[同步资料] 获取到用户信息 - 昵称: %s, 头像: %s, stats: %d 项",
                    name, avatar[:50] if avatar else "无", len(stats),
                )

                if not name and not avatar and not stats:
                    logger.info(f"[dayu] sync_profile 抓取为空,url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            finally:
                await context.close()
        finally:
            await browser.close()

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。"""
        return await self._scrape_stats(page)

    @staticmethod
    async def _scrape_stats(page) -> list:
        """抓取首页 .index2-summary 运营数据。

        label_map: 标题文本 -> (ICON, SORT, 标准化 NAME)。
        "我的成长"是等级文本(非数字)不计入 stats;"--" 按 0 处理。
        """
        try:
            await page.wait_for_selector(".index2-summary_data", timeout=8000)
        except Exception:
            logger.info("[dayu stats] 等待 .index2-summary_data 超时")

        try:
            result = await page.evaluate(
                '''() => {
                    const out = [];
                    document.querySelectorAll('.index2-summary_data').forEach(item => {
                        const titleEl = item.querySelector('.index2-summary_data_header');
                        const bodyEl = item.querySelector('.index2-summary_data_body');
                        if (!titleEl || !bodyEl) return;
                        const title = (titleEl.textContent || '').trim();
                        const num = (bodyEl.textContent || '').trim();
                        if (title && num) out.push({title, num});
                    });
                    return out;
                }'''
            )
        except Exception as e:
            logger.info("[dayu stats] 抓取失败: %s", e)
            return []

        label_map = {
            "昨日阅读/播放": ("play", 1, "昨日阅读/播放"),
            "本月收益":     ("coin", 2, "本月收益"),
            "粉丝数":       ("user", 3, "粉丝数"),
        }
        stats = []
        for item in (result or []):
            title = item.get("title", "")
            num_str = str(item.get("num", "0"))
            # 标题里可能带问号图标文字,用前缀匹配
            matched = next((k for k in label_map if title.startswith(k)), None)
            if not matched:
                continue
            icon, sort_no, std_name = label_map[matched]
            cleaned = (
                num_str.replace("￥", "").replace("¥", "")
                .replace(",", "").replace(" ", "").strip()
            )
            try:
                count = int(float(cleaned)) if cleaned else 0
            except (ValueError, TypeError):
                count = 0  # "--" 等非数字按 0
            stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
        return stats

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Dayu creator centre in a visible browser window."""
        logger.info("[打开创作中心] 正在打开创作中心...")
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(HOME_URL)
                logger.info("[打开创作中心] 创作中心已打开")
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
    # publish_video — full Dayu upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Dayu via CloakBrowser."""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始大鱼号视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", [])
        category = kwargs.get("category", "") or ""
        desc = kwargs.get("desc", "")
        enableTimer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        # 16:9 / 9:16 次尺寸封面(大鱼号横版视频封面用 16:9,竖版封面用 9:16)
        thumbnail_landscape_169_path = kwargs.get("thumbnail_landscape_169_path", "")
        thumbnail_portrait_916_path = kwargs.get("thumbnail_portrait_916_path", "")
        # 信息来源(作品声明): 无需标注/AI生成/虚构演绎/营销信息/转载/个人观点/不适宜未成年人
        creation_declaration = kwargs.get("creation_declaration", "") or ""
        # 信息来源=转载 时的原文链接(必填)
        dayu_repost_url = kwargs.get("dayu_repost_url", "") or ""

        if isinstance(category, list):
            # 前端级联组件可能传数组,取末级文本
            category = category[-1] if category else ""
        category = str(category).strip()

        # 打印发布参数
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频分类: %s", category or "未选择")
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 信息来源: %s", creation_declaration or "未选择(默认无需标注)")
        logger.info("[发布参数] 转载原文链接: %s", dayu_repost_url or "无")
        logger.info("[发布参数] 横版16:9封面: %s", thumbnail_landscape_169_path or "无")
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版9:16封面: %s", thumbnail_portrait_916_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")

        if len(title) < MIN_TITLE_LENGTH:
            raise RuntimeError(
                f"大鱼号标题至少 {MIN_TITLE_LENGTH} 个字 (当前 {len(title)} 字)"
            )

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(f) for f in files]

        # Determine publish strategy and schedule times
        publish_strategy = "scheduled" if enableTimer and schedule_time_str else "immediate"
        logger.info("[发布策略] 发布策略: %s", publish_strategy)
        if schedule_time_str:
            logger.info("[发布策略] 定时发布时间: %s", schedule_time_str)

        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(file_paths),
            enableTimer,
            videos_per_day,
            daily_times,
            start_days,
        )

        for file_index, file_path in enumerate(file_paths):
            logger.info("-" * 40)
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s", file_index + 1, len(file_paths), file_path)
            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                    await self._upload_one_video(
                        title=title,
                        file_path=file_path,
                        tags=tags,
                        publish_date=publish_datetimes[file_index],
                        account_file=cookie_path,
                        publish_strategy=publish_strategy,
                        desc=desc,
                        category=category,
                        thumbnail_landscape_path=thumbnail_landscape_path or None,
                        thumbnail_portrait_path=thumbnail_portrait_path or None,
                        thumbnail_landscape_169_path=thumbnail_landscape_169_path or None,
                        thumbnail_portrait_916_path=thumbnail_portrait_916_path or None,
                        creation_declaration=creation_declaration,
                        dayu_repost_url=dayu_repost_url,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        publish_strategy: str,
        desc="",
        category="",
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_landscape_169_path=None,
        thumbnail_portrait_916_path=None,
        creation_declaration="",
        dayu_repost_url="",
    ):
        """Upload a single video to one Dayu account."""
        logger.info("[上传视频] 开始上传视频: %s", file_path)
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()
                await self._open_write_page(page)

                # Upload video file
                logger.info("[上传视频] 正在上传视频文件...")
                file_input_idx = await page.evaluate(
                    """() => {
                        const inputs = [...document.querySelectorAll('input[type=file]')];
                        for (let i = 0; i < inputs.length; i++) {
                            const accept = (inputs[i].accept || '').toLowerCase();
                            if (!accept || accept.includes('video')) return i;
                        }
                        return -1;
                    }"""
                )
                if file_input_idx >= 0:
                    file_input = page.locator('input[type="file"]').nth(file_input_idx)
                else:
                    file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择，等待上传完成...")

                # Wait for upload to complete:
                # 上传中: .article-write_video-container-uploading (进度条/百分比)
                # 完成:   .article-write_video-container-result 出现"视频上传成功"
                max_wait = 14400  # 4 hours for large files
                start_time = asyncio.get_event_loop().time()
                upload_complete = False
                last_progress = ""
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    raise_if_page_closed(page)
                    try:
                        result_box = page.locator(".article-write_video-container-result")
                        if await result_box.count():
                            result_text = (await result_box.text_content() or "").strip()
                            if "视频上传成功" in result_text:
                                upload_complete = True
                                logger.info("[上传视频] 视频上传成功!")
                                break
                        # 打印上传进度
                        progress_text = page.locator(".article-write_video-container-uploading_status")
                        if await progress_text.count():
                            current_progress = (
                                (await progress_text.first.text_content() or ""
                                 ).strip().replace("\n", " ")
                            )
                            if current_progress and current_progress != last_progress:
                                logger.info("[上传视频] %s", current_progress)
                                last_progress = current_progress
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                if not upload_complete:
                    raise RuntimeError(f"[上传视频] 视频上传超时! 已等待 {max_wait} 秒")

                await asyncio.sleep(2)

                # 检测横竖版(上传结果里会提示"检测为竖版视频")
                is_portrait = False
                try:
                    resolution_tip = page.locator(".video-resulotion-result")
                    if await resolution_tip.count():
                        tip_text = (await resolution_tip.first.text_content() or "").strip()
                        if "竖版" in tip_text:
                            is_portrait = True
                            logger.info("[视频类型] 检测到竖版视频")
                        else:
                            logger.info("[视频类型] 检测到横版视频")
                except Exception:
                    logger.info("[视频类型] 默认为横版视频")

                # ---- 填写标题(contenteditable,最少5字/最多60字) ----
                logger.info("[填写标题] 标题: %s", title[:MAX_TITLE_LENGTH])
                title_input = page.locator(".w-form-field-content-editable").first
                await title_input.wait_for(state="visible", timeout=10000)
                await clear_and_type(page, title[:MAX_TITLE_LENGTH], title_input)
                await asyncio.sleep(0.5)
                # 标题框带 tribute 联想(data-tribute),按 Esc 关闭联想下拉
                try:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                except Exception:
                    pass
                logger.info("[填写标题] 标题填写完成")

                # ---- 填写视频简介(textarea,最多200字) ----
                if desc:
                    logger.info("[填写简介] 开始填写视频简介...")
                    desc_input = page.locator(".w-form-field-textarea textarea").first
                    if await desc_input.count():
                        await desc_input.fill(desc[:MAX_DESC_LENGTH])
                        logger.info("[填写简介] 视频简介填写成功!")
                    else:
                        logger.warning("[填写简介] 未找到视频简介输入框!")
                else:
                    logger.info("[填写简介] 无视频简介")

                # ---- 设置视频分类(必选) ----
                if category:
                    logger.info("[设置分类] 开始设置视频分类: %s", category)
                    await self._set_category(page, category)
                else:
                    logger.info("[设置分类] 未选择分类(默认保持页面初始值)")

                # ---- 填写标签(最多10个) ----
                if tags:
                    logger.info("[填写标签] 开始填写标签: %s", tags[:MAX_TAGS])
                    await self._fill_tags(page, tags[:MAX_TAGS])
                    logger.info("[填写标签] 标签填写完成")
                else:
                    logger.info("[填写标签] 无标签")

                # ---- 设置封面 ----
                # 视频封面(必填,横版 16:9) + 竖版封面(选填,9:16)
                landscape_cover = thumbnail_landscape_169_path or thumbnail_landscape_path
                portrait_cover = thumbnail_portrait_916_path or thumbnail_portrait_path
                if landscape_cover or portrait_cover:
                    logger.info("[设置封面] 开始设置封面...")
                    await self._set_covers(page, landscape_cover, portrait_cover)
                    logger.info("[设置封面] 封面设置完成")
                else:
                    logger.info("[设置封面] 无自定义封面")

                # ---- 信息来源(作品声明,必选) ----
                declaration = creation_declaration or "无需标注"
                if not creation_declaration:
                    logger.info("[设置声明] 未选择信息来源,默认选择「无需标注」")
                logger.info("[设置声明] 开始设置信息来源: %s", declaration)
                await self._set_source_remark(page, declaration, dayu_repost_url)
                logger.info("[设置声明] 信息来源设置完成")

                # ---- 定时发布(只能选 5 分钟间隔,7 天范围内) ----
                # _set_schedule_time 任一步失败都会抛 RuntimeError 中止发布,
                # 避免定时设置失败后视频被立即发布。
                if publish_strategy == "scheduled" and publish_date != 0:
                    logger.info("[定时发布] 开始设置定时发布时间: %s", publish_date)
                    await self._set_schedule_time(page, publish_date)

                # ---- 点击发表 ----
                # 主定位: data-spm-click 属性的语义段(阿里 SPM 埋点协议的稳定部分,
                # 属性值里的 wmid 是账号级随机 hex,不做匹配依据)。
                # 兜底: 限定 .article-write_box-opt 容器(发表/预览/清空/保存 按钮组的
                # 固定父级,语义 class)——has_text 是子串匹配,不限容器会误中
                # 预览弹窗里的「确认发表」按钮。
                if manual_review_enabled('dayu', 'video'):
                    # 人工验收：保留页面，用户亲自点「发表」及二次弹窗
                    # 「确认发表」，程序不再点击。成功判定沿用自动分支：
                    # 跳转 /dashboard/contents（is_success_url('dayu') 同款）。
                    await wait_for_manual_publish(page, 'dayu')
                else:
                    logger.info("[发布] 正在点击发表按钮...")
                    publish_btn = page.locator('button[data-spm-click*="videowrite.publish"]')
                    if not await publish_btn.count():
                        publish_btn = page.locator(
                            '.article-write_box-opt button.w-btn_primary', has_text="发表"
                        )
                    await publish_btn.first.click()

                    # 等待发布结果:处理二次弹窗,成功则跳转 /dashboard/contents
                    await self._wait_publish_result(page)

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ------------------------------------------------------------------
    # Helper: wait for publish result (popups + redirect)
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_publish_result(page, timeout_s: int = 180):
        """点击「发表」后等待发布结果。

        需要处理的弹窗(出现哪个点哪个,可重复出现):
          1. 「视频画质过低提醒」-> 点击「继续上传」
          2. 「视频预览」二次确认 -> 点击「确认发表」

        成功标志:页面跳转到 https://mp.dayu.com/dashboard/contents
        """
        logger.info("[发布] 等待发布结果...")
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout_s:
            raise_if_page_closed(page)
            try:
                # 1. 画质过低提醒 -> 继续上传
                low_quality_pop = page.locator(
                    '.widgets-pop_container:has-text("视频画质过低")'
                )
                if await low_quality_pop.count():
                    continue_btn = low_quality_pop.locator(
                        'button', has_text="继续上传"
                    )
                    if await continue_btn.count():
                        await continue_btn.first.click()
                        logger.info("[发布] 已点击「继续上传」(画质过低提醒)")
                        await asyncio.sleep(1)
                        continue

                # 2. 视频预览确认弹窗 -> 确认发表
                confirm_btn = page.locator(
                    '.article-write-preview_btn button', has_text="确认发表"
                )
                if await confirm_btn.count():
                    await confirm_btn.first.click()
                    logger.info("[发布] 已点击「确认发表」(视频预览弹窗)")
                    await asyncio.sleep(1)
                    continue

                # 3. 跳转到内容管理页 = 发布成功
                if "/dashboard/contents" in page.url:
                    logger.info("[发布] 视频发布成功! 页面跳转到: %s", page.url)
                    return
            except Exception:
                pass
            await asyncio.sleep(1)

        raise RuntimeError(
            f"[发布] 等待发布结果超时({timeout_s}s),页面未跳转到内容管理页"
        )

    # ------------------------------------------------------------------
    # Helper: open video write page (hover 发布内容 -> 短视频)
    # ------------------------------------------------------------------

    @staticmethod
    async def _open_write_page(page):
        """直接跳转视频发布页(不再走 首页悬停「发布内容」→「短视频」 的不稳定路径)。"""
        logger.info("[上传视频] 正在直接打开视频发布页: %s", WRITE_URL)
        try:
            await page.goto(WRITE_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            raise RuntimeError(f"[上传视频] 打开视频发布页失败(cookie 可能失效或网络异常): {e}")
        # 等待发布页核心容器出现,确认页面加载完成
        # (未登录时大鱼号会重定向到登录页,不会出现 article-write 系列容器)
        try:
            await page.wait_for_selector("[class*='article-write']", timeout=20000)
        except Exception as e:
            raise RuntimeError(
                f"[上传视频] 发布页未加载出编辑区(可能未登录被重定向到 {page.url}): {e}"
            )
        logger.info("[上传视频] 发布页面已打开: %s", page.url)

    # ------------------------------------------------------------------
    # Helper: set video category
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_category(page, category: str):
        """点击分类下拉,选择与 category 文本一致的选项。"""
        try:
            container = page.locator(".widgets-selects_container").first
            if not await container.count():
                logger.warning("[设置分类] 未找到分类下拉组件!")
                return
            await container.click()
            await asyncio.sleep(1)

            options = page.locator(".widgets-selects_select_container a")
            count = await options.count()
            target = None
            fallback_other = None
            for i in range(count):
                text = (await options.nth(i).text_content() or "").strip()
                if text == category:
                    target = options.nth(i)
                    break
                if text == "其他":
                    fallback_other = options.nth(i)
            if target is None:
                logger.warning("[设置分类] 未找到分类「%s」,回退选择「其他」", category)
                target = fallback_other
            if target is not None:
                await target.click()
                await asyncio.sleep(0.5)
                logger.info("[设置分类] 分类已选择")
            else:
                logger.warning("[设置分类] 分类选项列表为空!")
        except Exception as e:
            logger.error("[设置分类] 设置视频分类失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: fill tags (max 10, type + Enter, 1s interval)
    # ------------------------------------------------------------------

    @staticmethod
    async def _fill_tags(page, tags: list):
        """点击标签输入区激活输入组件,逐个输入标签并回车。"""
        try:
            tags_box = page.locator(".article-write_video-tags").first
            if not await tags_box.count():
                logger.warning("[填写标签] 未找到标签输入区!")
                return
            await tags_box.click()
            await asyncio.sleep(1)

            tag_input = tags_box.locator("input")
            for i, tag in enumerate(tags):
                if not tag:
                    continue
                logger.info("[填写标签] 填写第 %d 个标签: %s", i + 1, tag)
                if await tag_input.count():
                    await tag_input.first.click()
                # 打字机效果逐字符输入(比 fill 可靠,能触发输入框 onChange)
                await page.keyboard.type(str(tag), delay=100)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)

            logger.info("[填写标签] 所有标签填写完成")
        except Exception as e:
            logger.error("[填写标签] 填写标签失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set covers (视频封面 + 竖版封面,上传后点弹窗「保存」)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_covers(page, landscape_cover=None, portrait_cover=None):
        """设置视频封面(横版)和竖版封面。

        - 视频封面: #coverImg 内隐藏 input[type=file](16:9 横版)
        - 竖版封面: .article-write_box-vertical-cover 内 input[type=file](9:16)
        - 上传后弹出截取窗口,直接点击弹窗内的「保存」按钮
        """
        try:
            if landscape_cover:
                cover_input = page.locator("#coverImg input[type='file']").first
                if await cover_input.count():
                    logger.info("[设置封面] 上传视频封面(横版): %s", landscape_cover)
                    await cover_input.set_input_files(landscape_cover)
                    await asyncio.sleep(2)
                    await DayuPlatform._click_cover_dialog_save(page)
                else:
                    logger.warning("[设置封面] 未找到视频封面上传入口!")

            if portrait_cover:
                vertical_input = page.locator(
                    ".article-write_box-vertical-cover input[type='file']"
                ).first
                if await vertical_input.count():
                    logger.info("[设置封面] 上传竖版封面: %s", portrait_cover)
                    await vertical_input.set_input_files(portrait_cover)
                    await asyncio.sleep(2)
                    await DayuPlatform._click_cover_dialog_save(page)
                else:
                    logger.warning("[设置封面] 未找到竖版封面上传入口!")
        except Exception as e:
            logger.error("[设置封面] 设置封面失败: %s", e)

    @staticmethod
    async def _click_cover_dialog_save(page):
        """点击封面截取弹窗里的「保存」按钮(.widgets-pop_container 内 w-btn_primary)。"""
        try:
            save_btn = page.locator(
                ".widgets-pop_container button.w-btn_primary", has_text="保存"
            )
            if await save_btn.count():
                await save_btn.first.click()
                logger.info("[设置封面] 已点击封面弹窗「保存」")
                await asyncio.sleep(1.5)
            else:
                logger.info("[设置封面] 未出现封面截取弹窗,跳过保存")
        except Exception as e:
            logger.warning("[设置封面] 点击封面弹窗「保存」失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set 信息来源 (source remark radio + 转载原文链接)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_source_remark(page, declaration: str, repost_url: str = ""):
        """选择信息来源单选项;选「转载」时填写必填的原文链接。

        radio 的 value 与文案一致(无需标注/AI生成/虚构演绎/营销信息/转载/
        个人观点/不适宜未成年人),点击对应 label.ant-radio-wrapper。
        """
        try:
            wrapper = page.locator(
                "label.ant-radio-wrapper", has_text=declaration
            ).first
            if await wrapper.count():
                await wrapper.click()
                logger.info("[设置声明] 已选择信息来源: %s", declaration)
                await asyncio.sleep(0.5)
            else:
                logger.warning("[设置声明] 未找到信息来源选项: %s", declaration)
                return

            if declaration == "转载":
                if not repost_url:
                    raise RuntimeError("信息来源选择「转载」时必须填写原文链接")
                link_input = page.locator('input.ant-input[placeholder*="原文链接"]').first
                if not await link_input.count():
                    link_input = page.locator(
                        ".source-remark-detail input.ant-input"
                    ).first
                if await link_input.count():
                    await link_input.wait_for(state="visible", timeout=5000)
                    await link_input.fill(repost_url)
                    logger.info("[设置声明] 原文链接已填写: %s", repost_url)
                else:
                    raise RuntimeError("未找到原文链接输入框")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("[设置声明] 设置信息来源失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set schedule time (datetimepicker, 5-minute interval)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """设置定时发布时间(视频发布页)。

        大鱼号定时发布组件只能选 5 分钟间隔(11:05/11:10...),7 天范围内。
        流程:点击「定时发布」开关 -> 出现日期组件 -> 依次选择 日/时/分。

        目标分钟数向上取整到 5 的倍数(避免比用户指定时间早发布)。
        """
        try:
            # 1. 点击「定时发布」开关
            timer_radio = page.locator(
                '.article-write_radio:has-text("定时发布") .w-radio'
            ).first
            if not await timer_radio.count():
                raise RuntimeError("未找到「定时发布」开关")
            await timer_radio.click()
            await asyncio.sleep(1)
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"[定时发布] 设置定时发布时间失败: {e}") from e
        await DayuPlatform._pick_datetime_calendar(page, publish_date)

    @staticmethod
    async def _set_article_schedule_time(page, publish_date):
        """设置图文文章定时发布时间。

        两个坑(2026-10 实测):
          1. 图文页「定时发布」radio 尺寸为 0, Playwright click 报
             "element is not visible" → 用 JS 触发 click。
          2. 日期弹层是 bootstrap-datetimepicker(jQuery 插件), 只认真实
             鼠标 mousedown 事件; 合成事件点 span.hour/span.minute 不提交,
             控件值一直是 formData 默认值(当前时间 +2 小时)。因此先尝试
             日历点击, 未生效时直接写页面 Vue 模型 formData.time_for_release
             (保存/发表接口的取数来源), 再校验控件显示与模型一致。
        """
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              for (const el of document.querySelectorAll(
                  '.article-write_radio')) {
                if (!vis(el)) continue;
                const txt = (el.innerText || '').trim();
                if (!txt.includes('定时发布')) continue;
                const radio = el.querySelector('.w-radio');
                (radio || el).click();
                return true;
              }
              return false;
            }"""
        )
        if not clicked:
            raise RuntimeError("[定时发布] 未找到「定时发布」开关")
        await asyncio.sleep(2.5)
        form = await DayuPlatform._read_article_form(page)
        if form and not form.get("is_timed_release"):
            raise RuntimeError(
                "[定时发布] 点击「定时发布」开关后未开启(is_timed_release=false)"
            )

        # 目标时间对齐到 5 分钟粒度(大鱼号只支持 5 分钟间隔)
        minute = publish_date.minute
        snapped = ((minute + 4) // 5) * 5
        target = publish_date + timedelta(minutes=snapped - minute)
        target_ts = int(target.timestamp() * 1000)
        logger.info(
            "[定时发布] 图文定时目标时间: %s (原 %s)",
            target.strftime("%Y-%m-%d %H:%M"),
            publish_date.strftime("%Y-%m-%d %H:%M"),
        )

        # 先走一遍日历 UI(平台组件行为变化时仍能正确设置)
        try:
            await DayuPlatform._pick_datetime_calendar(page, publish_date)
        except Exception as e:
            logger.warning("[定时发布] 日历点击未完成(转写表单模型): %s", e)
        await asyncio.sleep(1)
        await DayuPlatform._write_article_schedule_model(page, target_ts)

        # 校验模型与控件显示
        final = await DayuPlatform._read_article_form(page)
        got = int(final.get("time_for_release") or 0)
        if not final.get("is_timed_release") or abs(got - target_ts) > 60000:
            raise RuntimeError(
                "[文章][大鱼号] 定时时间设置失败: 期望 "
                f"{target.strftime('%Y-%m-%d %H:%M')}, 实际 ts={got}"
            )
        shown = await page.evaluate(
            """() => {
              const el = document.querySelector(
                '.widgets-datepicker-m_input');
              return el ? el.value : '';
            }"""
        )
        logger.info(
            "[定时发布] 图文定时已设置: %s (控件显示: %s)",
            target.strftime("%Y-%m-%d %H:%M"), shown or "无",
        )

    @staticmethod
    async def _write_article_schedule_model(page, target_ts: int):
        """把定时时间写入页面 Vue 模型(日期控件合成点击不提交时的兜底)。"""
        result = await page.evaluate(
            """(ts) => {
              const seen = new Set();
              const stack = [document.body];
              let vm = null;
              while (stack.length) {
                const el = stack.pop();
                if (!el || seen.has(el)) continue;
                seen.add(el);
                if (el.__vue__) {
                  let v = el.__vue__;
                  while (v) {
                    if (v.formData && 'title' in v.formData) {
                      vm = v; break;
                    }
                    v = v.$parent;
                  }
                  if (vm) break;
                }
                for (const c of el.children) stack.push(c);
              }
              if (!vm) return null;
              vm.formData.is_timed_release = true;
              vm.formData.time_for_release = ts;
              try { vm.$forceUpdate(); } catch (e) {}
              // 尝试同步日期组件显示(组件暴露 setValue 时)
              try {
                const root = document.querySelector(
                  '.widgets-datepicker-m');
                const dv = root && root.__vue__;
                if (dv) {
                  if (typeof dv.setValue === 'function') dv.setValue(ts);
                  else if ('model' in dv) dv.model = ts;
                }
              } catch (e) {}
              return vm.formData.time_for_release;
            }""",
            target_ts,
        )
        if result is None:
            raise RuntimeError(
                "[文章][大鱼号] 未找到页面 Vue 实例, 无法写入定时时间"
            )
        logger.info("[定时发布] 已写入表单模型 time_for_release=%s", result)
        await asyncio.sleep(1)

    @staticmethod
    async def _pick_datetime_calendar(page, publish_date):
        """在已展开的日期组件里依次选择 日/时/分(5 分钟粒度)。

        组件结构: .widgets-datepicker-m > input + img + .widgets-datepicker-m_mask。
        mask 遮罩在真正 input 之上, Playwright 直接点 input 会被拦截; 这里用
        JS 点 mask(不依赖可见性/遮挡), 对视频页/图文页都稳定。
        失败一律抛错: 定时设置失败若继续点「发表」会导致立即发布。
        """
        # 分钟向上取整到 5 的倍数
        minute = publish_date.minute
        snapped = ((minute + 4) // 5) * 5
        target = publish_date + timedelta(minutes=snapped - minute)
        logger.info(
            "[定时发布] 目标时间 %s (原 %s,对齐到 5 分钟间隔)",
            target.strftime("%Y-%m-%d %H:%M"),
            publish_date.strftime("%Y-%m-%d %H:%M"),
        )

        try:
            # 2. 点击日期组件弹出日/时/分选择
            raise_if_page_closed(page, action="定时发布")
            date_input = page.locator(".widgets-datepicker-m_input").first
            # mask 覆盖在 input 上且自身尺寸可能为 0, 这里只等 attached,
            # 实际展开用 JS 点 mask(不依赖可见性/遮挡判断)。
            await date_input.wait_for(state="attached", timeout=10000)
            opened = await page.evaluate(
                """() => {
                  const mask = document.querySelector(
                    '.widgets-datepicker-m_mask');
                  if (mask) { mask.click(); return 'mask'; }
                  const input = document.querySelector(
                    '.widgets-datepicker-m_input');
                  if (input) { input.click(); return 'input'; }
                  return null;
                }"""
            )
            if not opened:
                raise RuntimeError("未找到定时日期组件入口")
            await asyncio.sleep(1)

            # 3-5. 选择 日 / 时 / 分。
            # 日历弹层由第三方 datepicker 渲染, 位置常在视口外(top-right)
            # 且页面可能残留多个实例, Playwright click 会卡「waiting for
            # element to be visible/stable」; 统一用 JS 在「当前可见实例」
            # 内精确匹配文案后 click(不依赖遮挡与视口位置)。
            for _ in range(2):  # 最多跨 1 个月
                raise_if_page_closed(page, action="定时发布")
                switch_text = await page.evaluate(
                    """() => {
                      const views = [...document.querySelectorAll(
                        '.datetimepicker-days')];
                      const view = views.find((v) => v.offsetParent !== null)
                        || views[0];
                      const th = view && view.querySelector('th.switch');
                      return th ? (th.textContent || '').trim() : '';
                    }"""
                )
                shown = _parse_switch(switch_text)
                if shown == (target.year, target.month):
                    break
                if shown == (0, 0):
                    raise RuntimeError(
                        f"无法解析日历月份标题: {switch_text!r}"
                    )
                direction = (
                    "next" if (target.year, target.month) > shown else "prev"
                )
                navigated = await page.evaluate(
                    """(direction) => {
                      const tap = (el) => {
                        const opts = {bubbles: true, cancelable: true,
                                      view: window, button: 0};
                        el.dispatchEvent(new MouseEvent('mousedown', opts));
                        el.dispatchEvent(new MouseEvent('mouseup', opts));
                        el.dispatchEvent(new MouseEvent('click', opts));
                      };
                      const views = [...document.querySelectorAll(
                        '.datetimepicker-days')];
                      const view = views.find((v) => v.offsetParent !== null)
                        || views[0];
                      const th = view && view.querySelector(
                        'th.' + direction);
                      if (!th) return 'no-arrow';
                      if (getComputedStyle(th).visibility === 'hidden') {
                        return 'hidden-arrow';
                      }
                      tap(th);
                      return 'ok';
                    }""",
                    direction,
                )
                if navigated != "ok":
                    raise RuntimeError(
                        f"日历无法从 {switch_text} 导航到 "
                        f"{target.year}-{target.month:02d}"
                        "(超出可选范围,大鱼号定时仅支持 7 天内)"
                    )
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError(
                    f"日历翻页 2 次后仍未对齐到 "
                    f"{target.year}-{target.month:02d}"
                )

            raise_if_page_closed(page, action="定时发布")
            picked = await page.evaluate(
                """(day) => {
                  const tap = (el) => {
                    const opts = {bubbles: true, cancelable: true,
                                  view: window, button: 0};
                    el.dispatchEvent(new MouseEvent('mousedown', opts));
                    el.dispatchEvent(new MouseEvent('mouseup', opts));
                    el.dispatchEvent(new MouseEvent('click', opts));
                  };
                  const views = [...document.querySelectorAll(
                    '.datetimepicker-days')];
                  const view = views.find((v) => v.offsetParent !== null)
                    || views[0];
                  if (!view) return 'no-view';
                  const cells = [...view.querySelectorAll('td.day')].filter(
                    (td) => !td.classList.contains('old')
                      && !td.classList.contains('new')
                      && !td.classList.contains('disabled')
                      && (td.textContent || '').trim() === String(day));
                  if (!cells.length) return 'no-day';
                  tap(cells[0]);
                  return 'ok';
                }""",
                target.day,
            )
            if picked != "ok":
                raise RuntimeError(
                    f"日期面板未找到可点击的 {target.month}月{target.day}日"
                    f"({picked})"
                )
            logger.info("[定时发布] 日期已选择: %s 日", target.day)
            await asyncio.sleep(0.6)

            # 4. 选择小时(.datetimepicker-hours)
            raise_if_page_closed(page, action="定时发布")
            hour_picked = await page.evaluate(
                """(cands) => {
                  const tap = (el) => {
                    const opts = {bubbles: true, cancelable: true,
                                  view: window, button: 0};
                    el.dispatchEvent(new MouseEvent('mousedown', opts));
                    el.dispatchEvent(new MouseEvent('mouseup', opts));
                    el.dispatchEvent(new MouseEvent('click', opts));
                  };
                  const views = [...document.querySelectorAll(
                    '.datetimepicker-hours')];
                  const view = views.find((v) => v.offsetParent !== null)
                    || views[0];
                  if (!view) return 'no-view';
                  const opts = [...view.querySelectorAll('span.hour')];
                  const hit = opts.find((o) => cands.includes(
                    (o.textContent || '').trim()));
                  if (!hit) return 'no-hour';
                  tap(hit);
                  return 'ok';
                }""",
                [f"{target.hour}:00", f"{target.hour:02d}:00"],
            )
            if hour_picked != "ok":
                raise RuntimeError(
                    f"小时面板未找到 {target.hour}:00 选项({hour_picked})"
                )
            logger.info("[定时发布] 小时已选择: %s", target.hour)
            await asyncio.sleep(0.6)

            # 5. 选择分钟(.datetimepicker-minutes,5 分钟间隔)
            raise_if_page_closed(page, action="定时发布")
            want_minute = f"{target.hour:02d}:{target.minute:02d}"
            minute_picked = await page.evaluate(
                """(cands) => {
                  const tap = (el) => {
                    const opts = {bubbles: true, cancelable: true,
                                  view: window, button: 0};
                    el.dispatchEvent(new MouseEvent('mousedown', opts));
                    el.dispatchEvent(new MouseEvent('mouseup', opts));
                    el.dispatchEvent(new MouseEvent('click', opts));
                  };
                  const views = [...document.querySelectorAll(
                    '.datetimepicker-minutes')];
                  const view = views.find((v) => v.offsetParent !== null)
                    || views[0];
                  if (!view) return 'no-view';
                  const opts = [...view.querySelectorAll('span.minute')]
                    .map((o) => ({
                      el: o, text: (o.textContent || '').trim(),
                    }));
                  let hit = opts.find((o) => cands.includes(o.text));
                  // 兜底: 匹配「*:MM」结尾(小时补零样式不一致时)
                  if (!hit && cands.length) {
                    const suffix = cands[0].slice(-3);
                    hit = opts.find((o) => o.text.endsWith(suffix));
                  }
                  if (!hit) return 'no-minute';
                  tap(hit.el);
                  return 'ok';
                }""",
                [want_minute, f"{target.hour}:{target.minute:02d}",
                 f"{target.hour:02d}:{target.minute}"],
            )
            if minute_picked != "ok":
                raise RuntimeError(
                    f"分钟面板未找到 {want_minute} 选项(5 分钟间隔)"
                    f"({minute_picked})"
                )
            logger.info("[定时发布] 分钟已选择: %s", want_minute)
            logger.info(
                "[定时发布] 定时发布时间设置完成: %s",
                target.strftime("%Y-%m-%d %H:%M"),
            )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"[定时发布] 设置定时发布时间失败: {e}") from e

    # ==================================================================
    # publish_article — 图文文章发布(标题 + 富文本正文 + 封面 + 信息来源 + 定时)
    # ==================================================================
    #
    # 编辑器结构(2026-10 实测, https://mp.dayu.com/dashboard/article/write):
    #   - 标题:  input#title.article-write_box-title-input(最少 5 / 最多 50 字)
    #   - 正文:  UEditor, iframe#ueditor_0 → body[contenteditable]
    #   - 正文图/封面图: 页面内 fetch /ueditor/controller?action=uploadimage
    #            (field=upfile, ≤5MB) → https://mp.dayu.com/dayu/image?...
    #   - 作者名称: 选填(声明原创时才必填；本账号无原创入口)
    #   - 横版封面: 默认「三封面」需 3 张才能过校验 → 统一切「单封面」
    #            (单封面且无封面图也能发表); 封面只能从「正文图片」中选
    #   - 竖版封面: 选填, 本实现不设置
    #   - 信息来源: 必选 radio(无需标注/AI生成/虚构演绎/营销信息/转载/
    #            个人观点/不适宜未成年人)
    #   - 其他设置: 定时发布(datepicker, 与视频页同一 widgets-datepicker-m)
    #   - 保存/发表: 按钮事件绑定在 mousedown(不是 click)
    #       保存 → POST /dashboard/save-draft → 跳 /dashboard/draft
    #       发表 → POST /dashboard/save-draft → 预览弹窗「确认发表」
    #              → POST /dashboard/submit-article → 跳 /dashboard/contents
    #   注意: 「分类」article_type 由平台默认(1)，页面无分类控件；
    #   原创声明入口(original=0)本账号未开通。

    def publish_article(self, **kwargs) -> bool:
        """发布图文文章到大鱼号(同步入口)。

        kwargs:
            title (*str*) -- 文章标题(5~50 字)
            html (*str*) -- 正文 HTML(img src 指向本地素材/本地绝对路径,
                自动上传大鱼号图床后替换为 CDN URL)
            account_file (*list[str]*) -- cookie 文件名列表
            cover_path (*str*, optional) -- 封面图本地路径/素材 URL
                (大鱼号封面只能从正文图片中选择 → 会在正文末尾临时插图,
                封面设置成功后再尝试移除, 详见 _set_article_cover)
            dayu_source_remark (*str*, optional) -- 信息来源, 默认「无需标注」
                可选: 无需标注/AI生成/虚构演绎/营销信息/转载/个人观点/
                不适宜未成年人
            dayu_original_url (*str*, optional) -- 信息来源=转载 时的原文链接
            author (*str*, optional) -- 作者名称(编辑器「作者名称」, ≤10 字)
            is_draft (*bool*) -- True(默认)= 保存草稿; False = 真实发表
            dry_run (*bool*) -- True = 强制保存草稿(不发表)
            schedule_time_str (*str*, optional) -- 定时发表时间
                (仅 is_draft=False 时生效; 当前时间后 2 小时 ~ 7 天,
                 平台只支持 5 分钟粒度, 自动向上取整到 5 分钟)
        """
        allowed_keys = (
            "title", "html", "account_file", "cover_path",
            "is_draft", "dry_run", "schedule_time_str",
            "dayu_source_remark", "dayu_original_url", "author",
        )
        filtered = {k: kwargs[k] for k in allowed_keys if k in kwargs}
        if filtered.get("dry_run", False):
            # dry-run 安全默认: 只存草稿, 永不点「发表」
            filtered["is_draft"] = True
        filtered.setdefault("is_draft", True)
        account_file = filtered.get("account_file") or []
        if isinstance(account_file, str):
            account_file = [account_file]
        filtered["account_file"] = account_file
        asyncio.run(self._publish_article_one(**filtered))
        return True

    async def _publish_article_one(
        self,
        title: str,
        html: str,
        account_file: list,
        cover_path: str = "",
        is_draft: bool = True,
        dry_run: bool = False,
        schedule_time_str: str = "",
        dayu_source_remark: str = "",
        dayu_original_url: str = "",
        author: str = "",
    ):
        """单账号图文文章发布完整流程。"""
        from datetime import datetime, timedelta

        from services.article_html import sanitize_article_html

        logger.info("=" * 60)
        logger.info("[文章][大鱼号] 开始图文文章发布流程")
        logger.info("=" * 60)

        title = (title or "").strip()
        html = html or ""
        source_remark = (dayu_source_remark or "").strip() or "无需标注"
        author = (author or "").strip()

        logger.info("[文章][大鱼号] 标题: %s", title)
        logger.info("[文章][大鱼号] 正文 HTML 长度: %d", len(html))
        logger.info("[文章][大鱼号] 封面: %s", cover_path or "无")
        logger.info("[文章][大鱼号] 作者名称: %s", author or "平台默认")
        logger.info("[文章][大鱼号] 信息来源: %s", source_remark)
        logger.info(
            "[文章][大鱼号] 模式: %s (dry_run=%s)",
            "保存草稿" if is_draft else "发表", dry_run,
        )
        logger.info(
            "[文章][大鱼号] 定时发表: %s",
            schedule_time_str or "无",
        )

        if not title:
            raise RuntimeError("[文章][大鱼号] 标题不能为空")
        if not (ARTICLE_MIN_TITLE_LENGTH <= len(title)
                <= ARTICLE_MAX_TITLE_LENGTH):
            raise RuntimeError(
                f"[文章][大鱼号] 标题长度需在 {ARTICLE_MIN_TITLE_LENGTH}~"
                f"{ARTICLE_MAX_TITLE_LENGTH} 字之间(当前 {len(title)} 字)"
            )
        if not html.strip():
            raise RuntimeError("[文章][大鱼号] 正文不能为空")
        if source_remark not in ARTICLE_SOURCE_OPTIONS:
            raise RuntimeError(
                f"[文章][大鱼号] 不支持的信息来源「{source_remark}」,可选: "
                + "/".join(ARTICLE_SOURCE_OPTIONS)
            )
        if author and len(author) > ARTICLE_AUTHOR_MAX_LEN:
            logger.warning(
                "[文章][大鱼号] 作者名称超长(%d>%d 字),已截断",
                len(author), ARTICLE_AUTHOR_MAX_LEN,
            )
            author = author[:ARTICLE_AUTHOR_MAX_LEN]
        if not account_file:
            raise RuntimeError("[文章][大鱼号] 缺少账号 cookie 配置")
        # 信息来源=转载 时原文链接必填(与平台编辑器「原文链接」必填校验一致)
        if source_remark == "转载" and not (dayu_original_url or "").strip():
            raise RuntimeError(
                "[文章][大鱼号] 信息来源选择「转载」时必须填写原文链接"
            )
        # 定时发表窗口: 当前时间后 2 小时 ~ 7 天(平台实测, 5 分钟粒度)
        if not is_draft and schedule_time_str:
            publish_dt = parse_schedule_time(
                schedule_time_str, 1, True, 1, None, 0
            )[0]
            diff = publish_dt - datetime.now()
            if not (
                timedelta(hours=ARTICLE_SCHEDULE_MIN_HOURS)
                <= diff
                <= timedelta(days=ARTICLE_SCHEDULE_MAX_DAYS)
            ):
                raise RuntimeError(
                    "[文章][大鱼号] 定时发表需为当前时间后 "
                    f"{ARTICLE_SCHEDULE_MIN_HOURS} 小时 ~ "
                    f"{ARTICLE_SCHEDULE_MAX_DAYS} 天内"
                )

        clean_html = sanitize_article_html(html)
        cookie_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]

        for cookie_index, cookie_path in enumerate(cookie_paths):
            cookie_name = Path(cookie_path).name
            nick = get_account_name_by_cookie_file(cookie_name)
            with bind_account_name(nick or "-"):
                logger.info(
                    "[文章][大鱼号] 发布到第 %d/%d 个账号 (%s)",
                    cookie_index + 1, len(cookie_paths), nick or "未知",
                )
                await self._publish_article_to_account(
                    page_title=title,
                    clean_html=clean_html,
                    account_file=cookie_path,
                    cover_path=str(cover_path or ""),
                    is_draft=bool(is_draft),
                    dry_run=bool(dry_run),
                    schedule_time_str=str(schedule_time_str or ""),
                    source_remark=source_remark,
                    original_url=str(dayu_original_url or ""),
                    author=author,
                )

        logger.info("=" * 60)
        logger.info("[文章][大鱼号] 图文文章发布流程完成!")
        logger.info("=" * 60)

    async def _publish_article_to_account(
        self,
        page_title: str,
        clean_html: str,
        account_file: str,
        cover_path: str = "",
        is_draft: bool = True,
        dry_run: bool = False,
        schedule_time_str: str = "",
        source_remark: str = "无需标注",
        original_url: str = "",
        author: str = "",
    ):
        """单账号执行：填表 → 封面 → 信息来源 → 定时 → 保存/发表。"""
        from services.article_html import extract_img_srcs, replace_img_srcs

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser, storage_state=account_file
            )
            try:
                page = await context.new_page()
                capture = _DayuApiCapture()
                await capture.install(page)

                await self._open_article_write_page(page)

                # 1. 标题
                await self._fill_article_title(page, page_title)

                # 1.5 作者名称(可选, ≤10 字)
                if author:
                    try:
                        await self._fill_article_author(page, author)
                    except Exception as e:
                        logger.warning(
                            "[文章][大鱼号] 作者名称设置失败(跳过): %s", e
                        )

                # 2. 正文图片 → 大鱼号图床 → 替换 src
                mapping = await self._upload_article_images(
                    page, extract_img_srcs(clean_html)
                )
                if mapping:
                    clean_html = replace_img_srcs(clean_html, mapping)

                # 3. 封面图：先上传图床，再临时插入正文(封面只能从正文选)
                cover_cdn = ""
                cover_para = ""
                if cover_path and Path(cover_path).exists():
                    try:
                        cover_cdn = await self._upload_cover_image(
                            page, cover_path
                        )
                        cover_para = f'<p><img src="{cover_cdn}"></p>'
                        logger.info(
                            "[文章][大鱼号] 封面图已上传图床: %s",
                            cover_cdn[:80],
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][大鱼号] 封面图上传失败(跳过封面): %s", e
                        )
                        cover_cdn = ""
                elif cover_path:
                    logger.warning(
                        "[文章][大鱼号] 封面文件不存在,忽略: %s", cover_path
                    )

                # 4. 粘贴正文: 有封面图时作为「正文首图」插入。
                # 大鱼号封面只能从正文图片中选择, 且平台每 100ms 的
                # removeAutoCovers 会在"封面来源图从正文消失"时清空封面,
                # 因此封面图必须保留在正文里。
                await self._paste_article_html(page, cover_para + clean_html)
                await asyncio.sleep(2)

                # 5. 切换「单封面」(三封面模式必须 3 张图才能过校验)
                await self._switch_article_single_cover(page)

                # 6. 从正文图片里选封面
                if cover_cdn:
                    try:
                        await self._set_article_cover(page, cover_cdn)
                        logger.info(
                            "[文章][大鱼号] 封面设置成功"
                            "(封面图已作为正文首图保留)"
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][大鱼号] 封面设置失败(跳过): %s", e
                        )

                # 7. 信息来源(必选)
                await self._set_article_source_remark(
                    page, source_remark, original_url
                )

                # 8. 定时发表(仅真实发表模式)
                if not is_draft and schedule_time_str:
                    publish_dt = parse_schedule_time(
                        schedule_time_str, 1, True, 1, None, 0
                    )[0]
                    logger.info(
                        "[文章][大鱼号] 设置定时发表: %s", publish_dt
                    )
                    await self._set_article_schedule_time(page, publish_dt)

                # 9. 保存草稿 / 真实发表
                await self._save_or_publish_article(
                    page, capture,
                    is_draft=is_draft,
                    dry_run=dry_run,
                    title=page_title,
                )

                # Save updated cookie state
                try:
                    await context.storage_state(path=account_file)
                    logger.info("[文章][大鱼号] Cookie 状态已更新")
                except Exception:
                    pass
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ------------------------------------------------------------------
    # article helpers — 页面/表单
    # ------------------------------------------------------------------

    @staticmethod
    async def _open_article_write_page(page):
        """打开图文编辑器, 校验标题框与 UEditor iframe 就绪。"""
        logger.info(
            "[文章][大鱼号] 正在打开图文编辑器: %s", ARTICLE_WRITE_URL
        )
        try:
            await page.goto(
                ARTICLE_WRITE_URL, wait_until="domcontentloaded", timeout=60000
            )
        except Exception as e:
            raise RuntimeError(
                f"[文章][大鱼号] 打开图文编辑器失败(cookie 可能失效): {e}"
            )
        try:
            await page.locator("input#title").wait_for(
                state="visible", timeout=30000
            )
        except Exception:
            raise RuntimeError(
                "[文章][大鱼号] 图文编辑器未就绪(标题框未出现, 当前 URL="
                f"{page.url}), 可能被重定向到登录页, 请重新登录账号"
            )
        try:
            await page.wait_for_selector("iframe#ueditor_0", timeout=20000)
        except Exception as e:
            raise RuntimeError(
                f"[文章][大鱼号] 正文编辑器(UEditor)未加载: {e}"
            )
        await asyncio.sleep(2)
        logger.info("[文章][大鱼号] 编辑器已打开: %s", page.url)

    @staticmethod
    async def _fill_article_title(page, title: str):
        """填写标题(input#title, v-model)。"""
        title = title[:ARTICLE_MAX_TITLE_LENGTH]
        title_input = page.locator("input#title").first
        await title_input.click()
        await title_input.fill(title)
        await asyncio.sleep(0.5)
        # 校验 v-model 是否同步(个别情况下 fill 不触发 input 事件)
        try:
            current = (await title_input.input_value()).strip()
        except Exception:
            current = ""
        if current != title:
            logger.info("[文章][大鱼号] 标题 fill 未生效, 改用逐字符输入")
            await title_input.fill("")
            await title_input.press_sequentially(title, delay=40)
            await asyncio.sleep(0.5)
        # 失焦触发标题校验(标题党检测等), 避免键盘事件留在标题框
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.5)
        logger.info("[文章][大鱼号] 标题已填写: %s", title)

    @staticmethod
    async def _fill_article_author(page, author: str):
        """填写「作者名称」(0/10 字, 可选; 空则用平台默认作者)。"""
        author = (author or "").strip()[:ARTICLE_AUTHOR_MAX_LEN]
        if not author:
            return
        filled = await page.evaluate(
            """(author) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
              // 找到「作者名称」标签, 取同一行的输入框
              let row = null;
              for (const el of document.querySelectorAll(
                  'label, div, span, p')) {
                if (!vis(el)) continue;
                if (norm(el.innerText) !== '作者名称') continue;
                const r = el.getBoundingClientRect();
                if (r.height > 60) continue;
                row = el.closest('div');
                break;
              }
              if (!row) return 'no-row';
              // 向上找包含 input 的容器
              let cur = row;
              for (let i = 0; i < 4 && cur; i++) {
                const inp = cur.querySelector('input[type=text]');
                if (inp && vis(inp)) {
                  const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                  setter.call(inp, author);
                  inp.dispatchEvent(new Event('input', {bubbles: true}));
                  inp.dispatchEvent(new Event('change', {bubbles: true}));
                  return 'ok:' + inp.value;
                }
                cur = cur.parentElement;
              }
              return 'no-input';
            }""",
            author,
        )
        await asyncio.sleep(1)
        form = await DayuPlatform._read_article_form(page)
        got = (form.get("author") or "").strip()
        if got != author:
            raise RuntimeError(
                f"[文章][大鱼号] 作者名称填写未生效(期望 {author}, 实际 {got!r}, "
                f"步骤={filled})"
            )
        logger.info("[文章][大鱼号] 作者名称已填写: %s", author)

    @staticmethod
    async def _log_article_form_state(page):
        """保存/发表前打印表单关键设置(DOM 回读, 验证证据)。"""
        try:
            form = await DayuPlatform._read_article_form(page)
            cover = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                  const row = {};
                  row.normalMode = [...document.querySelectorAll(
                      '.article-write-article-cover_normal-option')]
                    .filter(vis).map((el) => ({
                      text: norm(el.innerText),
                      checked: (typeof el.className === 'string' ? el.className
                        : '').includes('checked')})).slice(0, 4);
                  row.chooseButtons = document.querySelectorAll(
                    '.article-write-article-cover-cover-item_choose button')
                    .length;
                  row.timerChecked = [...document.querySelectorAll(
                      '.article-write_radio')].filter(vis).some(
                    (el) => !!(el.querySelector('.w-radio_checked')));
                  return row;
                }"""
            )
            relink = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const inp = [...document.querySelectorAll('input')]
                    .filter(vis).find((el) => (el.placeholder || '')
                      .includes('原文链接'));
                  return inp ? inp.value : '';
                }"""
            )
            logger.info(
                "[文章][大鱼号] 保存前表单回读: 标题=%r 作者=%r 信息来源=%s "
                "转载链接=%s 封面模式=%s 封面=%s 定时=%s(%s) 定时时间=%s",
                form.get("title") or "",
                form.get("author") or "",
                form.get("source_remark_type") or "未选择",
                relink or "无",
                "三封面" if form.get("use_multi_cover") else "单封面",
                "已设置" if form.get("coverImg") else "未设置",
                "开" if form.get("is_timed_release") else "关",
                "控件勾选" if cover.get("timerChecked") else "控件未勾选",
                form.get("time_for_release") or "-",
            )
        except Exception as e:
            logger.info("[文章][大鱼号] 表单状态回读失败: %s", e)

    @staticmethod
    async def _paste_article_html(page, html: str) -> int:
        """粘贴 HTML 到 UEditor iframe, 返回 iframe innerHTML 长度。"""
        logger.info(
            "[文章][大鱼号] 粘贴正文 HTML(%d 字符)...", len(html)
        )
        length = 0
        for attempt in range(1, 3):
            length = await page.evaluate(_ARTICLE_PASTE_JS, html)
            await asyncio.sleep(2)
            if length and length >= 20:
                logger.info(
                    "[文章][大鱼号] 正文已粘贴(innerHTML %d 字符)", length
                )
                return length
            logger.warning(
                "[文章][大鱼号] 第 %d 次粘贴后内容过短(length=%s), 重试",
                attempt, length,
            )
            raise_if_page_closed(page, action="文章发布")
        raise RuntimeError(
            f"[文章][大鱼号] 正文粘贴失败(innerHTML length={length})"
        )

    @staticmethod
    async def _switch_article_single_cover(page):
        """切换横版封面为「单封面」模式。

        默认「三封面」模式下 checkCoverImg 要求 3 张封面都设置好才能保存/
        发表；单封面模式无封面图也可通过(平台允许无封面发表)。
        """
        changed = await page.evaluate(
            """() => {
              for (const opt of document.querySelectorAll(
                  '.article-write-article-cover_normal-option')) {
                if ((opt.innerText || '').trim() === '单封面') {
                  const radio = opt.querySelector('.w-radio') || opt;
                  radio.click();
                  return true;
                }
              }
              return false;
            }"""
        )
        await asyncio.sleep(1.2)
        if changed:
            logger.info("[文章][大鱼号] 横版封面已切换为「单封面」")
        else:
            logger.warning("[文章][大鱼号] 未找到「单封面」选项目录")

    @staticmethod
    async def _read_article_form(page):
        """读取页面 Vue 实例 formData 子集(失败返回 {})。"""
        try:
            return await page.evaluate(_ARTICLE_FORM_JS) or {}
        except Exception as e:
            logger.info("[文章][大鱼号] 读取表单状态失败: %s", e)
            return {}

    @staticmethod
    async def _click_article_button(page, texts: list) -> str:
        """点击底部操作栏按钮(事件绑定在 mousedown, 需派发 mousedown)。"""
        clicked = await page.evaluate(
            """(texts) => {
              const vis = (el) => el.getBoundingClientRect().width > 0;
              for (const b of document.querySelectorAll('button')) {
                if (!vis(b)) continue;
                const t = (b.innerText || '').trim();
                if (texts.includes(t)) {
                  const opts = {bubbles: true, cancelable: true,
                                view: window};
                  b.dispatchEvent(new MouseEvent('mousedown', opts));
                  return t;
                }
              }
              return '';
            }""",
            texts,
        )
        return clicked or ""

    # ------------------------------------------------------------------
    # article helpers — 图片上传 / 封面
    # ------------------------------------------------------------------

    async def _upload_article_images(self, page, srcs) -> dict:
        """逐张上传正文图片到 UEditor 图床, 返回 {原src: CDN URL}。

        任一张失败 → raise(正文图片缺失等于内容损坏)。
        """
        if not srcs:
            logger.info("[文章][大鱼号] 正文无图片, 跳过上传")
            return {}

        logger.info(
            "[文章][大鱼号] 正文含 %d 张图片, 开始上传图床...", len(srcs)
        )
        items = []
        for src in srcs:
            data, name, mime = self._resolve_image_bytes(src)
            if len(data) > ARTICLE_IMAGE_MAX_BYTES:
                raise RuntimeError(
                    f"[文章][大鱼号] 正文图片超过 5MB 上限: {name}"
                    f"({len(data) / 1024 / 1024:.1f}MB)"
                )
            items.append({
                "src": src,
                "name": name,
                "mime": mime,
                "b64": base64.b64encode(data).decode(),
            })

        results = await page.evaluate(_ARTICLE_UPLOAD_JS, items)
        mapping: dict[str, str] = {}
        for item, ret in zip(items, results or []):
            if not ret or not ret.get("ok") or not ret.get("cdn_url"):
                raise RuntimeError(
                    "[文章][大鱼号] 正文图片上传失败"
                    f"({ret.get('name') if ret else item['name']}): "
                    f"ret={ret.get('ret') if ret else '?'} "
                    f"{ret.get('err_msg') if ret else ''}"
                )
            mapping[item["src"]] = ret["cdn_url"]
            logger.info(
                "[文章][大鱼号] 图片已上传(%d/%d): %s",
                len(mapping), len(items), ret["cdn_url"][:80],
            )
        return mapping

    async def _upload_cover_image(self, page, cover_path: str) -> str:
        """上传封面图到图床, 返回 CDN URL。"""
        data, name, mime = self._resolve_image_bytes(cover_path)
        if len(data) > ARTICLE_IMAGE_MAX_BYTES:
            raise RuntimeError(
                f"[文章][大鱼号] 封面图超过 5MB 上限: {name}"
                f"({len(data) / 1024 / 1024:.1f}MB)"
            )
        results = await page.evaluate(
            _ARTICLE_UPLOAD_JS,
            [{
                "name": name,
                "mime": mime,
                "b64": base64.b64encode(data).decode(),
            }],
        )
        ret = (results or [{}])[0]
        if not ret.get("ok") or not ret.get("cdn_url"):
            raise RuntimeError(
                f"[文章][大鱼号] 封面上传失败({name}): ret={ret.get('ret')} "
                f"{ret.get('err_msg')}"
            )
        return ret["cdn_url"]

    @staticmethod
    def _resolve_image_bytes(src: str) -> tuple:
        """把 img src 解析为 (bytes, filename, mime)。

        支持: data: URL / 素材库 URL(/api/materials/file/<stored>/ 或
        http://127.0.0.1:5409/api/materials/file/...) / 外链 http(s) /
        本地绝对路径(脚本直传场景)。
        """
        from storage import get_storage

        src = (src or "").strip()
        if not src:
            raise RuntimeError("[文章][大鱼号] 正文图片 src 为空")

        if src.startswith("data:"):
            head, _, b64 = src.partition(",")
            mime = head[5:].split(";")[0] or "image/png"
            ext = mimetypes.guess_extension(mime) or ".png"
            return base64.b64decode(b64), f"inline{ext}", mime

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
                data = Path(local).read_bytes()
                name = Path(local).name
                mime = mimetypes.guess_type(name)[0] or "image/png"
                return data, name, mime
            full_url = src if src.startswith("http") else (
                f"http://127.0.0.1:5409{src}"
            )
            return DayuPlatform._download_image(full_url,
                                                stored.split("/")[-1])

        if src.startswith(("http://", "https://")):
            name = Path(parsed.path).name or "image.png"
            return DayuPlatform._download_image(src, name)

        p = Path(src)
        if p.exists():
            data = p.read_bytes()
            mime = mimetypes.guess_type(p.name)[0] or "image/png"
            return data, p.name, mime
        raise RuntimeError(f"[文章][大鱼号] 无法解析正文图片 src: {src}")

    @staticmethod
    def _download_image(url: str, name: str) -> tuple:
        """下载外链图片为 (bytes, filename, mime)。"""
        import requests

        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        ct = (resp.headers.get("content-type") or "image/png").split(";")[0]
        name = name or "image.png"
        if not Path(name).suffix:
            name += mimetypes.guess_extension(ct) or ".png"
        return resp.content, name, ct

    async def _set_article_cover(self, page, cover_cdn: str):
        """从正文图片中选择封面并保存裁剪。

        大鱼号图文封面不支持本地上传(cover 弹窗只有「正文」tab), 流程:
          1. 点封面槽的「从正文中选择」(按钮 hover 才显示, 用 JS click)
          2. 弹窗列出正文图片 → 点与 cover_cdn 匹配的那张
          3. 「下一步」→ 裁剪步骤 → 「保存」→ POST 图片裁剪接口
          4. 校验 formData.coverImg 已设置
        """
        clicked = await page.evaluate(
            """() => {
              const btns = [...document.querySelectorAll(
                '.article-write-article-cover-cover-item_choose button')];
              if (!btns.length) return false;
              btns[0].click();
              return true;
            }"""
        )
        if not clicked:
            raise RuntimeError("未找到封面「从正文中选择」按钮")
        await page.wait_for_selector(
            ".article-material-image-dialog_root", timeout=20000
        )
        await asyncio.sleep(1.5)

        token = cover_cdn
        if "?" in cover_cdn:
            token = cover_cdn.split("?", 1)[1].split("&", 1)[0]
        picked = await page.evaluate(
            """(token) => {
              const root = document.querySelector(
                '.article-material-image-dialog_root');
              if (!root) return 0;
              const items = [...root.querySelectorAll(
                '.article-material-image_image-choose > div')];
              let target = null;
              for (const it of items) {
                const img = it.querySelector('img');
                if (img && (img.src || '').includes(token)) {
                  target = it;
                  break;
                }
              }
              if (!target) target = items[0] || null;
              if (!target) return 0;
              target.click();
              return items.length;
            }""",
            token,
        )
        if not picked:
            await self._close_article_dialog(page)
            raise RuntimeError(
                "封面弹窗内没有可用正文图片(正文未包含封面图)"
            )
        await asyncio.sleep(1)

        # 下一步 → 裁剪
        nxt = await page.evaluate(
            """() => {
              const vis = (el) => el.getBoundingClientRect().width > 0;
              for (const b of document.querySelectorAll('button')) {
                if (!vis(b)) continue;
                if ((b.innerText || '').trim() === '下一步') {
                  b.click();
                  return true;
                }
              }
              return false;
            }"""
        )
        if not nxt:
            await self._close_article_dialog(page)
            raise RuntimeError("封面弹窗未找到「下一步」按钮")
        await asyncio.sleep(2.5)

        # 裁剪步骤「保存」(仅点弹窗内按钮, 避免误点底部「保存」)
        saved = await page.evaluate(
            """() => {
              const root = document.querySelector(
                '.article-material-image-dialog_root');
              if (!root) return false;
              const vis = (el) => el.getBoundingClientRect().width > 0;
              for (const b of root.querySelectorAll('button')) {
                if (!vis(b)) continue;
                if ((b.innerText || '').trim() === '保存') {
                  b.click();
                  return true;
                }
              }
              return false;
            }"""
        )
        if not saved:
            await self._close_article_dialog(page)
            raise RuntimeError("封面裁剪弹窗未找到「保存」按钮")

        # 等弹窗关闭 + 封面生效(裁剪接口异步, 最多等 30s)
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            form = await self._read_article_form(page)
            if form.get("coverImg"):
                return
            await asyncio.sleep(1)
        raise RuntimeError("封面裁剪保存后未生效(formData.coverImg 为空)")

    @staticmethod
    async def _close_article_dialog(page):
        """关闭图片弹窗(点弹窗内「取消」, 兜底 Escape), 避免遮罩拦截后续点击。"""
        closed = await page.evaluate(
            """() => {
              const root = document.querySelector(
                '.article-material-image-dialog_root');
              if (!root) return true;
              const vis = (el) => el.getBoundingClientRect().width > 0;
              for (const b of root.querySelectorAll('button')) {
                if (!vis(b)) continue;
                if ((b.innerText || '').trim() === '取消') {
                  b.click();
                  return true;
                }
              }
              return false;
            }"""
        )
        if not closed:
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
        await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # article helpers — 信息来源 / 保存与发表
    # ------------------------------------------------------------------

    async def _set_article_source_remark(self, page, source_remark: str,
                                         original_url: str = ""):
        """选择「信息来源」单选项; 选「转载」时填原文链接(必填)。"""
        clicked = await page.evaluate(
            """(want) => {
              const labels = [...document.querySelectorAll(
                'label.ant-radio-wrapper')]
                .filter((el) => el.getBoundingClientRect().width > 0);
              const hit = labels.find(
                (el) => (el.innerText || '').trim() === want);
              if (!hit) return false;
              const input = hit.querySelector('input[type=radio]');
              (input || hit).click();
              return true;
            }""",
            source_remark,
        )
        if not clicked:
            raise RuntimeError(
                f"[文章][大鱼号] 未找到信息来源选项「{source_remark}」"
            )
        await asyncio.sleep(1)
        form = await DayuPlatform._read_article_form(page)
        got = form.get("source_remark_type") or ""
        if got != source_remark:
            raise RuntimeError(
                "[文章][大鱼号] 信息来源选择未生效(期望 "
                f"「{source_remark}」, 表单实际「{got or '未选择'}」)"
            )
        logger.info("[文章][大鱼号] 信息来源已选择: %s", source_remark)

        if source_remark != "转载":
            return
        if not original_url:
            raise RuntimeError(
                "[文章][大鱼号] 信息来源选择「转载」时必须填写原文链接"
            )
        # 选「转载」后平台才渲染「原文链接」输入框
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 10
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            exists = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll('input')].filter(vis)
                    .some((el) => (el.placeholder || '')
                      .includes('原文链接'));
                }"""
            )
            if exists:
                break
            await asyncio.sleep(1)
        filled = await page.evaluate(
            """(url) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const inputs = [...document.querySelectorAll(
                'input[type=text],input[type=url],textarea')].filter(vis);
              const cand = inputs.find((el) => {
                const ph = (el.placeholder || '') + (el.getAttribute(
                  'data-placeholder') || '');
                return ph.includes('链接') || ph.includes('原文');
              });
              if (!cand) return false;
              const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
              setter.call(cand, url);
              cand.dispatchEvent(new Event('input', {bubbles: true}));
              cand.dispatchEvent(new Event('change', {bubbles: true}));
              return true;
            }""",
            original_url,
        )
        if not filled:
            raise RuntimeError(
                "[文章][大鱼号] 未找到「原文链接」输入框(信息来源=转载)"
            )
        await asyncio.sleep(0.8)
        form = await DayuPlatform._read_article_form(page)
        content = form.get("source_remark_content") or []
        first = content[0] if content else ""
        if isinstance(first, dict):
            first = first.get("content") or first.get("url") or ""
        if original_url not in str(first):
            logger.warning(
                "[文章][大鱼号] 原文链接回读未匹配(表单=%r, 期望=%r),"
                "可能为异步同步, 继续",
                first, original_url,
            )
        logger.info("[文章][大鱼号] 原文链接已填写: %s", original_url)

    async def _save_or_publish_article(self, page, capture, is_draft: bool,
                                       dry_run: bool, title: str):
        """保存草稿 / 真实发表(仅以 API 响应判定成败)。"""
        # 提交前表单设置回读(验证证据: 作者/信息来源/转链接/封面/定时)
        await DayuPlatform._log_article_form_state(page)
        # 提交前证据截图
        try:
            shot = Path(BASE_DIR) / "screenshots" / (
                "dayu_article_draft.png" if is_draft
                else "dayu_article_before_submit.png"
            )
            shot.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(shot), full_page=True)
            logger.info("[文章][大鱼号] 提交前截图: %s", shot)
        except Exception as e:
            logger.info("[文章][大鱼号] 提交前截图失败: %s", e)

        if is_draft:
            start = len(await capture.read(page))
            clicked = await self._click_article_button(page, ["保存"])
            if not clicked:
                raise RuntimeError("[文章][大鱼号] 未找到「保存」按钮")
            logger.info("[文章][大鱼号] 已点击「保存」, 等待 save-draft 响应...")
            item = await capture.wait(
                page, "/dashboard/save-draft", timeout_s=90, since=start
            )
            payload = self._parse_article_api(item, "保存草稿")
            logger.info(
                "[文章][大鱼号] 草稿保存成功 draft_id=%s",
                payload.get("_id"),
            )
            if dry_run:
                logger.info(
                    "[文章][大鱼号][DRY_RUN] 已完整填写表单并保存草稿, "
                    "未点击「发表」(标题=%s)", title,
                )
            # 等跳转草稿箱(软校验, 超时仅告警)
            deadline = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < deadline:
                if "/dashboard/draft" in (page.url or ""):
                    break
                await asyncio.sleep(1)
            if "/dashboard/draft" not in (page.url or ""):
                logger.warning(
                    "[文章][大鱼号] 草稿已保存但 20s 未跳转草稿箱: %s",
                    page.url,
                )
            return

        # ---- 真实发表: 点发表 → 保存草稿 + 预览弹窗 → 确认发表 ----
        if manual_review_enabled('dayu', 'article'):
            # 人工验收：保留页面，用户亲自完成「发表」→ 预览弹窗
            # 「确认发表」，程序不再点击。成功判定沿用铁律（发表成功
            # 只认 API 响应）：/dashboard/submit-article 响应 HTTP 200
            # 且含 content_id/_id，与 _parse_article_api 口径一致。
            since = len(await capture.read(page))

            async def _submit_article_ok(p) -> bool:
                try:
                    entries = await capture.read(p)
                except Exception:
                    return False
                for item in entries[since:]:
                    if "/dashboard/submit-article" not in item.get("url", ""):
                        continue
                    try:
                        self._parse_article_api(item, "文章发表")
                        return True
                    except RuntimeError:
                        continue
                return False

            await wait_for_manual_publish(
                page, 'dayu', success_check=_submit_article_ok
            )
            logger.info("[文章][大鱼号] ✓ 文章发表成功(人工验收)")
            await asyncio.sleep(1)
            return

        start = len(await capture.read(page))
        clicked = await self._click_article_button(page, ["发表"])
        if not clicked:
            raise RuntimeError("[文章][大鱼号] 未找到「发表」按钮")
        logger.info("[文章][大鱼号] 已点击「发表」, 等待预览弹窗...")
        item = await capture.wait(
            page, "/dashboard/save-draft", timeout_s=120, since=start
        )
        self._parse_article_api(item, "发表前保存草稿")
        logger.info("[文章][大鱼号] 发表前草稿已保存, 等待预览弹窗...")

        # 预览弹窗出现 → 点「确认发表」
        confirm_ready = False
        deadline = asyncio.get_event_loop().time() + 40
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            confirm_ready = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll(
                    '.article-write-preview_btn button')].some(
                      (b) => vis(b)
                        && (b.innerText || '').trim() === '确认发表');
                }"""
            )
            if confirm_ready:
                break
            await asyncio.sleep(1)
        if not confirm_ready:
            raise RuntimeError(
                "[文章][大鱼号] 发表预览弹窗未出现(未找到「确认发表」)"
            )

        start = len(await capture.read(page))
        confirmed = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              for (const b of document.querySelectorAll(
                  '.article-write-preview_btn button')) {
                if (!vis(b)) continue;
                if ((b.innerText || '').trim() === '确认发表') {
                  b.click();
                  return true;
                }
              }
              return false;
            }"""
        )
        if not confirmed:
            raise RuntimeError("[文章][大鱼号] 未找到「确认发表」按钮")
        logger.info("[文章][大鱼号] 已点击「确认发表」, 等待 submit-article 响应...")
        item = await capture.wait(
            page, "/dashboard/submit-article", timeout_s=180, since=start
        )
        try:
            payload = self._parse_article_api(item, "文章发表")
        except RuntimeError as e:
            if any(k in str(e) for k in
                   ("submit_limit", "captcha", "验证", "风控")):
                # 风控/人机校验: 有头浏览器等待用户在页面完成验证, 页面会
                # 自动重试 submit-article
                logger.warning(
                    "[文章][大鱼号] 触发人机校验/提交限制, 请在浏览器中完成"
                    "验证(最多等待 300 秒): %s", e,
                )
                cursor = item.get("_index", start) + 1
                deadline = asyncio.get_event_loop().time() + 300
                payload = None
                while asyncio.get_event_loop().time() < deadline:
                    raise_if_page_closed(page, action="文章发布")
                    try:
                        item = await capture.wait(
                            page, "/dashboard/submit-article",
                            timeout_s=15, since=cursor,
                        )
                    except RuntimeError:
                        continue
                    cursor = item.get("_index", cursor) + 1
                    try:
                        payload = self._parse_article_api(item, "文章发表")
                        break
                    except RuntimeError as e2:
                        logger.warning(
                            "[文章][大鱼号] 人机校验后仍未发表成功: %s", e2
                        )
                        payload = None
                if payload is None:
                    raise RuntimeError(
                        "[文章][大鱼号] 风控/人机校验未在 300 秒内完成, "
                        f"发表失败: {e}"
                    )
            else:
                raise
        logger.info(
            "[文章][大鱼号] ✓ 文章发表成功 content_id=%s",
            payload.get("content_id") or payload.get("_id"),
        )
        # 等跳转内容管理页(软校验, 超时仅告警)
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline:
            if "/dashboard/contents" in (page.url or ""):
                break
            await asyncio.sleep(1)
        if "/dashboard/contents" not in (page.url or ""):
            logger.warning(
                "[文章][大鱼号] 发表 API 成功但 30s 未跳转内容管理页: %s",
                page.url,
            )
        await asyncio.sleep(1)

    @staticmethod
    def _parse_article_api(item: dict, action: str) -> dict:
        """解析 save-draft / submit-article 响应, 成功返回 data dict。

        成功判定(唯一依据): HTTP 200 且响应 JSON 的 data._id /
        data.content_id 存在。失败 raise 含 code+msg。
        """
        status = item.get("status")
        data = item.get("json")
        if data is None:
            raise RuntimeError(
                f"[文章][大鱼号] {action}响应解析失败(HTTP {status}): "
                f"{item.get('err') or (item.get('text') or '')[:200]}"
            )
        payload = data.get("data")
        if not isinstance(payload, dict):
            payload = data if isinstance(data, dict) else {}
        if status == 200 and (payload.get("_id") or payload.get("content_id")):
            return payload
        code = (
            data.get("code")
            or data.get("error_type")
            or payload.get("code")
            or payload.get("error_type")
            or status
        )
        msg = (
            data.get("message") or data.get("msg") or data.get("error")
            or data.get("info") or payload.get("message")
            or payload.get("msg") or payload.get("error")
            or (item.get("text") or "")[:300]
        )
        raise RuntimeError(
            f"[文章][大鱼号] {action}失败 code={code} msg={msg}"
        )


def _parse_switch(switch_text: str):
    """把 datetimepicker 的「九月 2026」文本解析为 (year, month)。"""
    cn_nums = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
        "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
    }
    try:
        month_part, year_part = switch_text.replace("月", " 月 ").split(" 月 ")
        month = cn_nums.get(month_part.strip(), 0)
        year = int(year_part.strip())
        return (year, month)
    except Exception:
        return (0, 0)
