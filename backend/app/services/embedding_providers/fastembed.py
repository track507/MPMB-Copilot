# app/services/embedding_providers/fastembed_embed.py
from typing import List
from fastembed import TextEmbedding

class FastEmbedProvider:
    def __init__(self, model: str | None = None):
        # model can be None to use FastEmbed defaults
        self.model = TextEmbedding(model_name=model) if model else TextEmbedding()
        self.dimension = 0

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        vectors = [v.tolist() for v in self.model.embed(texts)]
        if vectors and not self.dimension:
            self.dimension = len(vectors[0])
        return vectors
