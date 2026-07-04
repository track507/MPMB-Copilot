"""
Programmatic Alembic runner - upgrades to head at startup (path-anchored, cwd-independent)
"""

from pathlib import Path

from app.logger import get_logger

logger = get_logger(__name__)

# backend/app/services/db/migrations.py -> parents[3] = backend/
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def run_migrations() -> None:
    from alembic.config import Config as AlembicConfig

    from alembic import command
    from app.config import config

    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", config.resolved_database_url)
    command.upgrade(cfg, "head")
    logger.info("alembic_upgraded_to_head")
