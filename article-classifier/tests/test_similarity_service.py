import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client.models import ScoredPoint

from src.similarity_service import SimilarityService, _NAMESPACE


def make_settings(collection="article_full"):
    s = MagicMock()
    s.QDRANT_FULL_ARTICLE_COLLECTION = collection
    return s


def make_service(qdrant_client=None, collection="article_full"):
    client = qdrant_client or AsyncMock()
    return SimilarityService(client, make_settings(collection))


# --- make_point_id ---


def test_make_point_id_is_deterministic():
    id1 = SimilarityService.make_point_id(42)
    id2 = SimilarityService.make_point_id(42)
    assert id1 == id2


def test_make_point_id_differs_for_different_articles():
    assert SimilarityService.make_point_id(1) != SimilarityService.make_point_id(2)


def test_make_point_id_is_valid_uuid():
    result = SimilarityService.make_point_id(99)
    parsed = uuid.UUID(result)
    assert str(parsed) == result


def test_make_point_id_uses_fixed_namespace():
    expected = str(uuid.uuid5(_NAMESPACE, "42"))
    assert SimilarityService.make_point_id(42) == expected


# --- ensure_collection ---


@pytest.mark.asyncio
async def test_ensure_collection_creates_when_missing():
    mock_client = AsyncMock()
    mock_client.get_collections.return_value = MagicMock(collections=[])
    svc = make_service(mock_client, collection="article_full")

    await svc.ensure_collection(vector_size=1536)

    mock_client.create_collection.assert_called_once()
    call_kwargs = mock_client.create_collection.call_args.kwargs
    assert call_kwargs["collection_name"] == "article_full"


@pytest.mark.asyncio
async def test_ensure_collection_skips_if_already_exists():
    mock_client = AsyncMock()
    existing = MagicMock()
    existing.name = "article_full"
    mock_client.get_collections.return_value = MagicMock(collections=[existing])
    svc = make_service(mock_client, collection="article_full")

    await svc.ensure_collection()

    mock_client.create_collection.assert_not_called()


# --- upsert_article ---


@pytest.mark.asyncio
async def test_upsert_article_calls_upsert_with_correct_id():
    mock_client = AsyncMock()
    svc = make_service(mock_client)
    vector = [0.1, 0.2, 0.3]
    metadata = {"article_id": 7, "article_title": "Test"}

    await svc.upsert_article(7, vector, metadata)

    mock_client.upsert.assert_called_once()
    call_kwargs = mock_client.upsert.call_args.kwargs
    assert call_kwargs["collection_name"] == "article_full"
    points = call_kwargs["points"]
    assert len(points) == 1
    assert points[0].id == SimilarityService.make_point_id(7)
    assert points[0].vector == vector
    assert points[0].payload == metadata


@pytest.mark.asyncio
async def test_upsert_article_uses_deterministic_id():
    mock_client = AsyncMock()
    svc = make_service(mock_client)

    await svc.upsert_article(42, [0.5], {})
    first_id = mock_client.upsert.call_args.kwargs["points"][0].id

    mock_client.reset_mock()
    await svc.upsert_article(42, [0.5], {})
    second_id = mock_client.upsert.call_args.kwargs["points"][0].id

    assert first_id == second_id


# --- find_most_similar ---


def _make_scored_point(article_id: int, score: float) -> ScoredPoint:
    point = MagicMock(spec=ScoredPoint)
    point.payload = {"article_id": article_id}
    point.score = score
    return point


@pytest.mark.asyncio
async def test_find_most_similar_returns_best_match():
    mock_client = AsyncMock()
    mock_client.search.return_value = [_make_scored_point(10, 0.92)]
    svc = make_service(mock_client)

    result = await svc.find_most_similar(1, [0.1, 0.2])

    assert result == (10, 0.92)


@pytest.mark.asyncio
async def test_find_most_similar_returns_none_when_no_results():
    mock_client = AsyncMock()
    mock_client.search.return_value = []
    svc = make_service(mock_client)

    result = await svc.find_most_similar(1, [0.1, 0.2])

    assert result is None


@pytest.mark.asyncio
async def test_find_most_similar_excludes_self():
    mock_client = AsyncMock()
    mock_client.search.return_value = []
    svc = make_service(mock_client)

    await svc.find_most_similar(article_id=5, vector=[0.1])

    call_kwargs = mock_client.search.call_args.kwargs
    query_filter = call_kwargs["query_filter"]
    excluded_ids = query_filter.must_not[0].has_id
    self_point_id = SimilarityService.make_point_id(5)
    assert self_point_id in excluded_ids


@pytest.mark.asyncio
async def test_find_most_similar_excludes_additional_ids():
    mock_client = AsyncMock()
    mock_client.search.return_value = []
    svc = make_service(mock_client)

    await svc.find_most_similar(article_id=5, vector=[0.1], exclude_ids=[3, 4])

    call_kwargs = mock_client.search.call_args.kwargs
    excluded_ids = call_kwargs["query_filter"].must_not[0].has_id
    assert SimilarityService.make_point_id(3) in excluded_ids
    assert SimilarityService.make_point_id(4) in excluded_ids
    assert SimilarityService.make_point_id(5) in excluded_ids


@pytest.mark.asyncio
async def test_find_most_similar_queries_correct_collection():
    mock_client = AsyncMock()
    mock_client.search.return_value = []
    svc = make_service(mock_client, collection="my_collection")

    await svc.find_most_similar(1, [0.0])

    assert mock_client.search.call_args.kwargs["collection_name"] == "my_collection"


@pytest.mark.asyncio
async def test_find_most_similar_limit_is_one():
    mock_client = AsyncMock()
    mock_client.search.return_value = []
    svc = make_service(mock_client)

    await svc.find_most_similar(1, [0.0])

    assert mock_client.search.call_args.kwargs["limit"] == 1
