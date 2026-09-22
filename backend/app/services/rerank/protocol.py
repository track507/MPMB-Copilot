"""
The reranking port

A second implementation is named in the rerank catalog, which is why this is a type and not a concrete import
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        """Reorder candidates by relevance to the query and return the top_k"""
        ...
