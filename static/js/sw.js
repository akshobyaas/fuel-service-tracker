// ── Fuel Tracker Service Worker — Phase 5A ──
const CACHE_NAME  = 'fst-v1';
const OFFLINE_URL = '/offline/';

// Shell assets to pre-cache on install
const PRECACHE = [
  '/',
  '/offline/',
  '/static/trk/css/style.css',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css',
  'https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Space+Mono:wght@400;700&display=swap',
];

// Install: cache shell
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// Activate: remove stale caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// Fetch strategy:
//   Navigation  → network-first, fallback offline page
//   CSS/JS/Font → cache-first, update in background
//   API/other   → network-only (skip)
self.addEventListener('fetch', event => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  const isSameOrigin = url.origin === self.location.origin;
  const isCDN = url.hostname.includes('jsdelivr.net') ||
                url.hostname.includes('fonts.googleapis.com') ||
                url.hostname.includes('fonts.gstatic.com');

  if (!isSameOrigin && !isCDN) return;

  // Skip API and admin routes — always network
  if (isSameOrigin && (url.pathname.startsWith('/api/') ||
                       url.pathname.startsWith('/admin/') ||
                       url.pathname.startsWith('/media/'))) return;

  // Navigation: network-first
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  // Static assets: cache-first, network fallback with background update
  if (request.destination === 'style' ||
      request.destination === 'script' ||
      request.destination === 'font'  ||
      isCDN) {
    event.respondWith(
      caches.open(CACHE_NAME).then(cache =>
        cache.match(request).then(cached => {
          const networkFetch = fetch(request).then(response => {
            cache.put(request, response.clone());
            return response;
          });
          return cached || networkFetch;
        })
      )
    );
  }
});
