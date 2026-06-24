"""图片元数据识别服务。

提供图片宽高识别功能，用于判断横竖版。
使用 PIL/Pillow 读取图片头信息，不解码全部像素，性能开销极小。
"""

from __future__ import annotations

from pathlib import Path

from util._logger import get_channel_logger

logger = get_channel_logger("backend")


def get_image_dimensions(image_path: str) -> tuple[int, int]:
    """获取图片宽高，返回 (width, height)。

    使用 PIL/Pillow 的 Image.open() 读取图片头信息。
    支持常见格式：jpg, png, gif, webp, bmp 等。
    失败返回 (0, 0)。
    """
    try:
        from PIL import Image

        path = Path(image_path)
        if not path.is_file():
            logger.warning("[ImageService] 文件不存在: {}", image_path)
            return (0, 0)

        with Image.open(path) as img:
            width, height = img.size
            return (width, height)
    except ImportError:
        logger.warning("[ImageService] PIL/Pillow 未安装，无法识别图片尺寸")
        return (0, 0)
    except Exception as exc:
        logger.warning("[ImageService] 识别图片尺寸失败 {}: {}", image_path, exc)
        return (0, 0)
