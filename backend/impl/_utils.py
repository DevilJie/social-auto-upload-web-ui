"""
Shared utilities for all platform implementations.

Provides profile scraping helpers, schedule-time parsing, and a unified
post-login flow (scrape profile -> save cookie -> write DB -> send SSE status).

All functions use standard Playwright Page/Context APIs only.
"""

import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from conf import BASE_DIR

# ---------------------------------------------------------------------------
# JS injection script for generic profile scraping
# Source: original login.py JS injection script
# ---------------------------------------------------------------------------

_SCRAPE_JS = '''() => {
    let name = '';
    let avatar = '';
    const candidates = [];

    // ====== 头像查找 ======
    function isAvatarUrl(url) {
        if (!url || !url.startsWith('http')) return false;
        const lower = url.toLowerCase();
        return !lower.endsWith('.svg') && !lower.includes('.svg') &&
            !lower.includes('icon') && !lower.includes('logo') &&
            !lower.includes('qrcode') && !lower.includes('placeholder') &&
            !lower.includes('default') && !lower.includes('blank') &&
            !lower.includes('sprite') && !lower.includes('bg');
    }

    const avatarCdnPatterns = [
        'aweme-avatar', 'douyinpic.com/avatar',
        'xhscdn.com/avatar', 'qlogo.cn', 'finderhead',
        'kuaishoucdn.com/avatar', 'head_url'
    ];
    const imgs = [...document.querySelectorAll('img')];

    // ====== 工具函数 ======
    const excludeTexts = ['登录','注册','密码','手机','首页','上传','数据','管理',
        '发布','创作','视频','直播','消息','设置','帮助','退出','更多','搜索',
        '扫码','关注','粉丝','获赞','作品','动态','喜欢','收藏',
        '共创','中心','工具','服务','收益','任务','课程','通知','评论',
        '互动','权限','认证','申请','开通','绑定','电商','带货',
        '网址','链接','复制','分享','下载','打开','全部','菜单',
        '内容','素材','流量','分析','商品','订单','结算','功能',
        '主页','首页','个人','专栏','活动','热门','推荐',
        '播放量','点赞数','评论数','转发数','浏览量','阅读量','新增','昨日'];

    function isValidName(text) {
        if (!text || text.length < 2 || text.length > 30) return false;
        if (/^\\d+(\\.\\d+)?[万亿]$/.test(text)) return false;
        if (/^\\d+$/.test(text)) return false;
        for (const ex of excludeTexts) {
            if (text.includes(ex)) return false;
        }
        return true;
    }

    // ====== 策略0 (最高优先级): 平台精确匹配，找到直接返回 ======
    // 抖音: container-xxx > avatar-xxx > img + name-xxx
    const dyAllContainers = document.querySelectorAll('div[class^="container-"]');
    for (const dyContainer of dyAllContainers) {
        const dyAvImg = dyContainer.querySelector(':scope > div[class^="avatar-"] > img');
        const dyNameEl = dyContainer.querySelector('div[class^="name-"]');
        if (dyAvImg && dyNameEl && isValidName(dyNameEl.textContent.trim())) {
            return {
                name: dyNameEl.textContent.trim(),
                avatar: dyAvImg.src || '',
                debug: [{text: dyNameEl.textContent.trim(), method: 'douyin-profile-container'}]
            };
        }
    }
    // 视频号: img[alt*="头像"] + h2.finder-nickname
    const wxAvatar = document.querySelector('img[alt*="头像"]');
    const wxName = document.querySelector('h2.finder-nickname') || document.querySelector('[class*="nickname"]');
    if (wxAvatar && wxName && isValidName(wxName.textContent.trim())) {
        return {
            name: wxName.textContent.trim(),
            avatar: wxAvatar.src || '',
            debug: [{text: wxName.textContent.trim(), method: 'wechat-profile'}]
        };
    }

    // ====== 以下为兜底策略 ======

    // 头像: 优先匹配平台头像 CDN（精确匹配）
    for (const img of imgs) {
        const src = img.src || '';
        if (isAvatarUrl(src) && !src.includes('cover') && !src.includes('video')) {
            for (const p of avatarCdnPatterns) {
                if (src.includes(p)) { avatar = src; break; }
            }
            if (avatar) break;
        }
    }
    // 兜底：尺寸匹配
    if (!avatar) {
        for (const img of imgs) {
            const rect = img.getBoundingClientRect();
            const w = rect.width, h = rect.height;
            if (w >= 24 && w <= 80 && h >= 24 && h <= 80 &&
                Math.abs(w - h) < Math.max(w, h) * 0.3 && isAvatarUrl(img.src)) {
                avatar = img.src;
                break;
            }
        }
    }

    // 昵称查找
    // 策略A: 找到头像后，找头像旁边的 name 元素
    if (avatar) {
        const avatarImg = imgs.find(i => i.src === avatar);
        if (avatarImg) {
            let parent = avatarImg.parentElement;
            if (parent) {
                const sibling = parent.nextElementSibling;
                if (sibling && sibling.className && sibling.className.startsWith('name-')) {
                    const text = sibling.textContent.trim();
                    if (isValidName(text)) {
                        candidates.push({text, method: 'avatar-sibling', level: 0});
                    }
                }
            }
            let container = avatarImg.parentElement;
            for (let i = 0; i < 5 && container; i++) {
                const leaves = container.querySelectorAll('span, div, p, a');
                for (const leaf of leaves) {
                    if (leaf.childElementCount > 0) continue;
                    const text = leaf.textContent.trim();
                    if (isValidName(text)) {
                        candidates.push({text, method: 'near-avatar', level: i});
                    }
                }
                container = container.parentElement;
            }
        }
    }

    // 策略B: class 选择器
    const selectors = [
        'div[class^="avatar-"] + div[class^="name-"]',
        'h2.finder-nickname', 'img.avatar[alt]',
        '[class*="user-name"]', '[class*="userName"]', '[class*="username"]',
        '[class*="nick-name"]', '[class*="nickname"]', '[class*="nickName"]',
        '[class*="NickName"]', '[class*="nick_name"]',
        '[class*="UserInfo"]', '[class*="userInfo"]', '[class*="user-info"]',
        '[class*="profile-name"]', '[class*="profileName"]',
        '[class*="name-text"]', '[class*="nameText"]',
    ];
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const text = el.textContent.trim();
            if (isValidName(text)) {
                candidates.push({text, method: 'class:' + sel});
            }
        }
    }

    // 策略C: img alt 属性
    for (const img of imgs) {
        if (img.alt && isValidName(img.alt)) {
            candidates.push({text: img.alt, method: 'img-alt'});
        }
    }

    const best = candidates[0];
    name = best ? best.text : '';

    return { name, avatar, debug: candidates.slice(0, 10) };
}'''


