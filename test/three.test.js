#!/usr/bin/env node
'use strict';
/* Unit tests for the pure helpers of the 3D surface page.
 *
 * Same approach as test/solver.test.js: extract the CLASSIC <script> from the
 * template and run it in a `vm` sandbox with no DOM. (`/ <script>([\s\S]*?)<\
 * /script>/` cannot match the module script above it, which carries attributes
 * and loads three.js — so this suite needs no WebGL and no browser.)
 *
 * Every helper listed in the template's `__api` object must be destructured
 * here; test_api.py asserts the two lists match exactly.
 */
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'templates', 'three.html'), 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.error('FAIL: no classic <script> found in three.html'); process.exit(1); }
if (m[1].includes('WebGLRenderer(') === false) { console.error('FAIL: extracted the wrong script'); process.exit(1); }

const sandbox = {
  console, Math, Number, String, Object, Array, Set, Map, JSON, isFinite, Infinity,
  parseInt, parseFloat, Float32Array, Uint32Array,
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
// `typeof window === 'undefined'` keeps boot(), the DOM code and the service
// worker registration from running here.
vm.runInContext(m[1], sandbox);

const {
  num, clamp01, heightT, parseHex, mixRgb,
  srgbToLinear, niceStep, niceTicks, tickLabel,
  fitView, clampPolar, camPos, rampFor, frameZ,
  surfaceBuffers, errorText, attrEscape,
} = sandbox.__api;

let failures = 0;
function check(name, actual, expected) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a === e) { console.log('ok   ' + name); }
  else { failures++; console.log('FAIL ' + name + '\n  expected: ' + e + '\n  actual:   ' + a); }
}
function near(name, actual, expected, tol) {
  const t = tol === undefined ? 1e-9 : tol;
  if (typeof actual === 'number' && Math.abs(actual - expected) <= t) { console.log('ok   ' + name); }
  else { failures++; console.log('FAIL ' + name + '\n  expected: ' + expected + ' +/- ' + t + '\n  actual:   ' + actual); }
}

// --- num(): the hole rule ---------------------------------------------------
// `isFinite(null)` is TRUE, so a hole would silently be plotted as z = 0 and
// its cell triangulated across the asymptote. This is the guard for that.
check('num(null) is false', num(null), false);
check('num(undefined) is false', num(undefined), false);
check('num(NaN) is false', num(NaN), false);
check('num(Infinity) is false', num(Infinity), false);
check('num("3") is false (strings are not samples)', num('3'), false);
check('num(0) is true', num(0), true);
check('num(-1.5) is true', num(-1.5), true);

// --- height ramp ------------------------------------------------------------
check('clamp01(-1)', clamp01(-1), 0);
check('clamp01(2)', clamp01(2), 1);
check('clamp01(0.25)', clamp01(0.25), 0.25);
near('heightT midpoint', heightT(0, -1, 1), 0.5);
check('heightT at the bottom', heightT(-1, -1, 1), 0);
check('heightT at the top', heightT(1, -1, 1), 1);
check('heightT clamps above', heightT(99, -1, 1), 1);
check('heightT clamps below', heightT(-99, -1, 1), 0);
check('heightT flat span is 0.5 (not a divide by zero)', heightT(2, 1, 1), 0.5);
check('heightT(flat span, NaN lo)', heightT(2, NaN, 6), 0.5);
check('heightT of a hole is 0', heightT(null, -1, 1), 0);

// --- colour -----------------------------------------------------------------
check('parseHex #fff', parseHex('#fff'), [255, 255, 255]);
check('parseHex #2563eb', parseHex('#2563eb'), [37, 99, 235]);
check('parseHex is case insensitive', parseHex('#FF0000'), [255, 0, 0]);
check('parseHex trims', parseHex('  #0a0b0c '), [10, 11, 12]);
check('parseHex rejects 4 digits', parseHex('#abcd'), null);
check('parseHex rejects 5 digits', parseHex('#12345'), null);
check('parseHex rejects a bare hex (no #)', parseHex('2563eb'), null);
check('parseHex rejects a name', parseHex('tomato'), null);
check('parseHex rejects rgb()', parseHex('rgb(1,2,3)'), null);
check('parseHex rejects empty', parseHex(''), null);
check('parseHex rejects null', parseHex(null), null);
check('parseHex rejects an injection attempt', parseHex('#-->'), null);
check('mixRgb midpoint', mixRgb([0, 0, 0], [10, 20, 30], 0.5), [5, 10, 15]);
check('mixRgb t=0', mixRgb([1, 2, 3], [9, 9, 9], 0), [1, 2, 3]);
check('mixRgb t=1', mixRgb([1, 2, 3], [9, 9, 9], 1), [9, 9, 9]);
near('srgbToLinear(0)', srgbToLinear(0), 0);
near('srgbToLinear(1)', srgbToLinear(1), 1);
// three.js expects vertex-colour attributes in LINEAR space; piping an sRGB
// value straight in renders visibly dark (0.5 -> 0.5 instead of 0.2140).
near('srgbToLinear(0.5) is the sRGB curve, not a passthrough', srgbToLinear(0.5), 0.21404114, 1e-6);
near('srgbToLinear(0.04) is still linear', srgbToLinear(0.04), 0.04 / 12.92, 1e-9);

