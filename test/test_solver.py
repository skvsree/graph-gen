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
        ("x + y = 3 = 4", 'Only one "="'),
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


# --- P3-1: implicit curves (F(x, y) = 0 via grid sampling) ---
@pytest.mark.parametrize(
    "raw,display",
    [
        ("x = 5", "x = 5"),                    # vertical line
        ("y^3 = x", "y^3 = x"),                # cubic — not solvable for y
        ("(x+1)^2 + y^2 = 100", "(x+1)^2+y^2 = 100"),  # shifted circle
        ("x^2 + y^3 = 7", "x^2+y^3 = 7"),
        ("x*y = 4", "x*y = 4"),                # hyperbola
        ("x^3 + y^3 = 6xy", "x^3+y^3 = 6xy"),  # folium of Descartes
        ("sin(x) + sin(y) = 1", "sin(x)+sin(y) = 1"),
    ],
)
def test_implicit_solve(raw, display):
    sol = solver.solve_equation(raw)
    assert sol["kind"] == "implicit"
    assert sol["display"] == display
    assert solver._has_var(sol["expr"])


def test_implicit_generate_points_contours():
    r = solver.generate_points("x^2 + y^3 = 7")
    assert r["solution"]["kind"] == "implicit"
    assert r["x_range"] == (-10.0, 10.0)  # default square window
    assert len(r["branches"]) >= 1
    total = sum(len(b["points"]) for b in r["branches"])
    assert 50 < total < 20000


def test_implicit_vertical_line_x_equals_5():
    r = solver.generate_points("x = 5")
    xs = {p[0] for b in r["branches"] for p in b["points"]}
    assert all(abs(x - 5) < 0.05 for x in xs)  # all points on x = 5
    ys = [p[1] for b in r["branches"] for p in b["points"]]
    assert min(ys) < -9 and max(ys) > 9  # full height of the window


def test_implicit_points_lie_on_curve():
    r = solver.generate_points("x*y = 4")
    F = r["solution"]["expr"]
    for b in r["branches"]:
        for (x, y) in b["points"]:
            assert abs(solver.eval_ast2(F, x, y)) < 0.1  # F ≈ 0 everywhere


def test_implicit_constant_equation_still_errors():
    with pytest.raises(solver.SolverError, match="no effective y term"):
        solver.solve_equation("5 = 5")


def test_implicit_explicit_window():
    r = solver.generate_points("x^2 + y^3 = 7", x_min=-5, x_max=5, x_step=0.2)
    assert r["x_range"] == (-5.0, 5.0)
    assert r["solution"]["kind"] == "implicit"


def test_implicit_no_points_errors():
    with pytest.raises(solver.SolverError, match="No real points"):
        solver.generate_points("x^2 + y^4 = -3")  # no real solutions → implicit path


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
    with pytest.raises(solver.SolverError, match="x_step must be"):
        solver.generate_points("y = x", x_min=1, x_max=10, x_step=step)


def test_fractional_step():
    result = solver.generate_points("y = sin(x)", x_min=0, x_max=2, x_step=0.5)
    assert result["step"] == 0.5
    assert [x for x, _ in result["branches"][0]["points"]] == [0, 0.5, 1, 1.5, 2]


def test_fractional_range():
    result = solver.generate_points("y = x", x_min=-1, x_max=1, x_step=0.25)
    assert [x for x, _ in result["branches"][0]["points"]] == [-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1]


def test_fractional_step_respects_point_cap():
    with pytest.raises(solver.SolverError, match="Range too large"):
        solver.generate_points("y = x", x_min=0, x_max=1, x_step=0.0001)


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


# --- functions (P2-1): y = f(x) expression path ---
@pytest.mark.parametrize(
    "raw,display",
    [
        ("y = sin(x)", "y = sin(x)"),
        ("y = cos(x)", "y = cos(x)"),
        ("y = tan(x)", "y = tan(x)"),
        ("y = log(x)", "y = log(x)"),
        ("y = ln(x)", "y = log(x)"),  # ln is an alias for log
        ("y = sqrt(x)", "y = sqrt(x)"),
        ("y = exp(x)", "y = exp(x)"),
        ("y = abs(x)", "y = abs(x)"),
        ("2y = sin(x)", "y = sin(x) / 2"),
        ("-2y = sin(x)", "y = \u2212sin(x) / 2"),
        ("sin(x) + y = 3", "y = 3 \u2212 sin(x)"),
        ("y = x + sin(x)", "y = x + sin(x)"),
        ("y*sin(x) = 1", "y = 1 / sin(x)"),
        ("y = e^x", "y = e^x"),
        ("y = pi*x", "y = pi * x"),
        ("y = (x+1)^2", "y = (x + 1)^2"),
        ("y = 2(x+1)", "y = 2(x + 1)"),
        ("y = (x)", "y = x"),
        ("y = 1/(x-5)", "y = 1 / (x \u2212 5)"),
    ],
)
def test_function_display(raw, display):
    sol = solver.solve_equation(raw)
    assert sol["kind"] == "function"
    assert sol["display"] == display


