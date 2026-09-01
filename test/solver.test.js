#!/usr/bin/env node
'use strict';
// Extract the <script> from index.html and unit-test the pure solver functions.
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'templates', 'index.html'), 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('FAIL: no <script> found in index.html'); process.exit(1); }

const sandbox = { console, Math, Number, String, Object, Set, Map, Array, isFinite, parseInt, parseFloat, JSON };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
// The guard `typeof document !== 'undefined'` prevents DOM code from running here.
vm.runInContext(m[1] + '\nthis.__api = { solveEquation: solveEquation, evalPoly: evalPoly, fmt: fmt, parseTerm: parseTerm, buildBranches: buildBranches, evalAst: evalAst, astStr: astStr };', sandbox);

const { solveEquation, evalPoly, fmt, parseTerm, buildBranches, evalAst, astStr } = sandbox.__api;

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
checkErr('two equals signs', 'x + y = 3 = 4', 'Only one "="');
checkErr('empty rhs', 'x = ', 'Both sides');
checkErr('empty lhs', '= 3', 'Both sides');
checkErr('garbage term', 'y = @#$', 'Cannot understand');
checkErr('empty input', '   ', 'Enter a formula');

// --- P3-1: implicit curves (F(x, y) = 0 via grid sampling) ---
check('x = 5 vertical line kind', solveEquation('x = 5').kind, 'implicit');
check('y^3 = x kind', solveEquation('y^3 = x').kind, 'implicit');
check('(x+1)^2+y^2 = 100 kind', solveEquation('(x+1)^2 + y^2 = 100').kind, 'implicit');
check('x*y = 4 kind', solveEquation('x*y = 4').kind, 'implicit');
check('x^2+y^3 = 7 kind', solveEquation('x^2 + y^3 = 7').kind, 'implicit');
check('x^3+y^3 = 6xy kind', solveEquation('x^3 + y^3 = 6xy').kind, 'implicit');
check('sin(x)+sin(y) = 1 kind', solveEquation('sin(x) + sin(y) = 1').kind, 'implicit');
check('implicit display', solveEquation('x^2 + y^3 = 7').display, 'x^2+y^3 = 7');
checkErr('5 = 5 still errors', '5 = 5', 'no effective y term');
{
  const b = buildBranches(solveEquation('x = 5'));
  check('implicit vertical line branches', b.branches.length >= 1, true);
  check('implicit points on x=5', b.branches[0].points.every(p => Math.abs(p.x - 5) < 0.05), true);
  check('implicit default range', b.xRange, { min: -10, max: 10 });
}
{
  const b = buildBranches(solveEquation('x^2 + y^3 = 7'));
  const total = b.branches.reduce((n, br) => n + br.points.length, 0);
  check('implicit contour has points', total > 50 && total < 20000, true);
}

// --- P3-2: inequality shading ---
check('y > 2x+1 op', solveEquation('y > 2x + 1').inequality.op, '>');
check('y > 2x+1 kind', solveEquation('y > 2x + 1').kind, 'linear');
check('2x+1 < y op', solveEquation('2x + 1 < y').inequality.op, '<');
check('y >= 2x+1 op', solveEquation('y >= 2x+1').inequality.op, '>=');
check('x^2+y^2 < 25 kind', solveEquation('x^2 + y^2 < 25').kind, 'quadratic');
check('y > sin(x) kind', solveEquation('y > sin(x)').kind, 'function');
{
  const b = buildBranches(solveEquation('y > 2x + 1'));
  check('y>2x+1 side above', b.inequality.side, 'above');
}
{
  const b = buildBranches(solveEquation('y < 2x + 1'));
  check('y<2x+1 side below', b.inequality.side, 'below');
}
{
  const b = buildBranches(solveEquation('x^2 + y^2 < 25'));
  check('circle interior side between', b.inequality.side, 'between');
}
{
  const b = buildBranches(solveEquation('x^2 + y^2 > 25'));
  check('circle exterior side outside', b.inequality.side, 'outside');
}
checkErr('two ops error', 'y > 2x + 1 < 3', 'Only one inequality');
checkErr('mixed = and > error', 'y = 2x + 1 > 3', "Mixing '='");

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
check('step 0 error', (() => { const b = buildBranches(solveEquation('y = x'), 1, 10, 0); return b.error || ''; })(), 'x_step must be > 0 and <= 1000.');
check('range too large error', (() => { const b = buildBranches(solveEquation('y = x'), 1, 1000000); return b.error || ''; })(), 'Range too large (max 5000 points) — increase the step.');
{
  const b = buildBranches(solveEquation('y = x'), 0, 2, 0.5);
  check('fractional step 0.5 x values', b.branches[0].points.map(p => p.x), [0, 0.5, 1, 1.5, 2]);
  check('fractional step reported', b.step, 0.5);
}
{
  const b = buildBranches(solveEquation('y = x'), -1, 1, 0.25);
  check('fractional range x values', b.branches[0].points.map(p => p.x), [-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1]);
}

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

