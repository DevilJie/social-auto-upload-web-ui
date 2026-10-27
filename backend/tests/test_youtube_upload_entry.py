"""Exercise the actual entry helper without uploading or publishing anything."""
import ast
import asyncio
from pathlib import Path
import re
import tempfile
import unittest
import uuid
from unittest.mock import AsyncMock, Mock

SOURCE = Path(__file__).resolve().parents[1] / 'impl/youtube/platform.py'


class UploadEntryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        fn = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_open_upload_dialog')
        namespace = dict(logger=Mock(), _msg=lambda x: x, Path=Path, BASE_DIR=Path(self.temp.name), re=re, uuid=uuid)
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<entry>', 'exec'), namespace)
        self.open = namespace['_open_upload_dialog']
        self.page = Mock(url='https://studio.youtube.com/channel/test')
        self.file = Mock()
        self.file.first = self.file
        self.file.wait_for = AsyncMock()
        self.file.count = AsyncMock(return_value=0)
        self.button = Mock()
        self.button.first = self.button
        self.button.wait_for = AsyncMock()
        self.button.click = AsyncMock()
        self.button.filter.return_value = self.button
        self.page.locator.side_effect = lambda s: self.file if s == 'input[name="Filedata"]' else self.button
        self.page.get_by_text.return_value = self.button
        self.page.screenshot = AsyncMock()

    async def test_existing_hidden_file_input_needs_no_click(self):
        await self.open(None, self.page)
        self.button.click.assert_not_awaited()
        self.file.wait_for.assert_awaited_once_with(state='attached', timeout=1000)

    async def test_direct_entry_waits_for_actual_input_not_old_visible_picker(self):
        self.file.wait_for.side_effect = [TimeoutError(), None]
        await self.open(None, self.page)
        self.button.click.assert_awaited_once_with(timeout=5000)
        self.assertTrue(all('select-files-button' not in c.args[0] for c in self.page.locator.call_args_list))
        self.assertTrue(all(c.kwargs['state'] == 'attached' for c in self.file.wait_for.call_args_list))

    async def test_create_menu_fallback(self):
        self.file.wait_for.side_effect = [TimeoutError(), TimeoutError(), None]
        await self.open(None, self.page)
        self.assertEqual(self.button.click.await_count, 3)
        self.page.get_by_text.assert_called_once()

    async def test_login_redirect_reports_login_problem(self):
        self.file.wait_for.side_effect = TimeoutError()
        self.page.url = 'https://accounts.google.com/signin'
        with self.assertRaisesRegex(RuntimeError, '登录状态'):
            await self.open(None, self.page)
        self.button.click.assert_not_awaited()

    async def test_failure_saves_diagnostics_without_upload(self):
        self.file.wait_for.side_effect = TimeoutError()
        with self.assertRaisesRegex(RuntimeError, '尚未选择视频文件'):
            await self.open(None, self.page)
        self.page.screenshot.assert_awaited_once()
        self.file.set_input_files.assert_not_called()

    def test_final_automatic_done_click_is_removed(self):
        text = SOURCE.read_text(encoding='utf-8')
        self.assertNotIn('await done_btn.click()', text)
        self.assertIn("await wait_for_manual_publish(page, 'youtube')", text)


if __name__ == '__main__':
    unittest.main()
