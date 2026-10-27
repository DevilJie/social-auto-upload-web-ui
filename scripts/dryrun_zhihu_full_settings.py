# -*- coding: utf-8 -*-
"""知乎文章全设置 dry-run: 声明+话题+投稿+来源+封面,is_draft=True 存草稿。

验证载体 = 草稿(编辑器自动保存);跑完后用 verify 脚本核对行状态。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl.registry import get_platform  # noqa: E402

COVER = (
    REPO / "data" / "materials" / "2026" / "09" / "14"
    / "eeee8be3-82d4-4826-b567-faf04e24eab9.jpg"
)

html = (
    "<h1>千帆同步 · 知乎文章全设置测试</h1>"
    "<p>验证<strong>创作声明</strong>、<em>文章话题</em>、投稿至问题、"
    "内容来源与封面的自动化设置。</p>"
    "<ul><li>声明: 虚构创作</li><li>话题: 软件测试</li></ul>"
    "<p>本稿件为 dry-run 测试,不点击发布。</p>"
)

platform = get_platform(14)
print("platform:", platform)
try:
    ok = platform.publish_article(
        title="千帆同步知乎文章全设置测试(dry-run)",
        html=html,
        account_file=["6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"],
        cover_path=str(COVER),
        creation_statement="虚构创作",
        target_question="软件测试 工具",
        topics=["软件测试", "自动化测试"],
        content_source="新闻报道",
        source_self_shot=True,
        shot_time="",
        shot_province="北京",
        shot_city="北京",
        is_draft=True,
        dry_run=True,
    )
    print("RESULT:", ok)
except Exception:
    import traceback
    traceback.print_exc()
