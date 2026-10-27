# -*- coding: utf-8 -*-
"""HTTP 全链路 dry-run: POST /api/article-publish/publish → 公众号草稿。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IMG_URL = (
    "http://127.0.0.1:5409/api/materials/file/"
    "materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)
ARTICLE_HTML = (
    "<h2>千帆同步 · HTTP 全链路测试</h2>"
    "<p>本段验证 <strong>Blueprint 层</strong>与<em>平台层</em>的完整发布链路,"
    "包含<strong>多种样式混排</strong>与图文混排。</p>"
    "<ul><li>图片自动转存微信 CDN</li><li>标题/作者/摘要自动填写</li></ul>"
    f'<p><img src="{IMG_URL}" alt="测试配图"></p>'
    "<blockquote>发布模式: dry-run(保存草稿,不群发)。</blockquote>"
    "<p>结尾段落,验证完整落盘。</p>"
)

payload = {
    "batchId": "e2e-article-dryrun-001",
    "account_configs": {
        "account_id": 46,
        "account_name": "czy个人测试",
        "platform": "weixin_gzh",
        "filePath": "f3cfc68b-8a7d-11f1-a26f-bc24114cad59.json",
        "articleTitle": "千帆同步文章发布HTTP全链路测试(dry-run)",
        "articleHtml": ARTICLE_HTML,
        "articleAuthor": "千帆同步",
        "articleDigest": "端到端HTTP链路验证摘要:图文混排一键分发到公众号草稿箱。",
        "gzhClaimSource": "个人观点，仅供参考",
        "gzhOriginalUrl": "",
        "scheduleTime": "",
        "dryRun": True,
        "isDraft": True,
    },
}

req = urllib.request.Request(
    "http://127.0.0.1:5409/api/article-publish/publish",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=600) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        print("STATUS:", resp.status)
        print("BODY:", json.dumps(body, ensure_ascii=False, indent=1))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode("utf-8")[:500])
