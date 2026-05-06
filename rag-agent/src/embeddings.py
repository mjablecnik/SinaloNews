import httpx


class EmbeddingError(Exception):
    pass


class EmbeddingClient:
    def __init__(self, api_url: str, api_key: str, model: str) -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self._api_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": texts},
                    timeout=60.0,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise EmbeddingError(f"Embedding API returned {e.response.status_code}") from e
            except httpx.RequestError as e:
                raise EmbeddingError(f"Embedding API request failed: {e}") from e
            data = response.json()
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_texts([text])
        return results[0]
