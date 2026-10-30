import logging
import sys

from app.core.config import settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging() -> None:
    """Configure root logging once, at application startup."""
    level = settings.LOG_LEVEL.upper()
    logging.basicConfig(level=level, format=LOG_FORMAT, stream=sys.stdout, force=True)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
