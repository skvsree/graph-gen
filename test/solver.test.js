#!/usr/bin/env node
'use strict';
// Extract the <script> from index.html and unit-test the pure solver functions.
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'templates', 'index.html'), 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('FAIL: no <script> found in index.html'); process.exit(1); }

const sandbox = { console, Math, Number, String, Object, Set, isFinite, parseInt, parseFloat, JSON };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
// The guard `typeof document !== 'undefined'` prevents DOM code from running here.
vm.runInContext(m[1] + '\nthis.__api = { solveEquation: solveEquation, evalPoly: evalPoly, fmt: fmt, parseTerm: parseTerm, buildBranches: buildBranches };', sandbox);

const { solveEquation, evalPoly, fmt, parseTerm, buildBranches } = sandbox.__api;

let failures = 0;
function check(name, actual, expected) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a === e) { console.log('ok   ' + name); }
  else { failures++; console.log('FAIL ' + name + '\n  expected: ' + e + '\n  actual:   ' + a); }
}
function checkErr(name, raw, needle) {
  const sol = solveEquation(raw);
  if (sol.error && sol.error.includes(needle)) { console.log('ok   ' + name); }
  else { failures++; console.log('FAIL ' + name + ' -> ' + JSON.stringify(sol)); }
}

// --- regression: bare x / y terms must get implicit coefficient 1
check('parseTerm("x")', parseTerm('x'), { coeff: 1, varName: 'x', exp: 1 });
check('parseTerm("-y")', parseTerm('-y'), { coeff: -1, varName: 'y', exp: 1 });
check('parseTerm("2x")', parseTerm('2x'), { coeff: 2, varName: 'x', exp: 1 });
check('parseTerm("x^3")', parseTerm('x^3'), { coeff: 1, varName: 'x', exp: 3 });

// --- user's example: x + y = 3  =>  y = 3 - x
{
  const sol = solveEquation('x + y = 3');
  check('x + y = 3 solves', sol.display, 'y = \u2212x + 3');
  check('x + y = 3 poly {-x, 3}', sol.poly, { 0: 3, 1: -1 });
  check('x + y = 3 denom 1', sol.denom, 1);
  check('y(1) = 2', evalPoly(sol.poly, 1) / sol.denom, 2);
  check('y(3) = 0', evalPoly(sol.poly, 3) / sol.denom, 0);
  check('y(100) = -97', evalPoly(sol.poly, 100) / sol.denom, -97);
}

// --- other shapes
check('y = 2x + 1', solveEquation('y = 2x + 1').display, 'y = 2x + 1');
check('2x + 3y = 6', solveEquation('2x + 3y = 6').display, 'y = (\u22122x + 6) / 3');
check('x + y = -3', solveEquation('x + y = -3').display, 'y = \u2212x \u2212 3');
check('y = 3 - x (reordered)', solveEquation('y = 3 - x').display, 'y = \u2212x + 3');
check('bare expr treated as y=', solveEquation('3 - x').display, 'y = \u2212x + 3');
check('y = 4 constant', solveEquation('y = 4').display, 'y = 4');
check('y = x^2 - 10x + 10', solveEquation('y = x^2 - 10x + 10').display, 'y = x^2 \u2212 10x + 10');
check('unicode minus normalised', solveEquation('y = x \u2212 2').display, 'y = x \u2212 2');
check('negative y coeff flips', solveEquation('-y + x = 2').display, 'y = x \u2212 2');
check('x moves across =', solveEquation('y - x = 1').display, 'y = x + 1');
check('fractional coeff', solveEquation('0.5x + y = 2').display, 'y = \u22120.5x + 2');

// --- error cases
checkErr('no y term', 'x = 5', 'no effective y term');
checkErr('two equals signs', 'x + y = 3 = 4', 'Only one "="');
checkErr('parentheses', 'y = (x)', 'Parentheses');
checkErr('y cubed', 'y^3 = x', 'linear or quadratic in y');
checkErr('empty rhs', 'x = ', 'Both sides');
checkErr('empty lhs', '= 3', 'Both sides');
checkErr('garbage term', 'y = @#$', 'Cannot understand');
checkErr('empty input', '   ', 'Enter a formula');

// --- x_step / explicit ranges (buildBranches) ---
{
  const sol = solveEquation('y = 2x');
  const b = buildBranches(sol, 1, 10, 2);
  check('step=2 x values', b.branches[0].points.map(p => p.x), [1, 3, 5, 7, 9]);
  check('step reported', b.step, 2);
  const c = buildBranches(sol, 1, 10);
  check('default step=1', c.step, 1);
}
check('partial range error', (() => { const b = buildBranches(solveEquation('y = x'), 1); return b.error || ''; })(), 'Provide both x_min and x_max, or neither.');
check('step 0 error', (() => { const b = buildBranches(solveEquation('y = x'), 1, 10, 0); return b.error || ''; })(), 'x_step must be between 1 and 1000.');
check('range too large error', (() => { const b = buildBranches(solveEquation('y = x'), 1, 1000000); return b.error || ''; })(), 'Range too large (max 5000 points) — increase the step.');

// --- quadratic in y: circles and friends ---
{
  const sol = solveEquation('x^2 + y^2 = 100');
  check('circle solves', sol.kind, 'quadratic');
  check('circle a,b', [sol.a, sol.b], [1, 0]);
  check('circle poly', sol.poly, { 0: 100, 2: -1 });
  check('circle display', sol.display, 'y = \u00b1\u221a(\u2212x^2 + 100)');
  const b = buildBranches(sol);
  check('circle x range', b.xRange, { min: -10, max: 10 });
  check('circle branches', b.branches.length, 2);
  check('circle plus[0] y=10', b.branches[0].points[10].y, 10);
  check('circle minus[0] y=-10', b.branches[1].points[10].y, -10);
  check('circle 21 pts per branch', [b.branches[0].points.length, b.branches[1].points.length], [21, 21]);
}
check('y^2=4x display', solveEquation('y^2 = 4x').display, 'y = \u00b1\u221a(4x)');
check('2y^2=x^2+8 display', solveEquation('2y^2 = x^2 + 8').display, 'y = \u00b1\u221a((x^2 + 8) / 2)');
check('y^2-x^2=1 display', solveEquation('y^2 - x^2 = 1').display, 'y = \u00b1\u221a(x^2 + 1)');
check('y^2+y=x display', solveEquation('y^2 + y = x').display, 'y = (\u22121 \u00b1 \u221a(1 + 4x)) / 2');
{
  const b = buildBranches(solveEquation('y^2 + y = x'));
  check('y^2+y=x plus(0)=0', b.branches[0].points[0].y, 0);
  check('y^2+y=x minus(0)=-1', b.branches[1].points[0].y, -1);
}
checkErr('empty input', '   ', 'Enter a formula');
{
  const b = buildBranches(solveEquation('y^2 = -1'));
  check('y^2=-1 no real y', b.error || '', 'No real y for the given x range.');
}

console.log(failures === 0 ? '\nALL TESTS PASSED' : '\n' + failures + ' TEST(S) FAILED');
process.exit(failures === 0 ? 0 : 1);
