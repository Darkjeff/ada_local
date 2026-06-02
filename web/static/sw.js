/* ADA Mobile — Service Worker
   Cache the app shell for offline support */

const CACHE = "ada-v24";
// Seuls les assets vraiment statiques sont mis en cache.
// Les JS/CSS des views sont toujours rechargés depuis le réseau
// pour éviter les problèmes de cache en développement.
const SHELL = [
  "/",
  "/static/manifest.json",
  "/static/icon.svg",
  "/static/core/base.css",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  // API calls et JS/CSS dynamiques — réseau uniquement, jamais de cache
  if (
    e.request.url.includes("/api/") ||
    e.request.url.includes("/static/views/") ||
    e.request.url.includes("/static/core/core.js")
  ) return;

  e.respondWith(
    caches.match(e.request).then((cached) => {
      if (cached) return cached;
      return fetch(e.request).then((resp) => {
        if (resp && resp.status === 200 && resp.type === "basic") {
          const clone = resp.clone();
          caches.open(CACHE).then((c) => c.put(e.request, clone));
        }
        return resp;
      });
    })
  );
});
