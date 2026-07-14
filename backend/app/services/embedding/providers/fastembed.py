from fastembed import TextEmbedding

from app.config import config
from app.core.onnx_device import onnx_providers


class FastEmbedProvider:
    def __init__(self, model: str | None = None):
        # ? cap ONNX threads so bulk indexing does not saturate the machine
        kwargs: dict = {
            "threads": config.resolved_embedding_threads,
            "cache_dir": str(config.fastembed_cache_path),
        }
        providers = onnx_providers()
        if providers is not None:
            kwargs["providers"] = providers
        self.model = TextEmbedding(model_name=model, **kwargs) if model else TextEmbedding(**kwargs)
        self.dimension = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = [v.tolist() for v in self.model.embed(texts)]
        if vectors and not self.dimension:
            self.dimension = len(vectors[0])
        return vectors
