from typing import List

class SBERTProvider:
    def __init__(self, model: str):
        self.model_name = model
        self.dimension = 0
        self._model = None

    def _load(self):
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed, but embedding_backend='sbert' was selected. "
                "Install it (and its deps) or switch embedding_backend."
            ) from e

        self._model = SentenceTransformer(self.model_name)
        self.dimension = int(self._model.get_sentence_embedding_dimension())

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        self._load()
        # keep output format consistent: List[List[float]]
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()
