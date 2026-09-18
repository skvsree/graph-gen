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
vm.runInContext(m[1] + '\nthis.__api = { solveEquation: solveEquation, evalPoly: evalPoly, fmt: fmt, parseTerm: parseTerm, buildBranches: buildBranches, evalAst: evalAst, astStr: astStr, applyFunc: applyFunc, applyFunc2: applyFunc2, colorFill: colorFill, colorWithAlpha: colorWithAlpha, spliceAtCaret: spliceAtCaret, FN_HELP: FN_HELP, FN_CONSTS: FN_CONSTS, FUNCTIONS: FUNCTIONS, TWO_ARG_FUNCTIONS: TWO_ARG_FUNCTIONS, styleDash: styleDash, styleCap: styleCap, styleLabel: styleLabel, strokeNum: strokeNum, STYLE_OPTIONS: STYLE_OPTIONS, DEFAULT_STYLE: DEFAULT_STYLE, DEFAULT_STROKE_WIDTH: DEFAULT_STROKE_WIDTH, calligraphyWidth: calligraphyWidth, pencilJitter: pencilJitter, hashUnit: hashUnit, penLabel: penLabel, PEN_OPTIONS: PEN_OPTIONS, DEFAULT_PEN: DEFAULT_PEN, animRowTotals: animRowTotals, animCounts: animCounts, animRate: animRate, animDurationMs: animDurationMs, animBranchCounts: animBranchCounts, ANIM_BASE_MS: ANIM_BASE_MS, ANIM_SPEEDS: ANIM_SPEEDS, animVideoTimes: animVideoTimes, pickVideoMime: pickVideoMime, VIDEO_MIMES: VIDEO_MIMES, ANIM_VIDEO_FPS: ANIM_VIDEO_FPS, videoPushable: videoPushable, videoStrategy: videoStrategy, MP4_VIDEO_CODECS: MP4_VIDEO_CODECS, VIDEO_BITRATE: VIDEO_BITRATE, videoFallbackReason: videoFallbackReason, animRowCounts: animRowCounts, animTotalMs: animTotalMs };', sandbox);

const { solveEquation, evalPoly, fmt, parseTerm, buildBranches, evalAst, astStr, applyFunc, applyFunc2, colorFill, colorWithAlpha, spliceAtCaret, FN_HELP, FN_CONSTS, FUNCTIONS, TWO_ARG_FUNCTIONS, styleDash, styleCap, styleLabel, strokeNum, STYLE_OPTIONS, DEFAULT_STYLE, DEFAULT_STROKE_WIDTH, calligraphyWidth, pencilJitter, hashUnit, penLabel, PEN_OPTIONS, DEFAULT_PEN, animRowTotals, animCounts, animRate, animDurationMs, animBranchCounts, ANIM_BASE_MS, ANIM_SPEEDS, animVideoTimes, pickVideoMime, VIDEO_MIMES, ANIM_VIDEO_FPS, videoPushable, videoStrategy, MP4_VIDEO_CODECS, VIDEO_BITRATE, videoFallbackReason, animRowCounts, animTotalMs } = sandbox.__api;

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

