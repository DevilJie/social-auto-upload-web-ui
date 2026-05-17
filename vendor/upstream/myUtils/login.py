import asyncio
import json
import sqlite3

from patchright.async_api import async_playwright

from myUtils.auth import check_cookie
from myUtils.browser import create_browser, create_context
import uuid
from pathlib import Path
from conf import BASE_DIR, LOGIN_HEADLESS


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


async def _scrape_bilibili_profile(page):
    """B站专用：从 account.bilibili.com/account/home 抓取用户资料"""
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await asyncio.sleep(2)
        # 昵称: span.home-top-msg-name
        name_el = page.locator('span.home-top-msg-name').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()
        # 头像: div.home-head img
        avatar_el = page.locator('div.home-head img').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()
        if name:
            print(f"✅ B站资料抓取成功 - 名称: {name}, 头像: {avatar[:50] if avatar else '无'}")
        else:
            print("⚠️ B站资料抓取失败，将使用默认名称")
    except Exception as e:
        print(f"⚠️ B站资料抓取异常: {e}")
    return name, avatar


async def _scrape_tencent_profile(page):
    """视频号专用：从 channels.weixin.qq.com/platform 抓取用户资料"""
    name = ""
    avatar = ""
    try:
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await asyncio.sleep(3)
        # 头像: img.avatar 或 img[alt="视频号头像"]
        avatar_el = page.locator('img.avatar, img[alt*="头像"]').first
        if await avatar_el.count():
            avatar = (await avatar_el.get_attribute('src') or '').strip()
        # 昵称: h2.finder-nickname 或 class 含 nickname
        name_el = page.locator('h2.finder-nickname, [class*="nickname"]').first
        if await name_el.count():
            name = (await name_el.text_content() or '').strip()
        if name:
            print(f"✅ 视频号资料抓取成功 - 名称: {name}, 头像: {avatar[:50] if avatar else '无'}")
        else:
            print("⚠️ 视频号资料抓取失败，将使用默认名称")
    except Exception as e:
        print(f"⚠️ 视频号资料抓取异常: {e}")
    return name, avatar


async def scrape_user_profile(page):
    """登录成功后从页面抓取用户名称和头像"""
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
        print(f"📋 抓取调试 - 候选: {debug}")
        if name:
            print(f"✅ 抓取到用户资料 - 名称: {name}, 头像: {avatar[:50] if avatar else '无'}")
        else:
            print("⚠️ 未能抓取到用户名称，将使用默认名称")
    except Exception as e:
        print(f"⚠️ 抓取用户资料失败: {e}")

    return name, avatar


# 抖音登录
async def douyin_cookie_gen(id, status_queue):
    url_changed_event = asyncio.Event()

    async def on_url_change():
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        browser = await create_browser(playwright, login_mode=True)
        context = await create_context(browser)
        page = await context.new_page()
        await page.goto("https://creator.douyin.com/")
        original_url = page.url
        img_locator = page.get_by_role("img", name="二维码")
        src = await img_locator.get_attribute("src")
        print("✅ 图片地址:", src)
        status_queue.put(src)
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)
        try:
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)
            print("监听页面跳转成功")
        except asyncio.TimeoutError:
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            status_queue.put("500")
            return None

        # 抓取用户资料
        user_name, avatar_url = await scrape_user_profile(page)
        if not user_name:
            user_name = f"抖音用户{int(asyncio.get_event_loop().time())}"

        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        await page.close()
        await context.close()
        await browser.close()
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO user_info (type, filePath, userName, status, avatar)
                                VALUES (?, ?, ?, ?, ?)
                                ''', (3, f"{uuid_v1}.json", user_name, 1, avatar_url))
            conn.commit()
            print("✅ 用户状态已记录")
        status_queue.put(json.dumps({"status": "200", "name": user_name, "avatar": avatar_url}))


# 视频号登录
async def get_tencent_cookie(id, status_queue):
    url_changed_event = asyncio.Event()

    async def on_url_change():
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        browser = await create_browser(playwright, login_mode=True, extra_args=['--lang en-GB'])
        context = await create_context(browser)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        original_url = page.url

        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        iframe_locator = page.frame_locator("iframe").first
        img_locator = iframe_locator.get_by_role("img").first
        src = await img_locator.get_attribute("src")
        print("✅ 图片地址:", src)
        status_queue.put(src)

        try:
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)
            print("监听页面跳转成功")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None

        # 抓取用户资料
        user_name, avatar_url = await _scrape_tencent_profile(page)
        if not user_name:
            user_name = f"视频号用户{int(asyncio.get_event_loop().time())}"

        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO user_info (type, filePath, userName, status, avatar)
                                VALUES (?, ?, ?, ?, ?)
                                ''', (2, f"{uuid_v1}.json", user_name, 1, avatar_url))
            conn.commit()
            print("✅ 用户状态已记录")
        status_queue.put(json.dumps({"status": "200", "name": user_name, "avatar": avatar_url}))


