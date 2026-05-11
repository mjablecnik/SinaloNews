import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from src.embedding_client import EmbeddingClient, EmbeddingError


def make_client():
    return EmbeddingClient(
        api_url="https://api.example.com/v1",
        api_key="test-key",
        model="openai/text-embedding-3-small",
    )


def make_api_response(embeddings: list[list[float]]) -> dict:
    return {
        "data": [
            {"index": i, "embedding": emb}
            for i, emb in enumerate(embeddings)
        ]
    }


@pytest.mark.asyncio
async def test_embed_texts_single():
    client = make_client()
    vector = [0.1, 0.2, 0.3]
    mock_response = MagicMock()
    mock_response.json.return_value = make_api_response([vector])
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.embed_texts(["hello world"])

    assert result == [vector]
    mock_http.post.assert_called_once()
    call_kwargs = mock_http.post.call_args
    assert call_kwargs.kwargs["json"]["input"] == ["hello world"]
    assert call_kwargs.kwargs["json"]["model"] == "openai/text-embedding-3-small"
    assert "Bearer test-key" in call_kwargs.kwargs["headers"]["Authorization"]


@pytest.mark.asyncio
async def test_embed_texts_multiple_sorted_by_index():
    client = make_client()
    vec_a = [0.1, 0.2]
    vec_b = [0.3, 0.4]
    mock_response = MagicMock()
    # Return in reverse order to verify sorting
    mock_response.json.return_value = {
        "data": [
            {"index": 1, "embedding": vec_b},
            {"index": 0, "embedding": vec_a},
        ]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.embed_texts(["first", "second"])

    assert result == [vec_a, vec_b]


@pytest.mark.asyncio
async def test_embed_texts_empty_returns_empty():
    client = make_client()
    result = await client.embed_texts([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_text_delegates_to_embed_texts():
    client = make_client()
    vector = [0.5, 0.6, 0.7]
    mock_response = MagicMock()
    mock_response.json.return_value = make_api_response([vector])
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.embed_text("single text")

    assert result == vector


@pytest.mark.asyncio
async def test_embed_texts_http_error_raises_embedding_error():
    client = make_client()

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=MagicMock(), response=mock_response
            )
        )
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(EmbeddingError, match="401"):
            await client.embed_texts(["text"])


@pytest.mark.asyncio
async def test_embed_texts_request_error_raises_embedding_error():
    client = make_client()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(
            side_effect=httpx.RequestError("connection refused", request=MagicMock())
        )
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(EmbeddingError, match="request failed"):
            await client.embed_texts(["text"])


@pytest.mark.asyncio
async def test_embed_texts_url_has_correct_endpoint():
    client = EmbeddingClient(
        api_url="https://openrouter.ai/api/v1/",  # trailing slash
        api_key="key",
        model="model",
    )
    mock_response = MagicMock()
    mock_response.json.return_value = make_api_response([[0.1]])
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await client.embed_texts(["text"])

    called_url = mock_http.post.call_args.args[0]
    assert called_url == "https://openrouter.ai/api/v1/embeddings"