def test_function_points_sin():
    result = solver.generate_points("y = sin(x)", x_min=1, x_max=5)
    assert result["solution"]["kind"] == "function"
    assert result["x_range"] == (1, 5)
    pts = result["branches"][0]["points"]
    assert len(pts) == 5
    assert pts[0][0] == 1
    assert abs(pts[0][1] - math.sin(1)) < 1e-9


def test_function_auto_range_and_nice_step():
    # Default range 1..100 sampled at a "nice" step (~400 points) so trig
    # curves render smoothly without a manual x_step.
    result = solver.generate_points("y = sin(x)")
    assert result["x_range"] == (1, 100)
    assert result["step"] == 0.5
    assert len(result["branches"][0]["points"]) == 199


def test_function_log_domain_skips_non_positive():
    result = solver.generate_points("y = log(x)", x_min=-5, x_max=5)
    assert [x for x, _ in result["branches"][0]["points"]] == [1, 2, 3, 4, 5]


def test_function_sqrt_domain_skips_negative():
    result = solver.generate_points("y = sqrt(x)", x_min=-10, x_max=10)
    assert [x for x, _ in result["branches"][0]["points"]] == list(range(0, 11))


def test_function_division_splits_segments():
    # 1/(x-5) is undefined at x=5 → two segments
    result = solver.generate_points("y = 1/(x-5)", x_min=1, x_max=10)
    assert [len(b["points"]) for b in result["branches"]] == [4, 5]
    assert result["branches"][0]["points"][-1][0] == 4
    assert result["branches"][1]["points"][0][0] == 6


def test_function_no_real_points_raises():
    with pytest.raises(solver.SolverError, match="No real y"):
        solver.generate_points("y = sqrt(x)", x_min=-10, x_max=-1)
    with pytest.raises(solver.SolverError, match="No real y"):
        solver.generate_points("y = log(x)", x_min=-5, x_max=0)


def test_function_step_respected():
    result = solver.generate_points("y = sin(x)", x_min=1, x_max=10, x_step=2)
    assert result["step"] == 2
    assert [x for x, _ in result["branches"][0]["points"]] == [1, 3, 5, 7, 9]


@pytest.mark.parametrize(
    "raw,needle",
    [
        ("y = foo(x)", "Unknown function"),
        ("y = (bar)", "Unknown symbol"),
        ("y = (2 + * 3)", "Unexpected"),
        ("y = sin(x+", "Unexpected end of formula"),
    ],
)
def test_function_errors(raw, needle):
    with pytest.raises(solver.SolverError) as exc:
        solver.solve_equation(raw)
    assert needle in str(exc.value)


# --- P3-2: inequality shading ---
@pytest.mark.parametrize(
    "raw,kind,op,side",
    [
        ("y > 2x + 1", "linear", ">", "above"),
        ("y < 2x + 1", "linear", "<", "below"),
        ("2x + 1 < y", "linear", "<", "above"),   # op flipped, still above
        ("y >= 2x+1", "linear", ">=", "above"),
        ("y <= x^2", "linear", "<=", "below"),
        ("x^2 + y^2 < 25", "quadratic", "<", "between"),   # inside circle
        ("x^2 + y^2 > 25", "quadratic", ">", "outside"),   # outside circle
        ("y^2 > x", "quadratic", ">", "outside"),
        ("y > sin(x)", "function", ">", "above"),
        ("y < sin(x)", "function", "<", "below"),
    ],
)
def test_inequality_solve_and_side(raw, kind, op, side):
    sol = solver.solve_equation(raw)
    assert sol["kind"] == kind
    assert sol["inequality"]["op"] == op
    r = solver.generate_points(raw)
    assert r["solution"]["inequality"]["side"] == side


