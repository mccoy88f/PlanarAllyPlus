/* Minimal Service Worker for PWA Installation */
const CACHE_NAME = 'planarally-cache-v1';

self.addEventListener('install', (event) => {
    // Pass-through install
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    // Pass-through activate
    event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
    // network-only strategy (we don't want to cache game assets yet)
    event.respondWith(fetch(event.request));
});
