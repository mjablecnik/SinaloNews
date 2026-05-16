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
        # Truncate texts to avoid token limit (approx 30000 chars ≈ 8000 tokens)
        truncated = [t[:30000] if len(t) > 30000 else t for t in texts]
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self._api_url}/embeddings",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"model": self._model, "input": truncated},
                    timeout=60.0,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise EmbeddingError(f"Embedding API returned {e.response.status_code}: {e.response.text[:200]}") from e
            except httpx.RequestError as e:
                raise EmbeddingError(f"Embedding API request failed: {e}") from e
            data = response.json()
            if "data" not in data:
                error_msg = data.get("error", {}).get("message", str(data)[:200])
                raise EmbeddingError(f"Embedding API error: {error_msg}")
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]

    async def embed_text(self, text: str) -> list[float]:
        results = await self.embed_texts([text])
        return results[0]
