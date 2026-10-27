# -*- coding: utf-8 -*-
"""知乎文章 dry-run: 走完整表单流程(图片上传图床+粘贴+封面),不点发布。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IMG_URL = (
    "http://127.0.0.1:5409/api/materials/file/"
    "materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)
COVER_STORED = "materials/2026/09/14/eeee8be3-82d4-4826-b567-faf04e24eab9.jpg"

payload = {
    "batchId": "zhihu-article-dryrun-001",
    "account_configs": {
        "account_id": 14,
        "account_name": "哈罗",
        "platform": "zhihu",
        "filePath": "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json",
        "articleTitle": "千帆同步知乎图文发布功能测试(dry-run)",
        "articleHtml": (
            "<h1>千帆同步 · 知乎图文发布测试</h1>"
            "<p>这是通过<strong>千帆同步</strong>发布的知乎文章测试段落,"
            "包含<em>斜体</em>、列表与图文混排。</p>"
            "<ul><li>图片自动上传知乎图床</li><li>Draft.js 粘贴解析</li></ul>"
            "<blockquote>本测试为 dry-run,只验证表单流程,不点击发布。</blockquote>"
            f'<p><img src="{IMG_URL}" alt="测试配图"></p>'
            "<p>结尾段落,验证完整渲染。</p>"
        ),
        "articleDigest": "",
        "gzhCollectionName": "",
        "gzhClaimSource": "",
        "gzhOriginalUrl": "",
        "scheduleTime": "",
        "coverStoredPath": COVER_STORED,
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
with urllib.request.urlopen(req, timeout=600) as resp:
    body = json.loads(resp.read().decode("utf-8"))
    print("STATUS:", resp.status)
    print("BODY:", json.dumps(body, ensure_ascii=False))
