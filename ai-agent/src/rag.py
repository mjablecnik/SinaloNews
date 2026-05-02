from datetime import datetime

import structlog
from qdrant_client.models import Distance, FieldCondition, Filter, VectorParams

from src.embeddings import EmbeddingClient
from src.schemas import RetrievedChunk

log = structlog.get_logger()


class RAGPipeline:
    def __init__(
        self,
        embedding_client: EmbeddingClient,
        qdrant_client,
        settings,
    ) -> None:
        self._embedding_client = embedding_client
        self._qdrant_client = qdrant_client
        self._settings = settings

    async def ensure_collection(self, vector_size: int) -> None:
        """Create the Qdrant collection if it doesn't already exist."""
        collections = await self._qdrant_client.get_collections()
        existing_names = {c.name for c in collections.collections}
        if self._settings.QDRANT_COLLECTION not in existing_names:
            await self._qdrant_client.create_collection(
                collection_name=self._settings.QDRANT_COLLECTION,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
            log.info(
                "qdrant_collection_created",
                collection=self._settings.QDRANT_COLLECTION,
                vector_size=vector_size,
            )

    async def retrieve(
        self,
        query: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[RetrievedChunk]:
        query_vector = await self._embedding_client.embed_query(query)

        search_filter: Filter | None = None
        if date_from is not None or date_to is not None:
            from qdrant_client.models import DatetimeRange

            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="published_at",
                        range=DatetimeRange(
                            gte=date_from.isoformat() if date_from else None,
                            lte=date_to.isoformat() if date_to else None,
                        ),
                    )
                ]
            )

        # Fetch enough results to apply per-article deduplication before top-k
        search_limit = self._settings.RAG_TOP_K * self._settings.RAG_MAX_CHUNKS_PER_ARTICLE

        response = await self._qdrant_client.query_points(
            collection_name=self._settings.QDRANT_COLLECTION,
            query=query_vector,
            query_filter=search_filter,
            limit=search_limit,
            with_payload=True,
        )

        article_chunk_counts: dict[int, int] = {}
        chunks: list[RetrievedChunk] = []

        for point in response.points:
            if len(chunks) >= self._settings.RAG_TOP_K:
                break

            payload = point.payload or {}
            article_id = payload.get("article_id")

            count = article_chunk_counts.get(article_id, 0)
            if count >= self._settings.RAG_MAX_CHUNKS_PER_ARTICLE:
                continue

            chunks.append(
                RetrievedChunk(
                    chunk_text=payload.get("chunk_text", ""),
                    article_id=article_id,
                    article_title=payload.get("article_title", ""),
                    article_url=payload.get("article_url", ""),
                    published_at=_parse_datetime(payload.get("published_at")),
                    score=point.score,
                )
            )
            article_chunk_counts[article_id] = count + 1

        return chunks


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
