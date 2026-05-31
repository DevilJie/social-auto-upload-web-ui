from storage.base import StorageBackend


class LocalStorage(StorageBackend):
    type = "local"

    def __init__(self, base_dir):
        from pathlib import Path
        self.base_dir = Path(base_dir)