// --- extended function set (Sep 2026): inverses, hyperbolics, log10/log2,
// --- cbrt, floor/ceil/round/sign, the two-argument atan2, and the gradient
// --- colour helper used by the legend/table dots ---
check('asin display', solveEquation('y = asin(x)').display, 'y = asin(x)');
check('acos display', solveEquation('y = acos(x)').display, 'y = acos(x)');
check('atan display', solveEquation('y = atan(x)').display, 'y = atan(x)');
check('sinh display', solveEquation('y = sinh(x)').display, 'y = sinh(x)');
check('cosh display', solveEquation('y = cosh(x)').display, 'y = cosh(x)');
check('tanh display', solveEquation('y = tanh(x)').display, 'y = tanh(x)');
check('log10 display', solveEquation('y = log10(x)').display, 'y = log10(x)');
check('log2 display', solveEquation('y = log2(x)').display, 'y = log2(x)');
check('cbrt display', solveEquation('y = cbrt(x)').display, 'y = cbrt(x)');
check('floor display', solveEquation('y = floor(x)').display, 'y = floor(x)');
check('ceil display', solveEquation('y = ceil(x)').display, 'y = ceil(x)');
check('round display', solveEquation('y = round(x)').display, 'y = round(x)');
check('sign display', solveEquation('y = sign(x)').display, 'y = sign(x)');
check('atan2 display', solveEquation('y = atan2(x, 1)').display, 'y = atan2(x, 1)');
check('2tanh display', solveEquation('y = 2tanh(x)').display, 'y = 2tanh(x)');
{
  const b = buildBranches(solveEquation('y = asin(x)'), -3, 3);
  check('asin domain skips', b.branches[0].points.map(p => p.x), [-1, 0, 1]);
}
{
  const b = buildBranches(solveEquation('y = acos(x)'), -3, 3);
  check('acos domain skips', b.branches[0].points.map(p => p.x), [-1, 0, 1]);
}
{
  const b = buildBranches(solveEquation('y = log10(x)'), -2, 3);
  check('log10 domain skips', b.branches[0].points.map(p => p.x), [1, 2, 3]);
}
{
  const b = buildBranches(solveEquation('y = log2(x)'), 8, 8);
  check('log2 value', b.branches[0].points.map(p => p.y), [3]);
}
{
  const b = buildBranches(solveEquation('y = cbrt(x)'), -8, 8, 8);
  check('cbrt keeps negatives real', b.branches[0].points.map(p => p.y), [-2, 0, 2]);
}
{
  const b = buildBranches(solveEquation('y = round(x)'), 0.5, 2.5, 0.5);
  check('round is half-up (Math.round)', b.branches[0].points.map(p => p.y), [1, 1, 2, 2, 3]);
}
{
  const b = buildBranches(solveEquation('y = floor(x)'), -1.2, 1.8, 1.5);
  check('floor values', b.branches[0].points.map(p => p.y), [-2, 0, 1]);
}
{
  const b = buildBranches(solveEquation('y = ceil(x)'), -1.2, 1.8, 1.5);
  check('ceil values', b.branches[0].points.map(p => p.y), [-1, 1, 2]);
}
{
  const b = buildBranches(solveEquation('y = sign(x)'), -3, 4, 1);
  check('sign values', b.branches[0].points.map(p => p.y), [-1, -1, -1, 0, 1, 1, 1, 1]);
}
{
  const b = buildBranches(solveEquation('y = atan2(x, 1)'), 1, 3);
  check('atan2(y=1, x=1) = pi/4', Math.abs(b.branches[0].points[0].y - Math.PI / 4) < 1e-12, true);
}
check('atan2 with y is implicit', solveEquation('y = atan2(y, x)').kind, 'implicit');
checkErr('atan2 one arg', 'y = atan2(x)', 'takes two arguments');
checkErr('atan2 three args', 'y = atan2(x, 1, 2)', 'Missing closing parenthesis');
checkErr('sin two args', 'y = sin(x, 1)', 'takes one argument');
check('x2 still x*2', solveEquation('y = x2').kind, 'implicit');
// Unknown names stay whole (never split into a known prefix + rest).
checkErr('unknown word kept whole', 'y = (logish)', 'Unknown symbol');
checkErr('unknown name kept whole', 'y = (sinx)', 'Unknown symbol');
check('applyFunc log10', applyFunc('log10', 1000), 3);
check('applyFunc cbrt', applyFunc('cbrt', -8), -2);
check('applyFunc2 atan2', Math.abs(applyFunc2('atan2', 1, 1) - Math.PI / 4) < 1e-12, true);
check('flat fill has no gradient', colorFill('#ff0000', '#ff0000', 1), 'rgba(255,0,0,1)');
check('missing end colour = flat', colorFill('#ff0000', undefined, 0.5), 'rgba(255,0,0,0.5)');
check('gradient fill', colorFill('#ff0000', '#0000ff', 1),
      'linear-gradient(90deg, rgba(255,0,0,1), rgba(0,0,255,1))');

// --- function menu: pure caret-splice helper + menu/tooltip lockstep ---
check('splice at caret mid-text', spliceAtCaret('y = 6', 4, 4, 'sin('),
      { value: 'y = sin(6', caret: 8 });
check('splice replaces a selection', spliceAtCaret('y = abc', 4, 7, 'x'),
      { value: 'y = x', caret: 5 });
check('caret lands inside the new parens', spliceAtCaret('y = ', 4, 4, 'log10(').caret, 10);
check('splice appends when there is no caret', spliceAtCaret('y = 2*', undefined, undefined, 'cos('),
      { value: 'y = 2*cos(', caret: 10 });
