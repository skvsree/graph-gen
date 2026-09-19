/* xy-graph-gen — service worker.
 *
 * Makes the grapher installable and usable offline:
 *   - the app shell ("/", "/3d", the manifest, the icons) is precached at
 *     install, each page under its own path;
 *   - navigations are network-first, falling back to the cached shell, so a
 *     deploy is picked up immediately but an offline reload still works;
 *   - GET /api/points and GET /api/surface are network-first with a bounded
 *     runtime cache, so a graph (or a 3D surface) you already plotted still
 *     draws offline. A never-plotted 2D formula offline is NOT a dead end:
 *     the page's built-in client-side solver takes over as soon as this worker
 *     rejects the fetch (the throw below is what triggers it) — hence the
 *     deliberate `throw err` on a total miss. (The 3D page has no client-side
 *     solver, so it says so plainly instead of showing a blank card.)
 *   - /vendor/ (three.js, mp4-muxer) is cache-first on use, never precached:
 *     someone who only plots 2D curves never pays for the WebGL library;
 *   - the Google font CSS/woff2 are stale-while-revalidate, so the hand-drawn
 *     face survives offline after one online visit;
 *   - /api/hits, /metrics and /health stay network-only: these are live data,
 *     caching them would just show stale numbers.
 *
 * BUMP `VERSION` on every shell change (template, icons, manifest): the old
 * caches are dropped in `activate`, and the page reloads once via the
 * controllerchange handler in templates/index.html.
 */

const VERSION = 'v15';
const SHELL_CACHE = 'xygg-shell-' + VERSION;
const API_CACHE = 'xygg-api-' + VERSION;
const FONT_CACHE = 'xygg-fonts-' + VERSION;
const KEEP = [SHELL_CACHE, API_CACHE, FONT_CACHE];

// Minimal set that must exist for an offline start. Keep it small and
// guaranteed-200 — a single 404 fails the whole install. The 3D page is tiny
// (its three.js is cached on demand by the /vendor/ rule, so the 720 KB of
// vendored WebGL code is not forced on someone who only ever plots 2D curves).
const SHELL_URLS = [
  '/',
  '/3d',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
];

const API_CACHE_MAX = 60;   // plotted graphs kept for offline
const FONT_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com'];

// --- install / activate -----------------------------------------------------

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    // Individually, so one failure can't abort the install.
    await Promise.all(SHELL_URLS.map((u) => cache.add(u).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => !KEEP.includes(k)).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

// --- helpers ----------------------------------------------------------------

async function putSafe(cache, request, response) {
  // `cache.put` rejects on a 206 or a `Vary: *` response; never let a caching
  // hiccup break the request it was piggy-backing on.
  try {
    await cache.put(request, response);
    return true;
  } catch (e) {
    return false;
  }
}

async function trim(cache, max) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - max; i++) await cache.delete(keys[i]);
}

function offlinePage() {
  return '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">' +
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">' +
    '<title>Offline — xy-graph-gen</title><style>' +
    'body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;' +
    'background:#f8fafc;color:#0f172a;display:flex;align-items:center;justify-content:center;' +
    'min-height:100vh;text-align:center;padding:24px}' +
    'h1{font-size:20px;margin:0 0 8px}p{color:#64748b;margin:0;font-size:15px}' +
    '</style></head><body><div><h1>You are offline</h1>' +
    '<p>xy-graph-gen has not been cached on this device yet.<br>' +
    'Reconnect once, then it will open without a network.</p></div></body></html>';
}

// --- strategies -------------------------------------------------------------

async function shellFirst(request) {
  // The shell is cached PER PATH ('/' and '/3d' are different pages). It used
  // to be cached under '/' only, which would have made an offline visit to the
  // 2D page serve the 3D page (and vice versa) as soon as both had been opened
  // — normalising the query string away is still needed, so a deep link such
  // as /3d?formula=… finds the shell.
  let path = '/';
  try {
    path = new URL(request.url).pathname || '/';
  } catch (e) {
    path = '/';
  }
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      const cache = await caches.open(SHELL_CACHE);
      await putSafe(cache, path, response.clone());
    }
    return response;
  } catch (e) {
    const cache = await caches.open(SHELL_CACHE);
    const cached = (await cache.match(path)) || (await cache.match(request))
      || (await cache.match('/'));
    if (cached) return cached;
    return new Response(offlinePage(), {
      status: 503,
      headers: { 'Content-Type': 'text/html; charset=utf-8' },
    });
  }
}

async function apiFirst(request) {
  const cache = await caches.open(API_CACHE);
  try {
    const response = await fetch(request);
    if (response && response.ok) {
      if (await putSafe(cache, request, response.clone())) await trim(cache, API_CACHE_MAX);
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw err; // network error -> the page's client-side solver fallback runs
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(SHELL_CACHE);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.ok) await putSafe(cache, request, response.clone());
  return response;
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then(async (response) => {
      if (response && (response.ok || response.type === 'opaque')) {
        await putSafe(cache, request, response.clone());
      }
      return response;
    })
    .catch(() => null);
  if (cached) return cached;
  const response = await network;
  if (response) return response;
  return new Response('', { status: 504, statusText: 'Offline' });
}

// --- routing ----------------------------------------------------------------

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;

  let url;
  try {
    url = new URL(request.url);
  } catch (e) {
    return;
  }
  const sameOrigin = url.origin === self.location.origin;

  if (request.mode === 'navigate') {
    event.respondWith(shellFirst(request));
    return;
  }
  if (!sameOrigin) {
    if (FONT_HOSTS.includes(url.hostname)) {
      event.respondWith(staleWhileRevalidate(request, FONT_CACHE));
    }
    return;
  }
  if (url.pathname === '/api/points' || url.pathname === '/api/surface') {
    event.respondWith(apiFirst(request));
    return;
  }
  if (url.pathname === '/manifest.webmanifest' || url.pathname.startsWith('/icons/')
      || url.pathname.startsWith('/vendor/') || url.pathname === '/favicon.ico') {
    event.respondWith(cacheFirst(request));
    return;
  }
  // Everything else (/api/hits, /metrics, /health, …) is live data: let the
  // network handle it, and let it fail when offline.
});
