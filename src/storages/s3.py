from contextlib import closing

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError
)

from src.core.config import Settings, get_settings


class StorageError(Exception):
    pass


class S3Storage:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _client(self, *, public: bool = False):
        if not self.settings.S3_ACCESS_KEY or not self.settings.S3_SECRET_KEY.get_secret_value():
            raise StorageError("S3 credentials are not configured")

        endpoint = self.settings.S3_ENDPOINT_URL

        if public and self.settings.S3_PUBLIC_ENDPOINT_URL:
            endpoint = self.settings.S3_PUBLIC_ENDPOINT_URL

        return boto3.client(
            "s3",
            endpoint_url=str(endpoint) if endpoint else None,
            aws_access_key_id=self.settings.S3_ACCESS_KEY,
            aws_secret_access_key=self.settings.S3_SECRET_KEY.get_secret_value(),
            region_name=self.settings.S3_REGION,
            config=Config(
                signature_version="s3v4", connect_timeout=5, read_timeout=10,
                retries={"max_attempts": 2},
                s3={"addressing_style": "path"},
            )
        )

    def upload_file(self, data: bytes, object_key: str, content_type: str) -> None:
        try:
            with closing(self._client()) as client:
                client.put_object(
                    Bucket=self.settings.S3_BUCKET_NAME,
                    Key=object_key,
                    Body=data,
                    ContentType=content_type
                )

        except (BotoCoreError, ClientError) as error:
            raise StorageError("Avatar upload failed") from error

    def get_file_url(self, object_key: str) -> str:
        try:
            with closing(self._client(public=True)) as client:
                return client.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.settings.S3_BUCKET_NAME,
                        "Key": object_key
                    },
                    ExpiresIn=self.settings.S3_URL_EXPIRE_SECONDS
                )

        except (BotoCoreError, ClientError) as error:
            raise StorageError("Avatar URL could not be generated") from error

    def delete_file(self, object_key: str) -> None:
        try:
            with closing(self._client()) as client:
                client.delete_object(
                    Bucket=self.settings.S3_BUCKET_NAME, Key=object_key,
                )

        except (BotoCoreError, ClientError) as error:
            raise StorageError("Avatar deletion failed.") from error


def get_s3_storage() -> S3Storage:
    return S3Storage(get_settings())
