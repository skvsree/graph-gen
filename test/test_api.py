"""API tests for app/main.py via FastAPI TestClient."""

import math

import pytest
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


def test_index_renders_multiple_formulas_from_query_params():
    r = client.get("/", params=[("formula", "y = sin(x)"), ("formula", "y = cos(x)")])
    assert r.status_code == 200
    assert r.text.count('class="formula-input"') == 2
    assert 'value="y = sin(x)"' in r.text
    assert 'value="y = cos(x)"' in r.text


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


def test_index_renders_polar_mode():
    r = client.get("/", params={"mode": "polar", "formula": "r = 2θ"})
    assert r.status_code == 200
    assert 'id="tabPolar"' in r.text
    assert 'value="r = 2θ"' in r.text


def test_index_invalid_mode_returns_400():
    r = client.get("/", params={"mode": "bogus"})
    assert r.status_code == 400


def test_index_renders_color_pickers_per_formula():
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="color-pick"') == 2
    # Palette defaults in row order.
    assert 'value="#dc2626"' in r.text  # row 0
    assert 'value="#16a34a"' in r.text  # row 1


def test_index_prefills_color_params_in_order():
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("formula", "y = 2x"), ("color", "#ff00aa"), ("color", "#123456")],
    )
    assert r.status_code == 200
    assert 'value="#ff00aa"' in r.text
    assert 'value="#123456"' in r.text


def test_index_color_params_fallback_to_palette():
    # Invalid + missing colours fall back to the palette for that position.
    r = client.get("/", params=[("formula", "y = x"), ("color", "not-a-colour")])
    assert r.status_code == 200
    assert 'value="#dc2626"' in r.text  # invalid -> palette[0]


def test_index_color_param_never_injects_markup():
    r = client.get("/", params=[("formula", "y = x"), ("color", '"><script>alert(1)</script>')])
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text


def test_index_renders_opacity_inputs_per_formula():
    # Each row carries an opacity field (percent of its colour), defaulting
    # to 100 = fully opaque.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="opacity-pick"') == 2
    assert r.text.count('value="100"') == 2  # both rows opaque by default


def test_index_prefills_opacity_params_in_order():
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("formula", "y = 2x"), ("op", "25"), ("op", "60")],
    )
    assert r.status_code == 200
    assert 'id="op0" value="25"' in r.text
    assert 'id="op1" value="60"' in r.text


def test_index_opacity_params_fallback_to_100():
    # Invalid + out-of-range op params fall back to 100 for that position.
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("formula", "y = 2x"), ("op", "not-a-number"), ("op", "500")],
    )
    assert r.status_code == 200
    assert 'id="op0" value="100"' in r.text  # invalid -> default
    assert 'id="op1" value="100"' in r.text  # out of range -> default


def test_index_opacity_params_pad_when_fewer_than_rows():
    # One op param for two rows: the second row keeps its default (100).
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x"), ("op", "40")])
    assert r.status_code == 200
    assert 'id="op0" value="40"' in r.text
    assert 'id="op1" value="100"' in r.text


def test_index_opacity_param_never_injects_markup():
    r = client.get("/", params=[("formula", "y = x"), ("op", '"><script>alert(1)</script>')])
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert 'id="op0" value="100"' in r.text


def test_index_renders_centre_inputs_per_formula():
    # Each row carries a centre-x and centre-y field, both defaulting to
    # blank (= 0,0 — the input's placeholder reads 0).
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="ctr-x"') == 2
    assert r.text.count('class="ctr-y"') == 2
    assert 'value="" placeholder="0"' in r.text.replace("\n", "")


def test_index_prefills_centre_params_in_order():
    r = client.get(
        "/",
        params=[
            ("formula", "y = x"),
            ("formula", "y = 2x"),
            ("cx", "2.5"),
            ("cx", "-1"),
            ("cy", "3"),
        ],
    )
    assert r.status_code == 200
    # Row 0: centre (2.5, 3); row 1: centre (-1, <blank default>).
    assert 'value="2.5"' in r.text
    assert 'value="3"' in r.text
    assert 'value="-1"' in r.text


