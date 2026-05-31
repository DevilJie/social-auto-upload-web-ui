from storage.base import StorageBackend


class S3Storage(StorageBackend):
    type = "s3"

    def __init__(self, endpoint, access_key, secret_key, bucket, region=""):
        pass
