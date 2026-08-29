# xy-graph-gen

A formula grapher: enter an equation in `x` and `y`, and it is solved for `y`
and plotted for `x = 1 … 100`, with the origin (0,0) at the centre of the
graph.

Linear equations plot a single line; quadratic-in-`y` equations (circles,
ellipses, sideways parabolas, hyperbolas) plot **two branches** and
auto-derive an x range that covers their real domain (e.g. `x^2 + y^2 = 100`
plots x = -10…10). Pass explicit `x_min`/`x_max` to override.

Function formulas — `y = sin(x)`, `y = e^x`, `y = 1/(x-5)` — plot through a
small expression solver supporting `sin cos tan log sqrt exp abs`, the
constants `e` and `pi`, parentheses and `+ - * / ^`. Domain holes and
vertical asymptotes are skipped (the polyline breaks across an asymptote),
so `tan` and reciprocal functions render cleanly.

The graph is interactive: **drag to pan, scroll or pinch to zoom, double-click
to reset**. A theme toggle (dark/light, persisted) and a grid on/off toggle sit
next to the plot button, and every successful plot is remembered in a
localStorage history row (last 12, click a chip to re-plot, ✕ clear).

**Plot up to 5 formulas at once** ("+ Add formula" adds an input row). Lines
get **fixed colours by index** — red, green, blue, cyan, teal — so curve 1 is
always red, curve 2 always green, and so on. A legend renders above the graph,
and the points table is grouped per formula. The shareable URL carries the
formulas as repeated `formula=` params:
`/?formula=y%3Dsin(x)&formula=y%3Dcos(x)&x_min=0&x_max=6.28`. One shared
x-range/step applies to all curves.

FastAPI + Jinja2 + vanilla JS. The page plots from the server-side solver
(`/api/points`) and falls back to a built-in client-side solver if the API is
unreachable (e.g. opened as a plain file).

## Run

```bash
cd /opt/xy-graph-gen
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'          # or without [dev] for runtime only
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8123
```

Open http://127.0.0.1:8123

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Renders the graph page. The formula is a query param: `/?formula=x%20%2B%20y%20%3D%203`. The page keeps the URL in sync (`?formula=…`) as you plot, so links are shareable. `?mode=polar` opens the polar tab (default `cartesian`). |
| `GET /api/points?mode=…&formula=…&formula=…&x_min=…&x_max=…&x_step=…` | Solves one or more formulas (max 5, repeated `formula=` params) and returns the curves as JSON: `{"mode", "formulas", "x_range": {"min","max"}, "step", "curves": [{"formula", "display", "kind", "branches": [{"label","points": [{"x","y"}, …]}, …]}, …]}`. `mode` is `cartesian` (default) or `polar`. Linear formulas return one branch, quadratic-in-`y` two ("+", "−"), function formulas one per contiguous segment. Polar points also carry `theta` and `r` (`{"x","y","theta","r"}`) so the table can show θ/r. `x_min`/`x_max`/`x_step` (fractions allowed; step must be > 0 and ≤ 1000; both range bounds required together) override the default range and sampling — e.g. `x_step=0.1` for a smooth trig curve. In polar mode they bound θ. Invalid formulas (or no real points) return `400` with a human-readable `detail`. |
| `GET /health` | Liveness probe: `{"status": "ok", "app": "xy-graph-gen"}` |

## Supported input

Any linear equation, and simple polynomials in `x` (linear in `y`):

| Input            | Solves to          |
|------------------|--------------------|
| `x + y = 3`      | `y = −x + 3`       |
| `y = 2x + 1`     | `y = 2x + 1`       |
| `2x + 3y = 6`    | `y = (−2x + 6) / 3` |
| `y = x^2 − 10x + 10` | `y = x^2 − 10x + 10` |
| `x^2 + y^2 = 100` | `y = ±√(−x^2 + 100)` — two branches, x = −10…10 |
| `y^2 = 4x`        | `y = ±√(4x)` — two branches, x = 0…200 |
| `y^2 + y = x`     | `y = (−1 ± √(1 + 4x)) / 2` — general quadratic in y |
| `y = sin(x)`      | `y = sin(x)` — function branch, x = 1…100 |
| `y = e^x`         | `y = e^x` — `e` is Euler's number |
| `y = 1/(x-5)`     | `y = 1 / (x − 5)` — x=5 skipped, two segments |
| `2y = sin(x)`     | `y = sin(x) / 2` — any equation linear in y |
| `sin(x) + y = 3`  | `y = 3 − sin(x)` |
| `y = (x+1)^2`     | `y = (x + 1)^2` — parentheses work in function form |
| `r = 2θ` (polar tab) | `r = 2θ` — Archimedean spiral; points are (r·cos θ, r·sin θ), default θ = 0…4π |
| `r = cos(2θ)` (polar tab) | `r = cos(2θ)` — four-petal rose |
| `r = 2/θ` (polar tab) | `r = 2 / θ` — hyperbolic spiral; θ = 0 skipped |

