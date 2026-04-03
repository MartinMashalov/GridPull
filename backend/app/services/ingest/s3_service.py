"""Hetzner Object Storage (S3-compatible) for ingest documents."""

import asyncio
import logging

import boto3
from botocore.config import Config as BotoConfig

from app.config import settings

logger = logging.getLogger(__name__)

_s3_client = None


def _get_client():
    """Return a reusable S3 client, creating one if needed."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.hetzner_s3_endpoint_url,
            aws_access_key_id=settings.hetzner_s3_access_key_id,
            aws_secret_access_key=settings.hetzner_s3_secret_access_key,
            region_name=settings.hetzner_s3_region,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )
        logger.info("S3 client created for %s", settings.hetzner_s3_endpoint_url)
    return _s3_client


async def upload_file(
    user_id: str,
    doc_id: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> str:
    """Upload bytes to S3, return the storage key."""
    storage_key = f"ingest/{user_id}/{doc_id}/{filename}"

    def _put():
        client = _get_client()
        extra = {}
        if content_type:
            extra["ContentType"] = content_type
        client.put_object(
            Bucket=settings.hetzner_s3_bucket,
            Key=storage_key,
            Body=data,
            **extra,
        )

    await asyncio.to_thread(_put)
    logger.info("S3 upload: %s (%d bytes)", storage_key, len(data))
    return storage_key


async def download_file(storage_key: str) -> bytes:
    """Download a file and return its bytes."""
    def _get():
        client = _get_client()
        response = client.get_object(
            Bucket=settings.hetzner_s3_bucket,
            Key=storage_key,
        )
        return response["Body"].read()

    data = await asyncio.to_thread(_get)
    logger.info("S3 download: %s (%d bytes)", storage_key, len(data))
    return data


async def delete_file(storage_key: str) -> None:
    """Delete a single file."""
    def _del():
        client = _get_client()
        client.delete_object(
            Bucket=settings.hetzner_s3_bucket,
            Key=storage_key,
        )

    await asyncio.to_thread(_del)
    logger.info("S3 delete: %s", storage_key)


async def delete_many_files(storage_keys: list[str]) -> None:
    """Delete multiple files in a single batch request."""
    if not storage_keys:
        return

    def _batch_del():
        client = _get_client()
        # S3 delete_objects accepts up to 1000 keys per request
        for i in range(0, len(storage_keys), 1000):
            batch = storage_keys[i:i + 1000]
            client.delete_objects(
                Bucket=settings.hetzner_s3_bucket,
                Delete={
                    "Objects": [{"Key": k} for k in batch],
                    "Quiet": True,
                },
            )

    await asyncio.to_thread(_batch_del)
    logger.info("S3 batch delete: %d files", len(storage_keys))