def test_index_centre_params_fallback_to_zero():
    # Invalid + missing centre params fall back to the blank (0,0) default
    # for that position; a param can never inject markup.
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("cx", "not-a-number"), ("cx", '"><script>alert(1)</script>'), ("cy", "3")],
    )
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    # cx[0] invalid -> blank (value=""); cy[0] = 3 still lands on row 0.
    assert 'id="ctrX0" value=""' in r.text
    assert 'id="ctrY0" value="3"' in r.text


def test_index_centre_params_pad_when_fewer_than_rows():
    # One cx/cy pair for two rows: the second row keeps its default.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x"), ("cx", "4"), ("cy", "5")])
    assert r.status_code == 200
    assert 'id="ctrX0" value="4"' in r.text and 'id="ctrY0" value="5"' in r.text
    assert 'id="ctrX1" value=""' in r.text and 'id="ctrY1" value=""' in r.text


def test_index_renders_rotation_inputs_per_formula():
    # Each row carries a rotation field (degrees about that curve's own
    # centre), defaulting to blank = 0 degrees (no rotation).
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="rot-pick"') == 2
    assert 'id="rot0" value="" placeholder="0"' in r.text


def test_index_prefills_rotation_params_in_order():
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("formula", "y = 2x"), ("rot", "45"), ("rot", "-0.5")],
    )
    assert r.status_code == 200
    assert 'id="rot0" value="45"' in r.text
    assert 'id="rot1" value="-0.5"' in r.text


def test_index_rotation_params_fallback_to_zero():
    # Invalid + missing rot params fall back to the blank (0 degrees) default
    # for that position; a param can never inject markup.
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("rot", "not-a-number"), ("rot", '"><script>alert(1)</script>')],
    )
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert 'id="rot0" value=""' in r.text


def test_index_rotation_params_pad_when_fewer_than_rows():
    # One rot param for two rows: the second row keeps its default (blank).
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x"), ("rot", "90")])
    assert r.status_code == 200
    assert 'id="rot0" value="90"' in r.text
    assert 'id="rot1" value=""' in r.text


def test_index_rotation_param_round_trips_scientific_notation():
    # Rotation values are kept as strings, so whatever a type=number input
    # produced (here 1e2 = 100 degrees) round-trips through the share URL.
    r = client.get("/", params=[("formula", "y = x"), ("rot", "1e2")])
    assert r.status_code == 200
    assert 'id="rot0" value="1e2"' in r.text


def test_template_palette_matches_js_palette():
    # The server's CURVE_PALETTE and the template's must stay in lockstep so a
    # URL without color= params renders the same defaults the client expects.
    from app.main import CURVE_PALETTE

    r = client.get("/")
    m = __import__("re").search(r"CURVE_PALETTE = \[([^\]]+)\]", r.text)
    assert m, "CURVE_PALETTE not found in template"
    js_hexes = [h.strip("'") for h in __import__("re").findall(r"'#[0-9a-fA-F]{6}'", m.group(1))]
    assert js_hexes == CURVE_PALETTE


def test_index_renders_hex_colour_box_and_palette_button_per_formula():
    # Each row's colour cell holds the device swatch, a hex/text box (any CSS
    # colour — Android's device dialog only offers a small fixed set) and a
    # button opening the built-in palette.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="color-cell"') == 2
    assert r.text.count('class="hex-pick"') == 2
    assert r.text.count('class="pal-btn"') == 2


def test_index_hex_box_mirrors_the_initial_colour():
    # The hex box shows the row's prefilled colour, so a share URL's color=
    # param is editable text as well as a swatch.
    r = client.get("/", params=[("formula", "y = x"), ("color", "#ff00aa")])
    assert r.status_code == 200
    assert r.text.count('value="#ff00aa"') == 2   # device swatch + hex box


def test_index_renders_palette_popover_with_presets():
    import re

    r = client.get("/")
    assert r.status_code == 200
    assert 'id="palPop"' in r.text and 'id="palGrid"' in r.text
    # The swatches are built in the template JS from PALETTE_PRESETS: assert
    # they are all valid distinct hexes (the popover has nothing else to show).
    m = re.search(r"PALETTE_PRESETS = \[([^\]]+)\]", r.text)
    assert m, "PALETTE_PRESETS not found in template"
    hexes = re.findall(r"'#[0-9a-f]{6}'", m.group(1))
    assert len(hexes) == 32
    assert len(set(hexes)) == 32


