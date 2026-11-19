/* Service worker — Monitor Banca Múltiple México (Sakbé)
   Estrategia:
   - index.html y navegación: NETWORK-FIRST (siempre baja la versión fresca;
     usa caché solo si no hay conexión). Evita que un deploy quede oculto tras
     una versión vieja cacheada.
   - Datos (.json / /data/): network-first con respaldo en caché.
   - Iconos y manifest: cache-first (no cambian).
*/
// Subir este número en cada deploy que cambie datos o metodología. Al activarse
// el SW borra todos los cachés con nombre distinto, así que un usuario con la
// versión anterior en disco queda limpio sin tener que borrar datos del sitio.
const CACHE = 'monitor-bancos-mx-v1';
const SHELL = [
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/icon-maskable-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL).catch(() => {})).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  const isHTML = req.mode === 'navigate' ||
                 url.pathname.endsWith('/') ||
                 url.pathname.endsWith('index.html');
  const isData = url.pathname.endsWith('.json') || url.pathname.includes('/data/');

  // HTML y datos: network-first (siempre fresco, caché como respaldo offline).
  if (isHTML || isData) {
    event.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req).then((c) => c || caches.match('./index.html')))
    );
    return;
  }

  // Resto (iconos, manifest): cache-first.
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      });
    })
  );
});
