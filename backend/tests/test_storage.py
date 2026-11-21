"""Durable storage: local backend and an S3-compatible one (moto)."""

import os
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from financequest.config import Settings
from financequest.storage import LocalStorage, S3Storage, get_storage, materialise, put_many


def _roundtrip(st: LocalStorage | S3Storage) -> None:
    assert not st.exists("quests/a/case.md")
    st.put_bytes("quests/a/case.md", b"hello", "text/markdown")
    assert st.exists("quests/a/case.md")
    assert st.get_bytes("quests/a/case.md") == b"hello"
    st.put_bytes("quests/a/case.md", b"changed")  # overwrite
    assert st.get_bytes("quests/a/case.md") == b"changed"
    assert st.url_or_path("quests/a/case.md")
    with pytest.raises(ValueError):
        st.put_bytes("../escape", b"x")


def test_local_backend(tmp_path: Path) -> None:
    st = LocalStorage(tmp_path)
    _roundtrip(st)
    assert (tmp_path / "quests" / "a" / "case.md").read_bytes() == b"changed"
    assert st.url_or_path("quests/a/case.md").endswith("quests/a/case.md")


@pytest.fixture
def s3_env() -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")}
    os.environ.update(AWS_ACCESS_KEY_ID="testing", AWS_SECRET_ACCESS_KEY="testing")
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="fq-bucket")
        yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_s3_backend(s3_env: None) -> None:
    st = S3Storage(boto3.client("s3", region_name="us-east-1"), "fq-bucket")
    _roundtrip(st)
    assert st.url_or_path("quests/a/case.md").startswith("https://")


def test_get_storage_picks_backend_from_settings(s3_env: None, tmp_path: Path) -> None:
    local = get_storage(Settings(data_dir=str(tmp_path), storage_bucket=""))
    assert isinstance(local, LocalStorage)
    s3 = get_storage(Settings(storage_bucket="fq-bucket", storage_region="us-east-1",
                              storage_access_key_id="testing",
                              storage_secret_access_key="testing"))  # fmt: skip
    assert isinstance(s3, S3Storage)
    s3.put_bytes("k", b"v")
    assert s3.get_bytes("k") == b"v"


def test_put_many_and_materialise(s3_env: None, tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("A")
    (src / "b.txt").write_text("B")
    st = S3Storage(boto3.client("s3", region_name="us-east-1"), "fq-bucket")
    put_many("p", {"a.txt": src / "a.txt", "b.txt": src / "b.txt"}, st)
    out = materialise("p", ["a.txt", "b.txt"], st)
    assert (out / "a.txt").read_text() == "A" and (out / "b.txt").read_text() == "B"
