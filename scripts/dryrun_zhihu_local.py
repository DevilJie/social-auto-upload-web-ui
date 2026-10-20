# -*- coding: utf-8 -*-
"""本地直调知乎 publish_article dry-run(拿完整 traceback)。"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl.registry import get_platform

IMG_URL = (
    "http://127.0.0.1:5409/api/materials/file/"
    "materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)
COVER_STORED = "materials/2026/09/14/eeee8be3-82d4-4826-b567-faf04e24eab9.jpg"

html = (
    "<h1>千帆同步 · 知乎图文发布测试</h1>"
    "<p>这是通过<strong>千帆同步</strong>发布的知乎文章测试段落,"
    "包含<em>斜体</em>、列表与图文混排。</p>"
    "<ul><li>图片自动上传知乎图床</li><li>Draft.js 粘贴解析</li></ul>"
    "<blockquote>本测试为 dry-run,只验证表单流程,不点击发布。</blockquote>"
    f'<p><img src="{IMG_URL}" alt="测试配图"></p>'
    "<p>结尾段落,验证完整渲染。</p>"
)

platform = get_platform(14)
print("platform:", platform)
try:
    ok = platform.publish_article(
        title="千帆同步知乎图文发布功能测试(dry-run)",
        html=html,
        account_file=["6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"],
        cover_path=str(REPO / "data" / "materials" / "2026" / "09" / "14"
                       / "eeee8be3-82d4-4826-b567-faf04e24eab9.jpg"),
        is_draft=True,
        dry_run=True,
    )
    print("RESULT:", ok)
except Exception:
    import traceback
    traceback.print_exc()
