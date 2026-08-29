"""xy-graph-gen — FastAPI service.

Endpoints:
    GET /             renders the graph page (formula via ?formula= query param)
    GET /api/points   returns the (x, y) points for a formula as JSON
    GET /health       liveness probe
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import solver

app = FastAPI(title="xy-graph-gen", version="0.5.0")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

DEFAULT_FORMULA = "x + y = 3"
MAX_FORMULAS = 5
MODES = {"cartesian", "polar"}


def _clean_formulas(raw: list[str]) -> list[str]:
    """Trim + drop empties from the repeated `formula` query params."""
    return [f.strip() for f in raw if f.strip()]


def _check_mode(mode: str) -> None:
    if mode not in MODES:
        raise HTTPException(status_code=400, detail="mode must be 'cartesian' or 'polar'.")


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    formula: list[str] = Query(default=[DEFAULT_FORMULA]),
    mode: str = "cartesian",
    x_min: str | None = None,
    x_max: str | None = None,
    x_step: str | None = None,
) -> HTMLResponse:
    """Render the graph page with the formulas pre-filled from query params.

    Repeated ``?formula=…&formula=…`` params pre-fill multiple formula rows
    (capped at MAX_FORMULAS for rendering). ``mode`` selects the tab
    (``cartesian`` or ``polar``) and is kept in the shareable URL.
    """
    _check_mode(mode)
    formulas = _clean_formulas(formula) or [DEFAULT_FORMULA]
    resp = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "formulas": formulas[:MAX_FORMULAS],
            "mode": mode,
            "x_min": x_min or "",
            "x_max": x_max or "",
            "x_step": x_step or "",
        },
    )
    # The template changes often during development; never let a browser or
    # proxy serve a stale copy of the page (the JS solver must match the API).
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/points")
def api_points(
    formula: list[str] = Query(default=[DEFAULT_FORMULA]),
    mode: str = "cartesian",
    x_min: float | None = None,
    x_max: float | None = None,
    x_step: float | None = None,
) -> dict:
    """Compute the points for one or more formulas (max MAX_FORMULAS).

    ``mode`` is ``cartesian`` (default: linear/quadratic/function curves) or
    ``polar`` (``r = f(θ)``; ``x_min``/``x_max``/``x_step`` bound θ).

    Returns ``{"mode", "formulas", "x_range", "step", "curves": [...]}``
    where each curve is ``{"formula", "display", "kind", "branches":
    [{"label", "points": [{"x","y"}, …]}, …]}``. ``x_range``/``step`` come
    from the first curve (explicit params override the auto ranges).
    ``x_step`` may be fractional (> 0, <= 1000). Invalid formulas (or no
    real points) return ``400`` with a human-readable ``detail``.
    """
    _check_mode(mode)
    formulas = _clean_formulas(formula)
    if not formulas:
        raise HTTPException(status_code=400, detail="Enter a formula first.")
    if len(formulas) > MAX_FORMULAS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_FORMULAS} formulas per graph.")
    try:
        results = [solver.generate_points(f, x_min, x_max, x_step, mode=mode) for f in formulas]
    except solver.SolverError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    first = results[0]
    return {
        "mode": mode,
        "formulas": formulas,
        "x_range": {"min": first["x_range"][0], "max": first["x_range"][1]},
        "step": first["step"],
        "curves": [
            {
                "formula": f,
                "display": r["solution"]["display"],
                "kind": r["solution"]["kind"],
                "branches": [
                    {
                        "label": b["label"],
                        "points": [_point(p) for p in b["points"]],
                    }
                    for b in r["branches"]
                ],
            }
            for f, r in zip(formulas, results)
        ],
    }


def _point(p) -> dict:
    """Serialise a branch point.

    Cartesian points are ``(x, y)``; polar points carry the extra
    ``(x, y, theta, r)`` so the table can show θ and r.
    """
    d = {"x": p[0], "y": p[1]}
    if len(p) == 4:
        d["theta"] = p[2]
        d["r"] = p[3]
    return d


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": app.title}
