"""
Compares captured catalog repo commits to live git HEAD

PR 1 ships the helper. PR 5 adds the 60s TTL cache wrapper around SourceCatalogService.health() call sites
"""

import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from app.logger import get_logger
from app.model.schemas.source_catalog import CatalogState, RepoProvenance

logger = get_logger(__name__)

# Map repo names from the analyzer to their live working-tree paths.
_REPO_LIVE_PATHS: dict[str, Path] = {
    "mpmb_source": Path("data/mpmb_source"),
    "mpmb_source_2024": Path("data/mpmb_source_2024"),
    "imports_source": Path("data/imports_source"),
}

_GIT_UNAVAILABLE_LOGGED = False


def _git_rev_parse_head(repo_name: str) -> Optional[str]:
    """
    Return live HEAD commit (full hash) or None on any failure
    """
    global _GIT_UNAVAILABLE_LOGGED

    repo_path = _REPO_LIVE_PATHS.get(repo_name)
    if repo_path is None or not repo_path.exists():
        return None

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        if not _GIT_UNAVAILABLE_LOGGED:
            logger.warning(
                "git_unavailable_for_staleness",
                repo=repo_name,
                error=str(exc),
            )
            _GIT_UNAVAILABLE_LOGGED = True
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip() or None


def check_staleness(
    repos: dict[str, RepoProvenance],
) -> tuple[CatalogState, dict[str, str]]:
    """
    Compare captured commits to live git HEADs

    Returns (state, live_commits). State stays HEALTHY if no commits can be verified (git unavailable, repos not present, etc)
    """
    live_commits: dict[str, str] = {}
    any_verified = False
    has_drift = False

    for repo_name, provenance in repos.items():
        live = _git_rev_parse_head(repo_name)
        if live is None:
            continue
        any_verified = True
        live_commits[repo_name] = live
        if provenance.commit and live != provenance.commit:
            has_drift = True

    if not any_verified:
        return CatalogState.HEALTHY, live_commits  # nothing to compare

    return (
        CatalogState.STALE if has_drift else CatalogState.HEALTHY,
        live_commits,
    )


class StalenessTTLCache:
    """60s TTL wrapper around `check_staleness`. Thread-safe."""

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._cached_at: float = 0.0
        self._cached_state: Optional[CatalogState] = None
        self._cached_live: dict[str, str] = {}

    def get_or_compute(
        self,
        repos: dict[str, RepoProvenance],
    ) -> tuple[CatalogState, dict[str, str]]:
        now = time.monotonic()
        with self._lock:
            if self._cached_state is not None and now - self._cached_at < self._ttl:
                return self._cached_state, dict(self._cached_live)
        state, live = check_staleness(repos)
        with self._lock:
            self._cached_state = state
            self._cached_live = dict(live)
            self._cached_at = now
        return state, live

    def invalidate(self) -> None:
        with self._lock:
            self._cached_state = None
            self._cached_live = {}
            self._cached_at = 0.0
