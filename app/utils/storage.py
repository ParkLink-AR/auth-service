from __future__ import annotations

import boto3

from app.config import settings


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    """Uploads `data` to the R2 bucket under `key`, returning its public URL."""
    _client().put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


def delete_object(url: str | None) -> None:
    """Best-effort delete of a previously-uploaded object, given its public URL."""
    if not url or not settings.R2_PUBLIC_URL:
        return
    prefix = f"{settings.R2_PUBLIC_URL.rstrip('/')}/"
    if not url.startswith(prefix):
        return
    key = url[len(prefix):]
    _client().delete_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
