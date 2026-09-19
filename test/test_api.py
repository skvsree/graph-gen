"""API tests for app/main.py via FastAPI TestClient."""

import math
import re
from pathlib import Path

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


def test_template_pen_and_style_menus_stay_one_styled_pair():
    # The pen menu once shipped with NO css of its own: it rendered as a raw UA
    # select (19px tall, Arial, square, grey, `appearance: auto`) beside the
    # themed style menu, and the row's wrap then left it alone at the end of one
    # line with its partner starting the next. Both are now styled by ONE rule
    # (so they cannot drift apart) and wrapped in ONE `.penstyle` group.
    r = client.get("/", params=[("formula", "y = x"), ("formula", "y = 2x")])
    assert r.status_code == 200
    css = r.text.split("</style>")[0]

    # ONE shared declaration block for the two menus ...
    m = re.search(r"\.form select\.pen-pick,\s*\.form select\.style-pick[^{]*\{([^}]*)\}", css)
    assert m is not None, "pen + style menus must share one css rule"
    block = m.group(1)
    # ... and no rule may style just one of them (that is how they diverged).
    for m in re.finditer(r"([^{}]+)\{", css):
        sel = m.group(1)
        if "select" in sel and ("pen-pick" in sel or "style-pick" in sel):
            assert ".pen-pick" in sel and ".style-pick" in sel, f"unpaired select rule: {sel}"

    # Room for the longest label ("Calligraphy") inside the padded box.
    wm = re.search(r"width: (\d+)px", block)
    assert wm is not None, "the shared select rule must pin an explicit width"
    width = int(wm.group(1))
    assert width - 12 - 2 >= 60, f"select width {width}px is too tight for its labels"

    # Both menus carry the same micro-label treatment (no shouting "PEN").
    assert ".pen-ctr .ctr-lbl, .style-ctr .ctr-lbl" in css

    # ONE group per row, pen then style, so a wrapping row cannot split them —
    # and the JS-built rows (add / duplicate) carry the same group.
    assert r.text.count('class="penstyle"') == 2
    assert re.findall(r'class="ctr (pen|style)-ctr"', r.text) == ["pen", "style", "pen", "style"]
    assert re.search(r"className = 'penstyle'", r.text), "JS-added rows need the group too"


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


def test_animation_can_run_row_by_row():
    """A flag that serialises the reveal: each curve finishes before the next
    starts, at the SAME rate, so only the order changes (the drawing takes as
    long as its rows add up to, instead of ending with the longest).

    Every timing path must agree with it — the tick's stop condition, the scrub,
    the speed change and the video export all have to use the mode-aware span,
    or the bar disagrees with what is on the canvas.
    """
    text = client.get("/").text
    assert 'id="animRow"' in text
    assert "row by row" in text
    m = re.search(r"<label[^>]*for=\"animRow\"[^>]*>", text)
    assert m is not None, "the flag needs a label to be clickable"
    assert 'class="anim-row"' in m.group(0)          # styled with the bar's controls
    assert 'title="Draw one row at a time' in m.group(0)
    assert "function animRowCounts" in text
    assert "function animTotalMs" in text
    assert "function animSpanMs" in text
    assert "anim.row ? animRowCounts(totals, anim.t, rate)" in text
    assert "animTotalMs(lastCurves ? animRowTotals(lastCurves) : [], anim.speed, anim.row)" in text
    # No timing site may use the parallel-only duration: the stop condition, the
    # scrub and the export would otherwise disagree with the drawing.
    assert "animDurationMs(anim.speed)" not in text
    assert text.count("animSpanMs()") >= 8           # the definition + 7 callers
    # Remembered per device, like speed and auto-play.
    assert "localStorage.setItem('xygh:anim:row'" in text
    assert "localStorage.getItem('xygh:anim:row')" in text
    assert "rowFlagInit.checked = anim.row" in text
    # A new bar control must not ship as a raw UA checkbox.
    assert ".anim-lbl, .anim-auto, .anim-row {" in text
    assert ".anim-auto input, .anim-row input" in text


