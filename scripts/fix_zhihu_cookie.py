# -*- coding: utf-8 -*-
"""修 zhihu _zhihu_publish_one_article 的 account_file(list→路径)。"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P = r"D:\work\QianfanSync\backend\impl\zhihu\platform.py"
src = open(P, encoding="utf-8").read()

old = (
    "context = await self.create_context(\n"
    "                browser, storage_state=account_file\n"
    "            )"
)
new = (
    'cookie_path = str(Path(BASE_DIR / "cookiesFile" / account_file[0]))\n'
    "                context = await self.create_context(\n"
    "                    browser, storage_state=cookie_path\n"
    "                )"
)
assert old in src, "anchor not found"
src = src.replace(old, new, 1)
open(P, "w", encoding="utf-8").write(src)
print("patched")

import py_compile

py_compile.compile(P, doraise=True)
print("compile OK")
