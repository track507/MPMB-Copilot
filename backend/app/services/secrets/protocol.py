"""
The port and the secret names for outbound provider credentials

Adapters satisfy SecretsProvider structurally, without importing or subclassing it
This is the outbound direction only: services/db/api_key_service.py owns the keys clients present to us
"""

from typing import Optional, Protocol

ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
OPENAI_API_KEY = "OPENAI_API_KEY"


class SecretsProvider(Protocol):
    """
    Where a credential comes from

    get returns the value alone, so expiry can arrive as a sibling method rather than as a widening of this one
    """

    def get(self, name: str) -> Optional[str]:
        """The secret's value, or None when this backend does not hold it or it is unset"""
        ...