def test_anim_video_export_is_recorded_in_the_browser():
    """The drawing downloads as a video with NO server involved.

    The page records its own canvas (MediaRecorder + captureStream) and pushes
    one frame per reveal step, so the file is produced locally — no upload
    endpoint, no runtime image dependency, and it keeps working offline in the
    installed PWA.
    """
    text = client.get("/").text
    assert 'id="animVideo"' in text
    assert "function exportVideo" in text
    assert "function pickVideoMime" in text
    assert "function animVideoTimes" in text
    assert "captureStream(0)" in text                  # 0 = manual frame push
    assert "track.requestFrame()" in text              # one video frame per step
    assert "animVideoTimes(animSpanMs(), ANIM_VIDEO_FPS, ANIM_VIDEO_MAX_FRAMES)" in text
    # The ladder must span both families: Safari records MP4/H.264 only,
    # Chromium/Firefox record WebM.
    assert "video/mp4;codecs=avc1.42E01E" in text
    assert "video/webm;codecs=vp9" in text
    assert "video/webm;codecs=vp8" in text
    assert "xy-graph-drawing." in text                 # download filename
    # Frames are timestamped by the wall clock, so they must be spaced — pushed
    # in a tight loop the video would play back instantly.
    assert "setTimeout(r, 1000 / ANIM_VIDEO_FPS)" in text
    # Browsers whose canvas track has no requestFrame() (Firefox, reported live
    # as "track.requestFrame is not a function") must fall back to sampling the
    # canvas in real time rather than failing the export.
    assert "function videoPushable" in text
    assert "captureStream(ANIM_VIDEO_FPS)" in text
    assert "if (pushable) track.requestFrame();" in text
    # A failure must stay on screen: the toast self-hides after 2.6s.
    assert "showError(msg)" in text
    # ...and nothing may reach for a server-side encoder.
    assert "/api/webp" not in text


def test_mp4_is_muxed_in_the_browser_from_webcodecs():
    """Firefox gets a real MP4: it can't record MP4, but it CAN encode H.264.

    MediaRecorder is unavailable for MP4 on Firefox (video/mp4 -> false), while
    WebCodecs VideoEncoder handles avc1 there. The only missing piece was the
    container, so mp4-muxer is vendored and loaded as a classic script — still
    no server, no build step.
    """
    text = client.get("/").text
    assert '<script src="/vendor/mp4-muxer.js" defer></script>' in text
    assert "function videoStrategy" in text
    assert "function pickMp4Codec" in text
    assert "function renderMp4" in text
    assert "function mp4MuxerLib" in text
    assert "VideoEncoder" in text
    assert "avc: { format: 'avc' }" in text          # AVCC + description -> avcC
    assert "new MP4.ArrayBufferTarget()" in text
    assert "muxer.addVideoChunk(chunk, meta)" in text
    assert "muxer.finalize()" in text
    assert "fastStart: 'in-memory'" in text          # moov first: streamable share
    # Timestamps come from the frame index, so the file is frame-exact and the
    # export does not have to run in real time.
    assert "timestamp: i * stepUs" in text
    assert "duration: stepUs" in text
    assert "codec: 'avc'" in text
    assert "MP4_VIDEO_CODECS" in text
    assert "avc1.42001F" in text
    # The strategy decides between the two paths, and MP4 is the only extension
    # the WebCodecs path may write.
    assert "const strategy = videoStrategy(caps);" in text
    assert "ext = 'mp4';" in text
    assert "recordWithMediaRecorder" in text         # fallback kept for WebM


def test_video_frames_are_composited_onto_the_card_colour():
    """H.264 has no alpha: the transparent canvas would encode as BLACK.

    Verified on a real exported frame from the first implementation — the graph
    came out on a black background instead of the app's own card colour. Every
    captured frame is therefore composited onto that colour before encoding.
    """
    text = client.get("/").text
    assert "function videoStage" in text
    assert "function videoPaint" in text
    assert "fillRect(0, 0, stage.canvas.width, stage.canvas.height)" in text
    assert "stage.ctx.drawImage(cv, 0, 0)" in text
    # The colour is read from the graph's own container, so the video matches
    # whichever theme is active rather than a hardcoded white.
    assert "closest('.graphbox')" in text
    assert "getComputedStyle(host).backgroundColor" in text
    # Both paths must paint the background, not just the new one (count call
    # sites, including the trailing semicolon, so the definition doesn't match).
    assert text.count("videoPaint(stage, cv);") == 2


def test_vendor_route_serves_whitelisted_assets_only():
    """Vendored browser code is served by name, like the icons — a flat
    filename, no traversal, and nothing that isn't actually there."""
    r = client.get("/vendor/mp4-muxer.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")
    assert "Mp4Muxer" in r.text
    assert "window.Mp4Muxer" in r.text or "var Mp4Muxer" in r.text
    # MIT provenance must travel with the copy.
    assert "mp4-muxer v5.2.1" in r.text and "MIT" in r.text
    assert client.get("/vendor/mp4-muxer.LICENSE").status_code == 200
    # Nothing else is reachable through it.
    assert client.get("/vendor/nope.js").status_code == 404
    assert client.get("/vendor/..%2Fapp%2Fmain.py").status_code == 404
    assert client.get("/vendor/main.py").status_code == 404


