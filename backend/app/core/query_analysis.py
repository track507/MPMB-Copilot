"""Query analysis for metadata-based retrieval narrowing.

Infers MPMB object type and D&D edition from query text to drive
metadata filters before vector search.  Both use language-agnostic
signals (code identifiers and numbers), so they work across languages.

Usage:
    from app.core.query_analysis import analyze_query

    analysis = analyze_query("How do I add a 2024 spell?")
    analysis.object_type   # "SpellsList"
    analysis.edition       # "2024"
    analysis.function_name # None
"""

import re
from dataclasses import dataclass
from typing import Optional


# * Result
@dataclass(frozen=True)
class QueryAnalysis:
    """Metadata inferred from the query text."""

    object_type: Optional[str]
    """MPMB object type (e.g. 'SpellsList', 'FeatsList') or None."""

    edition: Optional[str]
    """Detected edition ('2014' or '2024') or None (search both)."""

    function_name: Optional[str]
    """Detected MPMB function name (e.g. 'AddSubClass') or None."""


# * Object type inference

# Maps keywords -> MPMB ObjectType names used in chunk metadata.
# Multi-word phrases are checked first (longest match wins).
# Keys are lowercase for case-insensitive matching.
_OBJECT_TYPE_KEYWORDS: dict[str, str] = {
    # Multi-word (checked first)
    "magic item": "MagicItemsList",
    "magic items": "MagicItemsList",
    "background feature": "BackgroundFeatureList",
    "background features": "BackgroundFeatureList",
    "pact boon": "AddWarlockPactBoon",
    "fighting style": "AddFightingStyle",
    "fighting styles": "AddFightingStyle",
    "warlock invocation": "AddWarlockInvocation",
    "warlock invocations": "AddWarlockInvocation",
    "eldritch invocation": "AddWarlockInvocation",
    "eldritch invocations": "AddWarlockInvocation",
    "racial variant": "AddRacialVariant",
    "racial variants": "AddRacialVariant",
    # Single-word (checked after multi-word)
    "spell": "SpellsList",
    "spells": "SpellsList",
    "cantrip": "SpellsList",
    "cantrips": "SpellsList",
    "race": "RaceList",
    "races": "RaceList",
    "species": "RaceList",
    "feat": "FeatsList",
    "feats": "FeatsList",
    "class": "ClassList",
    "classes": "ClassList",
    "subclass": "ClassSubList",
    "subclasses": "ClassSubList",
    "weapon": "WeaponsList",
    "weapons": "WeaponsList",
    "armor": "ArmourList",
    "armour": "ArmourList",
    "background": "BackgroundList",
    "backgrounds": "BackgroundList",
    "creature": "CreatureList",
    "creatures": "CreatureList",
    "companion": "CompanionList",
    "companions": "CompanionList",
    "source": "SourceList",
    "ammo": "AmmoList",
    "ammunition": "AmmoList",
    "gear": "GearList",
    "pack": "PacksList",
}

# * Sorted by length descending so multi-word phrases match first
_OBJECT_TYPE_KEYWORDS_SORTED = sorted(_OBJECT_TYPE_KEYWORDS.items(), key=lambda x: len(x[0]), reverse=True)


def _infer_object_type(query: str) -> Optional[str]:
    """Detect MPMB object type from query text.

    Checks multi-word phrases first, then single words with word boundary.
    Also checks for literal ObjectType names (code identifiers).
    """
    query_lower = query.lower()

    # Check for literal code identifiers first (e.g. "SpellsList", "FeatsList")
    for code_name in (
        "SpellsList",
        "ClassList",
        "ClassSubList",
        "RaceList",
        "FeatsList",
        "MagicItemsList",
        "CreatureList",
        "BackgroundList",
        "BackgroundFeatureList",
        "WeaponsList",
        "ArmourList",
        "AmmoList",
        "GearList",
        "SourceList",
        "CompanionList",
        "PacksList",
    ):
        if code_name in query:
            return code_name

    # Check keyword phrases
    for keyword, obj_type in _OBJECT_TYPE_KEYWORDS_SORTED:
        if " " in keyword:
            # Multi-word: substring match
            if keyword in query_lower:
                return obj_type
        else:
            # Single-word: word boundary match to avoid "class" in "subclass"
            if re.search(rf"\b{re.escape(keyword)}\b", query_lower):
                return obj_type

    return None


# * Function name inference

# * MPMB function names - these are code identifiers, language-independent
_FUNCTION_NAMES = [
    "AddSubClass",
    "AddFeatureChoice",
    "AddRacialVariant",
    "AddBackgroundVariant",
    "AddWarlockInvocation",
    "AddFightingStyle",
    "AddWarlockPactBoon",
    "RequiredSheetVersion",
]


def _infer_function_name(query: str) -> Optional[str]:
    """Detect MPMB function name from query text.

    Only matches literal code identifiers (case-sensitive).
    """
    for func_name in _FUNCTION_NAMES:
        if func_name in query:
            return func_name
    return None


# * Edition inference

_EDITION_2024_PATTERN = re.compile(
    r"\b(2024|5\.5e|onednd|one\s*d&?d|dnd\s*2024|twenty.?four|"
    r"new\s+edition|revised\s+edition|phb\s*2024|5\.5)\b",
    re.IGNORECASE,
)

_EDITION_2014_PATTERN = re.compile(
    r"\b(2014|5e\s+original|legacy\s+edition|classic\s+edition|"
    r"pre.?2024|phb\s*2014|srd\s*5\.?1|original\s+edition|old\s+edition)\b",
    re.IGNORECASE,
)


def _infer_edition(query: str) -> Optional[str]:
    """Detect edition from query text.

    Returns '2014', '2024', or None (search both).
    Numbers and abbreviations are language-independent.
    """
    has_2024 = bool(_EDITION_2024_PATTERN.search(query))
    has_2014 = bool(_EDITION_2014_PATTERN.search(query))

    if has_2024 and not has_2014:
        return "2024"
    if has_2014 and not has_2024:
        return "2014"

    # Both or neither -> don't filter
    return None


# * Public API


def analyze_query(query: str) -> QueryAnalysis:
    """Analyze a query for MPMB-specific metadata signals.

    Extracts object type, edition, and function name from the query text.
    All detection is based on code identifiers and numbers, making it
    language-agnostic.

    Args:
        query: Raw user query text.

    Returns:
        QueryAnalysis with inferred metadata (any field may be None).
    """
    return QueryAnalysis(
        object_type=_infer_object_type(query),
        edition=_infer_edition(query),
        function_name=_infer_function_name(query),
    )
