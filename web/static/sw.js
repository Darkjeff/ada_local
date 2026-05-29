/* ADA Mobile — Service Worker
   Cache the app shell for offline support */

const CACHE = "ada-v8";
const SHELL = [
  "/",
  "/static/manifest.json",
  "/static/icon.svg",
  "/static/core/core.js",
  "/static/core/base.css",
  "/static/views/dashboard/index.js", "/static/views/dashboard/style.css",
  "/static/views/chat/index.js",      "/static/views/chat/style.css",
  "/static/views/memory/index.js",    "/static/views/memory/style.css",
  "/static/views/page/index.js",      "/static/views/page/style.css",
  "/static/views/webagent/index.js",  "/static/views/webagent/style.css",
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
  // API calls — réseau uniquement, pas de cache
  if (e.request.url.includes("/api/")) return;

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
