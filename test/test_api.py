"""API tests for app/main.py via FastAPI TestClient."""

import math
import re

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
    # The hex boxes show the row's prefilled colours, so a share URL's color=
    # param is editable text as well as a swatch. Each row has TWO colour parts
    # (gradient start → end), and the end colour defaults to the start colour,
    # so a single color= param fills both swatches and both hex boxes.
    r = client.get("/", params=[("formula", "y = x"), ("color", "#ff00aa")])
    assert r.status_code == 200
    assert r.text.count('value="#ff00aa"') == 4   # 2 swatches + 2 hex boxes


def test_index_renders_gradient_end_colour_controls_per_formula():
    # Every row carries a second colour part (gradient end) with its own device
    # swatch, hex/text box and palette button, plus the "→" between the parts.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="color2-pick"') == 2
    assert r.text.count('class="hex2-pick"') == 2
    assert r.text.count('class="pal2-btn"') == 2
    assert r.text.count('class="color-part"') == 4        # two per row
    assert r.text.count('class="color-arrow"') == 2


def test_index_prefills_color2_params_in_order():
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("formula", "y = 2x"),
                ("color", "#ff00aa"), ("color", "#123456"),
                ("color2", "#00ff00"), ("color2", "#0000ff")],
    )
    assert r.status_code == 200
    assert r.text.count('class="color2-pick" value="#00ff00"') == 1
    assert r.text.count('class="color2-pick" value="#0000ff"') == 1


def test_index_color2_params_fallback_to_the_row_colour():
    # A missing/invalid gradient end colour falls back to that row's FIRST
    # colour — a solid line, never the palette default (that would silently
    # paint a gradient the user never asked for).
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("formula", "y = 2x"),
                ("color", "#ff00aa"), ("color", "#123456"),
                ("color2", "not-a-colour")],
    )
    assert r.status_code == 200
    assert r.text.count('class="color2-pick" value="#ff00aa"') == 1   # row 0 -> its colour
    assert r.text.count('class="color2-pick" value="#123456"') == 1   # row 1 -> padded
    assert 'class="color2-pick" value="#dc2626"' not in r.text


def test_index_color2_param_never_injects_markup():
    r = client.get("/", params=[("formula", "y = x"), ("color2", '"><script>alert(1)</script>')])
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert 'class="color2-pick" value="#dc2626"' in r.text   # falls back to row colour


def test_index_renders_function_menu_button_per_formula():
    # Every row has a ƒ button that opens the shared function menu, which
    # inserts the chosen function into THAT row's formula field at the caret.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="fn-btn"') == 2
    assert 'id="fnPop"' in r.text
    assert 'id="fnGrid"' in r.text and 'id="fnConsts"' in r.text


def test_index_function_menu_covers_every_function():
    # The menu (and every tooltip) is built in the template from the template's
    # own FUNCTIONS array. Both must match the server's solver exactly, or the
    # drop-down offers a function the API rejects (or hides a supported one).
    import re

    from app.solver import FUNCTIONS, TWO_ARG_FUNCTIONS

    r = client.get("/")
    m = re.search(r"const FUNCTIONS = \[([^\]]+)\]", r.text)
    assert m, "FUNCTIONS not found in template"
    js_names = re.findall(r"'([a-z0-9]+)'", m.group(1))
    assert sorted(js_names) == sorted(FUNCTIONS)

    block = re.search(r"const FN_HELP = \{(.*?)\n\};", r.text, re.S)
    assert block, "FN_HELP not found in template"
    help_keys = re.findall(r"([a-z][a-z0-9]*)\s*:", block.group(1))
    assert sorted(help_keys) == sorted(js_names), "every function needs a tooltip entry"

    two = re.search(r"const TWO_ARG_FUNCTIONS = \[([^\]]*)\]", r.text)
    assert two, "TWO_ARG_FUNCTIONS not found in template"
    assert sorted(re.findall(r"'([a-z0-9]+)'", two.group(1))) == sorted(TWO_ARG_FUNCTIONS)


def test_index_renders_thickness_and_style_controls_per_formula():
    # Every row carries a line-thickness field (px) and a line-style menu,
    # both defaulting to the classic 2.5px solid pen.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="width-pick"') == 2
    assert r.text.count('class="style-pick"') == 2
    assert 'id="w0" value="2.5"' in r.text
    assert 'id="w1" value="2.5"' in r.text
    assert r.text.count('<option value="solid" selected>Solid</option>') == 2


def test_index_prefills_width_and_style_params_in_order():
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("formula", "y = 2x"),
                ("w", "7"), ("w", "1.5"),
                ("style", "dotted"), ("style", "longdash")],
    )
    assert r.status_code == 200
    assert 'id="w0" value="7.0"' in r.text
    assert 'id="w1" value="1.5"' in r.text
    assert 'value="dotted" selected' in r.text
    assert 'value="longdash" selected' in r.text


