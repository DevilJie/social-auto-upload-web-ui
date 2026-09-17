"""封面 4 比例中心裁剪（发布封面的统一裁剪规格）。

规格与前端 CoverEditorDialog 手动裁剪一致（长边 1920，JPEG q=92）：
  landscape_43  → 1920x1440 (coverLandscape)
  landscape_169 → 1920x1080 (coverLandscape169)
  portrait_34   → 1440x1920 (coverPortrait)
  portrait_916  → 1080x1920 (coverPortrait916)

被两个入口共用：
- /api/frames/save-cover   从视频抽帧图裁剪（网页添加视频时的自动封面）
- /api/materials/covers/crop 从素材库图片裁剪（MCP 发布前统一裁全比例）
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime
from uuid import uuid4

# 目标比例：key → (宽, 高)，长边 1920
RATIOS = {
    'landscape_43': (1920, 1440),
    'landscape_169': (1920, 1080),
    'portrait_34': (1440, 1920),
    'portrait_916': (1080, 1920),
}


def crop_image_to_covers(src, filename_prefix: str = "cover", ratios: list[str] | None = None) -> dict:
    """PIL 图像 → 指定比例（默认全部 4 个）的封面对象 dict。

    中心裁剪（cover 语义）：按目标比例取源图最大居中区域，再缩放到目标尺寸。
    文件存 covers/YYYY/MM/DD/<uuid>.jpg，不入素材库（materials 表）。
    """
    from PIL import Image
    from storage import get_storage

    wanted = ratios if ratios else list(RATIOS.keys())

    if src.mode not in ('RGB', 'L'):
        src = src.convert('RGB')

    storage = get_storage()
    date_dir = datetime.now().strftime('%Y/%m/%d')

    result = {}
    for key in wanted:
        tw, th = RATIOS[key]
        sw, sh = src.size
        scale = max(tw / sw, th / sh)   # 覆盖缩放：保证裁出区域 ≥ 目标比例映射回源图
        crop_w, crop_h = min(sw, tw / scale), min(sh, th / scale)
        left = (sw - crop_w) / 2
        top = (sh - crop_h) / 2
        box = (round(left), round(top), round(left + crop_w), round(top + crop_h))
        img = src.crop(box).resize((tw, th), Image.LANCZOS)

        buf = BytesIO()
        img.save(buf, format='JPEG', quality=92)
        file_bytes = buf.getvalue()

        file_id = str(uuid4())
        relative_path = f"covers/{date_dir}/{file_id}.jpg"
        storage.save_stream(iter([file_bytes]), relative_path)

        result[key] = {
            "id": file_id,
            "original_filename": f"{filename_prefix}_{key}.jpg",
            "stored_path": relative_path,
            "file_type": "image",
            "mime_type": "image/jpeg",
            "file_size": len(file_bytes),
            "url": storage.get_url(relative_path),
            "thumbnail_path": None,
        }
    return result
