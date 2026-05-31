from abc import ABC, abstractmethod


class StorageBackend(ABC):
    type: str = ""

    @abstractmethod
    def save(self, file_data: bytes, relative_path: str) -> str:
        """保存文件，返回实际存储路径"""

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