def test_index_width_and_style_params_fallback_to_defaults():
    # Out-of-range thickness -> 2.5; the style is an allow-list, so an unknown one
    # -> solid (a known one is accepted case-insensitively).
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("formula", "y = 2x"),
                ("w", "999"), ("style", "scribble"),
                ("w", "0.01"), ("style", "DASHED")],
    )
    assert r.status_code == 200
    assert 'id="w0" value="2.5"' in r.text
    assert 'id="w1" value="2.5"' in r.text
    assert r.text.count('<option value="solid" selected>Solid</option>') == 1
    assert 'value="dashed" selected' in r.text


def test_index_width_and_style_params_never_inject_markup():
    r = client.get(
        "/",
        params=[("formula", "y = x"), ("w", '"><script>alert(1)</script>'),
                ("style", '"><script>alert(1)</script>')],
    )
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert 'id="w0" value="2.5"' in r.text


def test_template_styles_match_server():
    # The style menu (order + labels) and the thickness bounds live in the
    # template; the server validates against its own copies. Drift would mean a
    # share URL rendering a style the menu cannot show, or a silently wrong
    # thickness clamp.
    import re

    from app.main import (STYLE_LABELS, DEFAULT_STYLE, DEFAULT_STROKE_WIDTH,
                          MAX_STROKE_WIDTH, MIN_STROKE_WIDTH)

    r = client.get("/")
    m = re.search(r"const STYLE_OPTIONS = \[(.*?)\n\];", r.text, re.S)
    assert m, "STYLE_OPTIONS not found in template"
    pairs = re.findall(r"\['([a-z]+)', '([^']+)'\]", m.group(1))
    assert [p[0] for p in pairs] == list(STYLE_LABELS)
    assert [p[1] for p in pairs] == list(STYLE_LABELS.values())

    # Numeric bounds are compared as FLOATS: Python writes 12.0 where JS writes
    # 12, and the point of the test is the value, not the formatting.
    for name, expected in (
        ("DEFAULT_STROKE_WIDTH", DEFAULT_STROKE_WIDTH),
        ("MIN_STROKE_WIDTH", MIN_STROKE_WIDTH),
        ("MAX_STROKE_WIDTH", MAX_STROKE_WIDTH),
    ):
        m2 = re.search(rf"const {name} = ([0-9.]+);", r.text)
        assert m2, f"{name} not found in template"
        assert float(m2.group(1)) == expected, f"{name}: template {m2.group(1)} != server {expected}"
    assert f"const DEFAULT_STYLE = '{DEFAULT_STYLE}'" in r.text


def test_index_renders_pen_menu_per_formula():
    # Every row carries a pen menu (technical / pencil / marker / calligraphy /
    # highlighter) next to the line style, both defaulting to the plain pen.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="pen-pick"') == 2
    assert r.text.count('<option value="technical" selected>Technical</option>') == 2
    for label in ("Pencil", "Marker", "Calligraphy", "Highlighter"):
        assert f">{label}</option>" in r.text, label


def test_index_prefills_pen_params_in_order():
    r = client.get(
        "/", params=[("formula", "y = x"), ("formula", "y = 2x"),
                     ("pen", "calligraphy"), ("pen", "pencil")],
    )
    assert r.status_code == 200
    assert 'value="calligraphy" selected' in r.text
    assert 'value="pencil" selected' in r.text


def test_index_calligraphy_disables_the_dash_style():
    # A chisel nib draws its own marks, so its style menu is greyed out — but
    # only for the rows that actually use calligraphy.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x"),
                                ("pen", "calligraphy"), ("pen", "marker")])
    assert r.status_code == 200
    assert r.text.count('class="style-pick" id="style0" disabled') == 1
    assert 'id="style1" disabled' not in r.text


def test_index_pen_params_fall_back_to_technical():
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x"),
                                ("pen", "crayon"), ("pen", '"><script>alert(1)</script>')])
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert r.text.count('<option value="technical" selected>Technical</option>') == 2


def test_index_legacy_brush_param_still_means_the_dash_style():
    # `brush=` was this control's first name; links shared before the rename
    # must keep working (and must not be read as a pen).
    r = client.get("/", params=[("formula", "y = x"), ("brush", "dotted")])
    assert r.status_code == 200
    assert 'value="dotted" selected' in r.text
    assert r.text.count('<option value="technical" selected>Technical</option>') == 1   # pen untouched


def test_template_pens_match_server():
    import re

    from app.main import DEFAULT_PEN, PEN_LABELS

    r = client.get("/")
    m = re.search(r"const PEN_OPTIONS = \[(.*?)\n\];", r.text, re.S)
    assert m, "PEN_OPTIONS not found in template"
    pairs = re.findall(r"\['([a-z]+)', '([^']+)'\]", m.group(1))
    assert [p[0] for p in pairs] == list(PEN_LABELS)
    assert [p[1] for p in pairs] == list(PEN_LABELS.values())
    assert f"const DEFAULT_PEN = '{DEFAULT_PEN}'" in r.text


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