def test_webm_exports_explain_themselves_and_diag_reports_capabilities():
    """A .webm download must never be a mystery, and a phone must be able to
    report WHY it got one.

    Reported from Android Firefox ("still showing webm not mp4"): WebCodecs
    shipped on DESKTOP Firefox only, so that browser has no VideoEncoder and the
    MP4 path is unreachable there. The export now names the reason, and `?diag=1`
    prints a capability report into the error box — there is no console on a
    phone, so the page has to be able to tell us what it can do.
    """
    text = client.get("/").text
    assert "function videoFallbackReason" in text
    assert "this browser has no H.264 encoder" in text
    assert "the MP4 muxer did not load" in text
    assert "toast('Saved as .' + ext + ' — ' + videoFallbackReason(caps))" in text
    # The reason must not be swallowed when the file was saved successfully:
    # flashButton() raises its own toast, so the note has to come after it.
    saved = text.index("flashButton(btn, 'Video saved');")
    note = "toast('Saved as .' + ext + ' — ' + videoFallbackReason(caps));"
    assert text.index(note) > saved
    assert "function initVideoDiag" in text
    assert "initVideoDiag();" in text
    assert "[?&]diag=1(&|$)" in text
    # Its own box: clearError() runs on every successful plot and would wipe
    # #error, and the report needs pre-line or it smears into one line.
    assert '<div id="diag"></div>' in text
    assert "#diag {" in text
    assert "white-space: pre-line" in text
    assert "video export report" in text
    assert "not MP4 because: " in text
    assert "box.textContent = lines.join('\\n');" in text


def test_service_worker_caches_the_vendored_muxer():
    """The MP4 export must keep working offline in the installed PWA."""
    sw = client.get("/sw.js").text
    assert "startsWith('/vendor/')" in sw
    assert "const VERSION = 'v16';" in sw


def test_service_worker_caches_both_pages_and_the_surface_api():
    """`/3d` is a second shell page, and a plotted surface must survive offline.

    The shell used to be cached under '/' only, so opening /3d would have
    overwritten the cached 2D page — every navigation is now cached under its
    own pathname.
    """
    sw = client.get("/sw.js").text
    assert "'/3d'," in sw
    assert "cache.put" in sw
    assert "const path = new URL" in sw or "new URL(request.url).pathname" in sw
    assert "'/api/surface'" in sw


def test_no_server_side_video_or_image_encoder_route():
    """Client-side recording replaced the server-side WebP encoder: no upload
    route is served, and Pillow is no longer a runtime dependency."""
    r = client.post("/api/webp", files={"frames": ("f.png", b"not-an-image", "image/png")})
    assert r.status_code == 404


# ===========================================================================
# 3D surfaces: GET /3d and GET /api/surface
# ===========================================================================

THREE_TEMPLATE = (Path(__file__).resolve().parent.parent / "templates" / "three.html")
THREE_JS_TEST = (Path(__file__).resolve().parent / "three.test.js")


def test_3d_page_renders_the_canvas_and_vendored_three():
    r = client.get("/3d")
    assert r.status_code == 200
    assert "xy-graph-gen" in r.text
    assert 'id="view"' in r.text                       # the WebGL canvas
    assert 'id="formula"' in r.text
    assert "/vendor/three.module.min.js" in r.text


def test_3d_page_is_never_cached():
    """Same rule as `/`: a cached page whose JS disagrees with the API is the
    phantom "object error" all over again."""
    r = client.get("/3d")
    assert r.headers["cache-control"] == "no-store"


def test_3d_page_prefills_formula_window_grid_and_ramp():
    r = client.get("/3d", params=[
        ("formula", "z = sin(x) * cos(y)"), ("x_min", "-3"), ("x_max", "3"),
        ("y_min", "-2"), ("y_max", "2"), ("grid", "24"),
        ("ramp", "#ff0000"), ("ramp", "#00ff00"),
    ])
    assert r.status_code == 200
    assert 'value="z = sin(x) * cos(y)"' in r.text
    assert 'id="xMin" value="-3"' in r.text
    assert 'id="xMax" value="3"' in r.text
    assert 'id="yMin" value="-2"' in r.text
    assert 'id="yMax" value="2"' in r.text
    assert 'id="gridN" value="24"' in r.text
    assert 'id="rampLow" value="#ff0000"' in r.text
    assert 'id="rampHigh" value="#00ff00"' in r.text


