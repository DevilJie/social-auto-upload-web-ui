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
            base_dir=BASE_DIR,
        )
    else:
        from storage.local import LocalStorage
        return LocalStorage(BASE_DIR)


def get_storage_by_type(storage_type: str):
    """根据素材的 storage_type 字段返回对应的存储实例，用于读取已有文件。

    与 get_storage() 不同，此函数不会参考当前全局配置，而是仅根据
    传入的 storage_type 决定用哪个后端，确保本地存储的文件始终用
    本地方式读取，S3 存储的文件始终用 S3 方式读取。
    """
    from conf import BASE_DIR

    if storage_type == "s3":
        # S3 文件需要当前 S3 配置来生成 presigned URL
        storage = get_storage()
        if storage.type == "s3":
            return storage
        # 全局配置已切回本地但部分文件在 S3 上——依然尝试用 S3 读取
        # 需要从 settings.json 读取 S3 配置
        settings_file = BASE_DIR / "settings.json"
        if settings_file.exists():
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                s3_config = settings.get("storage", {}).get("s3", {})
                if s3_config.get("endpoint"):
                    from storage.s3 import S3Storage
                    return S3Storage(
                        endpoint=s3_config["endpoint"],
                        access_key=s3_config.get("access_key", ""),
                        secret_key=s3_config.get("secret_key", ""),
                        bucket=s3_config.get("bucket", ""),
                        region=s3_config.get("region", ""),
                        base_dir=BASE_DIR,
                    )
            except (json.JSONDecodeError, OSError):
                pass
        # S3 配置不可用，回退到本地（至少能尝试）
        from storage.local import LocalStorage
        return LocalStorage(BASE_DIR)

    # local 或其他未知类型一律用本地存储
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
