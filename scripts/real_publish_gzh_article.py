# -*- coding: utf-8 -*-
"""真实发表一次文章到公众号(用户已授权,消耗当日群发次数)。

走 HTTP 链路(与前端一键发布完全一致): POST /api/article-publish/publish
dryRun=False + isDraft=False → 填表 → 发表 → 弹窗确认 → (如需)扫码。
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IMG_URL = (
    "http://127.0.0.1:5409/api/materials/file/"
    "materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)
ARTICLE_HTML = (
    "<h2>千帆同步 · 文章一键分发功能上线</h2>"
    "<p>这是通过<strong>千帆同步</strong>文章发布功能实际发表的一篇测试文章,"
    "用于验证<em>图文混排一键分发</em>的完整链路。</p>"
    "<blockquote>正文由本地富文本编辑器产出,图片自动上传转存到微信 CDN,"
    "标题、作者、摘要、创作来源全部自动填写。</blockquote>"
    "<ul><li>支持图文混排(自动转存图片)</li>"
    "<li>支持多账号一键分发</li>"
    "<li>支持定时发表</li></ul>"
    f'<p><img src="{IMG_URL}" alt="功能示意"></p>'
    "<p>如果你看到这篇文章,说明公众号文章发布链路已完全打通。"
    "后续将支持更多文章平台(知乎/CSDN/头条号等)。</p>"
)

payload = {
    "batchId": "real-article-publish-001",
    "account_configs": {
        "account_id": 46,
        "account_name": "czy个人测试",
        "platform": "weixin_gzh",
        "filePath": "f3cfc68b-8a7d-11f1-a26f-bc24114cad59.json",
        "articleTitle": "千帆同步 · 文章一键分发功能实测",
        "articleHtml": ARTICLE_HTML,
        "articleAuthor": "千帆同步",
        "articleDigest": "千帆同步文章发布功能实测:图文混排一键分发到公众号。",
        "gzhClaimSource": "个人观点，仅供参考",
        "gzhOriginalUrl": "",
        "scheduleTime": "",
        "dryRun": False,
        "isDraft": False,
    },
}

print(">>> 开始真实发表(如有扫码请配合)...", flush=True)
req = urllib.request.Request(
    "http://127.0.0.1:5409/api/article-publish/publish",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=900) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        print("STATUS:", resp.status)
        print("BODY:", json.dumps(body, ensure_ascii=False, indent=1))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode("utf-8")[:800])
