from flask import redirect

from storage.base import StorageBackend


class S3Storage(StorageBackend):
    type = "s3"

    def __init__(self, endpoint, access_key, secret_key, bucket, region=""):
        import boto3
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self.bucket = bucket

    def save(self, file_data: bytes, relative_path: str) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=relative_path,
            Body=file_data,
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

    def serve(self, relative_path: str):
        url = self.get_url(relative_path)
        return redirect(url)
