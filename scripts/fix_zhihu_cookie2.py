# -*- coding: utf-8 -*-
"""修正 cookie_path 段缩进 v2(锚点: browser 行 idx1587 + try 行 idx1588)。"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P = r"D:\work\QianfanSync\backend\impl\zhihu\platform.py"
lines = open(P, encoding="utf-8").read().splitlines()

assert "browser = await self.create_browser(headless=False)" in lines[1587], (
    f"1588: {lines[1587]}"
)
assert "try:" == lines[1588].strip(), f"1589: {lines[1588]}"

fixed = (
    lines[:1589]
    + [
        '        cookie_path = str(Path(BASE_DIR / "cookiesFile" / account_file[0]))',
        "        context = await self.create_context(",
        "            browser, storage_state=cookie_path",
        "        )",
    ]
    + lines[1592:]
)
open(P, "w", encoding="utf-8").write("\n".join(fixed) + "\n")
print("fixed")

import py_compile

py_compile.compile(P, doraise=True)
print("compile OK")
