"""Unit tests for the server-side solver (app/solver.py).

Mirrors test/solver.test.js — the two must stay in agreement.
"""

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
    assert sol["display"] == "y = \u2212x + 3"
    assert sol["poly"] == {0: 3.0, 1: -1.0}
    assert sol["denom"] == 1.0


def test_user_example_values():
    sol = solver.solve_equation("x + y = 3")
    assert solver.eval_poly(sol["poly"], 1) / sol["denom"] == 2
    assert solver.eval_poly(sol["poly"], 3) / sol["denom"] == 0
    assert solver.eval_poly(sol["poly"], 100) / sol["denom"] == -97


def test_generate_points_default_range():
    display, pts = solver.generate_points("x + y = 3")
    assert display == "y = \u2212x + 3"
    assert len(pts) == 100
    assert pts[0] == (1, 2.0)
    assert pts[2] == (3, 0.0)
    assert pts[99] == (100, -97.0)


# --- other shapes ---
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
def test_solve_display(raw, display):
    assert solver.solve_equation(raw)["display"] == display


# --- error cases ---
@pytest.mark.parametrize(
    "raw,needle",
    [
        ("x = 5", "no effective y term"),
        ("x + y = 3 = 4", 'Only one "="'),
        ("y = (x)", "Parentheses"),
        ("y^2 = x", "linear in y"),
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


def test_custom_range():
    _, pts = solver.generate_points("y = 2x", x_min=1, x_max=5)
    assert [y for _, y in pts] == [2.0, 4.0, 6.0, 8.0, 10.0]


def test_bad_range():
    with pytest.raises(solver.SolverError, match="x_min must be <= x_max"):
        solver.generate_points("y = x", x_min=10, x_max=5)


def test_fmt():
    assert solver.fmt(2.0) == "2"
    assert solver.fmt(-97.0) == "-97"
    assert solver.fmt(0.5) == "0.5"
    assert solver.fmt(-0.0) == "0"
    assert solver.fmt(1.3333333333333333) == "1.33333333333"
