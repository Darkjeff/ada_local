// Service Worker minimal — pas de cache pour l'instant
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
