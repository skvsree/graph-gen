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


def test_index_renders_range_from_query_params():
    r = client.get("/", params={"formula": "y = x", "x_min": "-5", "x_max": "5", "x_step": "2"})
    assert r.status_code == 200
    assert 'id="xMin" value="-5"' in r.text
    assert 'id="xMax" value="5"' in r.text
    assert 'id="xStep" value="2"' in r.text


def test_index_escapes_formula_against_xss():
    r = client.get("/", params={"formula": "<script>alert(1)</script>"})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_api_points_default_linear():
    r = client.get("/api/points")
    assert r.status_code == 200
    body = r.json()
    assert body["display"] == "y = \u2212x + 3"
    assert body["kind"] == "linear"
    assert body["x_range"] == {"min": 1, "max": 100}
    assert len(body["branches"]) == 1
    pts = body["branches"][0]["points"]
    assert len(pts) == 100
    assert pts[0] == {"x": 1, "y": 2}
    assert pts[99] == {"x": 100, "y": -97}


def test_api_points_linear_custom_range():
    r = client.get("/api/points", params={"formula": "y = 2x", "x_min": 1, "x_max": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["x_range"] == {"min": 1, "max": 5}
    assert body["step"] == 1
    assert [p["y"] for p in body["branches"][0]["points"]] == [2, 4, 6, 8, 10]


def test_api_points_explicit_step():
    r = client.get("/api/points", params={"formula": "y = 2x", "x_min": 1, "x_max": 10, "x_step": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["step"] == 2
    assert [p["x"] for p in body["branches"][0]["points"]] == [1, 3, 5, 7, 9]


def test_api_points_invalid_step_returns_400():
    r = client.get("/api/points", params={"formula": "y = x", "x_min": 1, "x_max": 5, "x_step": 0})
    assert r.status_code == 400
    assert "x_step" in r.json()["detail"]


def test_api_points_partial_range_returns_400():
    r = client.get("/api/points", params={"formula": "y = x", "x_min": 1})
    assert r.status_code == 400
    assert "both x_min and x_max" in r.json()["detail"]


def test_api_points_range_too_large_returns_400():
    r = client.get("/api/points", params={"formula": "y = x", "x_min": 1, "x_max": 1_000_000})
    assert r.status_code == 400
    assert "Range too large" in r.json()["detail"]


def test_api_points_circle():
    r = client.get("/api/points", params={"formula": "x^2 + y^2 = 100"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "quadratic"
    assert body["display"] == "y = \u00b1\u221a(\u2212x^2 + 100)"
    assert body["x_range"] == {"min": -10, "max": 10}
    assert len(body["branches"]) == 2
    plus = body["branches"][0]
    minus = body["branches"][1]
    assert plus["label"] == "+"
    assert minus["label"] == "\u2212"
    assert plus["points"][10] == {"x": 0, "y": 10}
    assert minus["points"][10] == {"x": 0, "y": -10}


def test_api_points_circle_explicit_range():
    r = client.get("/api/points", params={"formula": "x^2 + y^2 = 100", "x_min": 1, "x_max": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["x_range"] == {"min": 1, "max": 10}
    assert len(body["branches"][0]["points"]) == 10


def test_api_points_invalid_formula_returns_400():
    r = client.get("/api/points", params={"formula": "x = 5"})
    assert r.status_code == 400
    assert "no effective y term" in r.json()["detail"]


def test_api_points_function_sin():
    r = client.get("/api/points", params={"formula": "y = sin(x)"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "function"
    assert body["display"] == "y = sin(x)"
    assert body["x_range"] == {"min": 1, "max": 100}
    assert len(body["branches"]) == 1
    pts = body["branches"][0]["points"]
    assert len(pts) == 100
    assert abs(pts[0]["y"] - 0.8414709848078965) < 1e-9


def test_api_points_function_domain_skips():
    r = client.get("/api/points", params={"formula": "y = log(x)", "x_min": -5, "x_max": 5})
    assert r.status_code == 200
    body = r.json()
    assert [p["x"] for p in body["branches"][0]["points"]] == [1, 2, 3, 4, 5]


def test_api_points_function_segments():
    # 1/(x-5) is undefined at x=5 → two segments
    r = client.get("/api/points", params={"formula": "y = 1/(x-5)", "x_min": 1, "x_max": 10})
    assert r.status_code == 200
    body = r.json()
    assert [len(br["points"]) for br in body["branches"]] == [4, 5]


def test_api_points_function_invalid_returns_400():
    r = client.get("/api/points", params={"formula": "y = sin(y)"})
    assert r.status_code == 400
    assert "inside a function" in r.json()["detail"]
    r = client.get("/api/points", params={"formula": "y = foo(x)"})
    assert r.status_code == 400
    assert "Unknown function" in r.json()["detail"]


def test_api_points_no_real_points_returns_400():
    r = client.get("/api/points", params={"formula": "y^2 = -1"})
    assert r.status_code == 400
    assert "No real y" in r.json()["detail"]


def test_api_points_bad_range_returns_400():
    r = client.get("/api/points", params={"formula": "y = x", "x_min": 10, "x_max": 5})
    assert r.status_code == 400


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
