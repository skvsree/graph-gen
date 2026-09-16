"""xy-graph-gen — FastAPI service.

Endpoints:
    GET /             renders the graph page (formula via ?formula= query param)
    GET /api/points   returns the (x, y) points for a formula as JSON
    GET /metrics      Prometheus-style observability counters
    GET /health       liveness probe
"""

import logging
import re
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from . import solver

log = logging.getLogger("xy-graph-gen")

app = FastAPI(title="xy-graph-gen", version="0.9.0")

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

# Progressive-web-app assets (manifest, service worker, icons). Served from
# explicit routes rather than a StaticFiles mount because /sw.js must live at
# the origin root to control the whole scope.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
_ICON_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.png$")

DEFAULT_FORMULA = "x + y = 3"
MAX_FORMULAS = 5
MODES = {"cartesian", "polar"}

# Default line colours for formula rows, in row order. MUST mirror the JS
# `CURVE_PALETTE` array in templates/index.html — test_template_palette_matches_js
# keeps the two in lockstep.
CURVE_PALETTE = ["#dc2626", "#16a34a", "#2563eb", "#0891b2", "#0d9488"]
DEFAULT_OPACITY = 100  # per-row line opacity in percent (0..100), default opaque
DEFAULT_ROTATION = 0    # per-row rotation in degrees about the curve's own centre
# Per-row line thickness in CSS pixels and its accepted range. Must mirror
# DEFAULT_STROKE_WIDTH / MIN_STROKE_WIDTH / MAX_STROKE_WIDTH in the template JS.
DEFAULT_STROKE_WIDTH = 2.5
MIN_STROKE_WIDTH, MAX_STROKE_WIDTH = 0.5, 12.0
# Per-row line style (how the stroke is BROKEN UP). The ORDER here is the order
# of the menu in the template's <select>, and MUST mirror JS `STYLE_OPTIONS` —
# test_template_styles_match_server keeps the two in lockstep.
STYLE_LABELS: dict[str, str] = {
    "solid": "Solid",
    "dashed": "Dashed",
    "dotted": "Dotted",
    "dashdot": "Dash-dot",
    "longdash": "Long dash",
}
DEFAULT_STYLE = "solid"
# Per-row PEN (how the stroke is DRAWN: clean vector line, grainy pencil,
# translucent marker, chisel-tip calligraphy, flat highlighter). Must mirror JS
# `PEN_OPTIONS` / `DEFAULT_PEN`.
PEN_LABELS: dict[str, str] = {
    "technical": "Technical",
    "pencil": "Pencil",
    "marker": "Marker",
    "calligraphy": "Calligraphy",
    "highlighter": "Highlighter",
}
DEFAULT_PEN = "technical"
_COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")
# A per-row numeric field -- centre offset (cx, cy) or rotation (rot, degrees).
# Accepts plain decimals and scientific notation, and is kept as a string so
# whatever a type=number input produced round-trips through the share URL
# unchanged. Anything else is dropped, so a malformed param can never inject
# markup into the page.
_NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
_CENTER_RE = _NUM_RE

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


def _clean_colors(raw: list[str], n: int) -> list[str]:
    """Validate repeated `color` params (hex #rrggbb) and pad to length n.

    Invalid/missing entries fall back to the palette colour for that row
    position, so a `color` param can never inject markup into the page.
    """
    colors = []
    for i in range(n):
        c = raw[i].strip().lower() if i < len(raw) else ""
        if not _COLOR_RE.fullmatch(c):
            c = CURVE_PALETTE[i % len(CURVE_PALETTE)]
        colors.append(c)
    return colors


def _clean_end_colors(raw: list[str], n: int, colors: list[str]) -> list[str]:
    """Validate repeated `color2` params (gradient END colour, hex #rrggbb).

    A missing/invalid entry falls back to that row's FIRST colour — i.e. a
    solid line, the pre-gradient behaviour — so a `color2` param can never
    inject markup into the page.
    """
    ends = []
    for i in range(n):
        c = raw[i].strip().lower() if i < len(raw) else ""
        if not _COLOR_RE.fullmatch(c):
            c = colors[i] if i < len(colors) else CURVE_PALETTE[i % len(CURVE_PALETTE)]
        ends.append(c)
    return ends


def _clean_widths(raw: list[str], n: int) -> list[float]:
    """Validate repeated `w` params (line thickness in px) and pad to length n.

    Invalid or out-of-range entries fall back to ``DEFAULT_STROKE_WIDTH`` for
    that row position. Only floats are ever emitted, so a `w` param can never
    inject markup into the page.
    """
    widths = []
    for i in range(n):
        v = raw[i].strip() if i < len(raw) else ""
        try:
            w = float(v)
        except ValueError:
            w = DEFAULT_STROKE_WIDTH
        if not MIN_STROKE_WIDTH <= w <= MAX_STROKE_WIDTH:
            w = DEFAULT_STROKE_WIDTH
        widths.append(w)
    return widths


def _clean_styles(raw: list[str], n: int) -> list[str]:
    """Validate repeated `style` params (line style) and pad to length n.

    Anything outside ``STYLE_LABELS`` (including a missing entry) becomes
    ``DEFAULT_STYLE`` — an allow-list, so a `style` param can never reach the
    page as anything but one of the known style names.
    """
    styles = []
    for i in range(n):
        b = raw[i].strip().lower() if i < len(raw) else ""
        styles.append(b if b in STYLE_LABELS else DEFAULT_STYLE)
    return styles


def _clean_pens(raw: list[str], n: int) -> list[str]:
    """Validate repeated `pen` params (drawing pen) and pad to length n.

    An allow-list like ``_clean_styles``: an unknown/missing pen becomes
    ``DEFAULT_PEN`` (the plain vector line).
    """
    pens = []
    for i in range(n):
        p = raw[i].strip().lower() if i < len(raw) else ""
        pens.append(p if p in PEN_LABELS else DEFAULT_PEN)
    return pens


def _clean_opacities(raw: list[str], n: int) -> list[int]:
    """Validate repeated `op` params (percent 0..100) and pad to length n.

    Invalid/missing entries fall back to ``DEFAULT_OPACITY`` (100 = fully
    opaque) for that row position. Only ints are ever emitted, so an `op`
    param can never inject markup into the page.
    """
    ops = []
    for i in range(n):
        v = raw[i].strip() if i < len(raw) else ""
        try:
            o = int(v)
        except ValueError:
            o = DEFAULT_OPACITY
        if not 0 <= o <= 100:
            o = DEFAULT_OPACITY
        ops.append(o)
    return ops


def _clean_centers(raw_x: list[str], raw_y: list[str], n: int) -> list[tuple[str, str]]:
    """Validate repeated `cx`/`cy` params and pair them up per row.

    Each row's centre defaults to ``(0, 0)`` — an empty/invalid value
    becomes ``""`` (the template renders it as a blank input whose
    placeholder reads 0). Values are kept as strings (never re-parsed
    through float) so they round-trip through the share URL exactly as
    typed. A malformed param can therefore never inject markup.
    """
    centers = []
    for i in range(n):
        x = raw_x[i].strip() if i < len(raw_x) else ""
        y = raw_y[i].strip() if i < len(raw_y) else ""
        centers.append((x if _CENTER_RE.fullmatch(x) else "", y if _CENTER_RE.fullmatch(y) else ""))
    return centers


def _clean_rotations(raw: list[str], n: int) -> list[str]:
    """Validate repeated `rot` params (degrees) and pad to length n.

    Each row's rotation defaults to ``DEFAULT_ROTATION`` (0 degrees = the
    curve as typed) -- an empty/invalid value becomes ``""`` (the template
    renders it as a blank input whose placeholder reads 0). Values are kept
    as strings (never re-parsed through float) so they round-trip through the
    share URL exactly as typed. A malformed param can therefore never inject
    markup.
    """
    rotations = []
    for i in range(n):
        v = raw[i].strip() if i < len(raw) else ""
        rotations.append(v if _NUM_RE.fullmatch(v) else "")
    return rotations


def _check_mode(mode: str) -> None:
    if mode not in MODES:
        raise HTTPException(status_code=400, detail="mode must be 'cartesian' or 'polar'.")


# ---------------------------------------------------------------------------
# PWA assets: manifest, service worker, icons.
#
# The service worker is served with `Cache-Control: no-cache` (it must be
# revalidated on every load or a fixed bug stays fixed forever) and
# `Service-Worker-Allowed: /` so its scope covers the whole origin. Icons get a
# normal long-ish cache; they are also precached by the worker itself.
# ---------------------------------------------------------------------------


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    """Web app manifest — what makes the page installable."""
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/sw.js")
def service_worker() -> FileResponse:
    """Service worker (root scope: precaches the shell, offline /api/points)."""
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/icons/{name}")
def icon(name: str) -> FileResponse:
    """PWA launcher icons (whitelisted PNG names; no path traversal)."""
    if not _ICON_RE.fullmatch(name) or not (STATIC_DIR / "icons" / name).is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        STATIC_DIR / "icons" / name,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/screenshots/{name}")
def screenshot(name: str) -> FileResponse:
    """Manifest screenshots — they give Android's install sheet its preview."""
    if not _ICON_RE.fullmatch(name) or not (STATIC_DIR / "screenshots" / name).is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(
        STATIC_DIR / "screenshots" / name,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    formula: list[str] = Query(default=[DEFAULT_FORMULA]),
    color: list[str] = Query(default=[]),
    color2: list[str] = Query(default=[]),
    op: list[str] = Query(default=[]),
    w: list[str] = Query(default=[]),
    style: list[str] = Query(default=[]),
    brush: list[str] = Query(default=[]),
    pen: list[str] = Query(default=[]),
    cx: list[str] = Query(default=[]),
    cy: list[str] = Query(default=[]),
    rot: list[str] = Query(default=[]),
    mode: str = "cartesian",
    x_min: str | None = None,
    x_max: str | None = None,
    x_step: str | None = None,
) -> HTMLResponse:
    """Render the graph page with the formulas pre-filled from query params.

    Repeated ``?formula=…&formula=…`` params pre-fill multiple formula rows
    (capped at MAX_FORMULAS for rendering). ``mode`` selects the tab
    (``cartesian`` or ``polar``) and is kept in the shareable URL. Optional
    repeated ``?color=#rrggbb`` params pre-fill each row's colour picker and
    repeated ``?color2=#rrggbb`` params pre-fill its gradient END colour
    (default = that row's first colour, i.e. a solid line), repeated
    ``?op=…`` params pre-fill each row's line opacity (percent
    0..100, default 100), repeated ``?w=…`` params pre-fill its line thickness
    in px (0.5..12, default 2.5), repeated ``?style=solid|dashed|dotted|
    dashdot|longdash`` params pre-fill its line style and repeated ``?pen=
    technical|pencil|marker|calligraphy|highlighter`` params its pen (both
    default to the plain solid vector line; ``?brush=`` is kept as a legacy
    alias for ``style``), and
    repeated ``?cx=…&cy=…`` params pre-fill each
    row's centre offset (default 0,0). Repeated ``?rot=`` params pre-fill
    each row's rotation in degrees about that centre (default 0).
    """
    global _page_hits
    _check_mode(mode)
    formulas = _clean_formulas(formula) or [DEFAULT_FORMULA]
    colors = _clean_colors(color, len(formulas))
    end_colors = _clean_end_colors(color2, len(formulas), colors)
    opacities = _clean_opacities(op, len(formulas))
    widths = _clean_widths(w, len(formulas))
    # `brush` was this feature's first name for the dash style; keep accepting
    # it so links shared before the rename still render.
    styles = _clean_styles(style if style else brush, len(formulas))
    pens = _clean_pens(pen, len(formulas))
    centers = _clean_centers(cx, cy, len(formulas))
    rotations = _clean_rotations(rot, len(formulas))
    with _metrics_lock:
        _page_hits += 1
    hits = _page_hits
    resp = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "formulas": formulas[:MAX_FORMULAS],
            "colors": colors[:MAX_FORMULAS],
            "colors2": end_colors[:MAX_FORMULAS],
            "opacities": opacities[:MAX_FORMULAS],
            "widths": widths[:MAX_FORMULAS],
            "styles": styles[:MAX_FORMULAS],
            "style_options": list(STYLE_LABELS.items()),
            "pens": pens[:MAX_FORMULAS],
            "pen_options": list(PEN_LABELS.items()),
            "centers": centers[:MAX_FORMULAS],
            "rotations": rotations[:MAX_FORMULAS],
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
