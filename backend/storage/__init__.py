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
