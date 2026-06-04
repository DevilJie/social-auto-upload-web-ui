from flask import redirect
from pathlib import Path

from storage.base import StorageBackend


class S3Storage(StorageBackend):
    type = "s3"

    def __init__(self, endpoint, access_key, secret_key, bucket, region="", base_dir=None):
        import boto3
        from boto3.s3.transfer import TransferConfig
        from botocore.config import Config
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                proxies={"http": None, "https": None},
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        self.bucket = bucket
        self.base_dir = Path(base_dir) if base_dir else None
        # 分片上传配置：超过 8MB 自动使用分片上传
        self._transfer_config = TransferConfig(
            multipart_threshold=8 * 1024 * 1024,
            multipart_chunksize=8 * 1024 * 1024,
            max_concurrency=2,
        )

    def save(self, file_data: bytes, relative_path: str) -> str:
        import boto3.s3.transfer as transfer
        from io import BytesIO
        # 使用分片上传，更可靠
        self.client.upload_fileobj(
            BytesIO(file_data),
            self.bucket,
            relative_path,
            Config=self._transfer_config,
        )
        return relative_path

    def get(self, relative_path: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=relative_path)
        return resp["Body"].read()

    def get_url(self, relative_path: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": relative_path},
            ExpiresIn=3600,
        )

    def delete(self, relative_path: str) -> bool:
        self.client.delete_object(Bucket=self.bucket, Key=relative_path)
        return True

    def exists(self, relative_path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=relative_path)
            return True
        except Exception:
            return False

    def get_local_path(self, relative_path: str) -> str | None:
        # 优先检查本地文件（兼容从本地迁移到 S3 的过渡期）
        if self.base_dir:
            full_path = self.base_dir / relative_path
            if full_path.exists():
                return str(full_path)
        # 尝试从 S3 下载到临时目录
        try:
            data = self.get(relative_path)
            import tempfile
            ext = Path(relative_path).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            tmp.write(data)
            tmp.close()
            return tmp.name
        except Exception:
            return None

    def serve(self, relative_path: str):
        url = self.get_url(relative_path)
        return redirect(url)
