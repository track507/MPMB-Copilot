"""
Pydantic models for the analyzer-generated source catalog

The catalog is the JSON report produced by `scripts/analyze`
These models validate only the fields v1 consumes; the rest are passed through with
`extra="ignore"` so additive analyzer changes don't break load.
"""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class _IgnoreExtra(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RepoProvenance(_IgnoreExtra):
    branch: str
    commit: str
    short_commit: str
    date: str
    subject: str
    refs: str
    remote: str


class ObjectEntry(_IgnoreExtra):
    repo: Literal["mpmb_source", "mpmb_source_2024", "imports_source"]
    file: str
    line: int
    object_type: str
    object_key: str
    assignment_kind: str  # "bracket_object" | "function_object" | "dot_object"


class AddCallEntry(_IgnoreExtra):
    repo: str
    file: str
    line: int
    function_name: str
    mapped: bool


class FunctionEntry(_IgnoreExtra):
    repo: str
    file: str
    line: int
    name: str
    kind: str  # "declaration" | "var_function" | "assignment_function"


class CoverageWarning(_IgnoreExtra):
    key: str
    label: str
    current: int
    target: int
    missed: int
    severity: Literal["low", "medium", "high"]
    description: str
    action: str


class CatalogModel(_IgnoreExtra):
    """Validated top-level catalog. v1 fields only."""

    generated_at: str
    project_root: str
    repos: dict[str, RepoProvenance]
    objects: list[ObjectEntry]
    add_calls: list[AddCallEntry]
    functions: list[FunctionEntry]
    coverage_metrics: list[CoverageWarning]
    source_keys: dict[str, int] = Field(default_factory=dict)
    required_versions: dict[str, dict[str, int]] = Field(default_factory=dict)


# Service output models


class CatalogState(str, Enum):
    HEALTHY = "healthy"
    STALE = "stale"
    MISSING = "missing"
    MALFORMED = "malformed"


class SymbolKind(str, Enum):
    REGISTRY = "registry"
    ADD_DECLARATION = "add_declaration"


class SymbolEntry(BaseModel):
    name: str
    kind: SymbolKind
    occurrence_count: int
    repos: list[str]


class ObjectTypeMatch(BaseModel):
    object_type: str
    matched_via: Literal["code_identifier"]
    matched_term: str


class CatalogHealth(BaseModel):
    state: CatalogState
    message: str
    catalog_path: str
    file_mtime: Optional[datetime] = None
    generated_at: Optional[str] = None
    repos: dict[str, RepoProvenance] = Field(default_factory=dict)
    live_repo_commits: dict[str, str] = Field(default_factory=dict)
    object_count: int = 0
    symbol_count: int = 0
    coverage_severity_summary: dict[str, int] = Field(default_factory=dict)
    last_staleness_check: Optional[datetime] = None
