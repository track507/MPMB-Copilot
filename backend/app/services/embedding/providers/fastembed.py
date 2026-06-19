# app/services/embedding_providers/fastembed_embed.py
from typing import List

from fastembed import TextEmbedding

from app.config import config


class FastEmbedProvider:
    def __init__(self, model: str | None = None):
        # ? cap ONNX threads so bulk indexing does not saturate the machine
        threads = config.resolved_embedding_threads
        self.model = TextEmbedding(model_name=model, threads=threads) if model else TextEmbedding(threads=threads)
        self.dimension = 0

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        vectors = [v.tolist() for v in self.model.embed(texts)]
        if vectors and not self.dimension:
            self.dimension = len(vectors[0])
        return vectors
