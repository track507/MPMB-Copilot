"""
Outbound provider credentials, reached through one port so a second backend replaces one module

Nothing outside this package reads a key off config, which tests/services/secrets/test_no_direct_key_reads.py enforces
"""

from app.services.secrets.env import EnvSecretsProvider
from app.services.secrets.protocol import ANTHROPIC_API_KEY, OPENAI_API_KEY, SecretsProvider

secrets_service: SecretsProvider = EnvSecretsProvider()

__all__ = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "EnvSecretsProvider",
    "SecretsProvider",
    "secrets_service",
]
