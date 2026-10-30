import os

# Tests never touch a database. This only keeps the app settings importable when
# the real Supabase credentials are absent; no engine connection is ever opened.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")
os.environ["BACKGROUND_TASKS"] = "false"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