// --- axes -------------------------------------------------------------------
check('niceStep(0.9) -> 1', niceStep(0.9), 1);
check('niceStep(1.5) -> 2', niceStep(1.5), 2);
check('niceStep(3) -> 5', niceStep(3), 5);
check('niceStep(7) -> 10', niceStep(7), 10);
near('niceStep(0.02) -> 0.02', niceStep(0.02), 0.02);
check('niceStep(0) does not divide by zero', niceStep(0), 1);
check('niceStep(negative) does not produce a negative step', niceStep(-5), 1);
check('niceTicks(-5, 5, 5)', niceTicks(-5, 5, 5), { values: [-4, -2, 0, 2, 4], step: 2 });
check('niceTicks(0, 1, 5)', niceTicks(0, 1, 5).values, [0, 0.2, 0.4, 0.6000000000000001, 0.8, 1]);
check('niceTicks(0, 1, 5) step', niceTicks(0, 1, 5).step, 0.2);
check('niceTicks degenerate window', niceTicks(5, 5, 5), { values: [], step: 0 });
check('niceTicks inside the window only', niceTicks(0.5, 9.5, 5), { values: [2, 4, 6, 8], step: 2 });
check('tickLabel(0)', tickLabel(0), '0');
check('tickLabel(-2)', tickLabel(-2), '-2');
check('tickLabel(0.30000000000000004)', tickLabel(0.30000000000000004), '0.3');
check('tickLabel(huge)', tickLabel(1234567), '1.2e+6');
check('tickLabel(null)', tickLabel(null), '');

// --- camera -----------------------------------------------------------------
// fitView frames the whole bounding box off its DIAGONAL: the saddle spans 50 in
// z but only 10 in x and y, so framing the longest side alone left the surface a
// sliver in the middle of the card (seen in a real screenshot).
{
  const f = fitView(-5, 5, -5, 5, -25, 25);
  check('fitView centres an even window', f.target, [0, 0, -0]);
  near('fitView spans the box diagonal', f.span, 51.961524, 1e-5);
  near('fitView fits the box in the vertical FOV', f.distance, 76.037924, 1e-5);
}
{
  const f = fitView(1, 3, 2, 6, 0, 10);
  check('fitView maps maths y onto three -z', f.target, [2, 5, -4]);
  near('fitView span on an off-centre box', f.span, 10.954451, 1e-5);
  near('fitView distance on an off-centre box', f.distance, 16.030202, 1e-5);
}
near('fitView never divides by a zero span', fitView(1, 1, 1, 1, 1, 1).span, 2e-6, 1e-9);
near('clampPolar(0) keeps the camera off the pole', clampPolar(0), 0.02);
near('clampPolar(pi)', clampPolar(Math.PI), Math.PI - 0.02);
check('clampPolar passes a normal angle through', clampPolar(1), 1);
{
  const p = camPos([0, 0, 0], 10, 0, Math.PI / 2);
  near('camPos azimuth 0 -> +z', p[2], 10);
  near('camPos azimuth 0 -> y 0', p[1], 0, 1e-12);
  const q = camPos([1, 2, 3], 5, Math.PI / 2, Math.PI / 2);
  near('camPos is relative to the target (x)', q[0], 6);
  near('camPos keeps the target height at the equator', q[1], 2, 1e-12);
  near('camPos is relative to the target (z)', q[2], 3, 1e-12);
  const r0 = camPos([0, 0, 0], 10, 0, 0);
  near('camPos at polar 0 is directly above', r0[1], 10);
}