# ---------------------------------------------------------------------------
# Profile scraping functions
# ---------------------------------------------------------------------------

async def scrape_user_profile(page):
    """Generic scraper using _SCRAPE_JS injection.

    Works for Douyin, Kuaishou, Xiaohongshu, and most platforms.

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""

    try:
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await asyncio.sleep(3)
    except Exception:
        pass

    try:
        result = await page.evaluate(_SCRAPE_JS)
        name = result.get('name', '')
        avatar = result.get('avatar', '')
        debug = result.get('debug', [])
        print(f"[scrape] candidates: {debug}")
        if name:
            print(f"[scrape] found profile - name: {name}, avatar: {avatar[:50] if avatar else 'N/A'}")
        else:
            print("[scrape] could not find user name, will use default")
    except Exception as e:
        print(f"[scrape] failed to scrape user profile: {e}")

    return name, avatar


async def scrape_bilibili_profile(page):
    """Bilibili-specific scraper.

    Targets ``span.home-top-msg-name`` for the username and
    ``div.home-head img`` for the avatar.

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await asyncio.sleep(2)
        # Username: span.home-top-msg-name
        name_el = page.locator('span.home-top-msg-name').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()
        # Avatar: div.home-head img
        avatar_el = page.locator('div.home-head img').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()
        if name:
            print(f"[bilibili] profile scraped - name: {name}, avatar: {avatar[:50] if avatar else 'N/A'}")
        else:
            print("[bilibili] profile scrape failed, will use default name")
    except Exception as e:
        print(f"[bilibili] profile scrape error: {e}")
    return name, avatar


