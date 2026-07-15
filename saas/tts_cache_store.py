"""S3/MinIO-backed TTS cache store: objects at tts_cache/<key>.mp3, shared across all users."""
from __future__ import annotations

from botocore.exceptions import ClientError

from .object_storage import _bucket_name, get_s3_client, upload_bytes

CACHE_PREFIX = "tts_cache/"


class ObjectStorageCacheStore:
    def _object_key(self, key: str) -> str:
        return f"{CACHE_PREFIX}{key}.mp3"

    def fetch(self, key: str, dest_path: str) -> bool:
        client = get_s3_client()
        try:
            client.download_file(_bucket_name(), self._object_key(key), dest_path)
            return True
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey"):
                return False
            raise

    def store(self, key: str, src_path: str) -> None:
        with open(src_path, "rb") as f:
            upload_bytes(self._object_key(key), f.read())
