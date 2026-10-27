"""Offline tests: no account, browser launch, upload, or publication needed."""
import asyncio
import ast
import importlib.util
import json
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
        namespace = {
            'wait_for_manual_publish': gate,
            # gate 开关打桩为 True：验证人工验收分支只等待、绝不点击
            'manual_review_enabled': lambda *a, **k: True,
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<test>', 'exec'), namespace)
        page = object()
        await namespace['_click_publish_button'](page, '定时发布')
        gate.assert_awaited_once_with(page, 'xiaohongshu')


class ManualReviewMatrixTests(unittest.TestCase):
    """渠道×发布类型 粒度开关：矩阵读取、旧值迁移、失败兜底。"""

    def settings_patch(self, matrix_raw, legacy_raw):
        values = {
            review.MATRIX_KEY: matrix_raw,
            review.LEGACY_KEY: legacy_raw,
        }
        return patch.object(review, '_read_setting', side_effect=lambda key: values.get(key))

    def test_matrix_entries_are_respected(self):
        matrix = json.dumps({
            'douyin': {'video': True, 'image': False},
            'weibo': {'article': True},
        })
        with self.settings_patch(matrix, 'false'):
            self.assertTrue(review.manual_review_enabled('douyin', 'video'))
            self.assertFalse(review.manual_review_enabled('douyin', 'image'))
            self.assertTrue(review.manual_review_enabled('weibo', 'article'))
            self.assertFalse(review.manual_review_enabled('weibo', 'video'))
            self.assertFalse(review.manual_review_enabled('zhihu', 'article'))

    def test_legacy_true_migrates_nine_combos(self):
        with self.settings_patch(None, 'true'):
            self.assertTrue(review.manual_review_enabled('douyin', 'video'))
            self.assertTrue(review.manual_review_enabled('kuaishou', 'image'))
            self.assertTrue(review.manual_review_enabled('youtube', 'video'))
            self.assertFalse(review.manual_review_enabled('weibo', 'video'))
            self.assertFalse(review.manual_review_enabled('weibo', 'article'))
            self.assertFalse(review.manual_review_enabled('zhihu', 'article'))

    def test_legacy_false_means_all_auto(self):
        with self.settings_patch(None, 'false'):
            self.assertFalse(review.manual_review_enabled('douyin', 'video'))
            self.assertFalse(review.manual_review_enabled('zhihu', 'article'))

    def test_invalid_matrix_falls_back_to_legacy(self):
        with self.settings_patch('{not-json', 'true'):
            self.assertTrue(review.manual_review_enabled('xiaohongshu', 'image'))
        with self.settings_patch('{not-json', 'false'):
            self.assertFalse(review.manual_review_enabled('xiaohongshu', 'image'))

    def test_read_failure_falls_back_to_auto_submit(self):
        with patch.object(review, '_read_setting', side_effect=RuntimeError('db locked')):
            self.assertFalse(review.manual_review_enabled('douyin', 'video'))

    def test_new_success_url_rules(self):
        cases = {
            'baijiahao': 'https://baijiahao.baidu.com/builder/rc/clue?id=1',
            'tiktok': 'https://www.tiktok.com/tiktokstudio/content?tab=uploaded',
            'toutiao': 'https://mp.toutiao.com/profile_v4/graphic/articles',
            'dayu': 'https://mp.dayu.com/dashboard/contents',
            'taobao_guanghe': 'https://acs.aliyun.com/page/workspace/tb?id=9',
            'jd': 'https://dr.jd.com/jm/#/content-list',
        }
        for platform, url in cases.items():
            self.assertTrue(review.is_success_url(platform, url), platform)
        self.assertFalse(review.is_success_url('toutiao', 'https://mp.toutiao.com/profile_v4/xigua/upload-video'))
        self.assertFalse(review.is_success_url('jd', 'https://dr.jd.com/jm/#/publish-video'))
        self.assertFalse(review.is_success_url('baijiahao', 'https://example.com/builder/rc/clue'))

    def test_iqiyi_extra_success_labels(self):
        page = FakePage()
        ticks = 0

        def tick(_):
            nonlocal ticks
            ticks += 1
            page.callback({})
            page.visible_labels.add('提交成功')

        async def drive():
            with patch.object(review.asyncio, 'sleep', new=AsyncMock(side_effect=tick)):
                await review.wait_for_manual_publish(page, 'iqiyi')

        asyncio.run(drive())
        self.assertGreaterEqual(ticks, 1)


class ManualReviewCustomCheckTests(unittest.IsolatedAsyncioTestCase):
    async def run_review(self, tick, page=None, **kwargs):
        page = page or FakePage()
        with patch.object(review.asyncio, 'sleep', new=AsyncMock(side_effect=lambda _: tick(page))):
            await review.wait_for_manual_publish(page, 'zhihu', **kwargs)
        return page

    async def test_custom_success_check_overrides_defaults(self):
        page = FakePage()
        page.url = 'https://creator.douyin.com/creator-micro/content/manage'

        async def check(p):
            return p is page

        def tick(_):
            page.callback({})

        result = await self.run_review(tick, page, success_check=check)
        self.assertIs(result, page)

    async def test_failing_success_check_keeps_waiting(self):
        page = FakePage()
        calls = 0

        async def check(_):
            nonlocal calls
            calls += 1
            return calls >= 3

        def tick(_):
            page.callback({})

        await self.run_review(tick, page, success_check=check)
        self.assertGreaterEqual(calls, 3)

    async def test_raising_success_check_never_succeeds(self):
        ticks = 0

        async def check(_):
            raise RuntimeError('probe failed')

        def tick(page):
            nonlocal ticks
            ticks += 1
            page.callback({})
            if ticks == 6:
                page.closed = True

        with self.assertRaises(asyncio.CancelledError):
            await self.run_review(tick, success_check=check)
        self.assertEqual(ticks, 6)


class FakeFrame:
    def __init__(self):
        self.calls = []

    async def evaluate(self, script, args):
        self.calls.append(args)


class MultiFramePage(FakePage):
    """发布按钮在跨域 iframe 内的平台（淘宝广河/京东等）：监听需逐 frame 安装。"""

    def __init__(self):
        super().__init__()
        self._frames = [FakeFrame() for _ in range(3)]

    @property
    def frames(self):
        return self._frames


class ManualReviewFrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_listener_installed_on_every_frame_banner_only_main(self):
        page = MultiFramePage()

        def tick(_):
            page.callback({})
            page.url = 'https://creator.douyin.com/creator-micro/content/manage'

        with patch.object(review.asyncio, 'sleep', new=AsyncMock(side_effect=tick)):
            await review.wait_for_manual_publish(page, 'douyin')
        self.assertEqual([c['banner'] for c in page.frames[0].calls], [True])
        for frame in page.frames[1:]:
            self.assertEqual([c['banner'] for c in frame.calls], [False])

    async def test_page_without_frames_attribute_installs_once(self):
        page = FakePage()

        def tick(_):
            page.callback({})
            page.url = 'https://creator.douyin.com/creator-micro/content/manage'

        evaluate_calls = []
        original_evaluate = page.evaluate

        async def tracked_evaluate(script, args):
            evaluate_calls.append(args)
            await original_evaluate(script, args)

        page.evaluate = tracked_evaluate
        with patch.object(review.asyncio, 'sleep', new=AsyncMock(side_effect=tick)):
            await review.wait_for_manual_publish(page, 'douyin')
        self.assertEqual(len(evaluate_calls), 1)
        self.assertTrue(evaluate_calls[0]['banner'])


if __name__ == '__main__':
    unittest.main()
