from typing import Any, cast

import httpx


class OllamaEmbeddingProvider:
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.dimension = 0  # optionally set after first call

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        with httpx.Client(base_url=self.base_url, timeout=60.0) as client:
            for text in texts:
                response = client.post("/api/embeddings", json={"model": self.model, "prompt": text})
                response.raise_for_status()
                payload = cast(dict[str, Any], response.json())
                embedding = cast(list[float], payload["embedding"])
                if not self.dimension:
                    self.dimension = len(embedding)
                out.append(embedding)
        return out
