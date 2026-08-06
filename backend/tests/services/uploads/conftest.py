"""
Fixtures for the UploadService tests

The service's DB seam (upload_registry) is mocked here - the registry has its own integration tests
These target the service's own responsibilities: disk mechanics, hashing/dedup, access control, reconciliation, orphan cleanup
That keeps them fast and Postgres-free; only a temp upload_dir is real
"""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

import app.services.uploads.service as service_mod
from app.config import config


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    """
    Point config.upload_dir at a temp dir; return it as a Path
    """
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(config, "upload_dir", str(root), raising=False)
    return root


@pytest.fixture
def registry(monkeypatch):
    """
    Replace the service's upload_registry with an AsyncMock carrying sane defaults
    """
    mock = AsyncMock()
    mock.count_files.return_value = 0
    mock.get_by_name.return_value = None
    mock.upsert_file.return_value = SimpleNamespace(id=uuid4(), meta_data={})
    mock.mark_missing.return_value = None
    mock.delete_file.return_value = True
    monkeypatch.setattr(service_mod, "upload_registry", mock)
    return mock


@pytest.fixture
def make_upload():
    """
    Factory building a Starlette UploadFile from raw bytes
    """

    def _make(
        data: bytes = b"hello",
        filename: str = "a.js",
        content_type: str = "text/javascript",
    ) -> UploadFile:
        headers = Headers({"content-type": content_type}) if content_type else None
        return UploadFile(file=io.BytesIO(data), filename=filename, size=len(data), headers=headers)

    return _make
