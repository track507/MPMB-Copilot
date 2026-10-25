from types import SimpleNamespace

from app.services.embedding.providers import openai as openai_mod
from app.services.embedding.providers.openai import OpenAIEmbeddingProvider


class _OneTokenPerChar:
    def encode(self, text: str) -> list[str]:
        return list(text)

    def decode(self, tokens: list[str]) -> str:
        return "".join(tokens)


class _RecordingClient:
    def __init__(self) -> None:
        self.requests: list[list[str]] = []
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model: str, input: list[str]):
        self.requests.append(input)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[float(len(text))]) for text in input])


def _provider(monkeypatch, *, input_tokens: int, request_tokens: int, request_inputs: int = 2048):
    monkeypatch.setattr(openai_mod, "MAX_INPUT_TOKENS", input_tokens)
    monkeypatch.setattr(openai_mod, "MAX_REQUEST_TOKENS", request_tokens)
    monkeypatch.setattr(openai_mod, "MAX_REQUEST_INPUTS", request_inputs)
    provider = OpenAIEmbeddingProvider.__new__(OpenAIEmbeddingProvider)
    provider.model = "text-embedding-3-small"
    provider.dimension = 0
    provider._encoding = _OneTokenPerChar()
    provider.client = _RecordingClient()
    return provider


def test_an_oversized_input_is_cut_to_the_model_limit(monkeypatch):
    provider = _provider(monkeypatch, input_tokens=5, request_tokens=100)

    vectors = provider.embed_texts(["abcdefghij", "xy"])

    assert provider.client.requests == [["abcde", "xy"]]
    assert vectors == [[5.0], [2.0]]


def test_inputs_are_split_across_requests_under_the_token_budget_in_order(monkeypatch):
    provider = _provider(monkeypatch, input_tokens=10, request_tokens=6)

    vectors = provider.embed_texts(["aaa", "bbb", "cc", "dddd"])

    assert provider.client.requests == [["aaa", "bbb"], ["cc", "dddd"]]
    assert vectors == [[3.0], [3.0], [2.0], [4.0]]


def test_a_request_never_exceeds_the_input_count(monkeypatch):
    provider = _provider(monkeypatch, input_tokens=10, request_tokens=1000, request_inputs=2)

    provider.embed_texts(["a", "b", "c"])

    assert provider.client.requests == [["a", "b"], ["c"]]
