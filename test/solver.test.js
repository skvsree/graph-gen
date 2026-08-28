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
vm.runInContext(m[1] + '\nthis.__api = { solveEquation: solveEquation, evalPoly: evalPoly, fmt: fmt, parseTerm: parseTerm };', sandbox);

const { solveEquation, evalPoly, fmt } = sandbox.__api;

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
check('parseTerm("x")', sandbox.__api.parseTerm('x'), { coeff: 1, varName: 'x', exp: 1 });
check('parseTerm("-y")', sandbox.__api.parseTerm('-y'), { coeff: -1, varName: 'y', exp: 1 });
check('parseTerm("2x")', sandbox.__api.parseTerm('2x'), { coeff: 2, varName: 'x', exp: 1 });
check('parseTerm("x^3")', sandbox.__api.parseTerm('x^3'), { coeff: 1, varName: 'x', exp: 3 });

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
checkErr('y squared', 'y^2 = x', 'linear in y');
checkErr('empty rhs', 'x = ', 'Both sides');
checkErr('empty lhs', '= 3', 'Both sides');
checkErr('garbage term', 'y = @#$', 'Cannot understand');
checkErr('empty input', '   ', 'Enter a formula');

console.log(failures === 0 ? '\nALL TESTS PASSED' : '\n' + failures + ' TEST(S) FAILED');
process.exit(failures === 0 ? 0 : 1);
