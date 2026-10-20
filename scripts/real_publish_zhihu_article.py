# -*- coding: utf-8 -*-
"""知乎文章真实发表(点发布按钮,验证完整发表链路)。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:5409"
IMG_URL = BASE + "/api/materials/file/materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
COVER_STORED = "materials/2026/09/14/eeee8be3-82d4-4826-b567-faf04e24eab9.jpg"

payload = {
    "batchId": "zhihu-article-real-001",
    "account_configs": {
        "account_id": 14,
        "account_name": "哈罗",
        "platform": "zhihu",
        "filePath": "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json",
        "articleTitle": "千帆同步知乎图文发布功能实测",
        "articleHtml": (
            "<h1>千帆同步 · 知乎图文发布实测</h1>"
            "<p>这是通过<strong>千帆同步</strong>真实发表的知乎文章,"
            "验证图文混排一键分发链路。</p>"
            "<ul><li>图片自动上传知乎图床</li><li>Draft.js 富文本解析</li></ul>"
            "<blockquote>本文章由工具自动发表,验证后将删除。</blockquote>"
            f'<p><img src="{IMG_URL}" alt="测试配图"></p>'
            "<p>如果你看到这篇文章,说明知乎图文发布链路已完全打通。</p>"
        ),
        "articleDigest": "",
        "gzhCollectionName": "",
        "gzhClaimSource": "",
        "gzhOriginalUrl": "",
        "scheduleTime": "",
        "coverStoredPath": COVER_STORED,
        "dryRun": False,
        "isDraft": False,
    },
}

req = urllib.request.Request(
    BASE + "/api/article-publish/publish",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=600) as resp:
    body = json.loads(resp.read().decode("utf-8"))
    print("STATUS:", resp.status)
    print("BODY:", json.dumps(body, ensure_ascii=False))
