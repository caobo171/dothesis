import os
from pathlib import PurePosixPath

import boto3
from botocore.config import Config


class _Client:
    def __init__(self, bucket: str, prefix: str, region: str, ak: str, sk: str) -> None:
        self.bucket = bucket
        self.prefix = prefix if prefix.endswith("/") else prefix + "/"
        self.client = boto3.client("s3", region_name=region,
                                    aws_access_key_id=ak, aws_secret_access_key=sk,
                                    config=Config(signature_version="s3v4"))

    def _key(self, rel: str) -> str:
        if rel.startswith("/"):
            raise ValueError("S3 key must be relative")
        p = PurePosixPath(rel)
        if ".." in p.parts:
            raise ValueError("S3 key must not contain '..'")
        return self.prefix + str(p)

    def put_file(self, key: str, path: str) -> None:
        self.client.upload_file(path, self.bucket, self._key(key))


def s3_from_env() -> _Client:
    return _Client(
        bucket=os.environ["S3_BUCKET"],
        prefix=os.environ.get("S3_PREFIX", "opendraft/"),
        region=os.environ["AWS_REGION"],
        ak=os.environ["AWS_ACCESS_KEY"],
        sk=os.environ["AWS_SECRET_KEY"],
    )
