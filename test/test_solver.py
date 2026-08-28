"""Unit tests for the server-side solver (app/solver.py).

Mirrors test/solver.test.js — the two must stay in agreement.
"""

import math

import pytest

from app import solver


# --- regression: bare x / y terms must get implicit coefficient 1 ---
@pytest.mark.parametrize(
    "term,coeff,var,exp",
    [
        ("x", 1.0, "x", 1),
        ("-y", -1.0, "y", 1),
        ("2x", 2.0, "x", 1),
        ("x^3", 1.0, "x", 3),
        ("0.5x", 0.5, "x", 1),
        ("-2y^1", -2.0, "y", 1),
    ],
)
def test_parse_term(term, coeff, var, exp):
    t = solver.parse_term(term)
    assert t == {"coeff": coeff, "var": var, "exp": exp}


def test_parse_term_garbage():
    assert solver.parse_term("@#$") is None


# --- the user's example: x + y = 3  =>  y = 3 - x ---
def test_user_example_solves():
    sol = solver.solve_equation("x + y = 3")
    assert sol["kind"] == "linear"
    assert sol["display"] == "y = \u2212x + 3"
    assert sol["poly"] == {0: 3.0, 1: -1.0}
    assert sol["denom"] == 1.0


def test_user_example_values():
    sol = solver.solve_equation("x + y = 3")
    assert solver.eval_poly(sol["poly"], 1) / sol["denom"] == 2
    assert solver.eval_poly(sol["poly"], 3) / sol["denom"] == 0
    assert solver.eval_poly(sol["poly"], 100) / sol["denom"] == -97


def test_generate_points_default_range_linear():
    result = solver.generate_points("x + y = 3")
    assert result["solution"]["display"] == "y = \u2212x + 3"
    assert result["x_range"] == (1, 100)
    assert len(result["branches"]) == 1
    pts = result["branches"][0]["points"]
    assert len(pts) == 100
    assert pts[0] == (1, 2.0)
    assert pts[2] == (3, 0.0)
    assert pts[99] == (100, -97.0)


# --- other linear shapes ---
@pytest.mark.parametrize(
    "raw,display",
    [
        ("y = 2x + 1", "y = 2x + 1"),
        ("2x + 3y = 6", "y = (\u22122x + 6) / 3"),
        ("x + y = -3", "y = \u2212x \u2212 3"),
        ("y = 3 - x", "y = \u2212x + 3"),
        ("3 - x", "y = \u2212x + 3"),  # bare expr treated as y = ...
        ("y = 4", "y = 4"),
        ("y = x^2 - 10x + 10", "y = x^2 \u2212 10x + 10"),
        ("y = x \u2212 2", "y = x \u2212 2"),  # unicode minus
        ("-y + x = 2", "y = x \u2212 2"),
        ("y - x = 1", "y = x + 1"),
        ("0.5x + y = 2", "y = \u22120.5x + 2"),
    ],
)
def test_linear_display(raw, display):
    sol = solver.solve_equation(raw)
    assert sol["kind"] == "linear"
    assert sol["display"] == display


# --- quadratic in y: circles and friends ---
def test_circle_solves():
    sol = solver.solve_equation("x^2 + y^2 = 100")
    assert sol["kind"] == "quadratic"
    assert sol["a"] == 1.0
    assert sol["b"] == 0.0
    assert sol["poly"] == {0: 100.0, 2: -1.0}
    assert sol["display"] == "y = \u00b1\u221a(\u2212x^2 + 100)"


def test_circle_points_and_auto_range():
    result = solver.generate_points("x^2 + y^2 = 100")
    assert result["x_range"] == (-10, 10)
    assert len(result["branches"]) == 2
    plus = result["branches"][0]
    minus = result["branches"][1]
    assert plus["label"] == "+"
    assert minus["label"] == "\u2212"
    assert len(plus["points"]) == 21  # x = -10..10
    assert len(minus["points"]) == 21
    by_x = {x: y for x, y in plus["points"]}
    assert by_x[0] == 10.0
    assert by_x[6] == 8.0
    assert by_x[10] == 0.0
    m_by_x = {x: y for x, y in minus["points"]}
    assert m_by_x[0] == -10.0
    assert m_by_x[6] == -8.0


def test_circle_explicit_range_respected():
    result = solver.generate_points("x^2 + y^2 = 100", x_min=1, x_max=10)
    assert result["x_range"] == (1, 10)
    plus = result["branches"][0]["points"]
    assert plus[0] == (1, math.sqrt(99))  # x=1 -> y=+√99
    assert len(plus) == 10