async def scrape_tencent_profile(page):
    """WeChat Channels (视频号) specific scraper.

    Targets ``img.avatar`` (or ``img[alt*="头像"]``) for the avatar and
    ``h2.finder-nickname`` for the username.

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await asyncio.sleep(3)
        # Avatar: img.avatar or img[alt*="头像"]
        avatar_el = page.locator('img.avatar, img[alt*="头像"]').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()
        # Username: h2.finder-nickname or class containing "nickname"
        name_el = page.locator('h2.finder-nickname, [class*="nickname"]').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()
        if name:
            print(f"[channels] profile scraped - name: {name}, avatar: {avatar[:50] if avatar else 'N/A'}")
        else:
            print("[channels] profile scrape failed, will use default name")
    except Exception as e:
        print(f"[channels] profile scrape error: {e}")
    return name, avatar


async def scrape_baijiahao_profile(page):
    """Baijiahao (百家号) specific scraper.

    Navigates to the account settings page and targets
    ``img[class*="userImg"]`` for the avatar and
    ``div[class*="userName"]`` for the username.

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        # Navigate to account settings page where avatar and name are rendered
        await page.goto(
            "https://baijiahao.baidu.com/builder/rc/settings/accountSet",
            timeout=15000,
        )
        await page.wait_for_load_state('domcontentloaded', timeout=10000)
        await asyncio.sleep(2)

        # Avatar: img with class containing "userImg"
        avatar_el = page.locator('img[class*="userImg"]').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()

        # Username: div with class containing "userName"
        name_el = page.locator('div[class*="userName"]').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()

        print(f"[baijiahao] profile scraped - name={name!r} avatar={avatar[:50] if avatar else 'None'}")
    except Exception as e:
        print(f"[baijiahao] profile scrape error: {e}")
    return name, avatar