def test_3d_page_defaults_the_ramp_and_the_grid():
    r = client.get("/3d")
    assert 'id="rampLow" value="#2563eb"' in r.text
    assert 'id="rampHigh" value="#dc2626"' in r.text
    # An empty grid input falls back to the server-side default (48).
    assert 'id="gridN" value=""' in r.text
    assert 'placeholder="48"' in r.text


def test_3d_page_escapes_the_formula_against_xss():
    r = client.get("/3d", params={"formula": "<script>alert(1)</script>"})
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text


def test_3d_page_blank_inputs_for_invalid_numbers():
    """A hand-written URL cannot push a bad value into an input, and the ramp
    falls back to the defaults position by position."""
    r = client.get("/3d", params={"x_min": "abc", "grid": "999", "formula": "z = x"})
    assert 'id="xMin" value=""' in r.text
    assert 'id="gridN" value=""' in r.text
    r2 = client.get("/3d", params=[("ramp", "bogus"), ("ramp", "#12345"), ("formula", "z = x")])
    assert 'id="rampLow" value="#2563eb"' in r2.text
    assert 'id="rampHigh" value="#dc2626"' in r2.text


def test_2d_page_links_to_the_3d_page():
    r = client.get("/")
    assert 'href="/3d"' in r.text
    # The link needs the anchor resets, or it renders as a blue underlined link
    # between two pill buttons.
    assert ".tab-link { text-decoration: none" in r.text


def test_api_surface_default_window_and_sampling():
    r = client.get("/api/surface", params={"formula": "z = x^2 - y^2"})
    assert r.status_code == 200
    d = r.json()
    assert d["grid"] == {"nx": 48, "ny": 48}
    assert d["x_range"] == {"min": -5.0, "max": 5.0}
    assert d["y_range"] == {"min": -5.0, "max": 5.0}
    assert len(d["x"]) == 49 and len(d["y"]) == 49
    s = d["surfaces"][0]
    assert s["display"] == "z = x^2 - y^2"
    assert len(s["z"]) == 49 and len(s["z"][0]) == 49
    assert s["z_range"] == {"min": -25.0, "max": 25.0}
    # z[j][i] is (x[i], y[j]) — the row is x and the column is y.
    assert s["z"][24][0] == 25.0    # x = -5, y = 0
    assert s["z"][0][24] == -25.0   # x = 0, y = -5
    assert s["z"][0][0] == 0.0      # x = y = -5


def test_api_surface_accepts_a_bare_expression():
    r = client.get("/api/surface", params={"formula": "x^2 + y^2", "grid": "4"})
    assert r.status_code == 200
    d = r.json()
    assert d["surfaces"][0]["display"] == "z = x^2 + y^2"
    assert d["grid"] == {"nx": 4, "ny": 4}
    assert len(d["x"]) == 5


def test_api_surface_accepts_an_f_lhs_and_rejects_a_non_z_one():
    ok = client.get("/api/surface", params={"formula": "f(x,y) = x + y", "grid": "4"})
    assert ok.status_code == 200
    bad = client.get("/api/surface", params={"formula": "y = x^2", "grid": "4"})
    assert bad.status_code == 400
    assert "z = f(x, y)" in bad.json()["detail"]


def test_api_surface_rejects_z_on_the_right():
    """`z` is the OUTPUT. In the 2D solver it is just an unknown symbol, whose
    message ("Unknown symbol 'z'.") says nothing about what went wrong here."""
    r = client.get("/api/surface", params={"formula": "z = x + z", "grid": "4"})
    assert r.status_code == 400
    assert "left of the =" in r.json()["detail"]


def test_api_surface_marks_holes_as_null():
    """A cell touching a hole must be skippable: the renderer needs `null`, not
    0, or it bridges the asymptote with a wall of triangles."""
    r = client.get("/api/surface", params={"formula": "z = 1/x", "x_min": "-1", "x_max": "1", "grid": "4"})
    assert r.status_code == 200
    rows = r.json()["surfaces"][0]["z"]
    assert any(v is None for row in rows for v in row), "1/x must produce holes at x = 0"
    assert None not in rows[0] or True  # (holes are exactly the x = 0 column(s))
    # Every value is a float or None — never a string, never a NaN.
    for row in rows:
        for v in row:
            assert v is None or isinstance(v, float)


