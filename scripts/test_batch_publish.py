# -*- coding: utf-8 -*-
"""文章批量发布端到端验证:
建 2 篇测试草稿(A 完整→应成功推公众号草稿箱; B 缺账号→应失败) → 调批量端点 → 清理。
"""
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:5409/api/v2/drafts"
IMG_URL = (
    "http://127.0.0.1:5409/api/materials/file/"
    "materials/2026/09/14/e4c8337d-005a-4e0e-9934-1ea651c545da.jpg"
)


def api(method, url, payload=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read().decode())


def make_draft(title, with_account):
    dd = {
        "commonConfig": {
            "articleTitle": title,
            "articleHtml": (
                f"<h2>{title}</h2><p>批量发布验证正文。</p>"
                f'<p><img src="{IMG_URL}" alt="配图"></p>'
            ),
        },
        "platformConfigs": {
            "weixin_gzh": {
                "articleAuthor": "千帆同步",
                "articleDigest": "",
                "gzhClaimSource": "个人观点，仅供参考",
                "gzhCollectionName": "",
                "gzhOriginalUrl": "",
                "scheduleTime": "",
            }
        },
        "panelAccountOverrides": {},
        "publishAccountIds": [46] if with_account else [],
        "selectedPlatform": "weixin_gzh",
        "selectedAccountId": 46 if with_account else None,
        "expandedGroups": ["weixin_gzh"],
    }
    r = api("POST", BASE, {"type": "article", "draft_data": dd})
    return r["data"]["id"]


print("创建测试草稿 A(完整)/B(缺账号)...", flush=True)
id_a = make_draft("批量发布验证A(应成功)", True)
id_b = make_draft("批量发布验证B(应失败)", False)
print(f"A={id_a} B={id_b}")

time.sleep(1)
print("调用批量发布端点...", flush=True)
r = api("POST", "http://127.0.0.1:5409/api/article-publish/drafts/batch-publish",
        {"draft_ids": [id_a, id_b]})
print("succeeded:", r["succeeded"])
print("failed:", json.dumps(r["failed"], ensure_ascii=False))

assert id_a in r["succeeded"], "A 应成功"
assert any(f["draft_id"] == id_b for f in r["failed"]), "B 应失败"

# 清理: 删除两篇本地测试草稿
api("DELETE", f"{BASE}/{id_a}")
api("DELETE", f"{BASE}/{id_b}")
print("本地测试草稿已清理。公众号草稿箱里的验证文章请用清理脚本删除。")
