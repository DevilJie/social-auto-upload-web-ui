# -*- coding: utf-8 -*-
"""真实发表验证: 全设置 + 封面,is_draft=False 端到端(不投问题之外的设置全量)。

注意: 会真实发表一篇测试文章到知乎账号,验证后可手动删除。
不传 schedule_time_str(避免账号定时发文)。
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
    "<h1>千帆同步 · 知乎文章全功能验证稿</h1>"
    "<p>本稿件为<strong>千帆同步</strong>工具的真实发表功能验证,"
    "验证完成后可在知乎文章管理中删除。</p>"
    "<ul><li>封面: 自动上传</li><li>创作声明: 虚构创作</li>"
    "<li>话题: 软件测试 / 自动化测试</li>"
    "<li>内容来源: 新闻报道(自行拍摄)</li></ul>"
    "<p>正文结尾段落,验证完整渲染。</p>"
)

platform = get_platform(14)
print("platform:", platform)
try:
    ok = platform.publish_article(
        title="千帆同步知乎全功能验证稿(可删除)",
        html=html,
        account_file=["6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json"],
        cover_path=str(COVER),
        creation_statement="虚构创作",
        target_question="自动化测试 工具推荐",
        topics=["软件测试", "自动化测试"],
        content_source="新闻报道",
        source_self_shot=True,
        shot_time="",
        shot_province="北京",
        shot_city="北京",
        is_draft=False,
        dry_run=False,
    )
    print("RESULT:", ok)
except Exception:
    import traceback
    traceback.print_exc()
