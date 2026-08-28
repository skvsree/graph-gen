# xy-graph-gen

A formula grapher: enter an equation in `x` and `y`, and it is solved for `y`
and plotted for `x = 1 … 100`, with the origin (0,0) at the centre of the
graph.

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
| `GET /api/points?formula=…&x_min=1&x_max=100` | Solves the formula for `y` and returns the points as JSON: `{"formula", "display", "points": [{"x","y"}, …]}`. Invalid formulas return `400` with a human-readable `detail`. |
| `GET /health` | Liveness probe: `{"status": "ok", "app": "xy-graph-gen"}` |

## Supported input

Any linear equation, and simple polynomials in `x` (linear in `y`):

| Input            | Solves to          |
|------------------|--------------------|
| `x + y = 3`      | `y = −x + 3`       |
| `y = 2x + 1`     | `y = 2x + 1`       |
| `2x + 3y = 6`    | `y = (−2x + 6) / 3` |
| `y = x^2 − 10x + 10` | `y = x^2 − 10x + 10` |

- A bare expression without `=` is treated as `y = <expr>`.
- Terms like `2x`, `-3y`, `x^2`, decimals (`1.5x`) are supported.
- The `y` term must be to the first power (solved form is always `y = f(x)`).
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
