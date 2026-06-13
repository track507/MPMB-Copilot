from qdrant_client.models import MatchAny, MatchValue

from app.services.vector.qdrant import QdrantStore


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


def test_empty_filters_return_none():
    store = QdrantStore()
    assert store._build_qdrant_filter(None) is None
    assert store._build_qdrant_filter({}) is None