async def scrape_youtube_profile(page):
    """YouTube-specific scraper.

    YouTube Studio uses Polymer Shadow DOM. The channel name appears in
    ``ytcp-ve`` elements and the avatar uses Google profile image URLs.

    Strategy:
      1. Try button[id="avatar-button"] + adjacent span for name (Studio header)
      2. Scan all ``<img>`` for ``ggpht.com`` / ``googleusercontent`` URLs
      3. Fallback to page title

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state('networkidle', timeout=15000)
        await asyncio.sleep(5)

        # Strategy 1: Avatar button in Studio header contains channel info
        avatar_btn = page.locator('button[id="avatar-button"]')
        if await avatar_btn.count():
            # The avatar image is inside the button
            btn_img = avatar_btn.locator('img')
            if await btn_img.count():
                src = (await btn_img.get_attribute('src') or '').strip()
                if src:
                    avatar = src
                alt = (await btn_img.get_attribute('alt') or '').strip()
                if alt and len(alt) < 50:
                    name = alt
            # aria-label often contains "账号: <channel name>"
            if not name:
                aria = (await avatar_btn.get_attribute('aria-label') or '').strip()
                if aria:
                    # e.g. "账号: MyChannel" or "Account: MyChannel"
                    for sep in (':', '：'):
                        if sep in aria:
                            candidate = aria.split(sep, 1)[1].strip()
                            if candidate:
                                name = candidate
                                break

        # Strategy 2: div#entity-name (present in some Studio views)
        if not name:
            name_el = page.locator('div#entity-name').first
            if await name_el.count():
                name = (await name_el.text_content() or '').strip()

        # Strategy 3: Scan all images for Google profile URLs
        if not avatar:
            all_imgs = page.locator('img')
            count = await all_imgs.count()
            for i in range(count):
                img = all_imgs.nth(i)
                src = (await img.get_attribute('src') or '')
                if 'ggpht.com' in src or 'googleusercontent.com' in src:
                    avatar = src
                    if not name:
                        alt = (await img.get_attribute('alt') or '').strip()
                        if alt and len(alt) < 50:
                            name = alt
                    break

        # Fallback: page title ("Channel Name - YouTube Studio")
        if not name:
            title = await page.title()
            if ' - ' in title:
                candidate = title.split(' - ')[0].strip()
                if candidate and candidate != 'YouTube':
                    name = candidate

        print(f"[youtube] profile scraped - name={name!r} avatar={avatar[:50] if avatar else 'None'}")
    except Exception as e:
        print(f"[youtube] profile scrape error: {e}")
    return name, avatar


# ---------------------------------------------------------------------------
# Schedule time parser
# Source: original postVideo.py schedule parser
# ---------------------------------------------------------------------------

def parse_schedule_time(schedule_time_str, total_files, enableTimer,
                       videos_per_day, daily_times, start_days):
    """Parse a user-specified schedule time string.

    If *enableTimer* is True and *schedule_time_str* can be parsed, returns
    that datetime repeated for every file.  Otherwise falls back to
    auto-generated times via ``generate_schedule_time_next_day``.

    Args:
        schedule_time_str: ISO-ish datetime string from the frontend.
        total_files: Number of files to schedule.
        enableTimer: Whether timed publishing is enabled.
        videos_per_day: Videos per day for auto-generation.
        daily_times: List of daily publish times for auto-generation.
        start_days: Offset in days for auto-generation.

    Returns:
        list[int | datetime]: One entry per file.
    """
    if enableTimer and schedule_time_str:
        try:
            raw = str(schedule_time_str)
            # Handle UTC ISO format (frontend may send 2026-05-16T13:00:00.000Z)
            is_utc = raw.endswith("Z") or "+00:00" in raw
            raw_clean = raw.replace("+08:00", "").replace("+00:00", "")

            for fmt in (
                "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
            ):
                try:
                    dt = datetime.strptime(raw_clean, fmt)
                    if is_utc:
                        dt = dt + timedelta(hours=8)
                    print(f"[schedule] using user-specified time: {dt}")
                    return [dt] * total_files
                except ValueError:
                    continue
            print(f"[schedule] cannot parse time '{schedule_time_str}', falling back to auto-generation")
        except Exception as e:
            print(f"[schedule] error parsing time: {e}, falling back to auto-generation")

    # No user-specified time: auto-generate
    if enableTimer:
        # Lazy import to avoid circular dependency
        from utils.files_times import generate_schedule_time_next_day
        return generate_schedule_time_next_day(total_files, videos_per_day, daily_times, start_days)
    else:
        return [0 for _ in range(total_files)]


# ---------------------------------------------------------------------------
# Unified post-login flow
# ---------------------------------------------------------------------------

async def save_login_result(
    context,
    page,
    platform_id: int,
    platform_name: str,
    status_queue,
    scrape_fn=None,
):
    """Shared post-login flow: scrape profile, save cookie, write DB, send SSE.

    This consolidates the repeated pattern found in every platform's login
    handler (Douyin, Bilibili, Xiaohongshu, Kuaishou, Channels, Baijiahao,
    YouTube, TikTok).

    Args:
        context: Playwright BrowserContext (used for cookie storage).
        page: Playwright Page (used for profile scraping).
        platform_id: Numeric platform identifier (matches ``user_info.type``).
        platform_name: Human-readable platform name for default usernames.
        status_queue: Queue for sending SSE status messages back to the
            frontend.
        scrape_fn: Optional async ``async (page) -> (name, avatar)`` callable.
            Defaults to :func:`scrape_user_profile` (the generic JS scraper).
    """
    if scrape_fn is None:
        scrape_fn = scrape_user_profile

    # 1. Scrape user profile
    user_name, avatar_url = await scrape_fn(page)
    if not user_name:
        user_name = f"{platform_name}用户{int(asyncio.get_event_loop().time())}"

    # 2. Save cookie file
    uuid_v1 = uuid.uuid1()
    print(f"UUID v1: {uuid_v1}")
    cookies_dir = Path(BASE_DIR / "cookiesFile")
    cookies_dir.mkdir(exist_ok=True)
    cookie_filename = f"{uuid_v1}.json"
    await context.storage_state(path=cookies_dir / cookie_filename)

    # 3. Write to database
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
            INSERT INTO user_info (type, filePath, userName, status, avatar)
            VALUES (?, ?, ?, ?, ?)
            ''',
            (platform_id, cookie_filename, user_name, 1, avatar_url),
        )
        conn.commit()
        print(f"[login] {platform_name} user record saved")

    # 4. Send SSE status
    status_queue.put(json.dumps({
        "status": "200",
        "name": user_name,
        "avatar": avatar_url,
    }))


# ---------------------------------------------------------------------------
# Platform URL registry (for sync_profile / open_creator_center)
# ---------------------------------------------------------------------------

PLATFORM_SYNC_URLS = {
    1: "https://creator.xiaohongshu.com/",
    2: "https://channels.weixin.qq.com/platform/post/create",
    3: "https://creator.douyin.com/",
    4: "https://cp.kuaishou.com/article/publish/video",
    5: "https://account.bilibili.com/account/home",
    6: "https://baijiahao.baidu.com/builder/rc/home",
    7: "https://www.tiktok.com/",
    8: "https://studio.youtube.com",
    9: "https://mp.v.qq.com/",
    10: "https://creator.iqiyi.com/",
}


# ---------------------------------------------------------------------------
# Platform scrape-function registry
# ---------------------------------------------------------------------------

PLATFORM_SCRAPE_FNS = {
    1: scrape_user_profile,         # Xiaohongshu
    2: scrape_tencent_profile,      # WeChat Channels
    3: scrape_user_profile,         # Douyin
    4: scrape_user_profile,         # Kuaishou
    5: scrape_bilibili_profile,     # Bilibili
    6: scrape_baijiahao_profile,    # Baijiahao
    7: scrape_user_profile,         # TikTok
    8: scrape_youtube_profile,      # YouTube
}
