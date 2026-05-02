import re
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.embeddings import EmbeddingClient, EmbeddingError
from src.models import Article, IndexedArticle
from src.schemas import IndexingResult

log = structlog.get_logger()

_CHUNK_UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class ArticleIndexer:
    def __init__(
        self,
        db_session_factory: async_sessionmaker,
        embedding_client: EmbeddingClient,
        qdrant_client,
        settings,
    ) -> None:
        self._session_factory = db_session_factory
        self._embedding_client = embedding_client
        self._qdrant_client = qdrant_client
        self._settings = settings

    def chunk_text(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        """Split text into overlapping chunks at sentence boundaries."""
        if not text.strip():
            return []

        sentences = _SENTENCE_SPLIT.split(text.strip())
        sentences = [s for s in sentences if s]

        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if current and len(current) + 1 + len(sentence) > chunk_size:
                chunks.append(current.strip())
                # Begin next chunk with the overlap tail of the finished chunk
                tail = current[-overlap:] if len(current) > overlap else current
                current = tail + " " + sentence
            else:
                current = (current + " " + sentence) if current else sentence

        if current.strip():
            chunks.append(current.strip())

        return chunks

    async def index_articles(self, full_sync: bool = False) -> IndexingResult:
        articles_processed = 0
        chunks_created = 0
        errors: list[str] = []

        async with self._session_factory() as session:
            query = select(Article).where(Article.status == "extracted")
            if not full_sync:
                already_indexed = select(IndexedArticle.article_id)
                query = query.where(Article.id.not_in(already_indexed))
            result = await session.execute(query)
            articles = result.scalars().all()

        for article in articles:
            try:
                text = article.extracted_text or ""
                chunks = self.chunk_text(text, self._settings.CHUNK_SIZE, self._settings.CHUNK_OVERLAP)
                if not chunks:
                    chunks = [text] if text else ["(no content)"]

                embeddings = await self._embedding_client.embed_texts(chunks)

                from qdrant_client.models import PointStruct

                now_iso = datetime.now(timezone.utc).isoformat()
                published_iso = article.published_at.isoformat() if article.published_at else None

                points = [
                    PointStruct(
                        id=str(uuid.uuid5(_CHUNK_UUID_NAMESPACE, f"{article.id}:{i}")),
                        vector=embedding,
                        payload={
                            "article_id": article.id,
                            "chunk_index": i,
                            "chunk_text": chunk,
                            "article_title": article.title or "",
                            "article_url": article.url or "",
                            "published_at": published_iso,
                            "indexed_at": now_iso,
                        },
                    )
                    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
                ]

                await self._qdrant_client.upsert(
                    collection_name=self._settings.QDRANT_COLLECTION,
                    points=points,
                )

                async with self._session_factory() as session:
                    existing = await session.get(IndexedArticle, article.id)
                    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
                    if existing:
                        existing.indexed_at = now_naive
                        existing.chunk_count = len(chunks)
                    else:
                        session.add(
                            IndexedArticle(
                                article_id=article.id,
                                indexed_at=now_naive,
                                chunk_count=len(chunks),
                            )
                        )
                    await session.commit()

                articles_processed += 1
                chunks_created += len(chunks)
                log.info("article_indexed", article_id=article.id, chunks=len(chunks))

            except EmbeddingError as e:
                log.error("embedding_failed", article_id=article.id, error=str(e))
                errors.append(f"article {article.id}: {e}")
            except Exception as e:
                log.error("indexing_failed", article_id=article.id, error=str(e))
                errors.append(f"article {article.id}: {e}")

        return IndexingResult(
            articles_processed=articles_processed,
            chunks_created=chunks_created,
            errors=errors,
        )
