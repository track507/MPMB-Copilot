import pytest

from app.core.query_analysis import analyze_query


@pytest.mark.parametrize(
    "query,expected",
    [
        # Exact identifier matches
        ("How do I use ClassList?", "ClassList"),
        ("What about ClassSubList?", "ClassSubList"),
        ("Show me BackgroundFeatureList syntax", "BackgroundFeatureList"),
        ("How do BackgroundList entries work?", "BackgroundList"),
        ("Tell me about SpellsList", "SpellsList"),
        # Prefix collisions - the longer name must win when both are present
        ("How does ClassSubList differ from ClassList?", "ClassSubList"),
        # Typo / non-existent identifier must not falsely match a prefix
        ("What about SubClassList?", None),
        # Natural language falls through to keyword matching
        ("How do I add a subclass?", "ClassSubList"),
        ("How do I add a spell?", "SpellsList"),
        ("Show me feats", "FeatsList"),
        # Bare "source" is intentionally not mapped
        ("Where is the source code?", None),
    ],
)
def test_object_type_inference(query: str, expected: str | None) -> None:
    assert analyze_query(query).object_type == expected


@pytest.mark.parametrize(
    "query,expected",
    [
        ("How do I add a 2024 spell?", "2024"),
        ("Show me the 2014 PHB rules", "2014"),
        ("What's new in OneD&D?", "2024"),
        ("Explain the classic edition", "2014"),
        ("How do I add a spell?", None),  # No edition signal
    ],
)
def test_edition_inference(query: str, expected: str | None) -> None:
    assert analyze_query(query).edition == expected
