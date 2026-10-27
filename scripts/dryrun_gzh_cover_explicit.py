# -*- coding: utf-8 -*-
"""显式封面 dry-run: coverStoredPath 走「图片库选择」流程,存草稿验证。

正文图 = e4c8337d(蓝渐变 v1.2.7)
显式封面 = eeee8be3(另一张图)
→ before_submit 截图里封面缩略图应是 eeee8be3(与正文图不同)。
"""
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
    "batchId": "cover-explicit-dryrun-001",
    "account_configs": {
        "account_id": 46,
        "account_name": "czy个人测试",
        "platform": "weixin_gzh",
        "filePath": "f3cfc68b-8a7d-11f1-a26f-bc24114cad59.json",
        "articleTitle": "显式封面功能测试(dry-run)",
        "articleHtml": (
            "<h2>显式封面验证</h2><p>正文里的配图是蓝渐变 v1.2.7 图。</p>"
            f'<p><img src="{IMG_URL}" alt="配图"></p>'
            "<p>封面应该用的是另一张图(eeee8be3)。</p>"
        ),
        "articleAuthor": "千帆同步",
        "articleDigest": "",
        "gzhClaimSource": "个人观点，仅供参考",
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
