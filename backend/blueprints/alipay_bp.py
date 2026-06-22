"""支付宝内容创作平台相关 API 代理。

仿 ``douyin_image_bp.py`` 的网络拦截模式:用 CloakBrowser 打开支付宝发布页 →
上传一个空视频文件触发表单渲染 → 在合集搜索框输入关键词 → 监听
``queryCompilationsByPublicId.json`` 响应 → 把结果转发给前端。

文档 ~/zfb.md 明确要求:合集列表是会话级的(需登录态 appId + ctoken),
必须通过浏览器自动化获取,且 UI 参考"抖音图文发布的选择音乐下拉搜索组件"。

请求体(文档实测): {"pageNum":1,"pageSize":999,"publicId":"...","searchName":"一键"}
响应结构:
    {
      "stat": "ok",
      "result": {
        "total": 1, "hasMore": false,
        "list": [
          {"compilationId":"CC...","coverUrl":"...","title":"一键分发系统",
           "category":"科技数码","total": 1}
        ]
      }
    }
"""

import asyncio
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("alipay")

alipay_bp = Blueprint('alipay', __name__, url_prefix='/api/alipay')

# 支付宝发布页(文档 ~/zfb.md)
_ALIPAY_PUBLISH_URL = (
    "https://c.alipay.com/page/content-creation/publish/short-video"
)


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str:
    """从数据库取账号 cookie 文件名。account_id 为空时取任意一个支付宝账号。"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 12 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# ======================================================================
# /api/alipay/compilation-search
# ======================================================================

@alipay_bp.route('/compilation-search', methods=['GET'])
def search_compilation():
    """搜索支付宝合集 —— 浏览器拦截 queryCompilationsByPublicId.json。

    Query params:
        account_id: 账号 id(用于取 cookie)
        keyword:    合集名称关键词

    Returns:
        {"code": 200, "data": {"list": [...], "total": N, "hasMore": bool}}
    """
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')

    logger.info(
        f"[合集搜索] 收到请求: account_id={account_id}, keyword={keyword}"
    )

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少 keyword 参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[合集搜索] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的支付宝账号"}), 404

        result = run_async(_search_compilation_via_browser(cookie_file, keyword))

        if result.get("success"):
            data = result.get("data", {})
            items = data.get("list", [])
            logger.info(
                f"[合集搜索] 成功,共 {len(items)} 个合集"
            )
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[合集搜索] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[合集搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _search_compilation_via_browser(cookie_file: str, keyword: str) -> dict:
    """用 CloakBrowser 打开发布页 + 上传空视频 + 监听合集搜索响应。

    与抖音音乐搜索同构(参考 ``douyin_image_bp._search_music_via_browser``)。

    步骤:
        1. 准备一个最小空视频(首次创建,缓存复用)
        2. 开启 response 监听,匹配 queryCompilationsByPublicId.json
        3. goto 发布页 → 等 input[type=file]
        4. 上传空视频 → 等表单渲染(标题输入框出现)
        5. 定位合集搜索框 ``input[id$='_compilationInfo']`` → fill keyword
        6. 轮询等 captured_response(最长 15s)
        7. 解析响应,提取 result.list
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 1. 准备空视频(支付宝要求先上传视频才会渲染完整表单)
    empty_video = Path(BASE_DIR / ".alipay_empty_video.mp4")
    if not empty_video.exists():
        try:
            _create_minimal_mp4(empty_video)
        except Exception as e:
            logger.error(f"[合集搜索] 创建空视频失败: {e}")
            return {"success": False, "error": f"创建空视频失败: {e}"}

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 2. 监听合集搜索接口
            captured_response = None

            async def handle_response(response):
                nonlocal captured_response
                if (
                    "queryCompilationsByPublicId.json" in response.url
                    and captured_response is None
                ):
                    try:
                        data = await response.json()
                        captured_response = data
                        logger.info(
                            f"[浏览器拦截] 捕获到合集搜索响应: "
                            f"stat={data.get('stat')}, "
                            f"total={data.get('result', {}).get('total')}"
                        )
                    except Exception as e:
                        logger.error(f"[浏览器拦截] 解析响应失败: {e}")

            page.on("response", handle_response)

            # 3. 打开发布页
            logger.info("[合集搜索] 打开支付宝发布页...")
            await page.goto(_ALIPAY_PUBLISH_URL, timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=30000)

            # 4. 上传空视频
            logger.info("[合集搜索] 上传空视频触发表单渲染...")
            file_input = page.locator("input[type='file']").first
            await file_input.wait_for(state="attached", timeout=15000)
            await file_input.set_input_files(str(empty_video))

            # 5. 等表单渲染(标题输入框出现 = 上传完成 + 表单可交互)
            logger.info("[合集搜索] 等待表单渲染...")
            title_input = page.locator(
                "input[placeholder*='好的标题']"
            ).first
            try:
                await title_input.wait_for(state="visible", timeout=120000)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"等待表单渲染超时: {e}",
                }

            # 6. 定位合集搜索框 + fill 触发请求
            logger.info(f"[合集搜索] 输入关键词: {keyword}")
            compilation_input = page.locator(
                "input[id$='_compilationInfo']"
            ).first
            try:
                await compilation_input.wait_for(
                    state="visible", timeout=10000
                )
            except Exception as e:
                return {
                    "success": False,
                    "error": f"未找到合集搜索框: {e}",
                }

            await compilation_input.click()
            await compilation_input.fill(keyword)

            # 7. 轮询等响应(最长 15s)
            for i in range(150):
                if captured_response is not None:
                    break
                await asyncio.sleep(0.1)

            if captured_response is None:
                return {"success": False, "error": "未能拦截到合集搜索结果"}

            # 解析响应:文档实测 stat=ok, result.list 是合集数组
            stat = captured_response.get("stat")
            result_obj = captured_response.get("result") or {}
            if stat != "ok":
                return {
                    "success": False,
                    "error": f"接口返回 stat={stat}",
                    "data": captured_response,
                }

            # 标准化输出(只保留前端需要的字段)
            items = []
            for raw in (result_obj.get("list") or []):
                items.append({
                    "compilationId": raw.get("compilationId", ""),
                    "title": raw.get("title", ""),
                    "coverUrl": raw.get("coverUrl", ""),
                    "category": raw.get("category", ""),
                    "total": raw.get("total", 0),
                })

            return {
                "success": True,
                "data": {
                    "list": items,
                    "total": result_obj.get("total", len(items)),
                    "hasMore": bool(result_obj.get("hasMore", False)),
                },
            }

        finally:
            await context.close()
    finally:
        await browser.close()


