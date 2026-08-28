"""Equation solver for xy-graph-gen.

Solves an equation in ``x`` and ``y`` for ``y`` in terms of ``x``:

- linear in ``y`` (e.g. ``"x + y = 3"`` -> ``y = -x + 3``): one branch
- quadratic in ``y`` (e.g. ``"x^2 + y^2 = 100"`` -> ``y = ±√(100 - x²)``):
  two branches via the quadratic formula; only x with a real discriminant
  produce points.

This module is the server-side twin of the client-side solver embedded in
``templates/index.html`` (which acts as an offline fallback when the API is
unreachable). The two must stay in agreement.
"""

from __future__ import annotations

import math
import re

_TERM_RE = re.compile(r"^([+-]?)(\d*\.?\d*)?([xy]?)(?:\^(\d+))?$")

X_MIN_DEFAULT = 1
X_MAX_DEFAULT = 100
MAX_EXPONENT = 12
AUTO_RANGE_LIMIT = 400      # max points per branch for auto-derived ranges
AUTO_SCAN_CAP = 10_000      # beyond this a domain tail is treated as unbounded
UNBOUNDED_WINDOW = 200      # span for one-sided unbounded domains
UNBOUNDED_FALLBACK = 100    # symmetric default for fully unbounded domains


class SolverError(ValueError):
    """Raised for formulas that cannot be solved or plotted."""


def fmt(n: float) -> str:
    """Format a number the way the client-side solver does (ints bare)."""
    if n == -0.0:
        n = 0.0
    s = f"{n:.12g}"
    if s.endswith(".0"):
        s = s[:-2]
    return s


def nice_ceil(v: float) -> float:
    """Smallest 'nice' number (1, 2, 5 x 10^k) that is >= v."""
    if not v > 0:
        return 1.0
    mag = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 5, 10):
        c = m * mag
        if c >= v:
            return float(c)
    return float(10 * mag)


def parse_term(t: str) -> dict | None:
    """Parse one term like '3', '-2x', 'x^3', 'y', '+0.5x'."""
    m = _TERM_RE.fullmatch(t)
    if not m:
        return None
    c_str = m.group(2)
    coeff = float(c_str) if c_str else 1.0
    if not math.isfinite(coeff):
        return None
    if m.group(1) == "-":
        coeff = -coeff
    var = m.group(3) or ""
    exp = int(m.group(4)) if m.group(4) else 1
    return {"coeff": coeff, "var": var, "exp": exp}


def tokenize_side(s: str) -> list[str]:
    """Split '2x-3y+5' into ['2x', '-3y', '+5']."""
    tokens = []
    i, n = 0, len(s)
    while i < n:
        sign = "+"
        if s[i] in "+-":
            sign = s[i]
            i += 1
        j = i
        while j < n and s[j] not in "+-":
            j += 1
        if j > i:
            body = s[i:j].strip()
            if body:
                tokens.append(("-" if sign == "-" else "") + body)
        i = j
    return tokens


def parse_side(s: str) -> dict:
    """Parse one side of the equation into x-terms / y-coefficients / constant."""
    res = {"x_terms": {}, "y_coeff": 0.0, "y2_coeff": 0.0, "const": 0.0}
    for t in tokenize_side(s):
        term = parse_term(t)
        if term is None:
            raise SolverError(f'Cannot understand term: "{t}"')
        if term["var"] == "x":
            if term["exp"] > MAX_EXPONENT:
                raise SolverError(f'Exponent too large: "{t}" (max {MAX_EXPONENT})')
            res["x_terms"][term["exp"]] = res["x_terms"].get(term["exp"], 0.0) + term["coeff"]
        elif term["var"] == "y":
            if term["exp"] == 1:
                res["y_coeff"] += term["coeff"]
            elif term["exp"] == 2:
                res["y2_coeff"] += term["coeff"]
            else:
                raise SolverError(f'Equation must be linear or quadratic in y: "{t}"')
        else:
            res["const"] += term["coeff"]
    return res


