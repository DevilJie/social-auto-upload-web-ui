# -*- coding: utf-8 -*-
"""端到端 dry-run: 公众号文章发布完整表单流程(保存草稿,不群发)。

验证点(逐项日志):
  1. token 解析 + 编辑页打开
  2. 上传凭证读取
  3. 正文图片 filetransfer 上传 → CDN URL 替换
  4. ProseMirror 粘贴正文 / 标题逐字输入
  5. 作者/摘要/创作来源
  6. before_submit 截图
  7. 保存草稿(URL 出现 appmsgid)
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(r"D:\work\QianfanSync")
sys.path.insert(0, str(REPO / "backend"))

from impl.registry import get_platform  # noqa: E402

COOKIE_FILE = "f3cfc68b-8a7d-11f1-a26f-bc24114cad59.json"

# 模拟前端编辑器输出:规范 HTML + 素材库 URL 图片(真实存量素材)
IMG_URL = (
    "http://127.0.0.1:5409/api/materials/file/"
    "materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)
ARTICLE_HTML = (
    "<h2>千帆同步 · 文章发布功能测试</h2>"
    "<p>这是一段<strong>加粗文字</strong>与<em>斜体</em>混排的测试段落,"
    "用于验证公众号文章发布的富文本链路。</p>"
    "<blockquote>这是一条引用:图文混排正文会先上传图片到微信 CDN,"
    "再整体粘贴进 ProseMirror 编辑器。</blockquote>"
    "<ul><li>列表项一:图片自动转存</li><li>列表项二:草稿箱验证</li></ul>"
    f'<p><img src="{IMG_URL}" alt="测试配图"></p>'
    "<p>图片之后的收尾段落。本测试为 dry-run,只保存草稿不发表。</p>"
)


def main() -> None:
    platform = get_platform(17)
    assert platform is not None
    ok = platform.publish_article(
        title="千帆同步文章发布功能测试(dry-run)",
        html=ARTICLE_HTML,
        account_file=[COOKIE_FILE],
        author="千帆同步",
        digest="端到端 dry-run 测试摘要:验证图文混排文章一键分发链路。",
        gzh_claim_source="个人观点，仅供参考",
        is_draft=True,   # 保存草稿,不群发
        dry_run=False,   # dry_run=True 会完全跳过;这里要真走表单
    )
    print("RESULT:", ok)


if __name__ == "__main__":
    main()
