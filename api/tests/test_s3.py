import boto3
import pytest
from moto import mock_aws

from app.s3 import S3Client


@pytest.fixture
def s3():
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="testbucket")
        yield S3Client(bucket="testbucket", prefix="dothesis/", region="us-east-1",
                        access_key="x", secret_key="y")


def test_put_and_get_url_use_prefix(s3):
    s3.put_object("foo.txt", b"hi", content_type="text/plain")
    url = s3.presigned_get("foo.txt", expires_in=60)
    assert "dothesis/foo.txt" in url


def test_refuses_keys_with_dotdot(s3):
    with pytest.raises(ValueError):
        s3.put_object("../escape.txt", b"x")


def test_object_key_must_be_relative(s3):
    with pytest.raises(ValueError):
        s3.put_object("/abs.txt", b"x")


def test_refuses_empty_key(s3):
    with pytest.raises(ValueError):
        s3.put_object("", b"x")


def test_head_object_returns_none_for_missing(s3):
    assert s3.head_object("does-not-exist.txt") is None