def _poly_str(poly: dict[int, float]) -> str:
    """Polynomial body like '−2x + 6', '100 − x²' or '0' (descending exponents)."""
    parts = []
    for e, c in sorted(poly.items(), key=lambda kv: -kv[0]):
        abs_c = abs(c)
        if e == 0:
            piece = fmt(abs_c)
        elif e == 1:
            piece = ("" if abs_c == 1 else fmt(abs_c)) + "x"
        else:
            piece = ("" if abs_c == 1 else fmt(abs_c)) + f"x^{e}"
        if not parts:
            piece = ("\u2212" if c < 0 else "") + piece
        else:
            piece = (" \u2212 " if c < 0 else " + ") + piece
        parts.append(piece)
    return "".join(parts) if parts else "0"


def solve_equation(raw: str) -> dict:
    """Solve ``raw`` for y.

    Returns ``{"kind": "linear"|"quadratic", "a", "b", "poly", "display"}``
    where ``a·y² + b·y = R(x)`` with ``R = poly``. Linear solutions keep the
    legacy ``denom`` field (== b). Raises :class:`SolverError` with a
    human-readable message for anything unsupported.
    """
    s = str(raw).replace(" ", "").replace("\u2212", "-")
    if not s:
        raise SolverError("Enter a formula first.")
    if "(" in s or ")" in s:
        raise SolverError("Parentheses are not supported yet.")

    eq = s.find("=")
    if eq == -1:
        lhs_str, rhs_str = "y", s
    else:
        if s.find("=", eq + 1) != -1:
            raise SolverError('Only one "=" allowed.')
        lhs_str, rhs_str = s[:eq], s[eq + 1 :]
    if not lhs_str or not rhs_str:
        raise SolverError('Both sides of "=" must have content.')

    lhs = parse_side(lhs_str)
    rhs = parse_side(rhs_str)

    # Normalise to:  a·y² + b·y = R(x)
    a = lhs["y2_coeff"] - rhs["y2_coeff"]
    b = lhs["y_coeff"] - rhs["y_coeff"]
    poly: dict[int, float] = {}
    for e in set(list(lhs["x_terms"]) + list(rhs["x_terms"])):
        c = rhs["x_terms"].get(e, 0.0) - lhs["x_terms"].get(e, 0.0)
        if c != 0:
            poly[e] = c
    c0 = rhs["const"] - lhs["const"]
    if c0 != 0:
        poly[0] = poly.get(0, 0.0) + c0

    if a != 0:
        if a < 0:  # normalise leading coefficient positive
            a, b = -a, -b
            poly = {e: -c for e, c in poly.items()}
        if b == 0:
            # y² = R/a  →  y = ±√(R/a)
            r_body = _poly_str(poly)
            if a == 1:
                display = f"y = \u00b1\u221a({r_body})"
            else:
                display = f"y = \u00b1\u221a(({r_body}) / {fmt(a)})"
        else:
            # y = (−b ± √(b² + 4aR)) / (2a)
            if not poly:
                d_str = fmt(b * b)
            else:
                r_disp = _poly_str(poly)
                mult = fmt(4 * a)
                if len(poly) > 1 or r_disp.startswith("\u2212"):
                    d_str = f"{fmt(b * b)} + {mult}\u00b7({r_disp})"
                else:
                    d_str = f"{fmt(b * b)} + {mult}{r_disp}"
            neg_b = -b
            num = (("\u2212" + fmt(-neg_b)) if neg_b < 0 else fmt(neg_b)) + f" \u00b1 \u221a({d_str})"
            denom = fmt(2 * a)
            display = f"y = {num}" if denom == "1" else f"y = ({num}) / {denom}"
        return {"kind": "quadratic", "a": a, "b": b, "poly": poly, "display": display}

    # Linear: b·y = R(x)
    if b == 0:
        raise SolverError("Equation has no effective y term — cannot solve for y.")
    if b < 0:
        b = -b
        poly = {e: -c for e, c in poly.items()}
    r_body = _poly_str(poly)
    display = f"y = {r_body}" if b == 1 else f"y = ({r_body}) / {fmt(b)}"
    return {"kind": "linear", "a": 0.0, "b": b, "denom": b, "poly": poly, "display": display}


def eval_poly(poly: dict[int, float], x: float) -> float:
    return sum(c * (x**e) for e, c in poly.items())


def _discriminant(sol: dict, x: float) -> float:
    """D = b² + 4a·R(x); real y exists where D >= 0."""
    return sol["b"] ** 2 + 4 * sol["a"] * eval_poly(sol["poly"], x)


