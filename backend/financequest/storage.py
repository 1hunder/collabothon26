"""Durable file storage: quest documents, location art and the TTS cache.

Two backends behind one small interface, chosen by settings:

- local filesystem under ``DATA_DIR`` (default; dev and tests)
- S3-compatible object storage (a Railway Bucket in production) when ``STORAGE_BUCKET`` is set

Keys are relative, forward-slash paths such as ``quests/<job id>/case.md``. A redeploy loses
nothing that lives behind this module when the S3 backend is on.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from financequest.config import Settings, get_settings


class Storage(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def url_or_path(self, key: str) -> str: ...


def _safe(key: str) -> str:
    if not key or key.startswith("/") or ".." in Path(key).parts:
        raise ValueError(f"invalid storage key: {key!r}")
    return key


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        return self.root / _safe(key)

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # readers never see a half-written file

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def url_or_path(self, key: str) -> str:
        return str(self._path(key).resolve())


class S3Storage:
    def __init__(self, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Key=_safe(key), Body=data, **extra)

    def get_bytes(self, key: str) -> bytes:
        res = self.client.get_object(Bucket=self.bucket, Key=_safe(key))
        return bytes(res["Body"].read())

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=_safe(key))
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise
        return True

    def url_or_path(self, key: str) -> str:
        """A short-lived presigned URL (buckets are private)."""
        return str(
            self.client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": _safe(key)}, ExpiresIn=3600
            )
        )


@lru_cache
def _s3_client(endpoint: str, key_id: str, secret: str, region: str) -> Any:
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint or None,
        aws_access_key_id=key_id or None,
        aws_secret_access_key=secret or None,
        region_name=region or None,
    )


def get_storage(settings: Settings | None = None) -> Storage:
    s = settings or get_settings()
    if s.storage_bucket:
        client = _s3_client(
            s.storage_endpoint, s.storage_access_key_id, s.storage_secret_access_key,
            s.storage_region,
        )  # fmt: skip
        return S3Storage(client, s.storage_bucket)
    return LocalStorage(Path(s.data_dir))


def put_many(prefix: str, files: dict[str, Path], storage: Storage | None = None) -> None:
    st = storage or get_storage()
    for name, path in files.items():
        st.put_bytes(f"{prefix}/{name}", path.read_bytes())


def materialise(prefix: str, names: list[str], storage: Storage | None = None) -> Path:
    """Copy ``prefix/<name>`` files into a fresh temp directory (for code that wants a path)."""
    st = storage or get_storage()
    out = Path(tempfile.mkdtemp(prefix="fq-pack-"))
    for name in names:
        (out / name).write_bytes(st.get_bytes(f"{prefix}/{name}"))
    return out


def read_ref_bytes(ref: str) -> bytes | None:
    """Bytes behind a stored reference: a local file path (older rows) or a storage key."""
    p = Path(ref)
    if p.is_file():
        return p.read_bytes()
    st = get_storage()
    try:
        return st.get_bytes(ref) if st.exists(ref) else None
    except ValueError:
        return None
