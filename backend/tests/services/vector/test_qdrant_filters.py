"""
Filter construction, including the tenant predicate the store composes itself

Conditions are looked up by key rather than by position, so adding another always-on predicate does not rewrite every test
"""

from typing import Any, Optional

from qdrant_client.models import Filter, HasIdCondition, MatchAny, MatchValue

from app.core.storage_keys import DEFAULT_TENANT_ID, SHARED_TENANT
from app.services.vector.qdrant import _IDENTITY_POINT_ID, QdrantStore

OTHER_TENANT = "019f3400-0000-7000-8000-0000000000ff"


def _by_key(f: Filter, key: str) -> Optional[Any]:
    return next((c for c in (f.must or []) if getattr(c, "key", None) == key), None)


def test_the_tenant_predicate_is_always_present():
    """
    The predicate the store composes from its argument, not from the filter dict

    This is the isolation boundary: if it is ever absent, every tenant reads every other tenant's chunks
    """
    store = QdrantStore()
    f = store._build_qdrant_filter({"edition": "2024"}, tenant_id=DEFAULT_TENANT_ID)

    tenant = _by_key(f, "tenant_id")
    assert tenant is not None
    assert set(tenant.match.any) == {DEFAULT_TENANT_ID, SHARED_TENANT}


def test_the_tenant_predicate_survives_an_empty_filter_dict():
    store = QdrantStore()
    for filters in (None, {}):
        f = store._build_qdrant_filter(filters, tenant_id=DEFAULT_TENANT_ID)
        assert _by_key(f, "tenant_id") is not None


def test_one_tenant_never_matches_another():
    store = QdrantStore()
    mine = _by_key(store._build_qdrant_filter(None, tenant_id=DEFAULT_TENANT_ID), "tenant_id")
    theirs = _by_key(store._build_qdrant_filter(None, tenant_id=OTHER_TENANT), "tenant_id")

    assert OTHER_TENANT not in mine.match.any
    assert DEFAULT_TENANT_ID not in theirs.match.any
    assert SHARED_TENANT in mine.match.any and SHARED_TENANT in theirs.match.any


def test_a_caller_cannot_widen_the_tenant_through_the_filter_dict():
    """
    A tenant_id passed in `filters` must not replace the composed predicate

    Otherwise a tool argument that reached the filter dict would choose its own isolation
    """
    store = QdrantStore()
    f = store._build_qdrant_filter({"tenant_id": OTHER_TENANT}, tenant_id=DEFAULT_TENANT_ID)

    composed = (f.must or [])[0]
    assert composed.key == "tenant_id"
    assert set(composed.match.any) == {DEFAULT_TENANT_ID, SHARED_TENANT}


def test_scalar_filter_uses_match_value():
    store = QdrantStore()
    f = store._build_qdrant_filter({"edition": "2024"}, tenant_id=DEFAULT_TENANT_ID)

    edition = _by_key(f, "edition")
    assert isinstance(edition.match, MatchValue)
    assert edition.match.value == "2024"


def test_list_filter_uses_match_any_not_multiple_musts():
    """
    A list means ANY-of

    One must-condition per value would demand a single-valued field equal all values at once, matching nothing
    """
    store = QdrantStore()
    f = store._build_qdrant_filter(
        {"source_tier": ["official_example", "community_example"]}, tenant_id=DEFAULT_TENANT_ID
    )

    tier = _by_key(f, "source_tier")
    assert isinstance(tier.match, MatchAny)
    assert set(tier.match.any) == {"official_example", "community_example"}


def test_object_type_maps_to_metadata_path():
    store = QdrantStore()
    f = store._build_qdrant_filter({"object_type": "RaceList"}, tenant_id=DEFAULT_TENANT_ID)

    assert _by_key(f, "metadata.object_type") is not None


def test_every_filter_excludes_the_identity_point():
    """The reserved embedding-identity stamp is never a search result"""
    store = QdrantStore()
    for filters in (None, {}, {"edition": "2024"}):
        f = store._build_qdrant_filter(filters, tenant_id=DEFAULT_TENANT_ID)
        assert any(isinstance(c, HasIdCondition) for c in f.must_not)
        assert f.must_not[0].has_id == [_IDENTITY_POINT_ID]
