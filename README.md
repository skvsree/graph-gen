# xy-graph-gen

A formula grapher: enter an equation in `x` and `y`, and it is solved for `y`
and plotted for `x = 1 … 100`, with the origin (0,0) at the centre of the
graph.

Linear equations plot a single line; quadratic-in-`y` equations (circles,
ellipses, sideways parabolas, hyperbolas) plot **two branches** and
auto-derive an x range that covers their real domain (e.g. `x^2 + y^2 = 100`
plots x = -10…10). Pass explicit `x_min`/`x_max` to override.

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
| `GET /` | Renders the graph page. The formula is a query param: `/?formula=x%20%2B%20y%20%3D%203`. The page keeps the URL in sync (`?formula=…`) as you plot, so links are shareable. |
| `GET /api/points?formula=…&x_min=…&x_max=…&x_step=…` | Solves the formula and returns the branches as JSON: `{"formula", "display", "kind", "x_range": {"min","max"}, "step", "branches": [{"label","points": [{"x","y"}, …]}, …]}`. Linear formulas return one branch, quadratic-in-`y` two ("+", "−"). `x_min`/`x_max`/`x_step` (1–1000, both range bounds required together) override the default range and sampling. Invalid formulas (or no real points) return `400` with a human-readable `detail`. |
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

- A bare expression without `=` is treated as `y = <expr>`.
- Terms like `2x`, `-3y`, `x^2`, decimals (`1.5x`) are supported.
- `y` may appear to the first or second power (linear, or quadratic in `y` —
  solved via the quadratic formula into one or two branches).
- Quadratic-in-`y` formulas get an auto x-range covering the real domain; pass
  `x_min`/`x_max` explicitly (URL or API) to control it.
- Parentheses are not supported.

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
- [ ] General functions: `sin`, `cos`, `tan`, `log`, `sqrt`, `exp`, `abs` (real grapher territory)
- [ ] Multiple formulas on one graph with legend (batch `/api/points` or comma-separated input)
- [ ] Derivative + tangent lines (symbolic for polynomials — cheap: differentiate the coefficient map)
- [ ] Intersection points between curves (solve linear/quadratic pairs symbolically)
- [ ] Zoom & pan on the canvas (drag to pan, wheel to zoom)
- [ ] Formula history (localStorage ring buffer, shown as chips)
- [ ] Points CSV export
- [ ] Dark mode / grid toggle

### P3 — bigger / probably not
- [ ] General implicit curves (grid sampling / contour rendering — different plotter)
- [ ] Inequality shading (`y > 2x + 1`)
- [ ] Docker packaging (already on systemd + Caddy)
- [ ] Caching / observability (premature for a single-user service)
