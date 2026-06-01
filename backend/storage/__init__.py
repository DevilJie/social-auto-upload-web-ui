import json
from pathlib import Path


def get_storage():
    """根据 settings.json 配置返回对应的存储实例"""
    from conf import BASE_DIR

    settings_file = BASE_DIR / "settings.json"
    storage_type = "local"
    s3_config = {}

    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            storage_cfg = settings.get("storage", {})
            storage_type = storage_cfg.get("type", "local")
            s3_config = storage_cfg.get("s3", {})
        except (json.JSONDecodeError, OSError):
            pass

    if storage_type == "s3" and s3_config.get("endpoint"):
        from storage.s3 import S3Storage
        return S3Storage(
            endpoint=s3_config["endpoint"],
            access_key=s3_config.get("access_key", ""),
            secret_key=s3_config.get("secret_key", ""),
            bucket=s3_config.get("bucket", ""),
            region=s3_config.get("region", ""),
        )
    else:
        from storage.local import LocalStorage
        return LocalStorage(BASE_DIR)


def reset_storage():
    """切换存储配置后调用（目前不需要缓存，每次 get_storage 重新读取配置）"""
    pass


def resolve_material_path(path_or_stored_path):
    """统一素材路径解析：stored_path → 本地绝对路径。

    视频发布、图文发布、抽帧、封面……所有需要把素材表的
    stored_path 转成本地可读路径的地方都应使用此函数，避免
    重复实现和分散逻辑。

    - 输入：本地存储下为相对路径（如 materials/2026/06/01/uuid.jpg）
            或已是绝对路径
    - 输出：本地绝对路径（若 storage 能解析）；否则原样返回
    """
    if not path_or_stored_path:
        return path_or_stored_path
    local = get_storage().get_local_path(path_or_stored_path)
    return local if local else path_or_stored_path
