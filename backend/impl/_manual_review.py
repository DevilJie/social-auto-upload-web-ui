"""Local policy: pause between fields; the user submits on the platform page.

No timeout, retry, or confirmation handler in this module may click publish.
Completion requires a user submit gesture AND a platform success signal.

「发布提交方式」按 渠道 × 发布类型(video/image/article) 粒度控制：

- settings 表 key='manualReviewMatrix'，JSON：
  {"douyin": {"video": true, "image": false}, ...}，缺省视为 false（自动提交）。
- 旧 key 'manualReview'（全局 'true'/'false'）仅作迁移基线：矩阵缺失或解析
  失败时，旧值为 true 视为历史上实际生效的 9 个组合开启，其余全部关闭。
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import urlparse

from conf import BASE_DIR

logger = logging.getLogger(__name__)
INPUT_PAUSE_SECONDS = 5

MATRIX_KEY = 'manualReviewMatrix'
LEGACY_KEY = 'manualReview'

# 旧全局开关 manualReview='true' 时历史上唯一实际生效的组合（迁移基线）：
# 视频×{抖音,小红书,快手,B站,视频号,YouTube} + 图文×{抖音,小红书,快手}
_LEGACY_ENABLED_COMBOS = frozenset({
    ('douyin', 'video'), ('xiaohongshu', 'video'), ('kuaishou', 'video'),
    ('bilibili', 'video'), ('channels', 'video'), ('youtube', 'video'),
    ('douyin', 'image'), ('xiaohongshu', 'image'), ('kuaishou', 'image'),
})

# 等待人工提交时除通用文案外的平台专属成功文案
_PLATFORM_EXTRA_LABELS = {
    'iqiyi': ('已发布', '提交成功', '发布完成'),
    'tencent_video': ('提交成功',),
}

_GENERIC_SUCCESS_LABELS = (
    '发布成功', '投稿成功', '发表成功', '稿件投递成功', '定时发布设置成功',
)


def _read_setting(key):
    db = Path(BASE_DIR) / "db" / "database.db"
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
    return row[0] if row else None


def _load_matrix():
    """读取 渠道×类型 开关矩阵，返回 {(platform, ptype): bool}。

    矩阵 key 缺失或 JSON 解析失败时，回退旧全局开关的迁移基线；
    读取失败一律按全关（自动提交）处理。
    """
    raw = None
    try:
        raw = _read_setting(MATRIX_KEY)
    except Exception as e:
        logger.warning("[人工验收] 读取矩阵设置失败,回退旧开关: %s", e)
    if raw:
        try:
            data = json.loads(raw)
            return {
                (str(platform), str(ptype)): bool(enabled)
                for platform, types in (data or {}).items()
                for ptype, enabled in (types or {}).items()
            }
        except (ValueError, TypeError) as e:
            logger.warning("[人工验收] 矩阵 JSON 解析失败,回退旧开关: %s", e)
    legacy = None
    try:
        legacy = _read_setting(LEGACY_KEY)
    except Exception as e:
        logger.warning("[人工验收] 读取旧开关失败,按自动提交处理: %s", e)
    if legacy is not None and str(legacy).strip().lower() in ("1", "true", "yes"):
        return {combo: True for combo in _LEGACY_ENABLED_COMBOS}
    return {}


def manual_review_enabled(platform, publish_type='video'):
    """系统设置「发布提交方式」（渠道×发布类型粒度）。

    true  = 人工验收：填写完成后保留浏览器，等待用户亲自点击平台发布。
    false / 未设置（默认）= 自动提交：程序自动点击平台发布按钮。
    读取失败一律按自动提交处理。
    """
    try:
        return bool(_load_matrix().get((str(platform), str(publish_type)), False))
    except Exception as e:
        logger.warning("[人工验收] 读取设置失败,按自动提交处理: %s", e)
        return False


async def pause_after_input():
    await asyncio.sleep(INPUT_PAUSE_SECONDS)


def is_success_url(platform, url):
    """平台专属成功页判定（URL 白名单 + 少量"离开发布页"型反向规则）。"""
    parsed = urlparse(url)
    host, path = parsed.hostname, parsed.path.rstrip('/')
    if platform == 'douyin':
        return host == 'creator.douyin.com' and path == '/creator-micro/content/manage'
    if platform == 'channels':
        return host == 'channels.weixin.qq.com' and path == '/platform/post/list'
    if platform == 'kuaishou':
        return host == 'cp.kuaishou.com' and path == '/article/manage/video'
    if platform == 'xiaohongshu':
        return host == 'creator.xiaohongshu.com' and path in (
            '/publish/success', '/publish/publish/success', '/new/note-manager',
        )
    if platform == 'bilibili':
        return host == 'member.bilibili.com' and path in (
            '/platform/upload/video/success', '/platform/upload-manager/article',
        )
    if platform == 'baijiahao':
        return host == 'baijiahao.baidu.com' and path.startswith('/builder/rc/clue')
    if platform == 'tiktok':
        return host in ('www.tiktok.com', 'tiktok.com') and path.startswith('/tiktokstudio/content')
    if platform == 'toutiao':
        # 点击发布后离开 upload-video 页即视为成功（与自动提交判据一致）
        return host == 'mp.toutiao.com' and 'upload-video' not in path
    if platform == 'dayu':
        return host == 'mp.dayu.com' and path.startswith('/dashboard/contents')
    if platform == 'taobao_guanghe':
        # 按钮在 iframe 内，成功跳转发生在主 frame
        return '/page/workspace/tb' in path
    if platform == 'jd':
        target = path + parsed.fragment
        return host == 'dr.jd.com' and 'publish-video' not in target
    if platform == 'csdn':
        return 'videoUpload' not in url
    if platform == 'vivo':
        return 'content/uploads' not in url and '#/uploads' not in url
    if platform == 'weibo':
        return host in ('weibo.com', 'www.weibo.com') and path.startswith('/u/')
    if platform == 'youtube':
        return host == 'studio.youtube.com'
    return False


_INSTALL_REVIEW = r"""({binding, banner}) => {
    const labels = /^(发布|发布视频|发布博客|预约发布|定时发布|确认发布|立即发布|发表|定时发表|确认发表|投稿|立即投稿|提交投稿|确认投稿|提交|确认提交|发送|完成|儲存|發布|排程|Done|Save|Publish|Schedule)$/i;
    const listener = event => {
        if (!event.isTrusted) return;
        if (event.type === 'keydown' && !['Enter', ' '].includes(event.key)) return;
        const match = event.composedPath().some(el => {
            if (!el || !el.tagName) return false;
            if (el.tagName.toLowerCase() === 'xhs-publish-btn' || el.matches?.('.xhs-publish-btn')) return true;
            if (el.matches?.('#done-button')) return true;
            if (!el.matches?.('button,[role="button"],input[type="submit"],.submit-add')) return false;
            const text = (el.innerText || el.textContent || '').trim();
            return labels.test(text);
        });
        if (match) window[binding]();
    };
    document.addEventListener('click', listener, true);
    document.addEventListener('keydown', listener, true);
    if (!banner) return;
    const bannerEl = document.createElement('div');
    bannerEl.dataset.sauManualReview = 'true';
    bannerEl.textContent = '等待人工验收：请核对标题、正文、标签、热点、位置、封面及定时。确认后请亲自点击平台发布按钮及后续确认；程序不会自动提交。关闭页面可取消。';
    bannerEl.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;padding:12px;background:#fff3cd;color:#352a00;font:14px/1.5 sans-serif;pointer-events:none';
    document.body.appendChild(bannerEl);
}"""


async def wait_for_manual_publish(page, platform, success_check=None):
    """Leave the filled form open until manual submission is observed.

    Invalid fields or a confirmation modal keep the task waiting. Closing the
    page is cancellation, never publication success. No automated input occurs
    once review starts, so the trusted gesture is a user's platform action.

    success_check: 可选异步回调 ``(page) -> bool``，平台专属成功判定
    （如知乎监听发布 API 响应）。提供时替代默认的「URL 白名单 + 成功文案」判定。
    """
    submitted_by_user = False

    def on_submit(source):
        nonlocal submitted_by_user
        submitted_by_user = True

    binding = '_sau_manual_' + uuid.uuid4().hex
    await page.expose_binding(binding, on_submit)
    # 跨域 iframe 里的发布按钮（淘宝广河/京东/极脉等）不会冒泡到主 document，
    # 监听必须逐 frame 安装；横幅只挂主 frame（page.frames 首个是主 frame）。
    frames = list(getattr(page, 'frames', None) or [page])
    for index, frame in enumerate(frames):
        try:
            await frame.evaluate(_INSTALL_REVIEW, {'binding': binding, 'banner': index == 0})
        except Exception as e:
            logger.debug('[人工验收] %s frame#%d 安装监听失败(忽略): %s', platform, index, e)
    await page.bring_to_front()
    logger.warning('[人工验收] %s 填写完成，等待用户亲自发布；不会超时自动提交', platform)
    while True:
        if page.is_closed():
            raise asyncio.CancelledError('人工验收页面已关闭，未确认发布结果')
        if submitted_by_user:
            if success_check is not None:
                try:
                    success = await success_check(page)
                except Exception as e:
                    # 平台判定器自身异常不应终止等待，也不应误判成功
                    logger.debug('[人工验收] %s 成功判定器异常,继续等待: %s', platform, e)
                    success = False
            else:
                success = is_success_url(platform, page.url)
                if platform == 'youtube':
                    # Studio stays on the same URL and opens a post-submit share dialog.
                    try:
                        success = await page.locator('ytcp-video-share-dialog').first.is_visible()
                    except Exception:
                        success = False  # Navigation may temporarily replace the DOM.
                # Some platform versions render the success view without navigation.
                if not success:
                    labels = _GENERIC_SUCCESS_LABELS + _PLATFORM_EXTRA_LABELS.get(platform, ())
                    for label in labels:
                        try:
                            if await page.get_by_text(label, exact=True).first.is_visible():
                                success = True
                                break
                        except Exception:
                            if page.is_closed():
                                raise asyncio.CancelledError('人工验收页面已关闭')
            if success:
                logger.info('[人工验收] %s 已观察到用户提交和平台成功反馈', platform)
                return
        await asyncio.sleep(0.5)
