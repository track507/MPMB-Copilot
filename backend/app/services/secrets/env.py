"""
The env-backed adapter: the only module in the tree that reads a credential off config

Reading through config rather than os.environ keeps .env honoured, since config is pydantic-settings
"""

from typing import Optional

from app.config import config
from app.services.secrets.protocol import ANTHROPIC_API_KEY, OPENAI_API_KEY


class EnvSecretsProvider:
    """
    Resolves a secret name against the config fields loaded from the environment and .env
    """

    _FIELDS = {
        ANTHROPIC_API_KEY: "anthropic_api_key",
        OPENAI_API_KEY: "openai_api_key",
    }

    def get(self, name: str) -> Optional[str]:
        field = self._FIELDS.get(name)
        if field is None:
            return None
        value: Optional[str] = getattr(config, field, None)
        return value or None