def test_inequality_error_cases():
    with pytest.raises(solver.SolverError, match="Only one inequality"):
        solver.solve_equation("y > 2x + 1 < 3")
    with pytest.raises(solver.SolverError, match="Mixing '='"):
        solver.solve_equation("y = 2x + 1 > 3")
    with pytest.raises(solver.SolverError, match="Both sides of the inequality"):
        solver.solve_equation("y >")
    with pytest.raises(solver.SolverError, match="solvable for y"):
        solver.solve_equation("x^2 + y^3 > 7")  # implicit boundary unsupported
    with pytest.raises(solver.SolverError, match="not supported in polar"):
        solver.generate_points("r > 2", mode="polar")


def test_function_range_caps_still_apply():
    with pytest.raises(solver.SolverError, match="Range too large"):
        solver.generate_points("y = sin(x)", x_min=1, x_max=1_000_000)


# --- polar mode (P2-4-ish): r = f(θ) ---
@pytest.mark.parametrize(
    "raw,display",
    [
        ("r = 2θ", "r = 2θ"),
        ("r = 2*theta", "r = 2θ"),
        ("r = 2/θ", "r = 2 / θ"),
        ("r = cos(2θ)", "r = cos(2θ)"),
        ("r = θ/2", "r = θ / 2"),
        ("2r = 4θ", "r = 2θ"),  # linear in r with a coefficient
        ("r = 2 + sin(3θ)", "r = 2 + sin(3θ)"),
    ],
)
def test_polar_display(raw, display):
    sol = solver.solve_equation(raw, polar=True)
    assert sol["kind"] == "polar"
    assert sol["display"] == display


def test_polar_points_archimedean():
    # r = 2θ  →  at θ = π/2: r = π, point (0, π)
    result = solver.generate_points("r = 2θ", mode="polar")
    assert result["solution"]["kind"] == "polar"
    assert result["x_range"] == (0.0, 4 * math.pi)
    assert result["step"] == 0.05  # nice step over 0..4π
    pts = result["branches"][0]["points"]
    assert len(pts) == 252
    # nearest sample to θ = π/2 maps to x ≈ 0, y ≈ π
    near = min(pts, key=lambda p: abs(p[0]) + abs(p[1] - math.pi))
    assert abs(near[0]) < 0.1 and abs(near[1] - math.pi) < 0.1


def test_polar_explicit_theta_range():
    result = solver.generate_points("r = 2θ", x_min=0, x_max=math.pi, mode="polar")
    assert result["x_range"] == (0, math.pi)
    assert len(result["branches"][0]["points"]) == 315  # nice step 0.01 → 315 points


def test_cartesian_points_remain_2tuples():
    for f in ("y = 2x + 1", "y = sin(x)", "x^2 + y^2 = 100"):
        result = solver.generate_points(f)
        pts = result["branches"][0]["points"]
        assert pts and all(len(p) == 2 for p in pts), f


def test_polar_rose():
    # r = cos(2θ) is a four-petal rose; all points within the unit circle
    result = solver.generate_points("r = cos(2θ)", mode="polar")
    pts = result["branches"][0]["points"]
    assert all(math.hypot(x, y) <= 1.0 + 1e-9 for x, y, th, r in pts)
    # polar points carry (x, y, theta, r) so the table can show θ and r
    assert len(pts[0]) == 4
    assert pts[0][2] == pytest.approx(0.0)  # first θ sample
    assert pts[0][3] == pytest.approx(1.0)  # cos(2·0) = 1


def test_polar_division_zero_splits_segments():
    # r = 2/θ is undefined at θ = 0 → segment starts after 0
    result = solver.generate_points("r = 2/θ", mode="polar")
    assert result["branches"][0]["points"][0][0] > 0 or result["branches"][0]["points"][0][1] != 0


def test_polar_errors():
    with pytest.raises(solver.SolverError, match="linear in r"):
        solver.solve_equation("r^2 = 2θ", polar=True)
    with pytest.raises(solver.SolverError, match="no effective r term"):
        solver.solve_equation("θ = 2", polar=True)
    with pytest.raises(solver.SolverError, match="Unknown function"):
        solver.solve_equation("r = foo(θ)", polar=True)
    with pytest.raises(solver.SolverError, match="No real points"):
        solver.generate_points("r = log(θ)", x_min=-10, x_max=-1, mode="polar")
