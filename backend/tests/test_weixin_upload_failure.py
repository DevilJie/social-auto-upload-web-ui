"""Exercise the real upload wait loop and its JS against a minimal page DOM."""
import ast
import asyncio
import json
import logging
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'impl/weixin_gzh/platform.py'
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
method = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)
              and n.name == '_wait_for_video_uploaded')
method.decorator_list = []
scope = {'asyncio': asyncio, 'logger': logging.getLogger(__name__),
         'raise_if_page_closed': lambda page: None}
exec(compile(ast.Module(body=[method], type_ignores=[]), str(SOURCE), 'exec'), scope)

class Page:
    def __init__(self, text, visible=True):
        self.text, self.visible = text, visible

    async def evaluate(self, script):
        harness = '''const el = {children: [], textContent: TEXT, offsetParent: VISIBLE ? {} : null};
        const document = {querySelectorAll: selector => selector === '*' ? [el] : []};
        console.log(JSON.stringify((SCRIPT)()));'''
        harness = harness.replace('TEXT', json.dumps(self.text)).replace('VISIBLE', json.dumps(self.visible)).replace('SCRIPT', script)
        return json.loads(subprocess.check_output(['node', '-e', harness], encoding='utf-8'))

    def locator(self, selector):
        return self

    async def all_inner_texts(self):
        return []

async def no_sleep(_):
    pass

class UploadFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_creation_failure_is_reported_instead_of_waiting(self):
        with patch.object(asyncio, 'sleep', no_sleep):
            with self.assertRaisesRegex(RuntimeError, '创建文件失败'):
                await scope['_wait_for_video_uploaded'](Page('创建文件失败'), timeout_s=0.2)

    async def test_hidden_failure_template_is_ignored(self):
        with patch.object(asyncio, 'sleep', no_sleep):
            with self.assertRaisesRegex(RuntimeError, '等待超时'):
                await scope['_wait_for_video_uploaded'](Page('创建文件失败', False), timeout_s=0.2)

    async def test_other_visible_failures_are_reported(self):
        for text in ('上传失败', '转码失败'):
            with self.subTest(text=text), self.assertRaisesRegex(RuntimeError, text):
                await scope['_wait_for_video_uploaded'](Page(text), timeout_s=2)

    async def test_visible_success_returns(self):
        await scope['_wait_for_video_uploaded'](Page('视频上传成功'), timeout_s=2)

if __name__ == '__main__':
    unittest.main()
