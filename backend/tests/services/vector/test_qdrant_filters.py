from qdrant_client.models import HasIdCondition, MatchAny, MatchValue

from app.services.vector.qdrant import _IDENTITY_POINT_ID, QdrantStore


def test_scalar_filter_uses_match_value():
    store = QdrantStore()
    f = store._build_qdrant_filter({"edition": "2024"})
    assert len(f.must) == 1
    assert f.must[0].key == "edition"
    assert isinstance(f.must[0].match, MatchValue)
    assert f.must[0].match.value == "2024"


def test_list_filter_uses_match_any_not_multiple_musts():
    """A list means ANY-of. One must-condition per value would demand a
    single-valued field equal all values at once - matching nothing."""
    store = QdrantStore()
    f = store._build_qdrant_filter({"source_tier": ["official_example", "community_example"]})
    assert len(f.must) == 1
    assert isinstance(f.must[0].match, MatchAny)
    assert set(f.must[0].match.any) == {"official_example", "community_example"}


def test_object_type_maps_to_metadata_path():
    store = QdrantStore()
    f = store._build_qdrant_filter({"object_type": "RaceList"})
    assert f.must[0].key == "metadata.object_type"


def test_empty_filters_still_exclude_identity_point():
    """No metadata filter still yields a filter that hides the reserved stamp point."""
    store = QdrantStore()
    for f in (store._build_qdrant_filter(None), store._build_qdrant_filter({})):
        assert f is not None
        assert f.must is None
        assert len(f.must_not) == 1
        assert isinstance(f.must_not[0], HasIdCondition)
        assert f.must_not[0].has_id == [_IDENTITY_POINT_ID]


def test_real_filters_also_exclude_identity_point():
    store = QdrantStore()
    f = store._build_qdrant_filter({"edition": "2024"})
    assert len(f.must) == 1
    assert any(isinstance(c, HasIdCondition) for c in f.must_not)
