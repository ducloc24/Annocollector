import os

# Tests use their own throwaway SQLite engine; this only keeps the app
# settings importable when the real Supabase credentials are absent.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.models  # noqa: E402, F401
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    await engine.dispose()
