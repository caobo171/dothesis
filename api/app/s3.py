from pathlib import PurePosixPath

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


class S3Client:
    def __init__(self, *, bucket: str, prefix: str, region: str, access_key: str, secret_key: str):
        if not prefix.endswith("/"):
            prefix += "/"
        self.bucket = bucket
        self.prefix = prefix
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

    def _full_key(self, relative_key: str) -> str:
        if not relative_key:
            raise ValueError("S3 key must not be empty")
        if relative_key.startswith("/"):
            raise ValueError("S3 key must be relative")
        p = PurePosixPath(relative_key)
        if ".." in p.parts:
            raise ValueError("S3 key must not contain '..'")
        return self.prefix + str(p)

    def put_object(self, key: str, body: bytes, *, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self.bucket, Key=self._full_key(key), Body=body, **extra)

    def put_file(self, key: str, path: str, *, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        with open(path, "rb") as f:
            self._client.upload_fileobj(f, self.bucket, self._full_key(key), ExtraArgs=extra)

    def presigned_get(self, key: str, *, expires_in: int = 300) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": self._full_key(key)},
            ExpiresIn=expires_in,
        )

    def head_object(self, key: str) -> dict | None:
        try:
            return self._client.head_object(Bucket=self.bucket, Key=self._full_key(key))
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return None
            raise


def get_s3_from_settings(settings) -> S3Client:
    return S3Client(
        bucket=settings.s3_bucket,
        prefix=settings.s3_prefix,
        region=settings.aws_region,
        access_key=settings.aws_access_key,
        secret_key=settings.aws_secret_key,
    )
