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
# 图集(图文)发布页 — 文档 ~/ZFB-tuji.md
_ALIPAY_SHORT_CONTENT_URL = (
    "https://c.alipay.com/page/content-creation/publish/short-content"
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


# ======================================================================
# /api/alipay/music-list — 图集背景音乐列表
# 文档 ~/ZFB-tuji.md:支付宝音乐组件无搜索,只有分页展示 + 试听
#
# 接口(实测抓包确认):
#   GET https://contentweb.alipay.com/life/queryAllMaterial.json
#       ?pamir_app_scene=CONTENT
#   一次性返回全部背景音乐(约 40 首),分页是前端纯 UI 分页。
#   音乐在 result.materialTypes[0].materials[0].materialDetails[]
#   字段映射:
#     name              -> title
#     code              -> musicId
#     snapshotImageUrl  -> coverUrl
#     resourceAccessUrl -> audioUrl(试听直链)
#     configs           -> JSON 字符串 {"audioTime": 秒数} -> duration
# ======================================================================

@alipay_bp.route('/music-list', methods=['GET'])
def music_list():
    """获取支付宝图集背景音乐列表(全量返回,前端客户端分页)。

    Query params:
        account_id: 账号 id(用于取 cookie)

    Returns:
        {"code": 200, "data": {
            "list": [{"musicId","title","coverUrl","audioUrl","duration"}],
            "total": N
        }}

    实现:
        打开图集发布页 → 点「添加音乐」打开 modal → 精确拦截
        queryAllMaterial.json 响应 → 解析 materialDetails 数组。
        一次返回全部,前端自行分页(避免每次翻页都开浏览器)。
    """
    account_id = request.args.get('account_id')

    logger.info(f"[音乐列表] 收到请求: account_id={account_id}")

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[音乐列表] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的支付宝账号"}), 404

        result = run_async(_fetch_music_list_via_browser(cookie_file))

        if result.get("success"):
            data = result.get("data", {})
            items = data.get("list", [])
            logger.info(f"[音乐列表] 成功,共 {len(items)} 首音乐")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[音乐列表] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[音乐列表] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_music_list_via_browser(cookie_file: str) -> dict:
    """用 CloakBrowser 打开图集页 + 点添加音乐 + 精确拦截音乐列表响应。

    接口 queryAllMaterial.json 一次性返回全部音乐,无翻页。

    注意:图集发布页的「添加音乐」按钮在表单完全渲染后才出现。
    表单渲染需要先上传至少一张图片(与视频页「先上传空视频」同理),
    所以这里会准备一张测试图,若按钮未自动出现则上传测试图触发表单。
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 准备测试图(1x1 JPEG),用于上传触发表单渲染
    test_image = Path(BASE_DIR / ".alipay_music_test.jpg")
    if not test_image.exists():
        try:
            _create_test_jpeg(test_image)
        except Exception as e:
            logger.warning(f"[音乐列表] 创建测试图失败(继续尝试): {e}")

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 监听音乐素材接口(精确匹配 queryAllMaterial.json)
            #    注册在 goto 之前,避免错过页面加载时触发的请求
            captured_response = None

            async def handle_response(response):
                nonlocal captured_response
                if captured_response is not None:
                    return
                if "queryAllMaterial.json" not in response.url:
                    return
                try:
                    data = await response.json()
                except Exception:
                    return
                stat = data.get("stat") if isinstance(data, dict) else None
                logger.info(
                    f"[音乐列表][命中] queryAllMaterial.json stat={stat}"
                )
                captured_response = data

            page.on("response", handle_response)

            # 2. 打开图集页
            logger.info("[音乐列表] 打开支付宝图集发布页...")
            await page.goto(_ALIPAY_SHORT_CONTENT_URL, timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=30000)

            # 3. 等「添加音乐」按钮可见 —— 若 3s 内没出现,上传测试图触发表单
            add_music_btn = page.locator(
                "button.ant-btn:has-text('添加音乐')"
            ).first
            try:
                await add_music_btn.wait_for(state="visible", timeout=3000)
                logger.info("[音乐列表] 「添加音乐」按钮已可见")
            except Exception:
                logger.info(
                    "[音乐列表] 「添加音乐」按钮未直接出现,"
                    "上传测试图触发表单渲染..."
                )
                if not test_image.exists():
                    return {
                        "success": False,
                        "error": "「添加音乐」按钮未出现,且测试图创建失败",
                    }
                try:
                    img_input = page.locator(
                        "input[type='file'][accept*='image']"
                    ).first
                    await img_input.wait_for(state="attached", timeout=10000)
                    await img_input.set_input_files(str(test_image))
                    logger.info("[音乐列表] 已上传测试图,等表单渲染")
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"上传测试图失败: {e}",
                    }
                # 等表单渲染(添加音乐按钮出现)
                try:
                    await add_music_btn.wait_for(
                        state="visible", timeout=20000
                    )
                    logger.info("[音乐列表] 上传后「添加音乐」按钮已可见")
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"上传测试图后仍未出现「添加音乐」按钮: {e}",
                    }

            # 4. 点击打开 modal(触发 queryAllMaterial.json 请求)
            await add_music_btn.click()
            logger.info("[音乐列表] 已点击「添加音乐」,等待 modal + 响应")

            # 等 modal 打开(并行等响应,接口在 modal 打开时触发)
            try:
                await page.locator(
                    'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")'
                ).first.wait_for(state="visible", timeout=10000)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"音乐 modal 未打开: {e}",
                }

            # 5. 轮询等响应(最长 15s)
            for _ in range(150):
                if captured_response is not None:
                    break
                await asyncio.sleep(0.1)

            if captured_response is None:
                return {
                    "success": False,
                    "error": "未能拦截到 queryAllMaterial.json 响应"
                    "(可能页面未触发请求,检查 cookie 是否有效)",
                }

            # 6. 解析响应,提取音乐数组并标准化
            items = _parse_music_response(captured_response)
            if not items:
                return {
                    "success": False,
                    "error": "响应已捕获但解析出 0 首音乐"
                    f"(stat={captured_response.get('stat')})",
                    "data": {"raw_sample": str(captured_response)[:500]},
                }

            return {
                "success": True,
                "data": {
                    "list": items,
                    "total": len(items),
                },
            }

        finally:
            await context.close()
    finally:
        await browser.close()


def _create_test_jpeg(path: Path):
    """创建一个 1x1 像素的最小 JPEG(用于上传触发表单渲染)。"""
    try:
        from PIL import Image
        img = Image.new('RGB', (1, 1), color='white')
        img.save(str(path), 'JPEG')
        return
    except ImportError:
        pass
    # 无 PIL 时,写一个硬编码的最小 JPEG 文件头
    path.write_bytes(
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01'
        b'\x00\x01\x00\x00\xff\xdb\x00C\x00\x08\xff\xff\xff\xff'
        b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        b'\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff'
        b'\xff\xff\xff\xff\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01'
        b'\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda'
        b'\x00\x08\x01\x01\x00\x00?\x00\xfb\xff\xd9'
    )


def _parse_music_response(data: dict) -> list:
    """解析 queryAllMaterial.json 响应,提取标准化音乐列表。

    响应路径:result.materialTypes[].materials[].materialDetails[]
    过滤:materialType 数组里 type == "music" 的分类下的 materialDetails。
    (实测响应里只有一个 music 分类,但保留遍历逻辑以防结构扩展)
    """
    if not isinstance(data, dict) or data.get("stat") != "ok":
        logger.warning(
            f"[音乐列表] 响应 stat 非 ok: {data.get('stat') if isinstance(data, dict) else type(data)}"
        )
        return []

    result = data.get("result") or {}
    material_types = result.get("materialTypes") or []
    items = []

    for mt in material_types:
        if not isinstance(mt, dict):
            continue
        # 只取 music 分类
        if mt.get("type") != "music":
            continue
        for material in (mt.get("materials") or []):
            for detail in (material.get("materialDetails") or []):
                if not isinstance(detail, dict):
                    continue
                items.append(_normalize_music_detail(detail))

    return items


def _normalize_music_detail(detail: dict) -> dict:
    """把单个 materialDetail 标准化为前端使用的音乐对象。

    字段映射(实测):
      - code:              音乐唯一码(如 M220260617163945272)
      - name:              音乐名
      - snapshotImageUrl:  封面图
      - resourceAccessUrl: 试听音频直链
      - configs:           JSON 字符串,如 {"audioTime": 24} (秒)
    """
    import json as _json

    # 解析 configs 里的 audioTime(秒数)
    duration = ""
    configs_raw = detail.get("configs") or ""
    if configs_raw:
        try:
            cfg = _json.loads(configs_raw)
            audio_time = cfg.get("audioTime")
            if isinstance(audio_time, (int, float)):
                duration = int(audio_time)
        except (ValueError, TypeError):
            pass

    return {
        "musicId": detail.get("code") or "",
        "title": detail.get("name") or "",
        "coverUrl": detail.get("snapshotImageUrl") or "",
        "audioUrl": detail.get("resourceAccessUrl") or "",
        "duration": duration,
    }
