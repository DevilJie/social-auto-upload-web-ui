"""全局测试视频获取 —— 供各平台 blueprint 触发发布表单渲染用。

统一入口 ``get_test_video()``:返回 ``data/materials/test_video.mp4``。
文件不存在则用 ffmpeg 生成一个竖屏测试视频(1080x1920 / 5s)后再返回。

所有平台需要「上传测试视频触发表单渲染」时,统一调用本模块,不再各自
维护候选路径列表。
"""

import subprocess
import threading
from pathlib import Path

from conf import BASE_DIR
from util._logger import get_channel_logger
from services.ffmpeg_service import _find_ffmpeg

logger = get_channel_logger("backend")

# 测试视频固定路径(data/ 已被 .gitignore 忽略,天然不进 git)
_TEST_VIDEO_PATH = BASE_DIR / "materials" / "test_video.mp4"

# 生成时加锁,避免并发请求重复生成
_lock = threading.Lock()


def _build_cmd(ffmpeg: str, with_drawtext: bool) -> list[str]:
    """构造 ffmpeg 生成命令。竖屏 1080x1920 / 5s / h264+aac / faststart。

    with_drawtext=True 时叠加时间戳水印(可辨识);失败时可改 False 走最兼容的
    纯 testsrc2(部分精简版 ffmpeg build 缺 drawtext 字体支持)。
    """
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30:duration=5",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
    ]
    if with_drawtext:
        cmd += [
            "-vf",
            "drawtext=text='QianFan Test':x=(w-text_w)/2:y=h-100:"
            "fontsize=64:fontcolor=white:box=1:boxcolor=black@0.5",
        ]
    cmd += [
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(_TEST_VIDEO_PATH),
    ]
    return cmd


def get_test_video() -> str:
    """返回测试视频绝对路径。

    - 文件已存在且非空(>100 字节)→ 直接返回。
    - 不存在 → 用 ffmpeg 生成后再返回。
    - 找不到 ffmpeg 或生成失败 → 返回空字符串。

    返回 "" 与原各 blueprint 的 ``_pick_test_video()`` 行为一致,调用方继续用
    ``if not test_video:`` 判断即可,无需改判断逻辑。
    """
    # 1. 已存在 → 直接返回(快速路径,无需加锁)
    if _TEST_VIDEO_PATH.is_file() and _TEST_VIDEO_PATH.stat().st_size > 100:
        return str(_TEST_VIDEO_PATH)

    # 2. 不存在 → 加锁生成(double-check 防并发重复生成)
    with _lock:
        if _TEST_VIDEO_PATH.is_file() and _TEST_VIDEO_PATH.stat().st_size > 100:
            return str(_TEST_VIDEO_PATH)

        # 复用 services/ffmpeg_service.py 的查找逻辑(系统 PATH → bundle)
        try:
            ffmpeg = _find_ffmpeg()
        except FileNotFoundError:
            logger.warning("ffmpeg not found, cannot generate test video")
            return ""

        try:
            _TEST_VIDEO_PATH.parent.mkdir(parents=True, exist_ok=True)
            # 先带 drawtext(可辨识),失败再 fallback 纯 testsrc2(最兼容)
            try:
                subprocess.run(
                    _build_cmd(ffmpeg, with_drawtext=True),
                    check=True, capture_output=True, timeout=60,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                logger.info("drawtext generate failed, fallback to plain testsrc2")
                subprocess.run(
                    _build_cmd(ffmpeg, with_drawtext=False),
                    check=True, capture_output=True, timeout=60,
                )
            logger.info(f"test video generated: {_TEST_VIDEO_PATH}")
            return str(_TEST_VIDEO_PATH)
        except Exception as e:
            logger.warning(f"generate test video failed: {e}")
            return ""
