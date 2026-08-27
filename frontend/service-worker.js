const CACHE="miu-trace-shell-v18";
const ASSETS=["./","index.html","sources.html","config.js","assets/app.css","assets/details.css","assets/app.js","assets/miu-trace-footprints.png","manifest.webmanifest","data/beta-events.json"];
self.addEventListener("install",event=>{self.skipWaiting();event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)))});
self.addEventListener("activate",event=>{event.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))),self.clients.claim()]))});
self.addEventListener("fetch",event=>{const url=new URL(event.request.url);if(url.pathname.includes("/api/")||event.request.method!=="GET")return;event.respondWith(fetch(event.request).then(response=>{const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));return response}).catch(()=>caches.match(event.request))) });
