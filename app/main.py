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

app = FastAPI(title="xy-graph-gen", version="0.2.0")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

DEFAULT_FORMULA = "x + y = 3"


@app.get("/", response_class=HTMLResponse)
def index(request: Request, formula: str = DEFAULT_FORMULA) -> HTMLResponse:
    """Render the graph page with the formula pre-filled from the query param."""
    return templates.TemplateResponse(
        request=request, name="index.html", context={"formula": formula}
    )


@app.get("/api/points")
def api_points(
    formula: str = DEFAULT_FORMULA, x_min: int = 1, x_max: int = 100
) -> dict:
    """Compute the points for a formula: y solved for x in [x_min, x_max]."""
    try:
        display, points = solver.generate_points(formula, x_min, x_max)
    except solver.SolverError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "formula": formula,
        "display": display,
        "points": [{"x": x, "y": y} for x, y in points],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": app.title}