def _create_minimal_mp4(path: Path):
    """创建一个最小的合法 mp4 文件(支付宝要求上传视频才渲染完整表单)。

    用 fmp4 atom 拼一个最小可识别的 mp4:ftyp + moov + mdat。
    支付宝只检测文件类型 + 能否解码开头,不真正播放,所以无需真实音视频数据。
    """
    import struct

    def box(box_type: bytes, payload: bytes = b"") -> bytes:
        size = 8 + len(payload)
        return struct.pack(">I", size) + box_type + payload

    # ftyp box: file type
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2avc1mp41")

    # 最小 moov(空 trak,仅占位让播放器认为是合法 mp4)
    mvhd_payload = (
        b"\x00" * 100  # version + flags + 96 字段占位
    )
    moov = box(b"moov", box(b"mvhd", mvhd_payload))

    # 空 mdat
    mdat = box(b"mdat", b"\x00" * 16)

    path.write_bytes(ftyp + moov + mdat)


# ======================================================================
# run_async helper(与 douyin_image_bp 一致)
# ======================================================================

def run_async(coro):
    """在新事件循环里跑协程(避免与 Flask 线程冲突,同 douyin_image_bp)。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 已在 loop 里(罕见),开新线程跑
            import threading
            result = {}
            def _run():
                new_loop = asyncio.new_event_loop()
                try:
                    result["v"] = new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            t = threading.Thread(target=_run)
            t.start()
            t.join()
            return result.get("v")
    except RuntimeError:
        pass
    return asyncio.run(coro)