def test_index_renders_duplicate_button_on_every_row():
    # Duplication is at FORMULA level: every row carries a .row-dup icon button
    # that inserts a copy of that row directly below it.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    assert r.text.count('class="row-dup"') == 2
    assert r.text.count('class="row-del"') == 2
    # No set-level duplicate action any more.
    assert 'id="dupSetBtn"' not in r.text


def test_index_toolbar_is_icon_only_with_accessible_names():
    # Each toolbar action is an inline-SVG icon button whose name is carried by
    # aria-label + title (there is no visible text label to fall back on).
    r = client.get("/")
    assert r.status_code == 200
    for btn_id, label in [
        ("plotBtn", "Plot"),
        ("addFormulaBtn", "Add formula"),
        ("pngBtn", "Download PNG"),
        ("copyBtn", "Copy link"),
        ("themeBtn", "Switch to the dark theme"),   # light is the default theme
        ("gridBtn", "Grid"),
        ("axisBtn", "Axis"),
    ]:
        m = re.search(r'<button[^>]*id="%s".*?</button>' % btn_id, r.text, re.S)
        assert m, btn_id
        html = m.group(0)
        assert "<svg" in html, btn_id
        assert 'aria-label="%s"' % label in html, (btn_id, label)
        assert "title=" in html, btn_id


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
    # Two independent ICON toggles next to the plot button: Grid (grid lines
    # only) and Axis (axis lines, arrows, tick numbers and the x/y labels).
    # An icon-only button carries its state in aria-pressed + the .on class.
    r = client.get("/")
    assert r.status_code == 200
    grid = re.search(r'<button[^>]*id="gridBtn"[^>]*>', r.text)
    axis = re.search(r'<button[^>]*id="axisBtn"[^>]*>', r.text)
    assert grid and 'aria-pressed="true"' in grid.group(0)
    assert "tool-toggle on" in grid.group(0)
    assert axis and 'aria-pressed="true"' in axis.group(0)
    assert "tool-toggle on" in axis.group(0)


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
    import re

    from app.main import app

    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # Compared against the app's own version (not a literal) so a release bump
    # never turns into a false test failure.
    assert body["version"] == app.version
    assert re.fullmatch(r"\d+\.\d+\.\d+", body["version"])
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


# ---------------------------------------------------------------------------
# PWA: manifest, service worker, icons (static/*, served by app/main.py)
# ---------------------------------------------------------------------------


def test_manifest_served_as_webmanifest_with_install_fields():
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    body = r.json()
    assert body["name"].startswith("xy-graph-gen")
    assert body["short_name"]
    assert body["start_url"] == "/"
    assert body["scope"] == "/"
    assert body["display"] == "standalone"
    assert body["theme_color"].startswith("#")
    assert body["background_color"].startswith("#")


def test_manifest_has_any_and_maskable_192_and_512_icons():
    body = client.get("/manifest.webmanifest").json()
    by_purpose: dict[str, set[str]] = {}
    for icon in body["icons"]:
        by_purpose.setdefault(icon.get("purpose", "any"), set()).add(icon["sizes"])
        assert icon["type"] == "image/png"
    # Chrome's installability check wants a >=192px icon in both groups.
    assert {"192x192", "512x512"} <= by_purpose["any"]
    assert {"192x192", "512x512"} <= by_purpose["maskable"]


def test_every_manifest_icon_actually_serves():
    body = client.get("/manifest.webmanifest").json()
    for icon in body["icons"]:
        r = client.get(icon["src"])
        assert r.status_code == 200, icon["src"]
        assert r.headers["content-type"] == "image/png"
        assert r.content.startswith(b"\x89PNG\r\n\x1a\n"), icon["src"]


def test_manifest_shortcuts_point_at_existing_modes():
    body = client.get("/manifest.webmanifest").json()
    urls = {s["url"] for s in body["shortcuts"]}
    assert urls == {"/?mode=cartesian", "/?mode=polar"}
    for url in urls:
        assert client.get(url).status_code == 200


def test_service_worker_is_root_scoped_and_revalidated():
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    # no-cache: a fixed worker must never be pinned in the HTTP cache.
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["service-worker-allowed"] == "/"
    # Sanity: it is the real worker, not an error page.
    assert "SHELL_CACHE" in r.text and "addEventListener('fetch'" in r.text


def test_service_worker_precache_list_is_servable():
    """Every precached URL must be a 200 — one 404 would fail the install."""
    sw = client.get("/sw.js").text
    block = sw.split("const SHELL_URLS = [", 1)[1].split("];", 1)[0]
    urls = re.findall(r"'([^']+)'", block)
    assert "/" in urls
    for url in urls:
        assert client.get(url).status_code == 200, url


