"""Equation solver for xy-graph-gen.

Solves an equation in ``x`` and ``y`` for ``y`` in terms of ``x`` (linear in
``y``), e.g. ``"x + y = 3"`` -> ``y = -x + 3``.

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
    """Parse one side of the equation into x-terms / y-coefficient / constant."""
    res = {"x_terms": {}, "y_coeff": 0.0, "const": 0.0}
    for t in tokenize_side(s):
        term = parse_term(t)
        if term is None:
            raise SolverError(f'Cannot understand term: "{t}"')
        if term["var"] == "x":
            if term["exp"] > MAX_EXPONENT:
                raise SolverError(f'Exponent too large: "{t}" (max {MAX_EXPONENT})')
            res["x_terms"][term["exp"]] = res["x_terms"].get(term["exp"], 0.0) + term["coeff"]
        elif term["var"] == "y":
            if term["exp"] != 1:
                raise SolverError(f'Equation must be linear in y: "{t}"')
            res["y_coeff"] += term["coeff"]
        else:
            res["const"] += term["coeff"]
    return res


def solve_equation(raw: str) -> dict:
    """Solve ``raw`` for y.

    Returns ``{"poly": {exp: coeff}, "denom": float, "display": str}`` where
    ``y = sum(poly[exp] * x**exp) / denom``. Raises :class:`SolverError` with a
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

    # Move everything to the right: yCoeff * y = sum(coeff_e * x^e)
    y_c = lhs["y_coeff"] - rhs["y_coeff"]
    if y_c == 0:
        raise SolverError("Equation has no effective y term — cannot solve for y.")

    poly: dict[int, float] = {}
    for e in set(list(lhs["x_terms"]) + list(rhs["x_terms"])):
        c = rhs["x_terms"].get(e, 0.0) - lhs["x_terms"].get(e, 0.0)
        if c != 0:
            poly[e] = c
    c0 = rhs["const"] - lhs["const"]
    if c0 != 0:
        poly[0] = poly.get(0, 0.0) + c0

    if y_c < 0:
        poly = {e: -c for e, c in poly.items()}
        y_c = -y_c

    # Human-readable form (terms in descending exponent order)
    parts = []
    for e in sorted(poly.keys(), reverse=True):
        c = poly[e]
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

    body = "".join(parts) if parts else "0"
    display = f"y = {body}" if y_c == 1 else f"y = ({body}) / {fmt(y_c)}"
    return {"poly": poly, "denom": y_c, "display": display}


def eval_poly(poly: dict[int, float], x: float) -> float:
    return sum(c * (x**e) for e, c in poly.items())


def generate_points(
    raw: str, x_min: int = X_MIN_DEFAULT, x_max: int = X_MAX_DEFAULT
) -> tuple[str, list[tuple[int, float]]]:
    """Return ``(display, points)`` for ``raw`` over integer x in [x_min, x_max]."""
    if x_min > x_max:
        raise SolverError("x_min must be <= x_max.")
    sol = solve_equation(raw)
    points = []
    for x in range(x_min, x_max + 1):
        y = eval_poly(sol["poly"], x) / sol["denom"]
        if not math.isfinite(y):
            raise SolverError(f"Result overflows at x = {x} — exponents too large?")
        points.append((x, y))
    return sol["display"], points
