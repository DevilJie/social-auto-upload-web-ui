from flask import send_from_directory
from pathlib import Path

from storage.base import StorageBackend


class LocalStorage(StorageBackend):
    type = "local"

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)

    def save(self, file_data: bytes, relative_path: str) -> str:
        full_path = self.base_dir / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(file_data)
        return relative_path

    def get(self, relative_path: str) -> bytes:
        full_path = self.base_dir / relative_path
        return full_path.read_bytes()

    def get_url(self, relative_path: str) -> str:
        return f"/api/materials/file/{relative_path}"

    def delete(self, relative_path: str) -> bool:
        full_path = self.base_dir / relative_path
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    def exists(self, relative_path: str) -> bool:
        return (self.base_dir / relative_path).exists()

    def serve(self, relative_path: str):
        full_path = self.base_dir / relative_path
        directory = str(full_path.parent)
        filename = full_path.name
        return send_from_directory(directory, filename)

    def get_local_path(self, relative_path: str) -> str | None:
        full_path = self.base_dir / relative_path
        if full_path.exists():
            return str(full_path)
        return None
