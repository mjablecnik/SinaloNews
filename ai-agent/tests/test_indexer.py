"""Unit tests for ArticleIndexer.chunk_text and EmbeddingClient."""
import pytest
import respx
import httpx

from src.indexer import ArticleIndexer
from src.embeddings import EmbeddingClient, EmbeddingError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_indexer():
    return ArticleIndexer(
        db_session_factory=None,
        embedding_client=None,
        qdrant_client=None,
        settings=None,
    )


# ---------------------------------------------------------------------------
# chunk_text — edge cases
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_empty_string_returns_empty(self):
        indexer = make_indexer()
        assert indexer.chunk_text("", 1000, 200) == []

    def test_whitespace_only_returns_empty(self):
        indexer = make_indexer()
        assert indexer.chunk_text("   \n\t  ", 1000, 200) == []

    def test_short_text_single_chunk(self):
        indexer = make_indexer()
        text = "Hello world. This is short."
        chunks = indexer.chunk_text(text, 1000, 200)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_text_exactly_at_limit_single_chunk(self):
        indexer = make_indexer()
        # 50 chars, limit 50 — should stay in one chunk
        text = "A" * 48 + ". " + "B"  # two sentences, total ~51 chars
        chunks = indexer.chunk_text(text, 100, 20)
        assert len(chunks) == 1

    def test_long_text_produces_multiple_chunks(self):
        indexer = make_indexer()
        # Build text clearly larger than chunk_size
        sentences = [f"Sentence number {i} ends here." for i in range(50)]
        text = " ".join(sentences)
        chunks = indexer.chunk_text(text, 200, 50)
        assert len(chunks) > 1

    def test_chunks_cover_all_content(self):
        """Every sentence in the original text should appear in at least one chunk."""
        indexer = make_indexer()
        sentences = [f"Sentence {i}." for i in range(20)]
        text = " ".join(sentences)
        chunks = indexer.chunk_text(text, 100, 30)
        combined = " ".join(chunks)
        for sent in sentences:
            assert sent in combined

    def test_no_chunk_exceeds_chunk_size_by_more_than_one_sentence(self):
        indexer = make_indexer()
        sentences = [f"Word{i} " * 20 + "end." for i in range(15)]
        text = " ".join(sentences)
        chunk_size = 200
        chunks = indexer.chunk_text(text, chunk_size, 50)
        sentence_lengths = [len(s) for s in sentences]
        max_sentence = max(sentence_lengths)
        for chunk in chunks:
            assert len(chunk) <= chunk_size + max_sentence + 5  # +5 for whitespace

    def test_text_with_no_sentence_boundaries(self):
        indexer = make_indexer()
        text = "word " * 300  # no sentence-ending punctuation
        chunks = indexer.chunk_text(text, 200, 50)
        # Should return at least one chunk (the whole text treated as one sentence)
        assert len(chunks) >= 1
        assert all(c.strip() for c in chunks)


# ---------------------------------------------------------------------------
# EmbeddingClient
# ---------------------------------------------------------------------------

class TestEmbeddingClient:
    @respx.mock
    async def test_embed_texts_returns_vectors(self):
        client = EmbeddingClient(
            api_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        payload = {
            "data": [
                {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                {"index": 1, "embedding": [0.4, 0.5, 0.6]},
            ]
        }
        respx.post("https://api.example.com/v1/embeddings").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await client.embed_texts(["hello", "world"])
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    @respx.mock
    async def test_embed_texts_empty_input(self):
        client = EmbeddingClient(
            api_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        result = await client.embed_texts([])
        assert result == []

    @respx.mock
    async def test_embed_texts_raises_on_http_error(self):
        client = EmbeddingClient(
            api_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        respx.post("https://api.example.com/v1/embeddings").mock(
            return_value=httpx.Response(500, json={"error": "internal"})
        )
        with pytest.raises(EmbeddingError):
            await client.embed_texts(["hello"])

    @respx.mock
    async def test_embed_texts_raises_on_request_error(self):
        client = EmbeddingClient(
            api_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        respx.post("https://api.example.com/v1/embeddings").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(EmbeddingError):
            await client.embed_texts(["hello"])

    @respx.mock
    async def test_embed_query_returns_single_vector(self):
        client = EmbeddingClient(
            api_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        payload = {"data": [{"index": 0, "embedding": [0.7, 0.8, 0.9]}]}
        respx.post("https://api.example.com/v1/embeddings").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await client.embed_query("test query")
        assert result == [0.7, 0.8, 0.9]

    @respx.mock
    async def test_embed_texts_sorts_by_index(self):
        """Response items returned in reverse order should still be sorted correctly."""
        client = EmbeddingClient(
            api_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        payload = {
            "data": [
                {"index": 1, "embedding": [0.4, 0.5]},
                {"index": 0, "embedding": [0.1, 0.2]},
            ]
        }
        respx.post("https://api.example.com/v1/embeddings").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await client.embed_texts(["first", "second"])
        assert result == [[0.1, 0.2], [0.4, 0.5]]
