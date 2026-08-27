# xy-graph-gen

A zero-dependency, single-page HTML formula grapher.

Enter an equation in `x` and `y` — it is solved for `y` and plotted for
`x = 1 … 100`, with the origin (0,0) at the centre of the graph.

## Run

```bash
cd /opt/xy-graph-gen
python3 -m http.server 8123
```

Then open http://localhost:8123 — or just open `index.html` directly in a
browser (no server needed, it is fully static).

## Supported input

Any linear equation, and simple polynomials in `x` (linear in `y`):

| Input            | Solves to          |
|------------------|--------------------|
| `x + y = 3`      | `y = 3 − x`        |
| `y = 2x + 1`     | `y = 2x + 1`       |
| `2x + 3y = 6`    | `y = (6 − 2x) / 3` |
| `y = x^2 − 10x + 10` | `y = x^2 − 10x + 10` |

- A bare expression without `=` is treated as `y = <expr>`.
- Terms like `2x`, `-3y`, `x^2`, decimals (`1.5x`) are supported.
- The `y` term must be to the first power (solved form is always `y = f(x)`).
- Parentheses are not supported yet.

## Files

- `index.html` — the whole app (HTML + CSS + JS)
- `README.md` — this file

## Tests

The solver functions are pure JS; they are exercised by
`test/solver.test.js` (run with Node, no dependencies):

```bash
node test/solver.test.js
```
