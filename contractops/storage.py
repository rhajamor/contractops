"""Pluggable baseline artifact storage backends.

Supported: local filesystem, AWS S3, Google Cloud Storage.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaselineStorage(ABC):
    """Abstract interface for baseline persistence."""

    @abstractmethod
    def save(self, key: str, payload: dict[str, Any]) -> str:
        """Persist a baseline artifact. Returns the storage location."""

    @abstractmethod
    def load(self, key: str) -> dict[str, Any]:
        """Load a baseline artifact by key."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if a baseline artifact exists."""

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """List stored baseline keys under a prefix."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove a baseline artifact."""


class LocalStorage(BaselineStorage):
    def __init__(self, base_path: str = ".contractops/baselines") -> None:
        self.base_dir = Path(base_path)

    def save(self, key: str, payload: dict[str, Any]) -> str:
        path = self._key_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def load(self, key: str) -> dict[str, Any]:
        path = self._key_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Baseline not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def exists(self, key: str) -> bool:
        return self._key_path(key).exists()

    def list_keys(self, prefix: str = "") -> list[str]:
        if not self.base_dir.exists():
            return []
        keys: list[str] = []
        for path in sorted(self.base_dir.rglob("*.json")):
            rel = path.relative_to(self.base_dir).as_posix()
            key = rel.removesuffix(".json")
            if prefix and not key.startswith(prefix):
                continue
            keys.append(key)
        return keys

    def delete(self, key: str) -> None:
        path = self._key_path(key)
        if path.exists():
            path.unlink()

    def _key_path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace("\\", "_")
        return self.base_dir / f"{safe}.json"


class S3Storage(BaselineStorage):
    """AWS S3 baseline storage. Requires boto3 (pip install contractops[s3])."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "contractops/baselines",
        region: str = "",
    ) -> None:
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 storage. Install with: pip install contractops[s3]"
            ) from None

        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        session_kwargs: dict[str, str] = {}
        if region:
            session_kwargs["region_name"] = region
        self._client = boto3.client("s3", **session_kwargs)

    def save(self, key: str, payload: dict[str, Any]) -> str:
        s3_key = self._s3_key(key)
        body = json.dumps(payload, indent=2).encode("utf-8")
        self._client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=body,
            ContentType="application/json",
        )
        return f"s3://{self.bucket}/{s3_key}"

    def load(self, key: str) -> dict[str, Any]:
        s3_key = self._s3_key(key)
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=s3_key)
            body = response["Body"].read().decode("utf-8")
            return json.loads(body)
        except self._client.exceptions.NoSuchKey:
            raise FileNotFoundError(f"Baseline not found: s3://{self.bucket}/{s3_key}")

    def exists(self, key: str) -> bool:
        s3_key = self._s3_key(key)
        try:
            self._client.head_object(Bucket=self.bucket, Key=s3_key)
            return True
        except self._client.exceptions.ClientError:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        s3_prefix = f"{self.prefix}/{prefix}" if prefix else f"{self.prefix}/"
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=s3_prefix):
            for obj in page.get("Contents", []):
                raw_key = obj["Key"]
                if raw_key.endswith(".json"):
                    rel = raw_key[len(self.prefix) + 1 :].removesuffix(".json")
                    keys.append(rel)
        return sorted(keys)

    def delete(self, key: str) -> None:
        s3_key = self._s3_key(key)
        self._client.delete_object(Bucket=self.bucket, Key=s3_key)

    def _s3_key(self, key: str) -> str:
        safe = key.replace("\\", "/")
        return f"{self.prefix}/{safe}.json"


class GCSStorage(BaselineStorage):
    """Google Cloud Storage baseline storage. Requires google-cloud-storage."""

    def __init__(self, bucket: str, prefix: str = "contractops/baselines") -> None:
        try:
            from google.cloud import storage as gcs
        except ImportError:
            raise ImportError(
                "google-cloud-storage is required for GCS storage. "
                "Install with: pip install contractops[gcs]"
            ) from None

        self.prefix = prefix.rstrip("/")
        client = gcs.Client()
        self._bucket = client.bucket(bucket)

    def save(self, key: str, payload: dict[str, Any]) -> str:
        blob_name = self._blob_name(key)
        blob = self._bucket.blob(blob_name)
        data = json.dumps(payload, indent=2)
        blob.upload_from_string(data, content_type="application/json")
        return f"gs://{self._bucket.name}/{blob_name}"

    def load(self, key: str) -> dict[str, Any]:
        blob_name = self._blob_name(key)
        blob = self._bucket.blob(blob_name)
        if not blob.exists():
            raise FileNotFoundError(
                f"Baseline not found: gs://{self._bucket.name}/{blob_name}"
            )
        return json.loads(blob.download_as_text())

    def exists(self, key: str) -> bool:
        blob_name = self._blob_name(key)
        return self._bucket.blob(blob_name).exists()

    def list_keys(self, prefix: str = "") -> list[str]:
        blob_prefix = f"{self.prefix}/{prefix}" if prefix else f"{self.prefix}/"
        keys: list[str] = []
        for blob in self._bucket.list_blobs(prefix=blob_prefix):
            if blob.name.endswith(".json"):
                rel = blob.name[len(self.prefix) + 1 :].removesuffix(".json")
                keys.append(rel)
        return sorted(keys)

    def delete(self, key: str) -> None:
        blob_name = self._blob_name(key)
        blob = self._bucket.blob(blob_name)
        if blob.exists():
            blob.delete()

    def _blob_name(self, key: str) -> str:
        safe = key.replace("\\", "/")
        return f"{self.prefix}/{safe}.json"


def build_storage(
    backend: str = "local",
    base_path: str = ".contractops/baselines",
    bucket: str = "",
    prefix: str = "contractops/baselines",
    region: str = "",
) -> BaselineStorage:
    """Factory for storage backends."""
    normalized = backend.strip().lower()
    if normalized == "local":
        return LocalStorage(base_path)
    if normalized == "s3":
        if not bucket:
            raise ValueError("S3 storage requires a 'bucket' parameter.")
        return S3Storage(bucket=bucket, prefix=prefix, region=region)
    if normalized in ("gcs", "gs"):
        if not bucket:
            raise ValueError("GCS storage requires a 'bucket' parameter.")
        return GCSStorage(bucket=bucket, prefix=prefix)
    raise ValueError(f"Unknown storage backend: {backend}. Use: local, s3, gcs")
