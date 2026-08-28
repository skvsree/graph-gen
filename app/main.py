"""xy-graph-gen — FastAPI service.

Endpoints:
    GET /             renders the graph page (formula via ?formula= query param)
    GET /api/points   returns the (x, y) points for a formula as JSON
    GET /health       liveness probe
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import solver

app = FastAPI(title="xy-graph-gen", version="0.3.0")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

DEFAULT_FORMULA = "x + y = 3"


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    formula: str = DEFAULT_FORMULA,
    x_min: str | None = None,
    x_max: str | None = None,
    x_step: str | None = None,
) -> HTMLResponse:
    """Render the graph page with the formula pre-filled from the query param."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "formula": formula,
            "x_min": x_min or "",
            "x_max": x_max or "",
            "x_step": x_step or "",
        },
    )


@app.get("/api/points")
def api_points(
    formula: str = DEFAULT_FORMULA,
    x_min: int | None = None,
    x_max: int | None = None,
    x_step: int | None = None,
) -> dict:
    """Compute the points for a formula.

    Linear formulas return one branch; quadratic-in-y formulas (circles, etc.)
    return two ("+", "−"). ``x_min``/``x_max``/``x_step`` override the range
    and sampling; with no explicit range, linear formulas use x = 1..100 and
    quadratic formulas derive a range from the real domain.
    """
    try:
        result = solver.generate_points(formula, x_min, x_max, x_step)
    except solver.SolverError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    sol = result["solution"]
    return {
        "formula": formula,
        "display": sol["display"],
        "kind": sol["kind"],
        "x_range": {"min": result["x_range"][0], "max": result["x_range"][1]},
        "step": result["step"],
        "branches": [
            {"label": branch["label"], "points": [{"x": x, "y": y} for x, y in branch["points"]]}
            for branch in result["branches"]
        ],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": app.title}