def test_service_worker_never_caches_live_endpoints():
    sw = client.get("/sw.js").text
    # Live data (/api/hits, /metrics, /health) must stay network-only, i.e. no
    # interception branch may exist for them — only /api/points is cached.
    assert "url.pathname === '/api/points'" in sw
    for path in ("/api/hits", "/metrics", "/health"):
        assert f"url.pathname === '{path}'" not in sw, path
        assert f"pathname.startsWith('{path}')" not in sw, path


def test_icon_route_serves_whitelisted_pngs_and_rejects_the_rest():
    assert client.get("/icons/icon-512.png").status_code == 200
    assert client.get("/icons/apple-touch-icon-180.png").status_code == 200
    assert client.get("/icons/icon-512.PNG").status_code == 404     # case-sensitive
    assert client.get("/icons/nope.png").status_code == 404
    assert client.get("/icons/index.html").status_code == 404
    assert client.get("/icons/.env").status_code == 404


def test_index_declares_pwa_metadata_and_registers_the_worker():
    r = client.get("/")
    assert r.status_code == 200
    assert 'rel="manifest" href="/manifest.webmanifest"' in r.text
    assert '<meta name="theme-color"' in r.text
    assert 'rel="apple-touch-icon" href="/icons/apple-touch-icon-180.png"' in r.text
    assert "serviceWorker.register('/sw.js')" in r.text


def test_manifest_screenshots_are_wide_and_narrow_and_servable():
    """Chrome's richer install sheet needs a >=1280x720 wide shot (plus narrow)."""
    body = client.get("/manifest.webmanifest").json()
    shots = {s["form_factor"]: s for s in body["screenshots"]}
    assert {"wide", "narrow"} <= set(shots)
    assert shots["wide"]["sizes"] == "1280x800"
    assert shots["narrow"]["sizes"] == "720x1280"
    for shot in shots.values():
        assert shot["type"] == "image/png"
        assert shot["label"]
        r = client.get(shot["src"])
        assert r.status_code == 200, shot["src"]
        assert r.headers["content-type"] == "image/png"
        assert r.content.startswith(b"\x89PNG\r\n\x1a\n")
        # ...and the pixel size matches what the manifest claims.
        import struct

        w, h = struct.unpack(">II", r.content[16:24])
        assert f"{w}x{h}" == shot["sizes"], (shot["src"], w, h)


def test_screenshot_route_whitelists_png_names():
    assert client.get("/screenshots/wide.png").status_code == 200
    assert client.get("/screenshots/narrow.png").status_code == 200
    assert client.get("/screenshots/nope.png").status_code == 404
    assert client.get("/screenshots/wide.PNG").status_code == 404


def test_index_has_share_and_install_controls():
    text = client.get("/").text
    # Share image (share sheet -> clipboard -> download) and the install button,
    # which starts hidden until the browser offers a prompt.
    assert 'id="shareBtn"' in text
    assert "navigator.canShare" in text and "ClipboardItem" in text
    assert 'id="installBtn"' in text and "hidden" in text
    assert "beforeinstallprompt" in text and "appinstalled" in text
    assert "display-mode: standalone" in text
    assert 'id="installHint"' in text
    # The old copy feedback wrote to textContent, which blanked the icon-only
    # button; the tick flash must keep the SVG.
    assert "function flashButton" in text and "ICON.check" in text
    assert "btn.textContent = 'Copied!'" not in text


def test_share_uses_a_pre_encoded_png_synchronously():
    """navigator.share() needs transient activation: the tap must not wait for
    an encode, so the PNG is cached after every repaint."""
    text = client.get("/").text
    assert "function markPngDirty" in text
    assert "function freshPngFile" in text
    assert "markPngDirty();" in text                      # wired into draw()
    assert "setTimeout(encodePngFile, 400)" in text        # debounced re-encode
    assert "function shareLinkOnly" in text                # link-only fallback
    # shareImage() must reach navigator.share with no await in between.
    share_fn = text.split("function shareImage()", 1)[1].split("function shareLinkOnly", 1)[0]
    assert "navigator.share(payload)" in share_fn
    assert "graphPngBlob" not in share_fn and "await" not in share_fn
    # Files unsupported/no image yet -> the link share still opens the sheet.
    assert "navigator.share({ title: title, text: text, url: location.href })" in text


def test_actions_also_report_to_a_toast():
    """Tooltips are invisible on touch, so flashButton mirrors its label."""
    text = client.get("/").text
    assert 'id="toast"' in text and "function toast" in text
    flash = text.split("function flashButton(btn, label)", 1)[1].split("function toast", 1)[0]
    assert "toast(label)" in flash