check('splice clamps an out-of-range caret', spliceAtCaret('y = x', 99, 99, 'pi'),
      { value: 'y = xpi', caret: 7 });
check('splice tolerates an empty field', spliceAtCaret('', 0, 0, 'sqrt('),
      { value: 'sqrt(', caret: 5 });
check('every function has a menu tooltip', FUNCTIONS.every(n => typeof FN_HELP[n] === 'string'), true);
check('no stale menu tooltips', Object.keys(FN_HELP).every(n => FUNCTIONS.indexOf(n) !== -1), true);
check('constants offered in the menu', FN_CONSTS.map(p => p[0]), ['pi', 'e', '\u03b8']);
check('atan2 advertised as two-argument', TWO_ARG_FUNCTIONS.indexOf('atan2') !== -1, true);

// --- line thickness + styles + pens (pure helpers) ---
check('solid style has no dash', styleDash('solid', 2.5), []);
check('dashed scales with width', styleDash('dashed', 2), [6, 4]);
check('dashed grows for a thick line', styleDash('dashed', 10), [30, 20]);
check('dash never collapses on a thin line', styleDash('dashed', 0.5), [3, 2]);
check('dotted is a dot pattern', styleDash('dotted', 2), [0.01, 4.4]);
check('dashdot pattern', styleDash('dashdot', 2), [7, 4, 0.01, 4]);
check('longdash pattern', styleDash('longdash', 2), [14, 6]);
check('unknown style falls back to solid', styleDash('wobble', 3), []);
check('dotted needs round caps', styleCap('dotted'), 'round');
check('dashdot needs round caps', styleCap('dashdot'), 'round');
check('dashed uses butt caps', styleCap('dashed'), 'butt');
check('solid keeps round caps', styleCap('solid'), 'round');
check('strokeNum default', strokeNum(''), 2.5);
check('strokeNum parses', strokeNum('6.5'), 6.5);
check('strokeNum clamps high', strokeNum('99'), 12);
check('strokeNum clamps low', strokeNum('0.1'), 0.5);
check('strokeNum rejects junk', strokeNum('abc'), 2.5);
check('style menu order', STYLE_OPTIONS.map(p => p[0]),
      ['solid', 'dashed', 'dotted', 'dashdot', 'longdash']);
check('every style has a label', STYLE_OPTIONS.every(p => p[1].length >= 4), true);
check('default style is solid', DEFAULT_STYLE, 'solid');
check('styleLabel', styleLabel('dashdot'), 'Dash-dot');

// --- pens: calligraphy nib maths + deterministic pencil noise ---
check('pen menu order', PEN_OPTIONS.map(p => p[0]),
      ['technical', 'pencil', 'marker', 'calligraphy', 'highlighter']);
