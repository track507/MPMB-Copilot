"""
Which credential each generation provider needs

Lives beside the provider switch rather than in the secrets service, so the secrets port stays free of vendor knowledge
Its own module because providers.py already imports catalog.py, and both need this
"""

from typing import Optional

from app.services.secrets import ANTHROPIC_API_KEY, OPENAI_API_KEY, secrets_service

_PROVIDER_KEYS = {
    "anthropic": ANTHROPIC_API_KEY,
    "openai": OPENAI_API_KEY,
}


def api_key_for(provider: str) -> Optional[str]:
    """
    The credential a generation provider needs, or None when it needs none or has none configured

    A caller cannot tell those two apart, which is correct: both mean there is no key to send
    """
    name = _PROVIDER_KEYS.get(provider)
    return None if name is None else secrets_service.get(name)
