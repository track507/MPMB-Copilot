"""
The query embedding port

Only what the domain calls: turning one query into a vector
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class QueryEmbedder(Protocol):
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string with whatever prefix the selected model expects"""
        ...
