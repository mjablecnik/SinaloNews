import os

# Must be set before any src imports since config.py creates Settings() at module level
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_db")

import pytest
import httpx
import respx

from src.services.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    return RateLimiter(delay_seconds=0.01)


@pytest.fixture
def mock_http_client():
    with respx.mock(assert_all_called=False) as mock:
        yield httpx.AsyncClient()
