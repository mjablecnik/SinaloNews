import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, Filter, HasIdCondition, PointStruct, VectorParams

_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


class SimilarityService:
    def __init__(self, qdrant_client: AsyncQdrantClient, settings) -> None:
        self._client = qdrant_client
        self._collection = settings.QDRANT_FULL_ARTICLE_COLLECTION

    async def ensure_collection(self, vector_size: int = 1536) -> None:
        collections = await self._client.get_collections()
        names = {c.name for c in collections.collections}
        if self._collection not in names:
            await self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    async def upsert_article(
        self,
        article_id: int,
        vector: list[float],
        metadata: dict,
    ) -> None:
        point_id = self.make_point_id(article_id)
        await self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=point_id, vector=vector, payload=metadata)],
        )

    async def find_most_similar(
        self,
        article_id: int,
        vector: list[float],
        exclude_ids: list[int] | None = None,
    ) -> tuple[int, float] | None:
        all_excluded = list(exclude_ids or []) + [article_id]
        exclude_point_ids = [self.make_point_id(aid) for aid in all_excluded]

        results = await self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            query_filter=Filter(must_not=[HasIdCondition(has_id=exclude_point_ids)]),
            limit=1,
            with_payload=True,
        )

        if not results:
            return None

        best = results[0]
        matched_article_id = best.payload["article_id"]
        return (matched_article_id, best.score)

    @staticmethod
    def make_point_id(article_id: int) -> str:
        return str(uuid.uuid5(_NAMESPACE, str(article_id)))
