"""
Fixtures for the UploadService tests

The service's DB seam (upload_registry) is mocked here - the registry has its own integration tests
These target the service's own responsibilities: disk mechanics, hashing/dedup, access control, reconciliation, orphan cleanup
That keeps them fast and Postgres-free; only a temp data_dir is real
"""

import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

import app.services.uploads.service as service_mod
from app.config import config
from app.core.storage_keys import DEFAULT_TENANT_ID, file_key, library_prefix, user_global_prefix


@pytest.fixture
def upload_root(tmp_path, monkeypatch):
    """
    Point the storage root at a temp dir and return the tenants subtree inside it

    data_dir is the single anchor: _scope_dir builds paths from it and storage_key is taken relative to it
    """
    data = tmp_path / "data"
    root = data / "tenants"
    root.mkdir(parents=True)
    monkeypatch.setattr(config, "data_dir", str(data), raising=False)
    monkeypatch.setattr(config, "tenants_dir", str(root), raising=False)
    return root


@pytest.fixture
def scope_dir(upload_root):
    """
    The directory a scope's bytes land in, spelled through the key scheme rather than through the service

    ? Spelling it independently is what keeps the assertion meaningful: calling _scope_dir would agree by construction
    """

    def _dir(scope: str, *, tenant_id: str = DEFAULT_TENANT_ID, user_id: str = "u1") -> Path:
        data = upload_root.parent
        if scope == "global":
            return data / user_global_prefix(tenant_id, user_id)
        return data / library_prefix(tenant_id)

    return _dir


@pytest.fixture
def file_key_for():
    """
    A full storage key for one file in a scope, spelled through the key scheme

    ? Tests used to hand-write flat keys like "shared/a.js", which stopped matching the layout without failing loudly
    """

    def _key(scope: str, name: str, *, tenant_id: str = DEFAULT_TENANT_ID, user_id: str = "u1") -> str:
        prefix = user_global_prefix(tenant_id, user_id) if scope == "global" else library_prefix(tenant_id)
        return file_key(prefix, name)

    return _key


@pytest.fixture
def registry(monkeypatch):
    """
    Replace the service's upload_registry with an AsyncMock carrying sane defaults
    """
    mock = AsyncMock()
    mock.count_files.return_value = 0
    mock.get_by_name.return_value = None
    mock.get_by_casefolded_name.return_value = None
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
