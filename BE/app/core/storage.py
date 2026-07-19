from functools import lru_cache
from typing import TYPE_CHECKING

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.config import settings

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


@lru_cache(maxsize=1)
def get_s3_client() -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        region_name=settings.S3_REGION,
        # path-style addressing is required for MinIO
        config=Config(s3={"addressing_style": "path"}),
    )


def ensure_bucket(bucket: str | None = None) -> None:
    client = get_s3_client()
    bucket = bucket or settings.S3_BUCKET
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=bucket)
        else:
            raise


def upload_blob(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    bucket: str | None = None,
) -> None:
    get_s3_client().put_object(
        Bucket=bucket or settings.S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def download_blob(key: str, bucket: str | None = None) -> bytes:
    response = get_s3_client().get_object(
        Bucket=bucket or settings.S3_BUCKET, Key=key
    )
    return response["Body"].read()


def delete_blob(key: str, bucket: str | None = None) -> None:
    get_s3_client().delete_object(Bucket=bucket or settings.S3_BUCKET, Key=key)


def presigned_url(
    key: str, expires_in: int = 3600, bucket: str | None = None
) -> str:
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket or settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )
