"""xy-graph-gen — FastAPI service.

Endpoints:
    GET /             renders the graph page (formula via ?formula= query param)
    GET /api/points   returns the (x, y) points for a formula as JSON
    GET /metrics      Prometheus-style observability counters
    GET /health       liveness probe
"""

import logging
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from . import solver

log = logging.getLogger("xy-graph-gen")

app = FastAPI(title="xy-graph-gen", version="0.6.0")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

DEFAULT_FORMULA = "x + y = 3"
MAX_FORMULAS = 5
MODES = {"cartesian", "polar"}

# ---------------------------------------------------------------------------
# Caching: small in-process TTL cache for /api/points responses.
# ---------------------------------------------------------------------------

_CACHE_TTL = 60.0          # seconds
_CACHE_MAX = 256           # entries
_cache: dict = {}
_cache_lock = threading.Lock()
_cache_order: list = []    # insertion order for simple LRU eviction


def _cache_get(key) -> dict | None:
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit is None:
            return None
        expires, value = hit
        if expires < now:
            _cache.pop(key, None)
            try:
                _cache_order.remove(key)
            except ValueError:
                pass
            return None
        return value


def _cache_set(key, value) -> None:
    now = time.monotonic()
    with _cache_lock:
        _cache[key] = (now + _CACHE_TTL, value)
        if key in _cache_order:
            _cache_order.remove(key)
        _cache_order.append(key)
        while len(_cache_order) > _CACHE_MAX:
            oldest = _cache_order.pop(0)
            _cache.pop(oldest, None)


# ---------------------------------------------------------------------------
# Observability: request counters + durations, cache hits/misses.
# ---------------------------------------------------------------------------

_metrics_lock = threading.Lock()
_request_counts: dict = {}      # (method, path, status) -> count
_request_durations: dict = {}   # path -> (count, total_seconds)
_cache_hits = 0
_cache_misses = 0
_page_hits = 0                  # number of times the graph page was rendered
_start_time = time.time()


def _observe(method: str, path: str, status: int, seconds: float) -> None:
    global _cache_hits, _cache_misses
    with _metrics_lock:
        key = (method, path, status)
        _request_counts[key] = _request_counts.get(key, 0) + 1
        c, t = _request_durations.get(path, (0, 0.0))
        _request_durations[path] = (c + 1, t + seconds)


def _metrics_text() -> str:
    with _metrics_lock:
        lines = [
            "# HELP xy_requests_total HTTP requests by method, path, status.",
            "# TYPE xy_requests_total counter",
        ]
        for (method, path, status), count in sorted(_request_counts.items()):
            lines.append(
                f'xy_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )
        lines.append("# HELP xy_request_duration_seconds Total request duration per path.")
        lines.append("# TYPE xy_request_duration_seconds counter")
        for path, (count, total) in sorted(_request_durations.items()):
            lines.append(f'xy_request_duration_seconds{{path="{path}"}} {total:.6f}')
            lines.append(f'xy_request_count{{path="{path}"}} {count}')
        lines.append("# HELP xy_cache_requests_total Cache hits/misses on /api/points.")
        lines.append("# TYPE xy_cache_requests_total counter")
        lines.append(f'xy_cache_hits_total{{endpoint="/api/points"}} {_cache_hits}')
        lines.append(f'xy_cache_misses_total{{endpoint="/api/points"}} {_cache_misses}')
        lines.append("# HELP xy_uptime_seconds Process uptime.")
        lines.append("# TYPE xy_uptime_seconds gauge")
        lines.append(f"xy_uptime_seconds {int(time.time() - _start_time)}")
    return "\n".join(lines) + "\n"


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        _observe(request.method, request.url.path, status, time.perf_counter() - start)


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
    global _page_hits
    _check_mode(mode)
    formulas = _clean_formulas(formula) or [DEFAULT_FORMULA]
    with _metrics_lock:
        _page_hits += 1
    hits = _page_hits
    resp = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "formulas": formulas[:MAX_FORMULAS],
            "mode": mode,
            "x_min": x_min or "",
            "x_max": x_max or "",
            "x_step": x_step or "",
            "page_hits": hits,
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
    response: Response = None,
) -> dict:
    """Compute the points for one or more formulas (max MAX_FORMULAS).

    ``mode`` is ``cartesian`` (default: linear/quadratic/function curves,
    implicit ``F(x, y) = 0`` contours, and inequality shading) or ``polar``
    (``r = f(θ)``; ``x_min``/``x_max``/``x_step`` bound θ).

    Returns ``{"mode", "formulas", "x_range", "step", "curves": [...]}``
    where each curve is ``{"formula", "display", "kind", "branches":
    [{"label", "points": [{"x","y"}, …]}, …]}``. Inequality curves carry an
    extra ``"inequality": {"op", "side"}`` (``side`` in above/below/
    between/outside). ``x_range``/``step`` come from the first curve
    (explicit params override the auto ranges). ``x_step`` may be
    fractional (> 0, <= 1000). Invalid formulas (or no real points) return
    ``400`` with a human-readable ``detail``.

    Responses are cached in-process for ``_CACHE_TTL`` seconds; the
    ``X-Cache`` header reports ``HIT``/``MISS``.
    """
    _check_mode(mode)
    formulas = _clean_formulas(formula)
    if not formulas:
        raise HTTPException(status_code=400, detail="Enter a formula first.")
    if len(formulas) > MAX_FORMULAS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_FORMULAS} formulas per graph.")

    key = (mode, tuple(formulas), x_min, x_max, x_step)
    cached = _cache_get(key)
    if cached is not None:
        if response is not None:
            response.headers["X-Cache"] = "HIT"
        return cached

    try:
        results = [solver.generate_points(f, x_min, x_max, x_step, mode=mode) for f in formulas]
    except solver.SolverError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    first = results[0]
    payload = {
        "mode": mode,
        "formulas": formulas,
        "x_range": {"min": first["x_range"][0], "max": first["x_range"][1]},
        "step": first["step"],
        "curves": [
            {
                "formula": f,
                "display": r["solution"]["display"],
                "kind": r["solution"]["kind"],
                "inequality": _inequality_public(r["solution"].get("inequality")),
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
    _cache_set(key, payload)
    if response is not None:
        response.headers["X-Cache"] = "MISS"
    return payload


def _inequality_public(ineq) -> dict | None:
    """Expose only {op, side} to the client — never the internal ASTs."""
    if not ineq:
        return None
    return {"op": ineq["op"], "side": ineq.get("side", "above")}


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
    return {
        "status": "ok",
        "app": app.title,
        "version": app.version,
        "uptime_s": int(time.time() - _start_time),
    }


@app.get("/api/hits")
def api_hits() -> dict:
    """Number of times the graph page has been rendered since start."""
    with _metrics_lock:
        return {"hits": _page_hits}


@app.get("/metrics")
def metrics() -> Response:
    """Prometheus-text metrics for the service (counters + durations)."""
    return Response(content=_metrics_text(), media_type="text/plain; version=0.0.4")
