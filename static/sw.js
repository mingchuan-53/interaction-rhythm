// 交互节律 Service Worker - PWA 离线支持
const CACHE_NAME = 'type-tracker-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json'
];

// 安装事件 - 缓存静态资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('缓存静态资源');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// 激活事件 - 清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// 请求拦截 - 网络优先策略
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API 请求使用网络优先
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // 缓存 GET 请求的响应
          if (request.method === 'GET' && response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // 网络失败时尝试从缓存获取
          return caches.match(request);
        })
    );
    return;
  }

  // 静态资源使用缓存优先
  event.respondWith(
    caches.match(request)
      .then((cached) => {
        if (cached) {
          return cached;
        }
        return fetch(request).then((response) => {
          // 缓存新的静态资源
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(CACHE_NAME).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        });
      })
  );
});
