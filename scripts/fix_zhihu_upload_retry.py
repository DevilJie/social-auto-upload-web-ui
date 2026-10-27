# -*- coding: utf-8 -*-
"""图片上传超时 90s + 自动重试一次。"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P = r"D:\work\QianfanSync\backend\impl\zhihu\platform.py"
src = open(P, encoding="utf-8").read()

src = src.replace("deadline = loop.time() + 60", "deadline = loop.time() + 90")

old = (
    '            if not new_src:\n'
    '                raise RuntimeError(\n'
    '                    f"[文章][知乎] 图片上传超时({Path(path).name})"\n'
    '                )\n'
    '            urls.append(new_src)'
)
new = (
    '            if not new_src:\n'
    '                # 冷启动偶发超时(OSS 签名/首传慢),自动重试一次\n'
    '                logger.warning(\n'
    '                    "[文章][知乎] 图片上传超时,重试一次: %s",\n'
    '                    Path(path).name,\n'
    '                )\n'
    '                await img_input.set_input_files(path)\n'
    '                deadline2 = loop.time() + 90\n'
    '                while loop.time() < deadline2:\n'
    '                    srcs2 = await page.evaluate(\n'
    '                        """() => [...document.querySelectorAll(\n'
    "                            '.public-DraftEditor-content img')].map("
    "(im) => im.src)\"\"\"\n"
    '                    )\n'
    '                    added2 = [\n'
    '                        s for s in srcs2\n'
    '                        if s.startswith("http") and s not in before\n'
    '                    ]\n'
    '                    if added2:\n'
    '                        new_src = added2[-1]\n'
    '                        break\n'
    '                    await asyncio.sleep(1.5)\n'
    '            if not new_src:\n'
    '                raise RuntimeError(\n'
    '                    f"[文章][知乎] 图片上传超时({Path(path).name})"\n'
    '                )\n'
    '            urls.append(new_src)'
)
assert old in src, "anchor not found"
src = src.replace(old, new, 1)
open(P, "w", encoding="utf-8").write(src)
print("patched")

import py_compile

py_compile.compile(P, doraise=True)
print("compile OK")