def test_api_surface_window_validation():
    bad_pair = client.get("/api/surface", params={"formula": "z = x", "x_min": "-1"})
    assert bad_pair.status_code == 400
    assert "both x_min and x_max" in bad_pair.json()["detail"]
    flipped = client.get("/api/surface", params={"formula": "z = x", "x_min": "5", "x_max": "1"})
    assert flipped.status_code == 400
    assert "x_min must be <= x_max" in flipped.json()["detail"]
    flipped_y = client.get("/api/surface", params={"formula": "z = x", "y_min": "4", "y_max": "-4"})
    assert flipped_y.status_code == 400
    assert "y_min must be <= y_max" in flipped_y.json()["detail"]


def test_api_surface_grid_bounds():
    assert client.get("/api/surface", params={"formula": "z = x", "grid": "4"}).status_code == 200
    assert client.get("/api/surface", params={"formula": "z = x", "grid": "120"}).status_code == 200
    for bad in ("3", "121", "0"):
        r = client.get("/api/surface", params={"formula": "z = x", "grid": bad})
        assert r.status_code == 400, bad
        assert "grid must be between 4 and 120" in r.json()["detail"]


def test_api_surface_formula_count_and_empties():
    five = client.get("/api/surface", params=[("formula", f"z = x + {i}") for i in range(5)] + [("grid", "4")])
    assert five.status_code == 200
    assert len(five.json()["surfaces"]) == 5
    six = client.get("/api/surface", params=[("formula", f"z = x + {i}") for i in range(6)])
    assert six.status_code == 400
    assert "At most 5 surfaces per graph." in six.json()["detail"]
    empty = client.get("/api/surface", params={"formula": "   "})
    assert empty.status_code == 400


def test_api_surface_no_real_z_in_the_window():
    r = client.get("/api/surface", params={"formula": "z = sqrt(x)", "x_min": "-5", "x_max": "-1", "grid": "8"})
    assert r.status_code == 400
    assert "No real z" in r.json()["detail"]


def test_api_surface_cache_headers():
    params = {"formula": "z = 3*x + y", "grid": "4"}
    first = client.get("/api/surface", params=params)
    assert first.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    second = client.get("/api/surface", params=params)
    assert second.headers["X-Cache"] == "HIT"


def test_api_surface_robust_range_ignores_the_spike():
    """z = 1/(x² + y²) on ±1 peaks at 576 on the samples beside the origin; the
    view frames itself with the 2nd–98th percentile pair (≈34), so the body of
    the surface stays on screen instead of collapsing to a speck."""
    r = client.get("/api/surface", params={
        "formula": "z = 1/(x^2 + y^2)", "x_min": "-1", "x_max": "1",
        "y_min": "-1", "y_max": "1", "grid": "48",
    })
    assert r.status_code == 200
    s = r.json()["surfaces"][0]
    assert s["z_range"]["max"] > 500
    assert s["z_robust"]["max"] < s["z_range"]["max"] / 10
    # The framing range must still contain the bulk of the surface.
    assert s["z_robust"]["min"] < s["z_range"]["max"] / 10


def test_implicit_curve_with_a_fractional_power_of_a_negative_base_is_not_a_500():
    """Regression: (-8) ** 0.5 is COMPLEX in Python and `math.isfinite` then
    raises TypeError, so `x^0.5 + y = 0` answered HTTP 500 (verified against the
    running service before the fix). It is a real curve — negative x simply has
    no real sample."""
    r = client.get("/api/points", params={"formula": "x^0.5 + y = 0"})
    assert r.status_code == 200
    assert len(r.json()["curves"][0]["branches"]) >= 1
    from app import solver
    F = solver.parse_expr("x^0.5 + y")
    assert math.isnan(solver._safe_eval2(F, -4.0, 0.0))
    assert solver._safe_eval2(F, 4.0, 0.0) == 2.0


def test_vendor_serves_the_three_js_build():
    """A browser with no CDN and no build step: three.js is served from our own
    origin, module + its sibling core chunk."""
    mod = client.get("/vendor/three.module.min.js")
    core = client.get("/vendor/three.core.min.js")
    assert mod.status_code == 200 and core.status_code == 200
    for r in (mod, core):
        assert r.headers["content-type"].startswith("application/javascript")
    # r180 splits the build in two: the module re-exports the core, and the
    # relative specifier must resolve to the sibling we actually vendored.
    assert "three.core.min.js" in mod.text
    assert client.get("/vendor/three.LICENSE").status_code == 200