@pytest.mark.parametrize(
    "raw,display,x_range",
    [
        ("y^2 = 4x", "y = \u00b1\u221a(4x)", (0, 200)),
        ("2y^2 = x^2 + 8", "y = \u00b1\u221a((x^2 + 8) / 2)", (-100, 100)),
        ("y^2 - x^2 = 1", "y = \u00b1\u221a(x^2 + 1)", (-100, 100)),
        ("y^2 + y = x", "y = (\u22121 \u00b1 \u221a(1 + 4x)) / 2", (0, 200)),
    ],
)
def test_quadratic_variants(raw, display, x_range):
    result = solver.generate_points(raw)
    assert result["solution"]["display"] == display
    assert result["x_range"] == x_range
    assert len(result["branches"]) == 2


def test_quadratic_general_formula_values():
    # y² + y = x  →  at x=0: y = (−1 ± 1)/2 = 0 and −1
    result = solver.generate_points("y^2 + y = x")
    plus = {x: y for x, y in result["branches"][0]["points"]}
    minus = {x: y for x, y in result["branches"][1]["points"]}
    assert plus[0] == 0.0
    assert minus[0] == -1.0


def test_quadratic_no_real_points_raises():
    with pytest.raises(solver.SolverError, match="No real y"):
        solver.generate_points("y^2 = -1")


def test_quadratic_no_real_points_in_explicit_range():
    with pytest.raises(solver.SolverError, match="No real y"):
        solver.generate_points("x^2 + y^2 = 100", x_min=50, x_max=60)


# --- error cases ---
@pytest.mark.parametrize(
    "raw,needle",
    [
        ("x = 5", "no effective y term"),
        ("x + y = 3 = 4", 'Only one "="'),
        ("y = (x)", "Parentheses"),
        ("y^3 = x", "linear or quadratic in y"),
        ("x = ", "Both sides"),
        ("= 3", "Both sides"),
        ("y = @#$", "Cannot understand"),
        ("   ", "Enter a formula"),
    ],
)
def test_solve_errors(raw, needle):
    with pytest.raises(solver.SolverError) as exc:
        solver.solve_equation(raw)
    assert needle in str(exc.value)


def test_custom_range_linear():
    result = solver.generate_points("y = 2x", x_min=1, x_max=5)
    assert [y for _, y in result["branches"][0]["points"]] == [2.0, 4.0, 6.0, 8.0, 10.0]


def test_explicit_step_linear():
    result = solver.generate_points("y = 2x", x_min=1, x_max=10, x_step=2)
    assert result["step"] == 2
    assert [x for x, _ in result["branches"][0]["points"]] == [1, 3, 5, 7, 9]


def test_explicit_step_quadratic():
    result = solver.generate_points("x^2 + y^2 = 100", x_min=-10, x_max=10, x_step=5)
    assert result["step"] == 5
    plus = result["branches"][0]["points"]
    assert [x for x, _ in plus] == [-10, -5, 0, 5, 10]
    assert {x: y for x, y in plus}[0] == 10.0


def test_step_with_auto_range():
    result = solver.generate_points("x^2 + y^2 = 100", x_step=2)
    assert result["step"] == 2
    assert result["x_range"] == (-10, 10)
    assert [x for x, _ in result["branches"][0]["points"]] == [-10, -8, -6, -4, -2, 0, 2, 4, 6, 8, 10]


@pytest.mark.parametrize("step", [0, -3, 1001])
def test_step_out_of_bounds(step):
    with pytest.raises(solver.SolverError, match="x_step must be between 1 and 1000"):
        solver.generate_points("y = x", x_min=1, x_max=10, x_step=step)


def test_partial_range_rejected():
    with pytest.raises(solver.SolverError, match="both x_min and x_max"):
        solver.generate_points("y = x", x_min=1)
    with pytest.raises(solver.SolverError, match="both x_min and x_max"):
        solver.generate_points("y = x", x_max=10)


def test_range_too_large_rejected():
    with pytest.raises(solver.SolverError, match="Range too large"):
        solver.generate_points("y = x", x_min=1, x_max=1_000_000)


def test_bad_range():
    with pytest.raises(solver.SolverError, match="x_min must be <= x_max"):
        solver.generate_points("y = x", x_min=10, x_max=5)


def test_fmt():
    assert solver.fmt(2.0) == "2"
    assert solver.fmt(-97.0) == "-97"
    assert solver.fmt(0.5) == "0.5"
    assert solver.fmt(-0.0) == "0"
    assert solver.fmt(1.3333333333333333) == "1.33333333333"
