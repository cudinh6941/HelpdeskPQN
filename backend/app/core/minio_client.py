from datetime import timedelta
from io import BytesIO
from pathlib import Path
from typing import Optional
import logging

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class StorageService:
    """
    Hybrid MinIO (S3) + Local Storage helper.
    Uses separate internal/public MinIO endpoints so presigned URL signatures
    remain valid for browsers outside Docker, and gracefully falls back to
    local disk storage when MINIO_ENABLED=false.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.local_root = Path(self.settings.LOCAL_STORAGE_DIR)
        self.local_root.mkdir(parents=True, exist_ok=True)
        self._internal_client: Optional[Minio] = None
        self._public_client: Optional[Minio] = None

    @property
    def minio_enabled(self) -> bool:
        return bool(self.settings.MINIO_ENABLED)

    def _get_internal_client(self) -> Minio:
        if self._internal_client is None:
            self._internal_client = Minio(
                self.settings.MINIO_INTERNAL_ENDPOINT,
                access_key=self.settings.MINIO_ROOT_USER,
                secret_key=self.settings.MINIO_ROOT_PASSWORD,
                secure=self.settings.MINIO_USE_SSL,
            )
        return self._internal_client

    def _get_public_client(self) -> Minio:
        if self._public_client is None:
            self._public_client = Minio(
                self.settings.MINIO_PUBLIC_ENDPOINT,
                access_key=self.settings.MINIO_ROOT_USER,
                secret_key=self.settings.MINIO_ROOT_PASSWORD,
                secure=self.settings.MINIO_USE_SSL,
            )
        return self._public_client

    def ensure_bucket(self) -> None:
        if not self.minio_enabled:
            return
        try:
            client = self._get_internal_client()
            if not client.bucket_exists(self.settings.MINIO_BUCKET):
                client.make_bucket(self.settings.MINIO_BUCKET)
        except Exception as exc:
            logger.warning("MinIO bucket initialization warning: %s", exc)

    def presigned_put_url(self, object_key: str, expires_minutes: int = 15) -> Optional[str]:
        if not self.minio_enabled:
            return None
        try:
            return self._get_public_client().presigned_put_object(
                self.settings.MINIO_BUCKET,
                object_key,
                expires=timedelta(minutes=expires_minutes),
            )
        except Exception as exc:
            logger.warning("Failed to generate MinIO presigned PUT URL: %s", exc)
            return None

    def presigned_get_url(self, object_key: str, expires_minutes: int = 30) -> Optional[str]:
        if not self.minio_enabled:
            return None
        try:
            return self._get_public_client().presigned_get_object(
                self.settings.MINIO_BUCKET,
                object_key,
                expires=timedelta(minutes=expires_minutes),
            )
        except Exception as exc:
            logger.warning("Failed to generate MinIO presigned GET URL: %s", exc)
            return None

    def put_object_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        if self.minio_enabled:
            try:
                client = self._get_internal_client()
                self.ensure_bucket()
                client.put_object(
                    self.settings.MINIO_BUCKET,
                    object_key,
                    BytesIO(data),
                    length=len(data),
                    content_type=content_type,
                )
                return
            except Exception as exc:
                logger.warning("MinIO put_object failed, falling back to local storage: %s", exc)

        target = (self.local_root / object_key).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get_object_bytes(self, object_key: str) -> Optional[bytes]:
        if self.minio_enabled:
            try:
                client = self._get_internal_client()
                response = client.get_object(self.settings.MINIO_BUCKET, object_key)
                try:
                    return response.read()
                finally:
                    response.close()
                    response.release_conn()
            except S3Error:
                pass
            except Exception as exc:
                logger.warning("MinIO get_object failed, checking local fallback: %s", exc)

        target = (self.local_root / object_key).resolve()
        if target.exists() and target.is_file():
            return target.read_bytes()
        return None

    def delete_object(self, object_key: str) -> None:
        if self.minio_enabled:
            try:
                client = self._get_internal_client()
                client.remove_object(self.settings.MINIO_BUCKET, object_key)
            except Exception as exc:
                logger.warning("MinIO remove_object failed for '%s': %s", object_key, exc)

        local_root_resolved = self.local_root.resolve()
        target = (self.local_root / object_key).resolve()
        if local_root_resolved in target.parents and target.exists() and target.is_file():
            target.unlink(missing_ok=True)


storage_service = StorageService()