check('default pen is technical', DEFAULT_PEN, 'technical');
check('penLabel', penLabel('calligraphy'), 'Calligraphy');
{
  // Full width across the nib edge (135° to a 45° nib), a quarter along it.
  check('chisel is full width across the edge', calligraphyWidth(3 * Math.PI / 4, 10), 10);
  check('chisel is a quarter width along the edge', calligraphyWidth(Math.PI / 4, 10), 2.5);
  check('chisel never vanishes', calligraphyWidth(Math.PI / 4, 2) > 0, true);
  // Horizontals and verticals are symmetric and bold-ish; a 45° diagonal is
  // thinner than both (the classic calligraphy modulation).
  const h = calligraphyWidth(0, 10), v = calligraphyWidth(Math.PI / 2, 10);
  check('horizontal and vertical match', Math.abs(h - v) < 1e-12, true);
  check('diagonal is thinner than straight', calligraphyWidth(Math.PI / 4, 10) < h, true);
}
{
  // Deterministic: same inputs -> same noise, and it stays in range. Random
  // jitter would crawl on every pan/zoom/redraw.
  const a = pencilJitter(3, 1, 7), b = pencilJitter(3, 1, 7), c = pencilJitter(3, 1, 8);
  check('pencil noise is deterministic', a, b);
  check('pencil noise differs per point', a[0] === c[0] && a[1] === c[1], false);
  check('pencil offsets stay in [-1, 1]',
        a.slice(0, 2).every(v => v >= -1 && v <= 1), true);
  check('pencil alpha stays in [0, 1]', a[2] >= 0 && a[2] <= 1, true);
  check('different rows get different noise', pencilJitter(1, 0, 5)[0] === pencilJitter(2, 0, 5)[0], false);
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

// ── draw animation + video export (pure helpers) ────────────────────────────
{
  // The pace the user asked to slow down: 2.6s -> 4s for the longest row at 1x.
  check('animation base duration is 4000ms at 1x', ANIM_BASE_MS, 4000);
  check('speed ladder', ANIM_SPEEDS, [0.5, 1, 2, 4]);
  check('duration follows the speed menu (1x on garbage)',
        [animDurationMs(0.5), animDurationMs(1), animDurationMs(2), animDurationMs(4), animDurationMs(0)],
        [8000, 4000, 2000, 1000, 4000]);

  check('row totals sum the row branches',
        animRowTotals([{ branches: [{ points: [1, 2, 3] }, { points: [1, 2] }] }, { branches: [] }]),
        [5, 0]);
  check('reveal starts at nothing', animCounts([100, 1000], 0, 1000 / 4000), [0, 0]);
  check('t < 0 means the whole graph', animCounts([100, 1000], -1, 1), [100, 1000]);
  check('rows share one rate and each clamps at its own total',
        [animCounts([100, 1000], 1000, 1000 / 4000), animCounts([100, 1000], 999999, 1000 / 4000)],
        [[100, 250], [100, 1000]]);
  check('an empty graph has rate 0 (playback still ends on time)', animRate([0, 0], 1), 0);
  check('the rate makes the longest row take the whole duration', animRate([10, 400], 1), 0.1);
  check('branches are consumed in order', animBranchCounts([5, 7, 4], 9), [5, 4, 0]);
  check('a zero reveal splits into nothing', animBranchCounts([5, 7], 0), [0, 0]);

  // Row-by-row: the SAME rate, so a curve traces at the same speed — only the
  // order changes, because each row must finish before the next one starts.
  // At 0.1 points/ms, 200ms is a budget of 20 points.
  check('row-by-row: the first row is traced before the second starts',
        animRowCounts([10, 30], 200, 0.1), [10, 10]);
  check('row-by-row: later rows are untouched while an earlier one draws',
        animRowCounts([10, 30], 50, 0.1), [5, 0]);
  check('row-by-row: the third row waits for the first two',
        animRowCounts([10, 20, 30], 320, 0.1), [10, 20, 2]);
  check('row-by-row: the budget never overflows a row',
        animRowCounts([10, 30], 1e6, 0.1), [10, 30]);
  check('row-by-row: nothing drawn at t = 0', animRowCounts([10, 30], 0, 0.1), [0, 0]);
  check('row-by-row: t < 0 is the finished drawing',
        animRowCounts([10, 30], -1, 0.1), [10, 30]);
  // The same totals, one budget: parallel spreads it, row-by-row serialises it.
  check('parallel counts spread one budget across the rows',
        animCounts([10, 30], 200, 0.1), [10, 20]);
  check('row-by-row counts spend it on the first row first',
        animRowCounts([10, 30], 200, 0.1), [10, 10]);

  // Span: parallel ends with the longest row, row-by-row with the LAST one.
  check('span: parallel is one base duration', animTotalMs([10, 30], 1, false), 4000);
  check('span: parallel does not grow with more rows',
        animTotalMs([30, 30, 30], 1, false), 4000);
  check('span: row-by-row is every row summed at the same rate',
        animTotalMs([10, 30], 1, true), 4000 * (40 / 30));
  check('span: row-by-row with three equal rows takes three times as long',
        animTotalMs([30, 30, 30], 1, true), 12000);
  check('span: row-by-row still follows the speed menu',
        animTotalMs([30, 30], 2, true), 4000);
  check('span: an empty graph keeps the base duration', animTotalMs([], 1, true), 4000);
  check('span: a point-less graph keeps the base duration',
        animTotalMs([0, 0], 1, true), 4000);
  check('span: junk totals keep the base duration', animTotalMs(null, 1, true), 4000);
}

{
  // Video export plan: 0 -> complete graph, ending on t = -1 (the finished
  // state the player itself ends on), evenly spaced at the capture rate.
  const times = animVideoTimes(4000, ANIM_VIDEO_FPS, 400);
  check('video plan: 25fps over 4s = 101 frames', times.length, 101);
  check('video plan starts at 0 and ends on the complete graph',
        [times[0], times[times.length - 1]], [0, -1]);
  check('video plan is evenly spaced at the capture rate', times[1], 40);
  check('video plan honours the frame cap', animVideoTimes(60000, 25, 400).length, 400);
  check('video plan survives junk input', animVideoTimes(0, 0, 0), [0, -1]);

  // Format ladder: Safari only writes MP4/H.264, Chromium/Firefox write WebM.
  check('mime ladder prefers mp4/h264 (Safari)',
        pickVideoMime(t => t === 'video/mp4;codecs=avc1.42E01E'),
        { mime: 'video/mp4;codecs=avc1.42E01E', ext: 'mp4' });
  check('mime ladder falls back to webm/vp8 (Chromium, Firefox)',
        pickVideoMime(t => t === 'video/webm;codecs=vp8'),
        { mime: 'video/webm;codecs=vp8', ext: 'webm' });
  check('mime ladder reports "cannot record" as null', pickVideoMime(() => false), null);
  check('mime ladder survives a throwing probe',
        pickVideoMime(() => { throw new Error('nope'); }), null);
  check('mime ladder is ordered mp4 -> webm',
        [VIDEO_MIMES[0][1], VIDEO_MIMES[VIDEO_MIMES.length - 1][1]], ['mp4', 'webm']);

  // Firefox's canvas track has no requestFrame() (reported live from the site:
  // "track.requestFrame is not a function"), so the export must be able to fall
  // back to sampling the canvas in real time.
  check('a track with requestFrame is pushable', videoPushable({ requestFrame: function () {} }), true);
  check('a track WITHOUT requestFrame is not pushable (Firefox, older Safari)',
        videoPushable({}), false);
  check('a missing track is not pushable', videoPushable(null), false);

  // Export strategy. WebCodecs + the vendored muxer is the good path: exact
  // frames, MP4 everywhere (Firefox included) and no real-time wait. The
  // MediaRecorder is the fallback, and it needs an encodable MIME to be usable.
  check('strategy: WebCodecs + muxer wins over a usable recorder',
        videoStrategy({ webcodecs: true, muxer: true, recorder: true, recordable: true }), 'webcodecs');
  check('strategy: no muxer falls back to a usable recorder',
        videoStrategy({ webcodecs: true, muxer: false, recorder: true, recordable: true }), 'recorder');
  check('strategy: no H.264 but a usable recorder -> recorder',
        videoStrategy({ webcodecs: false, muxer: true, recorder: true, recordable: true }), 'recorder');
  check('strategy: WebCodecs with no muxer and no recorder cannot record',
        videoStrategy({ webcodecs: true, muxer: false }), null);
  check('strategy: a recorder with no encodable format cannot record',
        videoStrategy({ webcodecs: false, muxer: true, recorder: true, recordable: false }), null);
  check('strategy: nothing available cannot record',
        videoStrategy({ webcodecs: false, muxer: false, recorder: false, recordable: false }), null);
  check('strategy: junk input cannot record', videoStrategy(null), null);

  // The H.264 ladder: baseline first (widest support), every entry an AVC profile.
  check('mp4 codec ladder starts on baseline', MP4_VIDEO_CODECS[0], 'avc1.42001F');
  check('mp4 codec ladder is all H.264/AVC',
        MP4_VIDEO_CODECS.every(function (c) { return c.indexOf('avc1.') === 0; }), true);
  check('bitrate is set for the encoder', VIDEO_BITRATE > 0, true);

  // When the export cannot be MP4, the user is told WHY. Reported from Android
  // Firefox ("still showing webm not mp4"): it has no VideoEncoder at all, so
  // the .webm arrives for a reason that is invisible from the outside.
  check('reason: a missing muxer is named',
        videoFallbackReason({ webcodecs: true, muxer: false }), 'the MP4 muxer did not load');
  check('reason: no H.264 encoder is named (Firefox for Android)',
        videoFallbackReason({ webcodecs: false, muxer: true }), 'this browser has no H.264 encoder');
  check('reason: an otherwise unexplained failure still says something',
        videoFallbackReason({ webcodecs: true, muxer: true }), 'MP4 encoding is unavailable here');
  check('reason: junk input still explains itself',
        videoFallbackReason(null), 'the MP4 muxer did not load');
}

process.exit(failures === 0 ? 0 : 1);