def _scan_edge(d, anchor: int, step: int, cap: int) -> int | None:
    """Last x (inclusive) in direction ``step`` from ``anchor`` with d(x) >= 0.

    Returns None when no negative point is found before ``cap`` (unbounded).
    """
    x = anchor
    while abs(x) <= cap:
        if d(x) < 0:
            return x - step
        x += step
    return None


def auto_range(sol: dict) -> tuple[int, int]:
    """Default x range for a solution.

    Linear formulas keep the classic x = 1..100. Quadratic formulas get a
    symmetric(-ish) range covering the real domain of the discriminant:
    a circle like x²+y²=100 gets x = -10..10; unbounded domains (e.g.
    hyperbolas) fall back to a ±100 window.
    """
    if sol["kind"] != "quadratic":
        return X_MIN_DEFAULT, X_MAX_DEFAULT
    d = lambda x: _discriminant(sol, x)

    anchor = 0
    if d(0) < 0:
        found = False
        for x in range(1, AUTO_SCAN_CAP + 1):
            if d(x) >= 0:
                anchor, found = x, True
                break
            if d(-x) >= 0:
                anchor, found = -x, True
                break
        if not found:
            return 0, 0  # no real y anywhere near — callers report "no points"

    right = _scan_edge(d, anchor, 1, AUTO_SCAN_CAP)
    left = _scan_edge(d, anchor, -1, AUTO_SCAN_CAP)
    if right is None and left is None:
        return -UNBOUNDED_FALLBACK, UNBOUNDED_FALLBACK
    if right is None:
        assert left is not None  # covered by the both-None return above
        right = left + UNBOUNDED_WINDOW
    if left is None:
        assert right is not None
        left = right - UNBOUNDED_WINDOW
    return left, right


def generate_points(
    raw: str, x_min: int | None = None, x_max: int | None = None
) -> dict:
    """Solve ``raw`` and build branch points.

    Returns ``{"solution", "x_range": (lo, hi), "branches": [...]}`` where each
    branch is ``{"label", "points": [(x, y), ...]}``. Linear formulas yield one
    branch (label ""), quadratic ones two ("+", "−").

    ``x_min``/``x_max`` override the range; when omitted, linear formulas use
    x = 1..100 and quadratic formulas derive a range from the real domain
    (see :func:`auto_range`), capped at AUTO_RANGE_LIMIT points per branch.
    """
    sol = solve_equation(raw)
    if x_min is None or x_max is None:
        lo, hi = auto_range(sol)
    else:
        if x_min > x_max:
            raise SolverError("x_min must be <= x_max.")
        lo, hi = x_min, x_max

    step = 1
    if sol["kind"] == "quadratic" and (x_min is None or x_max is None) and hi - lo > AUTO_RANGE_LIMIT:
        step = math.ceil((hi - lo) / AUTO_RANGE_LIMIT)

    branches = []
    if sol["kind"] == "linear":
        points = []
        for x in range(lo, hi + 1, step):
            y = eval_poly(sol["poly"], x) / sol["b"]
            if not math.isfinite(y):
                raise SolverError(f"Result overflows at x = {x} — exponents too large?")
            points.append((x, y))
        if not points:
            raise SolverError("No real y for the given x range.")
        branches = [{"label": "", "points": points}]
    else:
        plus, minus = [], []
        for x in range(lo, hi + 1, step):
            d = _discriminant(sol, x)
            if d < 0:
                continue
            if not math.isfinite(d):
                raise SolverError(f"Result overflows at x = {x} — exponents too large?")
            root = math.sqrt(d)
            y1 = (-sol["b"] + root) / (2 * sol["a"])
            y2 = (-sol["b"] - root) / (2 * sol["a"])
            if not (math.isfinite(y1) and math.isfinite(y2)):
                raise SolverError(f"Result overflows at x = {x} — exponents too large?")
            plus.append((x, y1))
            minus.append((x, y2))  # tangency points (root == 0) belong to both branches
        if not plus and not minus:
            raise SolverError("No real y for the given x range.")
        branches = [
            {"label": "+", "points": plus},
            {"label": "\u2212", "points": minus},
        ]

    return {"solution": sol, "x_range": (lo, hi), "branches": branches}