// --- functions (P2-1): y = f(x) expression path ---
{
  const sol = solveEquation('y = sin(x)');
  check('sin solves', sol.kind, 'function');
  check('sin display', sol.display, 'y = sin(x)');
  const b = buildBranches(sol, 1, 5);
  check('sin 5 pts', b.branches[0].points.length, 5);
  check('sin y(1)', Math.abs(b.branches[0].points[0].y - Math.sin(1)) < 1e-9, true);
}
check('2y=sin(x)', solveEquation('2y = sin(x)').display, 'y = sin(x) / 2');
check('-2y=sin(x)', solveEquation('-2y = sin(x)').display, 'y = \u2212sin(x) / 2');
check('sin(x)+y=3', solveEquation('sin(x) + y = 3').display, 'y = 3 \u2212 sin(x)');
check('y=x+sin(x)', solveEquation('y = x + sin(x)').display, 'y = x + sin(x)');
check('y*sin(x)=1', solveEquation('y*sin(x) = 1').display, 'y = 1 / sin(x)');
check('e^x', solveEquation('y = e^x').display, 'y = e^x');
check('pi*x', solveEquation('y = pi*x').display, 'y = pi * x');
check('(x+1)^2', solveEquation('y = (x+1)^2').display, 'y = (x + 1)^2');
check('2(x+1)', solveEquation('y = 2(x+1)').display, 'y = 2(x + 1)');
check('(x) solves', solveEquation('y = (x)').display, 'y = x');
check('ln alias', solveEquation('y = ln(x)').display, 'y = log(x)');
check('sqrt display', solveEquation('y = sqrt(x)').display, 'y = sqrt(x)');
check('abs display', solveEquation('y = abs(x)').display, 'y = abs(x)');
check('tan display', solveEquation('y = tan(x)').display, 'y = tan(x)');
{
  const b = buildBranches(solveEquation('y = log(x)'), -5, 5);
  check('log domain skips', b.branches[0].points.map(p => p.x), [1, 2, 3, 4, 5]);
}
{
  const b = buildBranches(solveEquation('y = sqrt(x)'), -10, 10);
  check('sqrt domain skips', b.branches[0].points.map(p => p.x), Array.from({ length: 11 }, (_, i) => i));
}
{
  const b = buildBranches(solveEquation('y = 1/(x-5)'), 1, 10);
  check('1/(x-5) segments', b.branches.map(br => br.points.length), [4, 5]);
}
{
  const b = buildBranches(solveEquation('y = sin(x)'), 1, 10, 2);
  check('function step respected', b.branches[0].points.map(p => p.x), [1, 3, 5, 7, 9]);
}
{
  const b = buildBranches(solveEquation('y = sin(x)'));
  check('function auto nice step', b.step, 0.5);
  check('function auto range', b.xRange, { min: 1, max: 100 });
  check('function auto 199 pts', b.branches[0].points.length, 199);
}
check('y = sin(y) is now implicit', solveEquation('y = sin(y)').kind, 'implicit');
checkErr('unknown function', 'y = foo(x)', 'Unknown function');
checkErr('unknown symbol', 'y = (bar)', 'Unknown symbol');
checkErr('parse garbage', 'y = (2 + * 3)', 'Unexpected');
checkErr('unclosed paren', 'y = sin(x+', 'Unexpected end of formula');
check('y + sin(x) = y + 2 is implicit', solveEquation('y + sin(x) = y + 2').kind, 'implicit');
{
  const b = buildBranches(solveEquation('y = sqrt(x)'), -10, -1);
  check('sqrt no real y', b.error || '', 'No real y for the given x range.');
}

// --- polar mode: r = f(θ) ---
{
  const sol = solveEquation('r = 2θ', true);
  check('polar solves', sol.kind, 'polar');
  check('polar display', sol.display, 'r = 2θ');
}
check('polar theta alias', solveEquation('r = 2*theta', true).display, 'r = 2θ');
check('polar coefficient fold', solveEquation('2r = 4θ', true).display, 'r = 2θ');
check('polar rose', solveEquation('r = cos(2θ)', true).display, 'r = cos(2θ)');
check('polar division', solveEquation('r = 2/θ', true).display, 'r = 2 / θ');
{
  const b = buildBranches(solveEquation('r = 2θ', true));
  check('polar default θ range', b.xRange, { min: 0, max: 4 * Math.PI });
  check('polar 252 pts', b.branches[0].points.length, 252);
  const near = b.branches[0].points.filter(p => Math.abs(p.y - Math.PI) < 0.1 && Math.abs(p.x) < 0.1);
  check('polar θ=π/2 maps to (≈0, π)', near.length >= 1, true);
  const p1 = b.branches[0].points[1];
  check('polar points carry theta+r', p1.theta === 0.05 && Math.abs(p1.r - 0.1) < 1e-12, true);
  const allOk = b.branches[0].points.every(p => Math.abs(p.r - 2 * p.theta) < 1e-9);
  check('polar r = 2θ everywhere', allOk, true);
  const cart = buildBranches(solveEquation('y = 2x + 1')).branches[0].points[0];
  check('cartesian points carry no theta', cart.theta === undefined && cart.r === undefined, true);
}
function checkErrPolar(name, raw, needle) {
  const sol = solveEquation(raw, true);
  if (sol.error && sol.error.includes(needle)) { console.log('ok   ' + name); }
  else { failures++; console.log('FAIL ' + name + ' -> ' + JSON.stringify(sol)); }
}
checkErrPolar('polar non-linear', 'r^2 = 2θ', 'linear in r');
checkErrPolar('polar no r', 'θ = 2', 'no effective r term');
checkErrPolar('polar unknown func', 'r = foo(θ)', 'Unknown function');

process.exit(failures === 0 ? 0 : 1);
