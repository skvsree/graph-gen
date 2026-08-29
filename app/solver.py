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
MAX_POINTS_PER_BRANCH = 5000  # explicit ranges are capped at this many points

FUNCTIONS = {"sin", "cos", "tan", "log", "ln", "sqrt", "exp", "abs"}
_FUNC_RE = re.compile(
    r"[()]|(?:sin|cos|tan|log|ln|sqrt|exp|abs)\(|(?<![a-zA-Z])e(?![a-zA-Z])|pi"
)
FUNCTION_Y_LIMIT = 1e6  # |y| beyond this is treated as an asymptote blow-up (tan, 1/x)


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

    Returns ``{"kind": "linear"|"quadratic"|"function", ...}``.

    - Polynomial formulas keep the existing behaviour: linear in ``y``
      (e.g. ``"x + y = 3"`` -> ``y = -x + 3``) or quadratic in ``y``
      (circles etc.), via :func:`_solve_polynomial`.
    - Formulas containing parentheses, function calls (``sin``, ``cos``,
      ``tan``, ``log``/``ln``, ``sqrt``, ``exp``, ``abs``) or the
      constants ``e``/``pi`` go through the expression path
      :func:`_solve_functional`, which solves any equation that is
      linear in ``y`` symbolically: ``y = f(x)``, ``2y = sin(x)``,
      ``y*sin(x) = 1``, ``(x+1)^2 + y = 3``, ``y = e^x`` … Raises
      :class:`SolverError` with a human-readable message for anything
      unsupported.
    """
    s = str(raw).replace(" ", "").replace("\u2212", "-")
    if not s:
        raise SolverError("Enter a formula first.")

    eq = s.find("=")
    if eq == -1:
        lhs_str, rhs_str = "y", s
    else:
        if s.find("=", eq + 1) != -1:
            raise SolverError('Only one "=" allowed.')
        lhs_str, rhs_str = s[:eq], s[eq + 1 :]
    if not lhs_str or not rhs_str:
        raise SolverError('Both sides of "=" must have content.')

    if _FUNC_RE.search(s):
        sol = _solve_functional(lhs_str, rhs_str)
        if sol is not None:
            return sol
    return _solve_polynomial(lhs_str, rhs_str)


def _solve_polynomial(lhs_str: str, rhs_str: str) -> dict:
    """Legacy term-based solver (linear/quadratic in y)."""
    s = lhs_str + "=" + rhs_str
    if "(" in s or ")" in s:
        raise SolverError("Parentheses are not supported yet.")

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


# ============================================================================
# Expression path: y = f(x) with parentheses, functions, e/pi constants.
# AST node shapes (tuples): ("num", v) ("sym", "e"|"pi") ("x",) ("y",)
#   ("neg", n) ("func", name, n) ("bin", op, l, r) ("pow", l, r)
# ============================================================================

class _NonLinearY(Exception):
    """Internal: the expression is not linear in y — fall back to polynomial."""


def _expr_value_end(tok: tuple) -> bool:
    return tok[0] == "num" or (tok[0] == "name" and tok[1] in ("x", "y")) or tok == ("op", ")")


def _expr_value_start(tok: tuple) -> bool:
    return tok[0] == "num" or tok[0] == "name" or tok == ("op", "(")


def expr_tokenize(s: str) -> list:
    """Tokenize an expression, inserting implicit ``*`` (``2x`` -> ``2*x``).

    Returns a list of ``("num", v) | ("name", n) | ("op", c)`` tokens.
    """
    tokens = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or c == ".":
            j = i
            while j < n and (s[j].isdigit() or s[j] == "."):
                j += 1
            try:
                v = float(s[i:j])
            except ValueError:
                raise SolverError(f'Cannot understand "{s[i:j]}".') from None
            tokens.append(("num", v))
            i = j
            continue
        if c.isalpha():
            j = i
            while j < n and s[j].isalpha():
                j += 1
            tokens.append(("name", s[i:j]))
            i = j
            continue
        if c in "+-*/^()":
            tokens.append(("op", c))
            i += 1
            continue
        raise SolverError(f'Cannot understand character "{c}".')
    out = []
    for idx, tok in enumerate(tokens):
        out.append(tok)
        if idx < len(tokens) - 1 and _expr_value_end(tok) and _expr_value_start(tokens[idx + 1]):
            out.append(("op", "*"))
    return out


class _ExprParser:
    """Recursive-descent: expr := term (('+'|'-') term)* ; term := unary
    (('*'|'/') unary)* ; unary := ('+'|'-') unary | power ;
    power := primary ('^' unary)?  (so ``-x^2`` == ``-(x^2)``)."""

    def __init__(self, tokens: list):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _next(self) -> tuple | None:
        t = self.peek()
        self.pos += 1
        return t

    def expr(self):
        node = self.term()
        while True:
            t = self.peek()
            if t in (("op", "+"), ("op", "-")):
                self._next()
                node = ("bin", t[1], node, self.term())
            else:
                return node

    def term(self):
        node = self.unary()
        while True:
            t = self.peek()
            if t in (("op", "*"), ("op", "/")):
                self._next()
                node = ("bin", t[1], node, self.unary())
            else:
                return node

    def unary(self):
        t = self.peek()
        if t == ("op", "+"):
            self._next()
            return self.unary()
        if t == ("op", "-"):
            self._next()
            return ("neg", self.unary())
        return self.power()

    def power(self):
        base = self.primary()
        if self.peek() == ("op", "^"):
            self._next()
            return ("pow", base, self.unary())
        return base

    def primary(self):
        t = self._next()
        if t is None:
            raise SolverError("Unexpected end of formula.")
        if t[0] == "num":
            return ("num", t[1])
        if t[0] == "name":
            if t[1] == "x":
                return ("x",)
            if t[1] == "y":
                return ("y",)
            if self.peek() == ("op", "("):
                self._next()
                inner = self.expr()
                if self._next() != ("op", ")"):
                    raise SolverError("Missing closing parenthesis.")
                name = "log" if t[1] == "ln" else t[1]
                if name not in FUNCTIONS:
                    raise SolverError(f"Unknown function '{t[1]}'.")
                return ("func", name, inner)
            if t[1] in ("e", "pi"):
                return ("sym", t[1])
            raise SolverError(f"Unknown symbol '{t[1]}'.")
        if t == ("op", "("):
            inner = self.expr()
            if self._next() != ("op", ")"):
                raise SolverError("Missing closing parenthesis.")
            return inner
        raise SolverError(f'Unexpected "{t[1]}".')


def parse_expr(s: str) -> tuple:
    return _ExprParser(expr_tokenize(s)).expr()


def _linearize(node) -> tuple:
    """Return ``(a, b)`` with ``node ≡ a·y + b``; ``a is None`` = no y term.

    Raises :class:`_NonLinearY` when y appears squared, in a denominator,
    in an exponent, or under a function — callers fall back to the
    polynomial path in that case.
    """
    t = node[0]
    if t in ("num", "sym", "x"):
        return None, node
    if t == "y":
        return ("num", 1.0), ("num", 0.0)
    if t == "neg":
        a, b = _linearize(node[1])
        return (None if a is None else ("neg", a), ("neg", b))
    if t == "func":
        a, b = _linearize(node[2])
        if a is not None:
            raise SolverError("Cannot solve — 'y' appears inside a function.")
        return None, ("func", node[1], b)
    if t == "pow":
        al, _bl = _linearize(node[1])
        ar, _br = _linearize(node[2])
        if al is not None or ar is not None:
            raise _NonLinearY()
        return None, ("pow", node[1], node[2])
    if t == "bin":
        op = node[1]
        al, bl = _linearize(node[2])
        ar, br = _linearize(node[3])
        if op == "+":
            return (_add_a(al, ar), ("bin", "+", bl, br))
        if op == "-":
            return (_sub_a(al, ar), ("bin", "-", bl, br))
        if op == "*":
            if al is not None and ar is not None:
                raise _NonLinearY()
            if al is not None:
                return (("bin", "*", al, br), ("bin", "*", bl, br))
            if ar is not None:
                return (("bin", "*", bl, ar), ("bin", "*", bl, br))
            return (None, ("bin", "*", bl, br))
        if op == "/":
            if ar is not None:
                raise _NonLinearY()
            if al is not None:
                return (("bin", "/", al, br), ("bin", "/", bl, br))
            return (None, ("bin", "/", bl, br))
    raise SolverError("Internal solver error.")


def _add_a(a, b):
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return ("bin", "+", a, b)


def _sub_a(a, b):
    if a is None and b is None:
        return None
    if a is None:
        return ("neg", b)
    if b is None:
        return a
    return ("bin", "-", a, b)


def _simplify(node) -> tuple:
    """Constant folding + identity elimination (x*1, x+0, 0*x, ...)."""
    t = node[0]
    if t in ("num", "sym", "x", "y"):
        return node
    if t == "neg":
        c = _simplify(node[1])
        if c[0] == "num":
            return ("num", -c[1])
        if c[0] == "neg":
            return c[1]
        return ("neg", c)
    if t == "func":
        return ("func", node[1], _simplify(node[2]))
    if t == "pow":
        l = _simplify(node[1])
        r = _simplify(node[2])
        if l[0] == "num" and r[0] == "num":
            try:
                return ("num", l[1] ** r[1])
            except (ValueError, ZeroDivisionError, OverflowError):
                return ("pow", l, r)
        if r[0] == "num":
            if r[1] == 1:
                return l
            if r[1] == 0:
                return ("num", 1.0)
        return ("pow", l, r)
    op = node[1]
    l = _simplify(node[2])
    r = _simplify(node[3])
    if op == "+":
        if l[0] == "num" and l[1] == 0:
            return r
        if r[0] == "num" and r[1] == 0:
            return l
        if l[0] == "num" and r[0] == "num":
            return ("num", l[1] + r[1])
        return ("bin", "+", l, r)
    if op == "-":
        if r[0] == "num" and r[1] == 0:
            return l
        if l[0] == "num" and r[0] == "num":
            return ("num", l[1] - r[1])
        return ("bin", "-", l, r)
    if op == "*":
        if l[0] == "num" and l[1] == 0:
            return ("num", 0.0)
        if r[0] == "num" and r[1] == 0:
            return ("num", 0.0)
        if l[0] == "num" and l[1] == 1:
            return r
        if r[0] == "num" and r[1] == 1:
            return l
        if l[0] == "num" and r[0] == "num":
            return ("num", l[1] * r[1])
        if l[0] == "num" and l[1] == -1:
            return ("neg", r)
        if r[0] == "num" and r[1] == -1:
            return ("neg", l)
        return ("bin", "*", l, r)
    if op == "/":
        if l[0] == "num" and l[1] == 0:
            return ("num", 0.0)
        if r[0] == "num" and r[1] == 1:
            return l
        if l[0] == "num" and r[0] == "num":
            try:
                return ("num", l[1] / r[1])
            except ZeroDivisionError:
                return ("bin", "/", l, r)
        return ("bin", "/", l, r)
    return node


def _prec(node) -> int:
    if node[0] in ("num", "sym", "x", "y", "func"):
        return 4
    if node[0] in ("neg", "pow"):
        return 3
    if node[0] == "bin":
        return 2 if node[1] in "*/" else 1
    return 0


def _ast_str(node) -> str:
    """Render an AST back to a compact expression (uses U+2212 minus)."""
    t = node[0]
    if t == "num":
        return fmt(node[1])
    if t == "sym":
        return node[1]
    if t == "x":
        return "x"
    if t == "func":
        return node[1] + "(" + _ast_str(node[2]) + ")"
    if t == "neg":
        inner = _ast_str(node[1])
        if node[1][0] in ("bin", "neg"):
            inner = "(" + inner + ")"
        return "\u2212" + inner
    if t == "pow":
        bs = _ast_str(node[1])
        if node[1][0] in ("bin", "neg"):
            bs = "(" + bs + ")"
        es = _ast_str(node[2])
        if node[2][0] in ("bin", "neg", "pow"):
            es = "(" + es + ")"
        return bs + "^" + es
    op, l, r = node[1], node[2], node[3]
    ls, rs = _ast_str(l), _ast_str(r)
    if op in ("+", "-"):
        if _prec(l) < 1:
            ls = "(" + ls + ")"
        if _prec(r) < 1 or r[0] == "neg":
            rs = "(" + rs + ")"
        return ls + (" + " if op == "+" else " \u2212 ") + rs
    if op == "*":
        if _prec(l) < 2:
            ls = "(" + ls + ")"
        if _prec(r) < 2:
            rs = "(" + rs + ")"
        if r[0] in ("num", "sym") or l[0] in ("x", "y", "sym"):
            return ls + " * " + rs
        return ls + rs  # "2x", "2sin(x)", "sin(x)cos(x)"
    if op == "/":
        if _prec(l) < 2:
            ls = "(" + ls + ")"
        if _prec(r) < 2:
            rs = "(" + rs + ")"
        return ls + " / " + rs
    return node  # pragma: no cover


def _solve_functional(lhs_str: str, rhs_str: str) -> dict | None:
    """Solve an equation linear in y as ``y = (B_r − B_l)/(A_l − A_r)``.

    Returns the solution dict, or ``None`` when the formula is not linear
    in y (caller falls back to the polynomial path so legacy error
    messages survive).
    """
    try:
        la, lb = _linearize(parse_expr(lhs_str))
        ra, rb = _linearize(parse_expr(rhs_str))
    except _NonLinearY:
        return None

    a_tot = _simplify(_sub_a(la, ra))  # y coefficient
    expr = _simplify(("bin", "-", rb, lb))  # R(x): b_r − b_l
    if a_tot is None or (a_tot[0] == "num" and a_tot[1] == 0):
        raise SolverError("Equation has no effective y term — cannot solve for y.")
    if a_tot[0] == "num" and a_tot[1] < 0:
        a_tot = ("num", -a_tot[1])
        expr = ("neg", expr)
    elif a_tot[0] == "neg" and a_tot[1][0] == "num":
        a_tot = ("num", -a_tot[1][1])
        expr = ("neg", expr)

    e_str = _ast_str(expr)
    if a_tot == ("num", 1.0):
        display = "y = " + e_str
    else:
        b_str = _ast_str(a_tot)
        body = f"({e_str})" if expr[0] == "bin" else e_str
        display = f"y = {body} / {b_str}"
    return {"kind": "function", "expr": expr, "b": a_tot, "display": display}


def eval_ast(node, x: float) -> float:
    """Numerically evaluate an x-only AST at ``x``."""
    t = node[0]
    if t == "num":
        return node[1]
    if t == "sym":
        return math.e if node[1] == "e" else math.pi
    if t == "x":
        return x
    if t == "y":
        raise SolverError("Internal solver error: y leaked into eval.")
    if t == "neg":
        return -eval_ast(node[1], x)
    if t == "func":
        v = eval_ast(node[2], x)
        f = node[1]
        if f == "sin":
            return math.sin(v)
        if f == "cos":
            return math.cos(v)
        if f == "tan":
            return math.tan(v)
        if f == "log":
            return math.log(v)
        if f == "sqrt":
            return math.sqrt(v)
        if f == "exp":
            return math.exp(v)
        if f == "abs":
            return abs(v)
        raise SolverError(f"Internal solver error: unknown function {f}.")  # pragma: no cover
    if t == "bin":
        l, r = eval_ast(node[2], x), eval_ast(node[3], x)
        op = node[1]
        if op == "+":
            return l + r
        if op == "-":
            return l - r
        if op == "*":
            return l * r
        if op == "/":
            return l / r
    if t == "pow":
        return eval_ast(node[1], x) ** eval_ast(node[2], x)
    raise SolverError("Internal solver error.")  # pragma: no cover


def eval_poly(poly: dict[int, float], x: float) -> float:
    return sum(c * (x**e) for e, c in poly.items())


def _eval_function(sol: dict, x: float) -> float | None:
    """Evaluate ``y = f(x)`` at ``x``; None when the value is not plottable."""
    try:
        num = eval_ast(sol["expr"], x)
        den = eval_ast(sol["b"], x)
        y = num / den
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    if not math.isfinite(y) or abs(y) > FUNCTION_Y_LIMIT:
        return None
    return y


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
    raw: str, x_min: float | None = None, x_max: float | None = None, x_step: float | None = None
) -> dict:
    """Solve ``raw`` and build branch points.

    Returns ``{"solution", "x_range": (lo, hi), "step", "branches": [...]}``
    where each branch is ``{"label", "points": [(x, y), ...]}``. Linear
    formulas yield one branch (label ""), quadratic ones two ("+", "−"),
    function formulas one per contiguous segment.

    ``x_min``/``x_max`` override the range; when omitted, linear formulas use
    x = 1..100, quadratic formulas derive a range from the real domain
    (see :func:`auto_range`), and function formulas use 1..100 sampled at a
    "nice" step (~AUTO_RANGE_LIMIT points). ``x_step`` (> 0, <= 1000, may be
    fractional) controls the sampling; every range is capped at
    MAX_POINTS_PER_BRANCH points.
    """
    sol = solve_equation(raw)
    if (x_min is None) != (x_max is None):
        raise SolverError("Provide both x_min and x_max, or neither.")
    if x_min is None:
        lo, hi = auto_range(sol)
    else:
        assert x_max is not None  # guaranteed by the both-or-neither check
        if x_min > x_max:
            raise SolverError("x_min must be <= x_max.")
        lo, hi = x_min, x_max

    if x_step is not None:
        if not x_step > 0 or x_step > 1000:
            raise SolverError("x_step must be > 0 and <= 1000.")
        step = x_step
    else:
        step = 1.0
        if x_min is None or x_max is None:
            if sol["kind"] == "quadratic" and hi - lo > AUTO_RANGE_LIMIT:
                step = math.ceil((hi - lo) / AUTO_RANGE_LIMIT)
            elif sol["kind"] == "function":
                step = nice_ceil((hi - lo) / AUTO_RANGE_LIMIT)
    n = int((hi - lo) / step + 1e-9) + 1
    if n > MAX_POINTS_PER_BRANCH:
        raise SolverError(
            f"Range too large (max {MAX_POINTS_PER_BRANCH} points) — increase the step."
        )
    xs = [lo + i * step for i in range(n) if lo + i * step <= hi + 1e-9]

    branches = []
    if sol["kind"] == "linear":
        points = []
        for x in xs:
            y = eval_poly(sol["poly"], x) / sol["b"]
            if not math.isfinite(y):
                raise SolverError(f"Result overflows at x = {x} — exponents too large?")
            points.append((x, y))
        if not points:
            raise SolverError("No real y for the given x range.")
        branches = [{"label": "", "points": points}]
    elif sol["kind"] == "function":
        # y = f(x): skip points outside the domain (log/sqrt of negatives,
        # division by zero) and asymptote blow-ups; each contiguous run of
        # valid points becomes its own branch/segment so the polyline does
        # not jump across a vertical asymptote.
        segments = []
        cur = []
        for x in xs:
            y = _eval_function(sol, x)
            if y is None:
                if cur:
                    segments.append(cur)
                    cur = []
                continue
            cur.append((x, y))
        if cur:
            segments.append(cur)
        if not segments:
            raise SolverError("No real y for the given x range.")
        branches = [{"label": "", "points": seg} for seg in segments]
    else:
        plus, minus = [], []
        for x in xs:
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

    return {"solution": sol, "x_range": (lo, hi), "step": step, "branches": branches}
