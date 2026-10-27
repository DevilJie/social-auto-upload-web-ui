"""Local policy: pause between fields; the user submits on the platform page.

No timeout, retry, or confirmation handler in this module may click publish.
Completion requires a user submit gesture AND a platform success signal.
"""

import asyncio
import logging
import uuid
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
INPUT_PAUSE_SECONDS = 5


async def pause_after_input():
    await asyncio.sleep(INPUT_PAUSE_SECONDS)


def is_success_url(platform, url):
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
    return False


_INSTALL_REVIEW = r"""({binding}) => {
    const labels = /^(发布|定时发布|确认发布|立即发布|发表|定时发表|确认发表|投稿|立即投稿|提交投稿|确认投稿|提交|确认提交|完成|儲存|發布|排程|Done|Save|Publish|Schedule)$/i;
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
    const banner = document.createElement('div');
    banner.dataset.sauManualReview = 'true';
    banner.textContent = '等待人工验收：请核对标题、正文、标签、热点、位置、封面及定时。确认后请亲自点击平台发布按钮及后续确认；程序不会自动提交。关闭页面可取消。';
    banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;padding:12px;background:#fff3cd;color:#352a00;font:14px/1.5 sans-serif;pointer-events:none';
    document.body.appendChild(banner);
}"""


async def wait_for_manual_publish(page, platform):
    """Leave the filled form open until manual submission is observed.

    Invalid fields or a confirmation modal keep the task waiting. Closing the
    page is cancellation, never publication success. No automated input occurs
    once review starts, so the trusted gesture is a user's platform action.
    """
    submitted_by_user = False

    def on_submit(source):
        nonlocal submitted_by_user
        submitted_by_user = True

    binding = '_sau_manual_' + uuid.uuid4().hex
    await page.expose_binding(binding, on_submit)
    await page.evaluate(_INSTALL_REVIEW, {'binding': binding})
    await page.bring_to_front()
    logger.warning('[人工验收] %s 填写完成，等待用户亲自发布；不会超时自动提交', platform)
    while True:
        if page.is_closed():
            raise asyncio.CancelledError('人工验收页面已关闭，未确认发布结果')
        if submitted_by_user:
            success = is_success_url(platform, page.url)
            if platform == 'youtube':
                # Studio stays on the same URL and opens a post-submit share dialog.
                try:
                    success = await page.locator('ytcp-video-share-dialog').first.is_visible()
                except Exception:
                    success = False  # Navigation may temporarily replace the DOM.
            # Some platform versions render the success view without navigation.
            if not success:
                for label in ('发布成功', '投稿成功', '发表成功', '稿件投递成功', '定时发布设置成功'):
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
