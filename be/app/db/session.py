from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

engine_kwargs: dict = {"echo": settings.DB_ECHO, "pool_pre_ping": True}

if settings.is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
elif settings.is_supabase:
    # Supabase transaction pooler (Supavisor): pooling happens on the server,
    # and prepared statements are not supported across pooled connections.
    engine_kwargs.update(
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "ssl": "require" if settings.DB_SSL else False,
            "timeout": 15,
        },
    )
else:
    engine_kwargs.update(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )

engine = create_async_engine(settings.database_url, **engine_kwargs)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Request-scoped unit of work: commit on success, roll back on error."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
