# app/services/embedding_providers/openai_embed.py
from typing import List

from openai import OpenAI


class OpenAIEmbeddingProvider:
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.client = OpenAI(api_key=api_key)
        self.dimension = 0

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        resp = self.client.embeddings.create(model=self.model, input=texts)
        vectors = [d.embedding for d in resp.data]
        if vectors and not self.dimension:
            self.dimension = len(vectors[0])
        return vectors
