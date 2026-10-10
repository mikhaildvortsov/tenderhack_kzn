import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas import AnalyzeResponse

TEXTS = ["молоток слесарный 500 г", "молатак 500г", "стол", "куртка мужская зимняя размер 52", ""]


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def ready(client):
    h = client.get("/health").json()
    if not h["index_loaded"]:
        pytest.skip("индекс не загружен")
    try:
        import engine.pipeline  # noqa: F401
    except ImportError:
        pytest.skip("engine.pipeline недоступен")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok" and {"positions", "index_loaded", "version"} <= d.keys()
    assert "x-process-time" in r.headers


def test_examples(client):
    r = client.get("/api/v1/examples")
    assert r.status_code == 200
    d = r.json()
    assert len(d) >= 8 and all({"category", "text", "note"} <= e.keys() for e in d)


def test_analyze_unavailable_gives_503_json(client):
    if client.get("/health").json()["index_loaded"]:
        pytest.skip("индекс загружен")
    r = client.post("/api/v1/analyze", json={"text": "молоток"})
    assert r.status_code == 503 and "detail" in r.json()


def test_analyze_validation(client):
    assert client.post("/api/v1/analyze", json={"text": "x" * 2001}).status_code == 422


@pytest.mark.parametrize("text", TEXTS)
def test_analyze(client, ready, text):
    r = client.post("/api/v1/analyze", json={"text": text})
    assert r.status_code == 200
    resp = AnalyzeResponse.model_validate(r.json())
    assert resp.text == text
    if not text:
        assert resp.status == "empty"


def test_ktru_404(client, ready):
    r = client.get("/api/v1/ktru/not-a-code-@@")
    assert r.status_code == 404 and "detail" in r.json()


def test_stream_result(client, ready):
    events = []
    with client.stream("GET", "/api/v1/stream", params={"text": "молоток слесарный 500 г"}) as r:
        assert r.status_code == 200
        ev = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                ev = line.split(":", 1)[1].strip()
            elif line.startswith("data:") and ev:
                events.append((ev, line.split(":", 1)[1].strip()))
    names = [e for e, _ in events]
    assert names and names[-1] == "result"
    AnalyzeResponse.model_validate(json.loads(events[-1][1]))
