from collections.abc import Iterator
from typing import TYPE_CHECKING, List, Optional

from openai import OpenAI

if TYPE_CHECKING:
    from tiktoken import Encoding

from app.logger import get_logger

logger = get_logger(__name__)

MAX_INPUT_TOKENS = 8191
MAX_REQUEST_TOKENS = 300_000
MAX_REQUEST_INPUTS = 2048


class OpenAIEmbeddingProvider:
    def __init__(self, model: str, api_key: str):
        self.model = model
        self.client = OpenAI(api_key=api_key)
        self.dimension = 0
        self._encoding: Optional["Encoding"] = None

    def _encoder(self) -> "Encoding":
        if self._encoding is None:
            import tiktoken

            try:
                self._encoding = tiktoken.encoding_for_model(self.model)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return self._encoding

    def _fit(self, text: str) -> tuple[str, int]:
        """The text cut to the per-input token limit, and its token count"""
        tokens = self._encoder().encode(text)
        if len(tokens) <= MAX_INPUT_TOKENS:
            return text, len(tokens)
        logger.warning(f"Truncated an embedding input from {len(tokens)} to {MAX_INPUT_TOKENS} tokens")
        return self._encoder().decode(tokens[:MAX_INPUT_TOKENS]), MAX_INPUT_TOKENS

    def _requests(self, texts: List[str]) -> Iterator[List[str]]:
        """Inputs grouped under the per-request input and token limits, order preserved"""
        batch: List[str] = []
        budget = 0
        for text in texts:
            fitted, count = self._fit(text)
            if batch and (len(batch) == MAX_REQUEST_INPUTS or budget + count > MAX_REQUEST_TOKENS):
                yield batch
                batch, budget = [], 0
            batch.append(fitted)
            budget += count
        if batch:
            yield batch

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for request in self._requests(texts):
            resp = self.client.embeddings.create(model=self.model, input=request)
            vectors.extend(d.embedding for d in resp.data)
        if vectors and not self.dimension:
            self.dimension = len(vectors[0])
        return vectors