def test_index_renders_duplicate_set_button():
    # "Duplicate set" clones every row (settings included) into new rows.
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="dupSetBtn"' in r.text


def test_template_max_rows_matches_api_limit():
    # The UI row ceiling (JS MAX_ROWS) must not drift from the server's
    # MAX_FORMULAS, or the page can offer rows the API rejects with a 400.
    import re

    from app.main import MAX_FORMULAS

    r = client.get("/")
    m = re.search(r"MAX_ROWS = (\d+)", r.text)
    assert m, "MAX_ROWS not found in template"
    assert int(m.group(1)) == MAX_FORMULAS


def test_index_renders_grid_and_axis_toggles():
    # Two independent view toggles next to the plot button: Grid (lines only)
    # and Axis (axis lines, arrows, tick numbers and the x/y labels).
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="gridBtn"' in r.text and "Grid: on" in r.text
    assert 'id="axisBtn"' in r.text and "Axis: on" in r.text


def test_api_points_polar():
    r = client.get("/api/points", params={"formula": "r = 2θ", "mode": "polar"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "polar"
    assert body["curves"][0]["kind"] == "polar"
    assert body["curves"][0]["display"] == "r = 2θ"
    assert body["x_range"]["min"] == 0.0
    assert body["x_range"]["max"] == pytest.approx(4 * math.pi)
    assert len(body["curves"][0]["branches"][0]["points"]) == 252


def test_api_points_polar_explicit_theta_range():
    r = client.get("/api/points", params={"formula": "r = 2θ", "mode": "polar", "x_min": 0, "x_max": math.pi})
    assert r.status_code == 200
    body = r.json()
    assert body["x_range"] == {"min": 0, "max": math.pi}
    assert len(body["curves"][0]["branches"][0]["points"]) == 315


def test_api_points_polar_carries_theta_and_r():
    r = client.get("/api/points", params={"formula": "r = 2θ", "mode": "polar"})
    assert r.status_code == 200
    pts = r.json()["curves"][0]["branches"][0]["points"]
    assert set(pts[0].keys()) == {"x", "y", "theta", "r"}
    assert pts[0]["theta"] == 0.0 and pts[0]["r"] == 0.0
    assert pts[1]["r"] == pytest.approx(2 * pts[1]["theta"])


def test_api_points_cartesian_points_have_no_theta():
    r = client.get("/api/points", params={"formula": "y = 2x + 1"})
    assert r.status_code == 200
    pts = r.json()["curves"][0]["branches"][0]["points"]
    assert set(pts[0].keys()) == {"x", "y"}


def test_api_points_polar_invalid_returns_400():
    r = client.get("/api/points", params={"formula": "r^2 = 2θ", "mode": "polar"})
    assert r.status_code == 400
    assert "linear in r" in r.json()["detail"]


def test_api_points_invalid_mode_returns_400():
    r = client.get("/api/points", params={"formula": "y = x", "mode": "bogus"})
    assert r.status_code == 400
    assert "mode" in r.json()["detail"]


def test_api_points_default_linear():
    r = client.get("/api/points")
    assert r.status_code == 200
    body = r.json()
    assert body["formulas"] == ["x + y = 3"]
    assert body["curves"][0]["display"] == "y = \u2212x + 3"
    assert body["curves"][0]["kind"] == "linear"
    assert body["x_range"] == {"min": 1, "max": 100}
    assert len(body["curves"][0]["branches"]) == 1
    pts = body["curves"][0]["branches"][0]["points"]
    assert len(pts) == 100
    assert pts[0] == {"x": 1, "y": 2}
    assert pts[99] == {"x": 100, "y": -97}


def test_api_points_linear_custom_range():
    r = client.get("/api/points", params={"formula": "y = 2x", "x_min": 1, "x_max": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["x_range"] == {"min": 1, "max": 5}
    assert body["step"] == 1
    pts = body["curves"][0]["branches"][0]["points"]
    assert [p["y"] for p in pts] == [2, 4, 6, 8, 10]


def test_api_points_explicit_step():
    r = client.get("/api/points", params={"formula": "y = 2x", "x_min": 1, "x_max": 10, "x_step": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["step"] == 2
    pts = body["curves"][0]["branches"][0]["points"]
    assert [p["x"] for p in pts] == [1, 3, 5, 7, 9]


def test_api_points_multiple_formulas():
    r = client.get("/api/points", params=[("formula", "y = sin(x)"), ("formula", "y = cos(x)")])
    assert r.status_code == 200
    body = r.json()
    assert body["formulas"] == ["y = sin(x)", "y = cos(x)"]
    assert len(body["curves"]) == 2
    assert body["curves"][0]["display"] == "y = sin(x)"
    assert body["curves"][1]["display"] == "y = cos(x)"
    assert body["curves"][0]["branches"][0]["points"][0]["x"] == 1
    assert len(body["curves"][1]["branches"][0]["points"]) == 199


def test_api_points_multiple_formulas_shared_explicit_range():
    r = client.get(
        "/api/points",
        params=[("formula", "y = sin(x)"), ("formula", "y = cos(x)"), ("x_min", "0"), ("x_max", "6.28"), ("x_step", "0.1")],
    )
    assert r.status_code == 200
    body = r.json()
    assert body["x_range"] == {"min": 0, "max": 6.28}
    assert body["step"] == 0.1
    assert len(body["curves"][0]["branches"][0]["points"]) == 63


def test_api_points_at_most_five_formulas():
    params = [("formula", f"y = {i}x") for i in range(6)]
    r = client.get("/api/points", params=params)
    assert r.status_code == 400
    assert "At most 5" in r.json()["detail"]


def test_api_points_five_formulas_ok():
    params = [("formula", f"y = {i}x") for i in range(5)]
    r = client.get("/api/points", params=params)
    assert r.status_code == 200
    assert len(r.json()["curves"]) == 5


def test_api_points_empty_formulas_returns_400():
    r = client.get("/api/points", params=[("formula", ""), ("formula", "  ")])
    assert r.status_code == 400
    assert "Enter a formula" in r.json()["detail"]


def test_api_points_invalid_formula_returns_400():
    r = client.get("/api/points", params={"formula": "5 = 5"})
    assert r.status_code == 400
    assert "no effective y term" in r.json()["detail"]


def test_api_points_invalid_second_formula_returns_400():
    r = client.get("/api/points", params=[("formula", "y = sin(x)"), ("formula", "5 = 5")])
    assert r.status_code == 400
    assert "no effective y term" in r.json()["detail"]


def test_api_points_implicit_curve():
    r = client.get("/api/points", params={"formula": "x^2 + y^3 = 7"})
    assert r.status_code == 200
    body = r.json()
    curve = body["curves"][0]
    assert curve["kind"] == "implicit"
    assert curve["display"] == "x^2+y^3 = 7"
    assert body["x_range"] == {"min": -10.0, "max": 10.0}
    assert len(curve["branches"]) >= 1
    assert len(curve["branches"][0]["points"]) > 50


def test_api_points_inequality_curve():
    r = client.get("/api/points", params={"formula": "y > 2x + 1"})
    assert r.status_code == 200
    curve = r.json()["curves"][0]
    assert curve["kind"] == "linear"
    assert curve["inequality"] == {"op": ">", "side": "above"}
    assert len(curve["branches"][0]["points"]) == 100


def test_api_points_inequality_quadratic_between():
    r = client.get("/api/points", params={"formula": "x^2 + y^2 < 25"})
    assert r.status_code == 200
    curve = r.json()["curves"][0]
    assert curve["inequality"] == {"op": "<", "side": "between"}


def test_api_points_implicit_invalid_returns_400():
    r = client.get("/api/points", params={"formula": "x^2 + y^4 = -3"})
    assert r.status_code == 400
    assert "No real points" in r.json()["detail"]


def test_api_points_inequality_implicit_boundary_returns_400():
    r = client.get("/api/points", params={"formula": "x^2 + y^3 > 7"})
    assert r.status_code == 400
    assert "solvable for y" in r.json()["detail"]


def test_api_points_cache_hit_returns_same_payload():
    params = {"formula": "y = 7x - 3"}  # unique key — nothing else warms it
    first = client.get("/api/points", params=params)
    second = client.get("/api/points", params=params)
    assert first.status_code == 200 and second.status_code == 200
    assert first.headers.get("x-cache") == "MISS"
    assert second.headers.get("x-cache") == "HIT"
    assert first.json() == second.json()


def test_api_points_different_formulas_not_cached_together():
    a = client.get("/api/points", params={"formula": "y = 8x - 3"})
    b = client.get("/api/points", params={"formula": "y = 8x - 4"})
    assert a.headers.get("x-cache") == "MISS"
    assert b.headers.get("x-cache") == "MISS"


def test_metrics_endpoint():
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "xy_requests_total" in r.text
    assert 'path="/api/points"' in r.text
    assert "xy_uptime_seconds" in r.text


def test_health_reports_version_and_uptime():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.6.0"
    assert body["uptime_s"] >= 0


def test_api_hits_counts_page_renders():
    before = client.get("/api/hits").json()["hits"]
    r = client.get("/")
    assert r.status_code == 200
    assert f"Hits: {before + 1}" in r.text  # footer shows the incremented count
    after = client.get("/api/hits").json()["hits"]
    assert after == before + 1


def test_api_points_invalid_step_returns_400():
    r = client.get("/api/points", params={"formula": "y = x", "x_min": 1, "x_max": 5, "x_step": 0})
    assert r.status_code == 400
    assert "x_step" in r.json()["detail"]


def test_api_points_fractional_step():
    r = client.get("/api/points", params={"formula": "y = sin(x)", "x_min": 0, "x_max": 2, "x_step": 0.5})
    assert r.status_code == 200
    body = r.json()
    assert body["step"] == 0.5
    assert [p["x"] for p in body["curves"][0]["branches"][0]["points"]] == [0, 0.5, 1, 1.5, 2]


def test_api_points_fractional_range():
    r = client.get("/api/points", params={"formula": "y = x", "x_min": -1.5, "x_max": 1.5})
    assert r.status_code == 200
    body = r.json()
    assert body["x_range"] == {"min": -1.5, "max": 1.5}


def test_api_points_non_numeric_step_returns_422():
    r = client.get("/api/points", params={"formula": "y = x", "x_step": "abc"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, list)  # FastAPI validation errors: array of objects


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
    assert body["curves"][0]["kind"] == "quadratic"
    assert body["curves"][0]["display"] == "y = \u00b1\u221a(\u2212x^2 + 100)"
    assert body["x_range"] == {"min": -10, "max": 10}
    assert len(body["curves"][0]["branches"]) == 2
    plus = body["curves"][0]["branches"][0]
    minus = body["curves"][0]["branches"][1]
    assert plus["label"] == "+"
    assert minus["label"] == "\u2212"
    assert plus["points"][10] == {"x": 0, "y": 10}
    assert minus["points"][10] == {"x": 0, "y": -10}


def test_api_points_circle_explicit_range():
    r = client.get("/api/points", params={"formula": "x^2 + y^2 = 100", "x_min": 1, "x_max": 10})
    assert r.status_code == 200
    body = r.json()
    assert len(body["curves"][0]["branches"][0]["points"]) == 10


def test_api_points_function_sin():
    r = client.get("/api/points", params={"formula": "y = sin(x)"})
    assert r.status_code == 200
    body = r.json()
    assert body["curves"][0]["kind"] == "function"
    assert body["curves"][0]["display"] == "y = sin(x)"
    assert body["x_range"] == {"min": 1, "max": 100}
    assert body["step"] == 0.5
    assert len(body["curves"][0]["branches"]) == 1
    pts = body["curves"][0]["branches"][0]["points"]
    assert len(pts) == 199
    assert abs(pts[0]["y"] - 0.8414709848078965) < 1e-9


def test_api_points_function_domain_skips():
    r = client.get("/api/points", params={"formula": "y = log(x)", "x_min": -5, "x_max": 5})
    assert r.status_code == 200
    body = r.json()
    assert [p["x"] for p in body["curves"][0]["branches"][0]["points"]] == [1, 2, 3, 4, 5]


def test_api_points_function_segments():
    # 1/(x-5) is undefined at x=5 → two segments
    r = client.get("/api/points", params={"formula": "y = 1/(x-5)", "x_min": 1, "x_max": 10})
    assert r.status_code == 200
    body = r.json()
    assert [len(br["points"]) for br in body["curves"][0]["branches"]] == [4, 5]


def test_api_points_function_invalid_returns_400():
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
