import pytest

from app.services.vector.qdrant import _IDENTITY_PAYLOAD_KEY, _IDENTITY_POINT_ID, QdrantStore


class _VectorParams:
    def __init__(self, size: int):
        self.size = size


class _CollectionParams:
    def __init__(self, dense_dim: int):
        self.vectors = {"dense": _VectorParams(dense_dim)}


class _CollectionConfig:
    def __init__(self, dense_dim: int):
        self.params = _CollectionParams(dense_dim)


class _Info:
    def __init__(self, count: int, dense_dim: int = 384):
        self.points_count = count
        self.config = _CollectionConfig(dense_dim)


class _Point:
    def __init__(self, payload: dict):
        self.payload = payload


class _FakeClient:
    """Minimal stand-in for the Qdrant client used by identity logic."""

    def __init__(self, count: int = 0, stored: dict | None = None, dense_dim: int = 384):
        self._count = count
        self._stored = stored
        self._dense_dim = dense_dim
        self.upserted: list = []

    def get_collection(self, name):
        return _Info(self._count, self._dense_dim)

    def retrieve(self, collection_name, ids, with_payload):
        if self._stored is None:
            return []
        return [_Point({_IDENTITY_PAYLOAD_KEY: self._stored})]

    def upsert(self, collection_name, points):
        self.upserted.extend(points)


def _store(client: _FakeClient) -> QdrantStore:
    store = QdrantStore()
    store.client = client
    return store


@pytest.mark.asyncio
async def test_empty_collection_is_ok_no_stamp():
    store = _store(_FakeClient(count=0, stored=None))
    await store._load_identity_state()
    assert store._identity_status == "ok"
    assert store._has_identity_point is False
    store._raise_if_identity_mismatch()  # must not raise


@pytest.mark.asyncio
async def test_populated_but_unstamped_is_missing_and_serves():
    store = _store(_FakeClient(count=10, stored=None))
    await store._load_identity_state()
    assert store._identity_status == "missing"
    # ! A legacy unstamped index must keep serving, not refuse queries
    store._raise_if_identity_mismatch()


@pytest.mark.asyncio
async def test_matching_stamp_is_ok():
    from app.services.embedding.service import embedding_service

    store = _store(_FakeClient(count=10, stored=dict(embedding_service.identity())))
    await store._load_identity_state()
    assert store._identity_status == "ok"
    assert store._has_identity_point is True


@pytest.mark.asyncio
async def test_mismatched_stamp_refuses_queries():
    store = _store(
        _FakeClient(count=10, stored={"provider": "openai", "model": "text-embedding-3-small", "dimension": 1536})
    )
    await store._load_identity_state()
    assert store._identity_status == "mismatch"
    with pytest.raises(RuntimeError, match="re-index required"):
        store._raise_if_identity_mismatch()


@pytest.mark.asyncio
async def test_identity_health_mapping():
    store = QdrantStore()

    store._identity_status, store._identity_message = "mismatch", "boom"
    assert await store.identity_health() == ("unavailable", "boom")

    store._identity_status, store._identity_message = "missing", "legacy"
    assert await store.identity_health() == ("ready", "legacy")

    store._identity_status, store._identity_message = "ok", "fastembed/x (384d)"
    status, message = await store.identity_health()
    assert status == "ready"
    assert message == "fastembed/x (384d)"


@pytest.mark.asyncio
async def test_write_identity_upserts_reserved_point():
    client = _FakeClient()
    store = _store(client)

    await store.write_identity({"provider": "fastembed", "model": "m", "dimension": 4})

    assert len(client.upserted) == 1
    point = client.upserted[0]
    assert str(point.id) == _IDENTITY_POINT_ID
    assert point.payload[_IDENTITY_PAYLOAD_KEY]["model"] == "m"
    assert store._identity_status == "ok"
    assert store._has_identity_point is True


def test_read_identity_none_when_absent():
    store = _store(_FakeClient(stored=None))
    assert store.read_identity() is None


def test_read_identity_returns_stored_payload():
    store = _store(_FakeClient(stored={"provider": "fastembed", "model": "m", "dimension": 4}))
    assert store.read_identity()["model"] == "m"


@pytest.mark.asyncio
async def test_adopt_identity_stamps_unstamped_matching_dim():
    from app.services.embedding.service import embedding_service

    dim = embedding_service.identity()["dimension"]
    client = _FakeClient(count=10, stored=None, dense_dim=dim)
    store = _store(client)

    adopted, _ = await store.adopt_identity()

    assert adopted is True
    assert len(client.upserted) == 1
    assert store._has_identity_point is True


@pytest.mark.asyncio
async def test_adopt_identity_refuses_on_dimension_mismatch():
    client = _FakeClient(count=10, stored=None, dense_dim=1536)
    store = _store(client)

    adopted, message = await store.adopt_identity()

    assert adopted is False
    assert "force_reindex" in message
    assert client.upserted == []


@pytest.mark.asyncio
async def test_adopt_identity_noop_when_already_stamped():
    from app.services.embedding.service import embedding_service

    client = _FakeClient(count=10, stored=dict(embedding_service.identity()))
    store = _store(client)
    await store._load_identity_state()

    adopted, message = await store.adopt_identity()

    assert adopted is True
    assert message == "index already stamped"
    assert client.upserted == []
