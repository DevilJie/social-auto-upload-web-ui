# -*- coding: utf-8 -*-
"""v2: 把模块级 article 块移回 ZhihuPlatform 类内(缩进+4,恢复 self 语义)。"""
import ast
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FILE = Path(r"D:\work\QianfanSync\backend\impl\zhihu\platform.py")
src = FILE.read_text(encoding="utf-8")
lines = src.splitlines()

tree = ast.parse(src)
cls_end = None
block_start = None
for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "ZhihuPlatform":
        cls_end = node.end_lineno
    f = node
    if isinstance(node, ast.FunctionDef) and node.name == "_zhihu_publish_article":
        block_start = node.lineno - 1  # 0-based
assert cls_end and block_start, f"cls_end={cls_end} block_start={block_start}"
print(f"类尾 {cls_end}, 块起 {block_start + 1}")

head = lines[:cls_end]        # 类(到 1528)
middle = lines[cls_end:block_start]  # 中间的模块级函数(原样)
block = lines[block_start:]   # article 块(当前模块级)

# 块缩进 +4 并恢复 self 语义
moved = []
for l in block:
    if l.strip():
        l = "    " + l
    # 入口改名 + self 恢复
    l = l.replace(
        "def _zhihu_publish_article(**kwargs) -> bool:",
        "def publish_article(self, **kwargs) -> bool:",
    )
    l = l.replace(
        "return _zhihu_publish_article(**filtered)",
        "asyncio.run(self._zhihu_publish_one_article(**filtered))",
    )
    l = l.replace(
        "asyncio.run(self._publish_one_article(**filtered))",
        "asyncio.run(self._zhihu_publish_one_article(**filtered))",
    )
    l = l.replace(
        "async def _zhihu_publish_one_article(self,",
        "async def _zhihu_publish_one_article(self,",
    )
    l = l.replace("await _paste_zhihu_html(", "await self._paste_zhihu_html(")
    l = l.replace(
        "await _upload_article_images_to_zhihu(",
        "await self._upload_article_images_to_zhihu(",
    )
    l = l.replace("await _set_zhihu_cover(", "await self._set_zhihu_cover(")
    l = l.replace("await _click_zhihu_publish(", "await self._click_zhihu_publish(")
    l = l.replace("_resolve_image_local_path(", "self._resolve_image_local_path(")
    l = l.replace("self.self.", "self.")
    moved.append(l)

# 入口函数签名修正(模块级版没有 self,现在要 self)
moved = [
    l.replace(
        "def publish_article(**kwargs) -> bool:",
        "def publish_article(self, **kwargs) -> bool:",
    )
    for l in moved
]

delegate_and_class_tail = moved  # 整块(含入口)作为类方法插到类尾

new_lines = (
    head
    + delegate_and_class_tail
    + middle
)

FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
ast.parse(FILE.read_text(encoding="utf-8"))
print(f"written & AST OK, {len(new_lines) + 1} lines")
