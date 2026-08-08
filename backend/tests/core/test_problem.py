import json

from app.core.problem import PROBLEM_MEDIA_TYPE, ProblemError, problem_response, type_for


def test_problem_response_shape_and_media_type():
    resp = problem_response(status=413, title="File too large", detail="Too big.", type="/api/problems/file-too-large")
    assert resp.status_code == 413
    assert resp.media_type == PROBLEM_MEDIA_TYPE
    body = json.loads(resp.body)
    assert body == {
        "type": "/api/problems/file-too-large",
        "title": "File too large",
        "status": 413,
        "detail": "Too big.",
    }


def test_problem_response_includes_instance_and_extensions_but_omits_none():
    resp = problem_response(
        status=422,
        title="Validation failed",
        detail="Bad.",
        instance="/api/x",
        errors=[{"field": "a", "message": "b"}],
        nothing=None,
    )
    body = json.loads(resp.body)
    assert body["instance"] == "/api/x"
    assert body["errors"] == [{"field": "a", "message": "b"}]
    assert "nothing" not in body


def test_problem_exception_carries_fields():
    exc = ProblemError(status=409, type="/api/problems/conflict", title="Conflict", detail="Exists.", other="x")
    assert (exc.status, exc.type, exc.title, exc.detail) == (409, "/api/problems/conflict", "Conflict", "Exists.")
    assert exc.extensions == {"other": "x"}


def test_type_for_hyphenates_the_code():
    assert type_for("file_too_large") == "/api/problems/file-too-large"