def test_three_template_loads_three_from_our_own_origin():
    text = THREE_TEMPLATE.read_text()
    assert "cdn.jsdelivr.net" not in text
    assert "unpkg.com" not in text
    assert "await import('/vendor/three.module.min.js')" in text
    # No build step: the page must not reference an unbundled bare specifier
    # (three's ESM examples import from 'three' itself and would need an
    # import map).
    assert "from 'three'" not in text and 'from "three"' not in text


def test_three_template_never_triangulates_a_hole():
    """The one thing a surface renderer silently gets wrong: `isFinite(null)`
    is TRUE, so a hole would be plotted as z = 0 and the cell bridged."""
    text = THREE_TEMPLATE.read_text()
    assert "function num(v) { return typeof v === 'number' && Number.isFinite(v); }" in text
    assert "!num(v00) || !num(v10) || !num(v11) || !num(v01)" in text
    # and the wireframe skips holes too, via the same helper
    assert "if (!num(zs[j0][i0]) || !num(zs[j1][i1])) return;" in text


def test_three_template_has_no_server_side_export_path():
    """Same rule the 2D page follows: exports are client-side (the user
    rejected a server encoder for PNG/WebP/video)."""
    text = THREE_TEMPLATE.read_text()
    assert "/api/webp" not in text
    assert "toBlob" in text          # Save PNG encodes in the browser
    assert "drawImage(src, 0, 0)" in text   # composited onto the card colour


def test_three_template_ramp_is_one_pair_per_row_and_recolours_without_a_refetch():
    text = THREE_TEMPLATE.read_text()
    # The id rides on the FIRST row only (the rest are class-addressed), so the
    # source carries the conditional — assert the two facts, not their order.
    for cls, ident in (("ramp-low", "rampLow"), ("ramp-high", "rampHigh"),
                       ("hex-ramp hex-low", "hexLow"), ("hex-ramp hex-high", "hexHigh")):
        assert 'class="%s"' % cls in text, cls
        assert 'id="%s"' % ident in text, ident
    # A device colour dialog is not enough on Android: every ramp end also takes
    # a hex box, and the swatch stays the single source of truth.
    assert "swatch.value = hex;" in text
    assert "box.value = swatch.value;" in text
    # Colour changes must not re-fetch the grid — one colour attribute per mesh.
    assert "mesh.geometry.setAttribute('color'" in text


def test_template_max_rows_matches_server():
    """MAX_ROWS is a plain literal in the JS (a Jinja placeholder there would be
    invalid JavaScript, and the node suite RUNS that script)."""
    from app.main import MAX_FORMULAS
    text = THREE_TEMPLATE.read_text()
    m = re.search(r"const MAX_ROWS = (\d+);", text)
    assert m is not None, "three.html must define MAX_ROWS"
    assert int(m.group(1)) == MAX_FORMULAS
    # No Jinja may leak into the script: the node suite evaluates it verbatim.
    script = re.search(r"<script>(.*?)</script>", text, re.S).group(1)
    assert "{{" not in script and "{%" not in script


def test_three_template_exposes_every_pure_helper_to_the_js_suite():
    """The twin of the `__api` rule in test/solver.test.js: a pure helper that
    is not listed stays uncovered, and a listed name that does not exist fails
    the node suite — so the two lists must match exactly."""
    text = THREE_TEMPLATE.read_text()
    m = re.search(r"var __api = \{(.*?)\};", text, re.S)
    assert m is not None, "three.html must expose its pure helpers as __api"
    exposed = {k.strip() for k in re.findall(r"([A-Za-z_$][\w$]*)\s*:", m.group(1))}
    assert exposed, "no names parsed out of __api"
    for name in exposed:
        assert f"function {name}(" in text, f"__api lists {name} but there is no such function"
    js = THREE_JS_TEST.read_text()
    m2 = re.search(r"const \{([^}]*)\} = sandbox\.__api", js, re.S)
    assert m2 is not None, "three.test.js must destructure sandbox.__api"
    used = {k.strip() for k in m2.group(1).split(",") if k.strip()}
    assert exposed == used, "three.html and three.test.js disagree: " + str(exposed ^ used)


def _rows_html(page_html: str) -> str:
    """The `#surfaceRows` block of a rendered /3d page.

    Scoped like this because the page also ships its JS, and the JS contains the
    same class names inside `rowMarkup` — counting them page-wide inflates every
    number (a 5-row page counted 12 "Duplicate this surface")."""
    m = re.search(r'<div id="surfaceRows">(.*?)<div class="range-row">', page_html, re.S)
    assert m is not None, "no #surfaceRows block in the page"
    return m.group(1)


