from typing import Any, List, cast


class SBERTProvider:
    def __init__(self, model: str):
        self.model_name = model
        self.dimension = 0
        # ? Any because sentence_transformers is an optional extra and may not be importable
        self._model: Any = None

    def _load(self):
        if self._model is not None:
            return

        try:
            # ? Optional extra: absent unless installed with uv sync --extra sbert
            from sentence_transformers import SentenceTransformer  # ty: ignore[unresolved-import]
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is not installed, but embedding_backend='sbert' was selected. "
                "Install the optional extra (uv sync --extra sbert) or switch embedding_backend."
            ) from e

        self._model = SentenceTransformer(self.model_name)

        # ! sentence-transformers 6 renamed this accessor, and the old name still works but warns
        # ! get_embedding_dimension returns None when no dimension can be inferred, which int() rejects
        dimension = self._model.get_embedding_dimension()
        if dimension is None:
            raise RuntimeError(f"sentence-transformers could not report an embedding dimension for {self.model_name}")
        self.dimension = int(dimension)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        self._load()
        # keep output format consistent: List[List[float]]
        embeddings = self._model.encode(texts, convert_to_numpy=True)
        return cast(List[List[float]], embeddings.tolist())