- A bare expression without `=` is treated as `y = <expr>`.
- Terms like `2x`, `-3y`, `x^2`, decimals (`1.5x`) are supported.
- `y` may appear to the first or second power (linear, or quadratic in `y` —
  solved via the quadratic formula into one or two branches).
- Quadratic-in-`y` formulas get an auto x-range covering the real domain; pass
  `x_min`/`x_max` explicitly (URL or API) to control it.
- `x_step` accepts **fractions** (`0.1`, `0.5`) up to 1000 — handy for smooth
  trig curves. Function formulas auto-sample at a "nice" step (~400 points)
  so `sin`, `tan`, etc. render smoothly without a manual step.
- Formulas containing **functions, parentheses or `e`/`pi`** are solved as
  `y = f(x)` by an expression solver: `sin cos tan log ln sqrt exp abs`,
  constants `e` and `pi`, operators `+ - * / ^` (implicit `2x`, `2sin(x)`),
  and any equation linear in `y` (`2y = sin(x)`, `y*sin(x) = 1`). `log` is
  the natural logarithm. Points outside a function's domain are skipped.
- **Polar mode** (`?mode=polar`, polar tab): formulas take the form
  `r = f(θ)` — linear in `r`. Use `θ` or `theta` for the angle
  (e.g. `r = 2θ`, `r = 3*sin(2θ)`, `r = e^(θ/10)`). `x_min`/`x_max`/`x_step`
  bound θ in this mode; the default range is θ = 0…4π at a "nice" step.
  Points map to the plane as (r·cos θ, r·sin θ) with signed r.
- Everything else (plain polynomials) uses the term solver, which still
  rejects parentheses — parenthesised formulas that are not linear in `y`
  (e.g. `(x+1)^2 + y^2 = 100`) error with "Parentheses are not supported
  yet."

## Project layout

```
app/
  main.py        FastAPI app (/, /api/points, /health)
  solver.py      server-side equation solver (pure Python, no deps)
templates/
  index.html     the graph page (client solver kept as offline fallback)
test/
  test_solver.py pytest unit tests for the solver
  test_api.py    pytest API tests (TestClient)
  solver.test.js node unit tests for the client-side fallback solver
pyproject.toml   deps + pytest config
```

## Tests

```bash
.venv/bin/pytest -q          # solver + API tests
node test/solver.test.js     # client-side fallback solver
```

The Python solver and the client-side JS solver mirror each other; keep them
in agreement when changing either.

## Production (this host)

Runs as a systemd service behind Caddy (TLS via Let's Encrypt):

- **Service:** `xy-graph-gen.service` → uvicorn on `127.0.0.1:8123`
  - `systemctl restart xy-graph-gen`, logs: `journalctl -u xy-graph-gen -f`
- **Site:** `xy.selviz.in` → `reverse_proxy 127.0.0.1:8123` in `/etc/caddy/Caddyfile`
  - `systemctl reload caddy` after editing the Caddyfile
- **DNS:** `xy.selviz.in` → this host (72.61.255.195)

Deploy a change:

```bash
cd /opt/xy-graph-gen
git pull
.venv/bin/pip install -e '.[dev]'   # only if pyproject.toml changed
.venv/bin/pytest -q
systemctl restart xy-graph-gen
```

## TODO / Roadmap

Tick items off as they land. P1 = planned next, P2 = valuable upgrades,
P3 = bigger / probably not worth it.

### P1 — planned next
- [x] x-range + step controls in the UI (`x_min` / `x_max` / step inputs; today they only work via URL/API)
- [x] Export graph as PNG + "Copy link" button (`canvas.toDataURL()` + existing `?formula=` share)
- [ ] GitHub Actions CI (pytest + node tests on push) — workflow written & tested locally, but push is **blocked**: the PAT needs `Workflows: Read and write` scope

### P2 — capability upgrades
- [x] General functions: `sin`, `cos`, `tan`, `log`, `sqrt`, `exp`, `abs` (real grapher territory)
- [x] Multiple formulas on one graph with legend (batch `/api/points` or comma-separated input)
- [x] Polar mode in a second tab (`?mode=polar&formula=r+%3D+2%CE%B8`; `r = f(θ)` with `θ`/`theta` for the angle, `x_min`/`x_max`/`x_step` bound θ; the points table shows θ and r in polar mode)
- [x] History & samples toggles — hide/show the history chips and points table; each tab keeps its own history ring and toggle preferences (`xygh:history:cartesian` / `xygh:history:polar`)
- [ ] Derivative + tangent lines (symbolic for polynomials — cheap: differentiate the coefficient map)
- [ ] Intersection points between curves (solve linear/quadratic pairs symbolically)
- [x] Zoom & pan on the canvas (drag to pan, wheel to zoom)
- [x] Formula history (localStorage ring buffer, shown as chips)
- [ ] Points CSV export
- [x] Dark mode / grid toggle

### P3 — bigger / probably not
- [ ] General implicit curves (grid sampling / contour rendering — different plotter)
- [ ] Inequality shading (`y > 2x + 1`)
- [ ] Docker packaging (already on systemd + Caddy)
- [ ] Caching / observability (premature for a single-user service)
