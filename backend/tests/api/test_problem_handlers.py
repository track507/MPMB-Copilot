import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.problem import PROBLEM_MEDIA_TYPE, ProblemError, register_problem_handlers
from app.services.uploads.errors import UploadError


@pytest.fixture
def client():
    app = FastAPI()
    register_problem_handlers(app)

    class Body(BaseModel):
        n: int

    @app.get("/boom")
    def boom():
        raise HTTPException(status_code=404, detail="Session not found")

    @app.post("/validate")
    def validate(_: Body):
        return {}

    @app.get("/problem")
    def problem():
        raise ProblemError(status=409, type="/api/problems/conflict", title="Conflict", detail="Exists.")

    @app.get("/upload")
    def upload():
        raise UploadError(413, "file_too_large", "File exceeds 50 MB.")

    return TestClient(app)


def test_httpexception_renders_problem(client):
    r = client.get("/boom")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert r.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Session not found",
        "instance": "/boom",
    }


def test_validation_renders_errors_extension(client):
    r = client.post("/validate", json={"n": "not-an-int"})
    body = r.json()
    assert r.status_code == 422
    assert body["type"] == "/api/problems/validation-error"
    assert body["errors"][0]["field"] == "n"


def test_problem_exception_uses_its_type(client):
    r = client.get("/problem")
    assert r.status_code == 409
    assert r.json()["type"] == "/api/problems/conflict"


def test_upload_error_maps_code_to_type_and_title(client):
    r = client.get("/upload")
    body = r.json()
    assert r.status_code == 413
    assert body["type"] == "/api/problems/file-too-large"
    assert body["title"] == "File too large"
    assert body["detail"] == "File exceeds 50 MB."


def test_unhandled_exception_renders_500_problem():
    app = FastAPI()
    register_problem_handlers(app)

    @app.get("/kaboom")
    def kaboom():
        raise RuntimeError("internal boom")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/kaboom")
    assert r.status_code == 500
    body = r.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Internal Server Error"