# 快手登录
async def get_ks_cookie(id, status_queue):
    url_changed_event = asyncio.Event()

    async def on_url_change():
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        browser = await create_browser(playwright, login_mode=True, extra_args=['--lang en-GB'])
        context = await create_context(browser)
        page = await context.new_page()
        await page.goto("https://cp.kuaishou.com")

        await page.get_by_role("link", name="立即登录").click()
        await page.get_by_text("扫码登录").click()
        img_locator = page.get_by_role("img", name="qrcode")
        src = await img_locator.get_attribute("src")
        original_url = page.url
        print("✅ 图片地址:", src)
        status_queue.put(src)
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        try:
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)
            print("监听页面跳转成功")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None

        # 抓取用户资料
        user_name, avatar_url = await scrape_user_profile(page)
        if not user_name:
            user_name = f"快手用户{int(asyncio.get_event_loop().time())}"

        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                        INSERT INTO user_info (type, filePath, userName, status, avatar)
                                        VALUES (?, ?, ?, ?, ?)
                                        ''', (4, f"{uuid_v1}.json", user_name, 1, avatar_url))
            conn.commit()
            print("✅ 用户状态已记录")
        status_queue.put(json.dumps({"status": "200", "name": user_name, "avatar": avatar_url}))


# 小红书登录
async def xiaohongshu_cookie_gen(id, status_queue):
    url_changed_event = asyncio.Event()

    async def on_url_change():
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        browser = await create_browser(playwright, login_mode=True, extra_args=['--lang en-GB'])
        context = await create_context(browser)
        page = await context.new_page()
        await page.goto("https://creator.xiaohongshu.com/")
        await page.locator('img.css-wemwzq').click()

        img_locator = page.get_by_role("img").nth(2)
        src = await img_locator.get_attribute("src")
        original_url = page.url
        print("✅ 图片地址:", src)
        status_queue.put(src)
        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        try:
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)
            print("监听页面跳转成功")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("监听页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None

        # 抓取用户资料
        user_name, avatar_url = await scrape_user_profile(page)
        if not user_name:
            user_name = f"小红书用户{int(asyncio.get_event_loop().time())}"

        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           INSERT INTO user_info (type, filePath, userName, status, avatar)
                           VALUES (?, ?, ?, ?, ?)
                           ''', (1, f"{uuid_v1}.json", user_name, 1, avatar_url))
            conn.commit()
            print("✅ 用户状态已记录")
        status_queue.put(json.dumps({"status": "200", "name": user_name, "avatar": avatar_url}))


