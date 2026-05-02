"""Smoke tests verifying service modules import and instantiate correctly."""
import asyncio
import time

import httpx
import pytest

from src.config import Settings
from src.data.models import Article, Feed, Website
from src.data.schemas import (
    ArticleDetailResponse,
    ArticleResponse,
    BatchSummaryResponse,
    FeedResponse,
    PaginatedResponse,
    WebsiteResponse,
)
from src.services.batch_service import BatchProcessor
from src.services.discovery_service import FeedDiscoveryService
from src.services.extractor_service import ArticleExtractorService
from src.services.parser_service import FeedParserService
from src.services.rate_limiter import RateLimiter


class TestSettings:
    def test_settings_loads_with_database_url(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
        s = Settings()
        assert s.DATABASE_URL == "postgresql+asyncpg://u:p@host/db"
        assert s.APP_HOST == "0.0.0.0"
        assert s.APP_PORT == 8000
        assert s.REQUEST_DELAY_SECONDS == 1.0
        assert s.REQUEST_TIMEOUT_SECONDS == 30

    def test_settings_accepts_custom_values(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
        monkeypatch.setenv("APP_PORT", "9000")
        monkeypatch.setenv("REQUEST_DELAY_SECONDS", "2.5")
        s = Settings()
        assert s.APP_PORT == 9000
        assert s.REQUEST_DELAY_SECONDS == 2.5


class TestRateLimiter:
    async def test_first_request_is_immediate(self):
        limiter = RateLimiter(delay_seconds=0.05)
        start = time.monotonic()
        await limiter.acquire("example.com")
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    async def test_second_request_is_delayed(self):
        limiter = RateLimiter(delay_seconds=0.05)
        await limiter.acquire("example.com")
        start = time.monotonic()
        await limiter.acquire("example.com")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.04

    async def test_different_domains_are_independent(self):
        limiter = RateLimiter(delay_seconds=0.1)
        await limiter.acquire("a.com")
        start = time.monotonic()
        await limiter.acquire("b.com")
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    async def test_notify_retry_after_delays_next_request(self):
        limiter = RateLimiter(delay_seconds=0.05)
        await limiter.acquire("example.com")
        await limiter.notify_retry_after("example.com", 0.1)
        start = time.monotonic()
        await limiter.acquire("example.com")
        elapsed = time.monotonic() - start
        assert elapsed >= 0.08


class TestServiceInstantiation:
    def test_rate_limiter_default(self):
        rl = RateLimiter()
        assert rl.delay_seconds == 1.0

    def test_rate_limiter_custom(self):
        rl = RateLimiter(delay_seconds=2.5)
        assert rl.delay_seconds == 2.5

    def test_discovery_service_instantiation(self):
        rl = RateLimiter()
        client = httpx.AsyncClient()
        svc = FeedDiscoveryService(http_client=client, rate_limiter=rl)
        assert svc.http_client is client
        assert svc.rate_limiter is rl

    def test_parser_service_instantiation(self):
        rl = RateLimiter()
        svc = FeedParserService(rate_limiter=rl)
        assert svc.rate_limiter is rl

    def test_extractor_service_instantiation(self):
        rl = RateLimiter()
        client = httpx.AsyncClient()
        svc = ArticleExtractorService(http_client=client, rate_limiter=rl)
        assert svc.http_client is client
        assert svc.rate_limiter is rl

    def test_batch_processor_instantiation(self):
        rl = RateLimiter()
        client = httpx.AsyncClient()
        parser = FeedParserService(rate_limiter=rl)
        extractor = ArticleExtractorService(http_client=client, rate_limiter=rl)
        batch = BatchProcessor(parser_service=parser, extractor_service=extractor)
        assert batch.parser_service is parser
        assert batch.extractor_service is extractor


class TestOrmModels:
    def test_website_model_has_required_columns(self):
        cols = {c.name for c in Website.__table__.columns}
        assert {"id", "name", "url", "domain", "created_at", "updated_at",
                "last_discovery_at", "discovery_status"}.issubset(cols)

    def test_feed_model_has_required_columns(self):
        cols = {c.name for c in Feed.__table__.columns}
        assert {"id", "website_id", "feed_url", "title", "feed_type",
                "created_at", "last_parsed_at"}.issubset(cols)

    def test_article_model_has_required_columns(self):
        cols = {c.name for c in Article.__table__.columns}
        assert {"id", "feed_id", "url", "title", "author", "published_at",
                "summary", "original_html", "extracted_text", "status",
                "feedparser_raw_entry", "created_at", "updated_at"}.issubset(cols)

    def test_website_discovery_status_default(self):
        col = Website.__table__.columns["discovery_status"]
        assert col.default.arg == "pending"

    def test_article_status_default(self):
        col = Article.__table__.columns["status"]
        assert col.default.arg == "pending"

    def test_feed_website_foreign_key(self):
        fk = list(Feed.__table__.columns["website_id"].foreign_keys)[0]
        assert "website" in fk.target_fullname

    def test_article_feed_foreign_key(self):
        fk = list(Article.__table__.columns["feed_id"].foreign_keys)[0]
        assert "feed" in fk.target_fullname

    def test_website_unique_constraints(self):
        constraints = {c.name for c in Website.__table__.constraints if hasattr(c, "columns")}
        col_sets = [
            {col.name for col in c.columns}
            for c in Website.__table__.constraints
            if hasattr(c, "columns")
        ]
        assert {"name"} in col_sets or any("name" in s for s in col_sets)
        assert {"url"} in col_sets or any("url" in s for s in col_sets)

    def test_feed_unique_constraint_on_website_and_url(self):
        col_sets = [
            frozenset(col.name for col in c.columns)
            for c in Feed.__table__.constraints
            if hasattr(c, "columns")
        ]
        assert frozenset({"website_id", "feed_url"}) in col_sets

    def test_article_unique_constraint_on_feed_and_url(self):
        col_sets = [
            frozenset(col.name for col in c.columns)
            for c in Article.__table__.constraints
            if hasattr(c, "columns")
        ]
        assert frozenset({"feed_id", "url"}) in col_sets


class TestPydanticSchemas:
    def test_website_response_schema(self):
        data = {
            "id": 1, "name": "Test", "url": "https://example.com",
            "domain": "example.com", "created_at": "2024-01-01T00:00:00",
            "discovery_status": "pending",
        }
        r = WebsiteResponse(**data)
        assert r.id == 1
        assert r.name == "Test"

    def test_feed_response_schema(self):
        data = {
            "id": 1, "website_id": 1, "feed_url": "https://example.com/feed",
            "title": None, "feed_type": "rss", "last_parsed_at": None,
        }
        r = FeedResponse(**data)
        assert r.feed_url == "https://example.com/feed"

    def test_article_response_schema(self):
        data = {
            "id": 1, "feed_id": 1, "url": "https://example.com/article",
            "title": "Test", "author": None, "published_at": None,
            "status": "pending",
        }
        r = ArticleResponse(**data)
        assert r.status == "pending"

    def test_article_detail_extends_article_response(self):
        assert issubclass(ArticleDetailResponse, ArticleResponse)

    def test_batch_summary_response_schema(self):
        data = {
            "feeds_parsed": 2, "articles_discovered": 10,
            "articles_extracted": 8, "errors": ["err1"],
        }
        r = BatchSummaryResponse(**data)
        assert r.feeds_parsed == 2
        assert r.articles_extracted == 8

    def test_paginated_response_is_generic(self):
        from src.data.schemas import PaginatedResponse
        import typing
        assert hasattr(PaginatedResponse, "__class_getitem__")
