# -*- coding: utf-8 -*-
"""更新 scheduleTime 为未来 1 小时并跑定时 dry-run。"""
import datetime
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:5409"
IMG_URL = BASE + "/api/materials/file/materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
COVER_STORED = "materials/2026/09/14/eeee8be3-82d4-4826-b567-faf04e24eab9.jpg"

t = (datetime.datetime.now() + datetime.timedelta(hours=1)).strftime(
    "%Y-%m-%d %H:%M:%S"
)
print("scheduleTime =", t)

payload = {
    "batchId": "zhihu-schedule-dryrun-005",
    "account_configs": {
        "account_id": 14,
        "account_name": "哈罗",
        "platform": "zhihu",
        "filePath": "6ebf9edd-7807-11f1-ac11-d6ff06b7ecbc.json",
        "articleTitle": "千帆同步知乎定时发布测试(dry-run)",
        "articleHtml": (
            "<h1>知乎定时发布测试</h1>"
            "<p>验证定时弹窗设置链路。</p>"
            f'<p><img src="{IMG_URL}" alt="配图"></p>'
            "<p>结尾。</p>"
        ),
        "articleDigest": "",
        "scheduleTime": t,
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
    print("STATUS:", resp.status)
    print("BODY:", json.loads(resp.read().decode("utf-8")))
