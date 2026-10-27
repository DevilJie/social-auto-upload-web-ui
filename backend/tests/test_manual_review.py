"""Offline tests: no account, browser launch, upload, or publication needed."""
import asyncio
import ast
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

IMPL = Path(__file__).resolve().parents[1] / 'impl'
spec = importlib.util.spec_from_file_location('manual_review', IMPL / '_manual_review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class FakeLocator:
    def __init__(self, page, label):
        self.page, self.label = page, label
        self.first = self

    async def is_visible(self):
        return self.label in self.page.visible_labels


class FakePage:
    def __init__(self):
        self.url = 'https://creator.douyin.com/creator-micro/content/upload'
        self.closed = False
        self.visible_labels = set()
        self.callback = None
        self.foreground = False

    async def expose_binding(self, name, callback):
        self.callback = callback

    async def evaluate(self, script, args):
        assert 'isTrusted' in script
        assert 'click()' not in script

    async def bring_to_front(self):
        self.foreground = True

    def is_closed(self):
        return self.closed

    def get_by_text(self, label, exact):
        assert exact
        return FakeLocator(self, label)

    def locator(self, selector):
        return FakeLocator(self, selector)


class ManualReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_is_five_seconds(self):
        with patch.object(review.asyncio, 'sleep', new_callable=AsyncMock) as sleep:
            await review.pause_after_input()
        sleep.assert_awaited_once_with(5)

    async def run_review(self, tick, page=None):
        page = page or FakePage()
        with patch.object(review.asyncio, 'sleep', new=AsyncMock(side_effect=lambda _: tick(page))):
            await review.wait_for_manual_publish(page, 'douyin')
        return page

    async def test_idle_never_submits_and_close_cancels(self):
        ticks = 0

        def tick(page):
            nonlocal ticks
            ticks += 1
            if ticks == 40:
                page.closed = True

        with self.assertRaises(asyncio.CancelledError):
            await self.run_review(tick)
        self.assertEqual(ticks, 40)

    async def test_success_url_without_user_submit_is_not_success(self):
        page = FakePage()
        page.url = 'https://creator.douyin.com/creator-micro/content/manage'
        with self.assertRaises(asyncio.CancelledError):
            await self.run_review(lambda p: setattr(p, 'closed', True), page)

    async def test_manual_submit_with_success_url_completes(self):
        def tick(page):
            page.callback({})
            page.url = 'https://creator.douyin.com/creator-micro/content/manage'
        page = await self.run_review(tick)
        self.assertTrue(page.foreground)

    async def test_manual_submit_with_success_message_completes(self):
        def tick(page):
            page.callback({})
            page.visible_labels.add('发布成功')
        await self.run_review(tick)

    async def test_validation_error_or_confirmation_dialog_keeps_waiting(self):
        ticks = 0

        def tick(page):
            nonlocal ticks
            ticks += 1
            page.callback({})
            page.visible_labels = {'确认发布', '请填写标题'}
            if ticks == 8:
                page.closed = True

        with self.assertRaises(asyncio.CancelledError):
            await self.run_review(tick)
        self.assertEqual(ticks, 8)

    async def test_cancel_propagates_without_publishing(self):
        def tick(page):
            raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.run_review(tick)

    async def test_youtube_requires_user_submission_and_share_dialog(self):
        page = FakePage()
        page.url = 'https://studio.youtube.com/channel/test'
        ticks = 0

        def tick(_):
            nonlocal ticks
            ticks += 1
            page.callback({})
            if ticks == 3:
                page.visible_labels.add('ytcp-video-share-dialog')

        with patch.object(review.asyncio, 'sleep', new=AsyncMock(side_effect=tick)):
            await review.wait_for_manual_publish(page, 'youtube')
        self.assertEqual(ticks, 3)

    def test_success_url_is_platform_specific(self):
        cases = {
            'douyin': 'https://creator.douyin.com/creator-micro/content/manage',
            'xiaohongshu': 'https://creator.xiaohongshu.com/publish/success',
            'kuaishou': 'https://cp.kuaishou.com/article/manage/video?status=2&from=publish',
            'channels': 'https://channels.weixin.qq.com/platform/post/list',
            'bilibili': 'https://member.bilibili.com/platform/upload-manager/article',
        }
        for platform, url in cases.items():
            self.assertTrue(review.is_success_url(platform, url))
            self.assertFalse(review.is_success_url(platform, url.replace('https://', 'https://wrong.')))
            self.assertFalse(review.is_success_url(platform, 'https://example.com/success'))
        self.assertFalse(review.is_success_url('douyin', 'https://creator.douyin.com/login'))

    def test_each_selected_platform_has_gate_and_field_pauses(self):
        for platform in ('douyin', 'xiaohongshu', 'kuaishou', 'channels', 'bilibili'):
            tree = ast.parse((IMPL / platform / 'platform.py').read_text(encoding='utf-8'))
            calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
            self.assertTrue(any(getattr(n.func, 'id', '') == 'wait_for_manual_publish' for n in calls), platform)
            self.assertGreaterEqual(sum(getattr(n.func, 'id', '') == 'pause_after_input' for n in calls), 3, platform)

    async def test_xiaohongshu_submit_helper_only_waits(self):
        tree = ast.parse((IMPL / 'xiaohongshu/platform.py').read_text(encoding='utf-8'))
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_click_publish_button')
        gate = AsyncMock()
        namespace = {'wait_for_manual_publish': gate}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<test>', 'exec'), namespace)
        page = object()
        await namespace['_click_publish_button'](page, '定时发布')
        gate.assert_awaited_once_with(page, 'xiaohongshu')


if __name__ == '__main__':
    unittest.main()
