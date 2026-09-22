/* ============================================================
   Zeta PWA — Service Worker
   Офлайн-кеш для работы без интернета
   ============================================================ */

const CACHE_NAME = 'zeta-pwa-v1';

const FILES_TO_CACHE = [
    './',
    './index.html',
    './style.css',
    './app.js',
    './manifest.json',
    './icon-192.png',
    './icon-512.png',
];

// ========== УСТАНОВКА ==========
self.addEventListener('install', (event) => {
    console.log('[SW] Установка...');

    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[SW] Кеширую файлы');
                return cache.addAll(FILES_TO_CACHE);
            })
            .then(() => self.skipWaiting())
    );
});

// ========== АКТИВАЦИЯ ==========
self.addEventListener('activate', (event) => {
    console.log('[SW] Активация...');

    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((name) => {
                    if (name !== CACHE_NAME) {
                        console.log('[SW] Удаляю старый кеш:', name);
                        return caches.delete(name);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// ========== FETCH (перехват запросов) ==========
self.addEventListener('fetch', (event) => {
    // Пропускаем внешние запросы (GitHub и т.д.)
    if (!event.request.url.startsWith(self.location.origin)) {
        return;
    }

    event.respondWith(
        caches.match(event.request).then((cached) => {
            // Если есть в кеше — отдаём
            if (cached) {
                return cached;
            }

            // Иначе — идём в сеть
            return fetch(event.request)
                .then((response) => {
                    // Кешируем новые файлы
                    if (response.status === 200) {
                        const responseClone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseClone);
                        });
                    }
                    return response;
                })
                .catch(() => {
                    // Если сеть недоступна и файл не найден в кеше
                    if (event.request.mode === 'navigate') {
                        return caches.match('./index.html');
                    }
                });
        })
    );
});

console.log('[SW] Service Worker загружен');