"""File storage behind one interface: Cloudflare R2 (S3 API) or a local folder for dev.

Clients upload with a short-lived signed URL, so file bytes never pass through the API
when R2 is used. The local variant signs URLs that point back at /storage/upload.
"""

import asyncio
import hashlib
import hmac
import time
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

from app.core.config import settings

UPLOAD_URL_SECONDS = 15 * 60


class Storage(Protocol):
    async def presign_put(self, key: str, content_type: str) -> str: ...

    async def size(self, key: str) -> int | None: ...

    async def read(self, key: str) -> bytes: ...


class R2Storage:
    def __init__(self) -> None:
        import boto3  # imported lazily: only needed when R2 is configured

        self.bucket: str = settings.R2_BUCKET or ""
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
        )

    async def presign_put(self, key: str, content_type: str) -> str:
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=UPLOAD_URL_SECONDS,
        )

    async def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        try:
            head = await asyncio.to_thread(self.client.head_object, Bucket=self.bucket, Key=key)
        except ClientError:
            return None
        return int(head["ContentLength"])

    async def read(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(obj["Body"].read)


def _sign(key: str, expires: int) -> str:
    message = f"{key}|{expires}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).hexdigest()


def verify_local_signature(key: str, expires: int, signature: str) -> bool:
    return expires >= int(time.time()) and hmac.compare_digest(_sign(key, expires), signature)


class LocalStorage:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.LOCAL_STORAGE_DIR)

    def path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        if self.root.resolve() not in target.parents:
            raise ValueError("Invalid storage key")
        return target

    async def presign_put(self, key: str, content_type: str) -> str:
        expires = int(time.time()) + UPLOAD_URL_SECONDS
        query = urlencode({"key": key, "expires": expires, "sig": _sign(key, expires)})
        return (
            f"{settings.API_PUBLIC_URL.rstrip('/')}{settings.API_V1_PREFIX}/storage/upload?{query}"
        )

    async def size(self, key: str) -> int | None:
        path = self.path(key)
        return path.stat().st_size if path.exists() else None

    async def read(self, key: str) -> bytes:
        return await asyncio.to_thread(self.path(key).read_bytes)

    async def write(self, key: str, data: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)


def get_storage() -> Storage:
    return R2Storage() if settings.r2_configured else LocalStorage()