// --- surfaceBuffers: geometry, holes, ramp ---------------------------------
{
  const xs = [0, 1, 2], ys = [0, 1, 2];
  const flat = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const b = surfaceBuffers(xs, ys, flat, '#000000', '#ffffff', -1, 1);
  check('flat grid vertex count', b.position.length, 27);
  check('flat grid triangle indices', b.index.length, 24);
  check('flat grid cells', b.cells, 4);
  check('flat grid has no holes', b.holes, 0);
  check('flat grid finite samples', b.finite, 9);
  check('flat grid mesh lines', b.wire.length, 72);   // 12 segments x 6 floats
  // maths (x, y, z) -> three (x, z, -y): vertex (i = 1, j = 2) is (1, 0, -2).
  check('vertex mapping is (x, z, -y)', Array.from(b.position.slice(21, 24)), [1, 0, -2]);
  // The ramp is mixed in LINEAR space (both ends are linearised first), which
  // is why a z at the middle of the range gets 0.5 — a mid-grey in linear light
  // — rather than the darker srgbToLinear(0.5) ~ 0.214. Mixing linearly is the
  // physically correct choice and it keeps both ENDPOINTS exactly equal to the
  // colours the user picked (checked by the two `lowest/highest z` cases below).
  near('mid-ramp colour mixes in linear light', b.color[0], 0.5, 1e-7);
}
{
  const xs = [0, 1], ys = [0, 1];
  const ramp = [[0, 1], [0, 1]];
  const b = surfaceBuffers(xs, ys, ramp, '#000000', '#ffffff', 0, 1);
  near('lowest z gets the low colour', b.color[0], 0);
  near('highest z gets the high colour', b.color[3], 1);
  check('ramp grid cells', b.cells, 1);
}
{
  // A hole (undefined z) in the middle of a 3x3 grid: all four touching cells
  // must be dropped, and the hole must NOT be bridged by a triangle.
  const xs = [0, 1, 2], ys = [0, 1, 2];
  const zs = [[0, 0, 0], [0, null, 0], [0, 0, 0]];
  const b = surfaceBuffers(xs, ys, zs, '#000000', '#ffffff', 0, 1);
  check('hole drops every touching cell', b.cells, 0);
  check('hole count', b.holes, 4);
  check('no triangle references a hole', b.index.length, 0);
  check('holes are not counted as samples', b.finite, 8);
  check('hole vertex sits at z = 0', Array.from(b.position.slice(12, 15)), [1, 0, -1]);
  check('mesh lines skip the hole', b.wire.length, 48);  // 8 segments x 6 floats
  for (let i = 0; i < b.wire.length; i++) {
    if (b.wire[i] === 1 && b.wire[i + 2] === -1) { failures++; console.log('FAIL a mesh line ends on the hole'); break; }
  }
}
{
  // NaN and Infinity behave exactly like null (the server sends null, but a
  // hand-built payload or a future client solver may send NaN).
  const xs = [0, 1], ys = [0, 1];
  const b = surfaceBuffers(xs, ys, [[0, NaN], [0, Infinity]], '#000000', '#ffffff', 0, 1);
  check('NaN/Infinity are holes', b.cells, 0);
  check('NaN/Infinity hole count', b.holes, 1);
}
{
  // A bad ramp must not throw: the buffers fall back to black.
  const xs = [0, 1], ys = [0, 1];
  const b = surfaceBuffers(xs, ys, [[0, 1], [0, 1]], 'nope', null, 0, 1);
  check('an unparsable ramp still builds', b.position.length, 12);
  check('an unparsable ramp falls back to black', Array.from(b.color.slice(0, 3)), [0, 0, 0]);
}

// --- multiple surfaces ------------------------------------------------------
// Default ramp per row: a second surface must not be a carbon copy of the first.
check('rampFor(0) is the original pair', rampFor(0), ['#2563eb', '#dc2626']);
check('rampFor(1) is a different pair', rampFor(1), ['#059669', '#facc15']);
check('rampFor wraps past the end', rampFor(5), rampFor(0));
check('rampFor hands back a fresh copy each call', rampFor(0) === rampFor(0), false);
{
  rampFor(0)[0] = '#000000';
  check('mutating a rampFor result cannot poison the table', rampFor(0)[0], '#2563eb');
}
{
  // The framing z window is the UNION of every surface's robust range: one
  // surface's spike must not zoom the others away, and a flat plane at z = 0
  // must not collapse the box.
  const data = {
    surfaces: [
      { z_range: { min: -25, max: 25 }, z_robust: { min: -23.4, max: 23.4 } },
      { z_range: { min: 0, max: 50 }, z_robust: { min: 0, max: 44 } },
    ],
  };
  check('frameZ spans every surface', frameZ(data), { min: -23.4, max: 44 });
}
check('frameZ of a flat plane stays finite', frameZ({
  surfaces: [{ z_range: { min: 0, max: 0 }, z_robust: { min: 0, max: 0 } }],
}), { min: 0, max: 1e-9 });
check('frameZ survives a missing range', frameZ({ surfaces: [{}] }), { min: -1, max: 1 });

// --- attribute escaping (the duplicate button copies a formula into markup) --
check('attrEscape escapes a quote', attrEscape('z = "x"'), 'z = &quot;x&quot;');
check('attrEscape escapes the tag characters', attrEscape('<script>'), '&lt;script&gt;');
check('attrEscape escapes an ampersand', attrEscape('a&b'), 'a&amp;b');
check('attrEscape handles null', attrEscape(null), '');

// --- error shapes -----------------------------------------------------------
// FastAPI's 422 detail is an ARRAY of objects: rendering it straight into
// textContent showed "[object Object]" on the live 2D page.
check('errorText(string)', errorText('boom'), 'boom');
check('errorText({detail})', errorText({ detail: 'bad formula' }), 'bad formula');
check('errorText(422 array)', errorText([{ msg: 'a' }, { msg: 'b' }]), 'a; b');
check('errorText(nested detail array)', errorText({ detail: [{ msg: 'x' }] }), 'x');
check('errorText(null)', errorText(null), 'Something went wrong.');
check('errorText(undefined)', errorText(undefined), 'Something went wrong.');
check('errorText keeps its head on an odd object', errorText({ weird: 1 }), '{"weird":1}');

if (failures) {
  console.log('\n' + failures + ' failure(s)');
  process.exit(1);
}
console.log('\nall 3D helper checks passed');