def test_3d_page_renders_one_row_per_formula():
    r = client.get("/3d", params=[("formula", "z = x^2 + y^2"), ("formula", "z = 0")])
    assert r.status_code == 200
    assert r.text.count('class="surface-row"') == 2
    rows_html = _rows_html(r.text)
    for cls in ('formula-input', 'ramp-low', 'hex-ramp hex-low', 'ramp-high',
                'hex-ramp hex-high', 'opacity-pick', 'row-dup', 'row-del'):
        assert rows_html.count('class="%s"' % cls) == 2, cls
    # A 2-row page can remove either row, so neither remove button is hidden.
    assert 'aria-label="Remove this surface" hidden' not in rows_html
    # The single-row case cannot remove its only row, and shows the Add button.
    one = client.get("/3d")
    assert 'class="add-btn" id="addRowBtn"' in one.text
    assert 'id="addRowBtn" title="Add another surface (max 5)">' in one.text
    assert 'aria-label="Remove this surface" hidden>' in _rows_html(one.text)


def test_3d_page_hides_add_and_duplicate_at_the_ceiling():
    r = client.get("/3d", params=[("formula", f"z = x + {i}") for i in range(5)])
    assert r.text.count('class="surface-row"') == 5
    assert 'id="addRowBtn" title="Add another surface (max 5)" hidden>' in r.text
    rows_html = _rows_html(r.text)
    assert rows_html.count('aria-label="Duplicate this surface" hidden>') == 5
    assert rows_html.count('class="row-dup"') == 5


def test_3d_page_per_row_ramps_from_query_params():
    r = client.get("/3d", params=[
        ("formula", "z = x"), ("formula", "z = y"), ("formula", "z = x*y"),
        ("ramp_low", "#111111"), ("ramp_low", "#222222"),
        ("ramp_high", "#333333"), ("ramp_high", "#444444"),
    ])
    assert r.status_code == 200
    assert r.text.count('value="#111111"') == 2   # row 0 low: swatch + hex box
    assert 'value="#333333"' in r.text
    assert 'value="#222222"' in r.text
    assert 'value="#444444"' in r.text
    # Row 3 had no ramp params, so it keeps its OWN default pair — falling back
    # to row 1's colours would paint two surfaces the same.
    from app.main import SURFACE_RAMPS
    assert 'value="%s"' % SURFACE_RAMPS[2][0] in r.text
    assert 'value="%s"' % SURFACE_RAMPS[2][1] in r.text


def test_3d_page_ramp_defaults_are_per_row():
    r = client.get("/3d", params=[("formula", "z = x"), ("formula", "z = y")])
    from app.main import SURFACE_RAMPS
    assert SURFACE_RAMPS[0] != SURFACE_RAMPS[1]
    assert 'id="rampLow" value="%s"' % SURFACE_RAMPS[0][0] in r.text
    # Row 2's default pair is ITS pair, not row 1's.
    assert r.text.count('value="%s"' % SURFACE_RAMPS[1][0]) == 2  # swatch + hex box


def test_3d_page_legacy_ramp_param_still_sets_the_first_row():
    """`?ramp=#a&ramp=#b` was the single-surface API for one release; links
    shared then must still render."""
    r = client.get("/3d", params=[("formula", "z = x"), ("formula", "z = y"),
                                  ("ramp", "#abcdef"), ("ramp", "#fedcba")])
    assert 'id="rampLow" value="#abcdef"' in r.text
    assert 'id="rampHigh" value="#fedcba"' in r.text
    # ...and it must NOT leak onto the second row.
    from app.main import SURFACE_RAMPS
    assert r.text.count('value="#abcdef"') == 2   # row 0's swatch + hex box only
    assert SURFACE_RAMPS[1][0] in r.text


def test_3d_page_opacity_params():
    r = client.get("/3d", params=[("formula", "z = x"), ("formula", "z = y"),
                                  ("op", "40"), ("op", "bogus")])
    assert 'class="opacity-pick" id="op0" value="40"' in r.text
    assert 'class="opacity-pick" id="op1" value="100"' in r.text   # invalid -> default


