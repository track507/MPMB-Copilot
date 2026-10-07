"""The compute lane port"""

from collections.abc import Callable
from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class ComputeLane(Protocol):
    async def run(self, fn: Callable[[], T]) -> T: ...
