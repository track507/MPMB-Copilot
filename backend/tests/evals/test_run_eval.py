from types import SimpleNamespace

from app.core.catalog import EMPTY_CATALOG
from app.core.storage_keys import DEFAULT_TENANT_ID


async def test_a_config_pass_retrieves_every_case_as_the_shared_corpus(monkeypatch):
    from evals import run_eval

    calls: list[dict] = []

    async def retrieve(query, edition=None, intent_override=None, *, tenant_id, catalog):
        calls.append({"query": query, "edition": edition, "tenant_id": tenant_id, "catalog": catalog})
        return SimpleNamespace(authoritative=[], examples=[])

    monkeypatch.setattr(run_eval, "get_retriever", lambda: SimpleNamespace(retrieve=retrieve))
    cases = [{"id": "c1", "query": "add a feat", "edition": "2014", "expect": {}}]

    run = await run_eval.run_config("baseline", {}, cases, EMPTY_CATALOG)

    assert calls == [
        {"query": "add a feat", "edition": "2014", "tenant_id": DEFAULT_TENANT_ID, "catalog": EMPTY_CATALOG}
    ]
    assert run["per_case"][0]["id"] == "c1"