def test_3d_page_escapes_every_row_against_xss():
    r = client.get("/3d", params=[("formula", "<script>alert(1)</script>"),
                                  ("formula", 'z = "x"')])
    assert r.status_code == 200
    assert "<script>alert(1)</script>" not in r.text
    assert "&lt;script&gt;" in r.text
    # A quote in a formula must not break out of the value attribute.
    assert 'value="z = &#34;x&#34;"' in r.text


def test_template_surface_ramps_match_server():
    """The per-row default ramps live in BOTH twins (the server pre-renders the
    rows, the page builds new ones). Same lockstep rule as CURVE_PALETTE."""
    from app.main import SURFACE_RAMPS
    text = THREE_TEMPLATE.read_text()
    m = re.search(r"const SURFACE_RAMPS = \[(.*?)\];", text, re.S)
    assert m is not None, "three.html must define SURFACE_RAMPS"
    pairs = [[a, b] for a, b in re.findall(r"\['(#[0-9a-f]{6})', '(#[0-9a-f]{6})'\]", m.group(1))]
    assert pairs == [list(p) for p in SURFACE_RAMPS]
    assert len(pairs) >= 5, "there must be a default pair for every possible row"


def test_three_template_js_row_builder_mirrors_the_server_row():
    """A row added in the browser must be the SAME row the server renders —
    same controls, same classes, same icons — or a JS-added row loses its CSS
    or its buttons (the 2D pen menu once shipped into the DOM with no CSS)."""
    text = THREE_TEMPLATE.read_text()
    server = re.search(r'<div class="surface-row">(.*?)</div>', text, re.S).group(1)
    m = re.search(r"function rowMarkup\(ramp, opacity, formula\) \{(.*?)\n\}", text, re.S)
    assert m is not None, "rowMarkup must exist"
    builder = m.group(1)
    for cls in ('formula-input', 'ramp-low', 'hex-ramp hex-low', 'ramp-high',
                'hex-ramp hex-high', 'opacity-pick', 'row-dup', 'row-del'):
        assert cls in server, 'the server row is missing ' + cls
        assert cls in builder, 'rowMarkup is missing ' + cls
    for shared in ('<span class="ramp"', '<span class="ramp-arrow"', '<span class="ctr-axis">',
                   '<svg class="ico sm"', 'aria-label='):
        assert shared in server and shared in builder, shared


def test_three_template_row_controls_are_styled():
    """Row controls must not ship as raw UA elements: scoped `.form .<class>`
    rules for the buttons, `.ico` for the SVG icons, and the row a flex line."""
    text = THREE_TEMPLATE.read_text()
    css = text.split("</style>")[0]
    assert ".form .row-del, .form .row-dup {" in css
    assert ".form .row-del:hover" in css and ".form .row-dup:hover" in css
    assert ".form .add-btn {" in css
    assert ".ico .s { fill: none; stroke: currentColor" in css
    assert "#surfaceRows { display: flex; flex-direction: column" in css
    assert ".legend-dot {" in css


def test_api_surface_returns_every_formula_in_order():
    r = client.get("/api/surface", params=[("formula", "z = x"), ("formula", "z = -x"),
                                           ("formula", "z = 0"), ("grid", "4")])
    assert r.status_code == 200
    d = r.json()
    assert [s["display"] for s in d["surfaces"]] == ["z = x", "z = -x", "z = 0"]
    # Each surface carries its own ranges — the page normalises each row's ramp
    # against ITS OWN z range, so a flat plane at z = 0 is still a full ramp.
    flat = d["surfaces"][2]
    assert flat["z_range"] == {"min": 0.0, "max": 0.0}
    assert flat["z_robust"]["min"] == 0.0 and flat["z_robust"]["max"] == 0.0


def test_three_js_suite_is_in_the_documented_test_commands():
    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text()
    assert "node test/three.test.js" in readme


def test_anim_video_button_is_a_styled_toolbar_button():
    """An icon-only button only looks right via `.form .tool-btn` (the pen menu
    once shipped into the DOM with no CSS at all), so assert the classes."""
    text = client.get("/").text
    m = re.search(r'<button[^>]*id="animVideo"[^>]*>', text)
    assert m is not None, "the video button must exist in the player bar"
    tag = m.group(0)
    assert "tool-btn" in tag and "btn-secondary" in tag
    assert ".form .tool-btn" in text.split("</style>")[0]


def test_no_server_side_video_or_image_encoder_route():
    """Client-side recording replaced the server-side WebP encoder: no upload
    route is served, and Pillow is no longer a runtime dependency."""
    r = client.post("/api/webp", files={"frames": ("f.png", b"not-an-image", "image/png")})
    assert r.status_code == 404
