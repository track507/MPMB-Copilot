from typing import List
import requests

class OllamaEmbeddingProvider:
    def __init__(self, model: str, base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.dimension = 0  # optionally set after first call

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        out = []
        for t in texts:
            r = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": t},
                timeout=60,
            )
            r.raise_for_status()
            emb = r.json()["embedding"]
            if not self.dimension:
                self.dimension = len(emb)
            out.append(emb)
        return out
