# -*- coding: utf-8 -*-
"""文章发布封面规格化：按各平台要求的比例/尺寸中心裁剪。

各平台文章封面规格（2026-10 调研：平台编辑器实测 + 官方文档/帮助页）：
  weixin_gzh  2.35:1  900x383   (转发卡片小图 1:1 由平台生成)
  zhihu       3:2     1080x720
  baijiahao   4:3     800x600   (单图/三图同比例)
  csdn        16:9    960x540
  weibo       16:9    1000x563  (官方 FAQ 1000x400, 比例为 16:9)
  dayu        16:9    1280x720  (横版单/三封面)
  toutiao     16:9    1200x675  (单图/三图同比例)

prepare_article_cover(cover_path, platform_key) 返回按平台比例裁剪后的本地
JPEG 路径；cover_path 为空 / 文件不存在 / 非图片时原样返回，不阻断发布
（平台侧会自行处理，最坏情况退回平台默认裁剪）。
"""
from __future__ import annotations

from pathlib import Path

from conf import BASE_DIR

# platform_key -> (宽, 高)
COVER_SPECS = {
    "weixin_gzh": (900, 383),
    "zhihu": (1080, 720),
    "baijiahao": (800, 600),
    "csdn": (960, 540),
    "weibo": (1000, 563),
    "dayu": (1280, 720),
    "toutiao": (1200, 675),
}

# 推荐上传尺寸（前端面板说明用，与 COVER_SPECS 保持一致）
COVER_RECOMMEND = {
    "weixin_gzh": "2.35:1，建议 900×383（或 1080×460），转发卡片小图 1:1",
    "zhihu": "3:2，建议 1080×720（或更高）",
    "baijiahao": "4:3，建议 800×600（或 1200×900），三图模式三张同比例",
    "csdn": "16:9，建议 960×540（或 1920×1080）",
    "weibo": "16:9，建议 1000×563（或 1200×675）",
    "dayu": "横版 16:9，建议 1280×720（或更高）；竖版封面 9:16",
    "toutiao": "16:9，建议 1200×675（或 1920×1080），三图模式三张同比例",
}

OUT_DIR = BASE_DIR / "covers_prepared"


def prepare_article_cover(cover_path: str, platform_key: str) -> str:
    """按平台比例中心裁剪封面，返回新本地路径；失败时返回原路径。"""
    target = COVER_SPECS.get(platform_key)
    if not cover_path or not target:
        return cover_path or ""
    src = Path(cover_path)
    if not src.is_file():
        return cover_path
    try:
        from PIL import Image

        with Image.open(src) as im:
            im.load()
            img = im.convert("RGB") if im.mode not in ("RGB", "L") else im.copy()
    except Exception:
        return cover_path

    tw, th = target
    sw, sh = img.size
    target_ratio = tw / th
    cur_ratio = sw / sh
    # 中心裁剪到目标比例（cover 语义：取最大居中区域）
    if cur_ratio > target_ratio:
        new_w = max(1, round(sh * target_ratio))
        left = (sw - new_w) // 2
        box = (left, 0, left + new_w, sh)
    else:
        new_h = max(1, round(sw / target_ratio))
        top = (sh - new_h) // 2
        box = (0, top, sw, top + new_h)
    cropped = img.crop(box)
    if cropped.size != (tw, th):
        cropped = cropped.resize((tw, th), Image.LANCZOS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{platform_key}_{src.stem}_{int(src.stat().st_mtime)}.jpg"
    cropped.save(out, format="JPEG", quality=92)
    return str(out)
