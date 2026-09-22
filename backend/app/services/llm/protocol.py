"""
The model factory port

The domain builds agents but must not choose a vendor, so the callable that constructs one arrives as a dependency
"""

from typing import Any, Optional, Protocol


class ModelFactory(Protocol):
    def __call__(
        self,
        *,
        provider: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> tuple[Any, Optional[Any]]:
        """Build a provider-specific model plus its settings, ready to hand to an Agent"""
        ...
