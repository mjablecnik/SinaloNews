"""Unit tests for RAGPipeline."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.rag import RAGPipeline, _parse_datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_settings(top_k=5, max_chunks_per_article=2, collection="test_chunks"):
    s = MagicMock()
    s.RAG_TOP_K = top_k
    s.RAG_MAX_CHUNKS_PER_ARTICLE = max_chunks_per_article
    s.QDRANT_COLLECTION = collection
    return s


def make_hit(article_id, score, chunk_text="chunk", published_at=None):
    hit = MagicMock()
    hit.score = score
    hit.payload = {
        "article_id": article_id,
        "chunk_text": chunk_text,
        "article_title": f"Title {article_id}",
        "article_url": f"http://example.com/{article_id}",
        "published_at": published_at,
    }
    return hit


def make_qdrant(search_results=None, collection_names=None):
    client = MagicMock()
    # query_points returns an object with a .points list
    points = search_results or []
    client.query_points = AsyncMock(return_value=SimpleNamespace(points=points))
    # get_collections returns an object with a .collections list of items with .name
    cols = [SimpleNamespace(name=n) for n in (collection_names or [])]
    client.get_collections = AsyncMock(return_value=SimpleNamespace(collections=cols))
    client.create_collection = AsyncMock()
    return client


def make_embedding_client(vector=None):
    client = MagicMock()
    client.embed_query = AsyncMock(return_value=vector or [0.1, 0.2, 0.3])
    return client


def make_pipeline(search_results=None, collection_names=None, top_k=5, max_chunks=2):
    settings = make_settings(top_k=top_k, max_chunks_per_article=max_chunks)
    embedding_client = make_embedding_client()
    qdrant_client = make_qdrant(search_results=search_results, collection_names=collection_names)
    return RAGPipeline(embedding_client, qdrant_client, settings), qdrant_client, embedding_client


# ---------------------------------------------------------------------------
# _parse_datetime
# ---------------------------------------------------------------------------

class TestParseDatetime:
    def test_none_returns_none(self):
        assert _parse_datetime(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_datetime("") is None

    def test_valid_iso_string(self):
        dt = _parse_datetime("2024-01-15T12:00:00+00:00")
        assert isinstance(dt, datetime)
        assert dt.year == 2024

    def test_invalid_string_returns_none(self):
        assert _parse_datetime("not-a-date") is None


# ---------------------------------------------------------------------------
# ensure_collection
# ---------------------------------------------------------------------------

class TestEnsureCollection:
    async def test_creates_collection_when_missing(self):
        pipeline, qdrant, _ = make_pipeline(collection_names=["other_collection"])
        await pipeline.ensure_collection(vector_size=1536)
        qdrant.create_collection.assert_called_once()
        call_kwargs = qdrant.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_chunks"
        assert call_kwargs["vectors_config"].size == 1536

    async def test_skips_creation_when_exists(self):
        pipeline, qdrant, _ = make_pipeline(collection_names=["test_chunks"])
        await pipeline.ensure_collection(vector_size=1536)
        qdrant.create_collection.assert_not_called()

    async def test_uses_cosine_distance(self):
        from qdrant_client.models import Distance

        pipeline, qdrant, _ = make_pipeline(collection_names=[])
        await pipeline.ensure_collection(vector_size=768)
        call_kwargs = qdrant.create_collection.call_args.kwargs
        assert call_kwargs["vectors_config"].distance == Distance.COSINE


# ---------------------------------------------------------------------------
# retrieve — basic behaviour
# ---------------------------------------------------------------------------

class TestRetrieve:
    async def test_returns_retrieved_chunks(self):
        hits = [make_hit(1, 0.9, "chunk text")]
        pipeline, qdrant, embedding = make_pipeline(search_results=hits)
        results = await pipeline.retrieve("test query")
        assert len(results) == 1
        assert results[0].article_id == 1
        assert results[0].chunk_text == "chunk text"
        assert results[0].score == 0.9

    async def test_embeds_query(self):
        pipeline, qdrant, embedding = make_pipeline(search_results=[])
        await pipeline.retrieve("my query")
        embedding.embed_query.assert_called_once_with("my query")

    async def test_searches_correct_collection(self):
        pipeline, qdrant, _ = make_pipeline(search_results=[])
        await pipeline.retrieve("q")
        call_kwargs = qdrant.query_points.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_chunks"

    async def test_empty_results(self):
        pipeline, _, _ = make_pipeline(search_results=[])
        results = await pipeline.retrieve("q")
        assert results == []

    async def test_results_ordered_by_descending_score(self):
        hits = [
            make_hit(1, 0.95),
            make_hit(2, 0.80),
            make_hit(3, 0.70),
        ]
        pipeline, _, _ = make_pipeline(search_results=hits, top_k=5, max_chunks=3)
        results = await pipeline.retrieve("q")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_parses_published_at(self):
        hits = [make_hit(1, 0.9, published_at="2024-03-10T08:00:00+00:00")]
        pipeline, _, _ = make_pipeline(search_results=hits)
        results = await pipeline.retrieve("q")
        assert results[0].published_at == datetime(2024, 3, 10, 8, 0, 0, tzinfo=timezone.utc)

    async def test_null_published_at(self):
        hits = [make_hit(1, 0.9, published_at=None)]
        pipeline, _, _ = make_pipeline(search_results=hits)
        results = await pipeline.retrieve("q")
        assert results[0].published_at is None


# ---------------------------------------------------------------------------
# retrieve — top-k
# ---------------------------------------------------------------------------

class TestTopK:
    async def test_respects_top_k(self):
        hits = [make_hit(i, 1.0 - i * 0.1) for i in range(10)]
        pipeline, _, _ = make_pipeline(search_results=hits, top_k=3, max_chunks=10)
        results = await pipeline.retrieve("q")
        assert len(results) <= 3

    async def test_returns_all_when_fewer_than_top_k(self):
        hits = [make_hit(i, 0.9) for i in range(2)]
        pipeline, _, _ = make_pipeline(search_results=hits, top_k=10, max_chunks=10)
        results = await pipeline.retrieve("q")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# retrieve — per-article deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    async def test_max_chunks_per_article(self):
        # 4 hits for article_id=1, cap is 2
        hits = [make_hit(1, 1.0 - i * 0.1) for i in range(4)]
        pipeline, _, _ = make_pipeline(search_results=hits, top_k=10, max_chunks=2)
        results = await pipeline.retrieve("q")
        assert len([r for r in results if r.article_id == 1]) == 2

    async def test_multiple_articles_respected(self):
        # 3 chunks for article 1, 3 for article 2, cap = 2 → expect 4 total
        hits = (
            [make_hit(1, 0.9 - i * 0.01) for i in range(3)]
            + [make_hit(2, 0.8 - i * 0.01) for i in range(3)]
        )
        pipeline, _, _ = make_pipeline(search_results=hits, top_k=10, max_chunks=2)
        results = await pipeline.retrieve("q")
        for aid in [1, 2]:
            assert len([r for r in results if r.article_id == aid]) <= 2


# ---------------------------------------------------------------------------
# retrieve — date filtering
# ---------------------------------------------------------------------------

class TestDateFiltering:
    async def test_no_filter_when_no_dates(self):
        pipeline, qdrant, _ = make_pipeline(search_results=[])
        await pipeline.retrieve("q")
        call_kwargs = qdrant.query_points.call_args.kwargs
        assert call_kwargs.get("query_filter") is None

    async def test_filter_applied_when_date_from(self):
        pipeline, qdrant, _ = make_pipeline(search_results=[])
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        await pipeline.retrieve("q", date_from=date_from)
        call_kwargs = qdrant.query_points.call_args.kwargs
        assert call_kwargs.get("query_filter") is not None

    async def test_filter_applied_when_date_to(self):
        pipeline, qdrant, _ = make_pipeline(search_results=[])
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        await pipeline.retrieve("q", date_to=date_to)
        call_kwargs = qdrant.query_points.call_args.kwargs
        assert call_kwargs.get("query_filter") is not None

    async def test_filter_applied_when_both_dates(self):
        pipeline, qdrant, _ = make_pipeline(search_results=[])
        date_from = datetime(2024, 1, 1, tzinfo=timezone.utc)
        date_to = datetime(2024, 12, 31, tzinfo=timezone.utc)
        await pipeline.retrieve("q", date_from=date_from, date_to=date_to)
        call_kwargs = qdrant.query_points.call_args.kwargs
        f = call_kwargs.get("query_filter")
        assert f is not None
        assert len(f.must) == 1
        cond = f.must[0]
        assert cond.key == "published_at"
