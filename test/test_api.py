"""API tests for app/main.py via FastAPI TestClient."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_index_renders_default_formula():
    r = client.get("/")
    assert r.status_code == 200
    assert 'value="x + y = 3"' in r.text
    assert "xy-graph-gen" in r.text


def test_index_renders_formula_from_query_param():
    r = client.get("/", params={"formula": "2x + 3y = 6"})
    assert r.status_code == 200
    assert 'value="2x + 3y = 6"' in r.text


def test_index_escapes_formula_against_xss():
    r = client.get("/", params={"formula": "<script>alert(1)</script>"})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_api_points_default():
    r = client.get("/api/points")
    assert r.status_code == 200
    body = r.json()
    assert body["display"] == "y = \u2212x + 3"
    assert len(body["points"]) == 100
    assert body["points"][0] == {"x": 1, "y": 2}
    assert body["points"][99] == {"x": 100, "y": -97}


def test_api_points_custom_range():
    r = client.get("/api/points", params={"formula": "y = 2x", "x_min": 1, "x_max": 5})
    assert r.status_code == 200
    assert [p["y"] for p in r.json()["points"]] == [2, 4, 6, 8, 10]


def test_api_points_invalid_formula_returns_400():
    r = client.get("/api/points", params={"formula": "x = 5"})
    assert r.status_code == 400
    assert "no effective y term" in r.json()["detail"]


def test_api_points_bad_range_returns_400():
    r = client.get("/api/points", params={"formula": "y = x", "x_min": 10, "x_max": 5})
    assert r.status_code == 400


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
