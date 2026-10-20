# -*- coding: utf-8 -*-
"""对比不同 python 解释器加载 zhihu platform 的结果。"""
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import shutil

print("PATH python =", shutil.which("python"))
print("sys.executable =", sys.executable)

probe = (
    "import sys; "
    "sys.path.insert(0, r'D:\\work\\QianfanSync\\backend'); "
    "from impl.zhihu.platform import ZhihuPlatform; "
    "print('has_pa:', hasattr(ZhihuPlatform, 'publish_article')); "
    "import impl.zhihu.platform as m; print('file:', m.__file__)"
)

for exe in [sys.executable, r"D:\QianFan Sync\dependency\bin\python.exe"]:
    try:
        r = subprocess.run(
            [exe, "-X", "utf8", "-c", probe],
            capture_output=True, text=True, timeout=30,
        )
        print(f"--- {exe}")
        print(" out:", r.stdout.strip()[:300])
        if r.stderr.strip():
            print(" err:", r.stderr.strip()[:200])
    except Exception as e:
        print(f"--- {exe} ERR {str(e)[:100]}")
