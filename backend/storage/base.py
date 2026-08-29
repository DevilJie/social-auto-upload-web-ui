from __future__ import annotations

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    type: str = ""

    @abstractmethod
    def save(self, file_data: bytes, relative_path: str) -> str:
        """保存文件（一次性 bytes），返回实际存储路径"""

    @abstractmethod
    def save_stream(self, stream_iter, relative_path: str) -> str:
        """流式保存文件（每次 yield 一个 bytes chunk），返回实际存储路径

        实现要点：
        - LocalStorage: 打开目标文件，按 chunk 写入后关闭
        - S3Storage: 包成 file-like 对象用 boto3 upload_fileobj（自带 multipart）
        """

    @abstractmethod
    def get(self, relative_path: str) -> bytes:
        """读取文件内容"""

    @abstractmethod
    def get_url(self, relative_path: str) -> str:
        """获取文件访问 URL"""

    @abstractmethod
    def delete(self, relative_path: str) -> bool:
        """删除文件"""

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        """文件是否存在"""

    @abstractmethod
    def serve(self, relative_path: str):
        """Flask 响应：本地返回文件，S3 重定向到 presigned URL"""

    def get_local_path(self, relative_path: str) -> str | None:
        """获取本地文件绝对路径（仅 LocalStorage 有意义）"""
        return None