# 用已有 cookies 同步账号资料（头像+昵称）
async def sync_account_profile(platform_type, cookie_file):
    """用已有 cookies 打开平台页面，抓取用户昵称和头像，返回 (name, avatar)"""
    platform_urls = {
        1: "https://creator.xiaohongshu.com/",
        2: "https://channels.weixin.qq.com/platform/post/create",
        3: "https://creator.douyin.com/",
        4: "https://cp.kuaishou.com/article/publish/video",
        5: "https://account.bilibili.com/account/home",
        6: "https://baijiahao.baidu.com/builder/rc/home",
        8: "https://studio.youtube.com",
    }
    url = platform_urls.get(platform_type)
    if not url:
        return "", ""

    async with async_playwright() as playwright:
        # YouTube 需要代理
        proxy = None
        if platform_type == 8:
            from conf import _load_proxy_url
            _proxy_url = _load_proxy_url()
            if _proxy_url:
                proxy = {"server": _proxy_url}

        # YouTube 无头模式会被 Google 拦截，需要有头模式
        headless = False if platform_type == 8 else True
        browser = await create_browser(playwright, headless=headless, proxy=proxy)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        context = await create_context(browser, storage_state=cookie_path)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
            if platform_type == 2:
                try:
                    await page.wait_for_selector('img.account-avatar, img[src*="finderhead"], img[src*="qlogo.cn"]', timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                name, avatar = await _scrape_tencent_profile(page)
            elif platform_type == 5:
                name, avatar = await _scrape_bilibili_profile(page)
            elif platform_type == 6:
                from uploader.baijiahao_uploader.main import _scrape_baijiahao_profile
                name, avatar = await _scrape_baijiahao_profile(page)
            elif platform_type == 8:
                from uploader.youtube_uploader.main import _scrape_youtube_profile
                name, avatar = await _scrape_youtube_profile(page)
            else:
                name, avatar = await scrape_user_profile(page)
            await page.close()
            await context.close()
            await browser.close()
            return name, avatar
        except Exception as e:
            print(f"⚠️ 同步资料失败: {e}")
            try:
                await page.close()
                await context.close()
                await browser.close()
            except Exception:
                pass
            return "", ""


# B站登录
async def bilibili_cookie_gen(id, status_queue):
    url_changed_event = asyncio.Event()

    async def on_url_change():
        if page.url != original_url:
            url_changed_event.set()

    async with async_playwright() as playwright:
        browser = await create_browser(playwright, login_mode=True)
        context = await create_context(browser)
        page = await context.new_page()
        await page.goto("https://passport.bilibili.com/login")
        original_url = page.url

        # B站登录页面会显示二维码，等待二维码图片加载
        try:
            qr_img = page.locator('.qrcode-img img, img[src*="qrcode"], .login-scan img').first
            src = await qr_img.get_attribute("src")
            if not src:
                qr_img = page.get_by_role("img").nth(0)
                src = await qr_img.get_attribute("src")
        except Exception as e:
            print(f"⚠️ 定位B站二维码失败: {e}")
            src = None

        if src:
            print("✅ B站二维码地址:", src[:80] if src else "无")
            status_queue.put(src)
        else:
            print("⚠️ 未找到B站二维码图片")
            status_queue.put("500")
            await page.close()
            await context.close()
            await browser.close()
            return None

        page.on('framenavigated',
                lambda frame: asyncio.create_task(on_url_change()) if frame == page.main_frame else None)

        try:
            await asyncio.wait_for(url_changed_event.wait(), timeout=200)
            print("B站登录页面跳转成功")
        except asyncio.TimeoutError:
            status_queue.put("500")
            print("B站登录页面跳转超时")
            await page.close()
            await context.close()
            await browser.close()
            return None

        # 登录成功后导航到账号页，抓取用户资料
        await page.goto("https://account.bilibili.com/account/home")
        await asyncio.sleep(2)
        user_name, avatar_url = await _scrape_bilibili_profile(page)
        if not user_name:
            user_name = f"B站用户{int(asyncio.get_event_loop().time())}"

        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        cookies_dir = Path(BASE_DIR / "cookiesFile")
        cookies_dir.mkdir(exist_ok=True)
        await context.storage_state(path=cookies_dir / f"{uuid_v1}.json")
        await page.close()
        await context.close()
        await browser.close()

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                           INSERT INTO user_info (type, filePath, userName, status, avatar)
                           VALUES (?, ?, ?, ?, ?)
                           ''', (5, f"{uuid_v1}.json", user_name, 1, avatar_url))
            conn.commit()
            print("✅ B站用户状态已记录")
        status_queue.put(json.dumps({"status": "200", "name": user_name, "avatar": avatar_url}))
