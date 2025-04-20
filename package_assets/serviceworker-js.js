/**
 * 小説ライブラリ用 Service Worker
 * オフラインでも閲覧できるようにするための機能を提供
 */

// キャッシュ名（バージョン管理のために使用）
const CACHE_NAME = 'novel-library-cache-v1';

// キャッシュするリソースのリスト
const urlsToCache = [
    './',                    // ルートページ
    './index.html',          // インデックスページ
    './assets/style.css',    // スタイルシート
    './assets/script.js',    // メインスクリプト
    './manifest.json',       // マニフェストファイル
    './assets/icon-192.png', // アイコン（小）
    './assets/icon-512.png'  // アイコン（大）
];

/**
 * Service Workerインストール時の処理
 * 初回実行時または更新時にキャッシュを作成する
 */
self.addEventListener('install', event => {
    // インストール処理が完了するまで待機するよう指示
    event.waitUntil(
        // 指定した名前のキャッシュを開く（存在しなければ作成）
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('キャッシュをオープンしました');
                // 指定したリソースをすべてキャッシュに追加
                return cache.addAll(urlsToCache);
            })
    );
});

/**
 * ネットワークリクエスト時の処理
 * 優先的にキャッシュからリソースを取得し、なければネットワークから取得
 */
self.addEventListener('fetch', event => {
    event.respondWith(
        // キャッシュ内に該当リソースがあるか確認
        caches.match(event.request)
            .then(response => {
                // キャッシュにあればそれを返す
                if (response) {
                    return response;
                }
                
                // キャッシュになければネットワークから取得
                return fetch(event.request)
                    .then(networkResponse => {
                        // レスポンスが有効か確認
                        if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
                            return networkResponse;
                        }
                        
                        // レスポンスを複製（レスポンスは一度しか使えないため）
                        const responseToCache = networkResponse.clone();
                        
                        // 新たに取得したリソースをキャッシュに追加
                        caches.open(CACHE_NAME)
                            .then(cache => {
                                cache.put(event.request, responseToCache);
                            });
                        
                        return networkResponse;
                    });
            })
    );
});

/**
 * Service Worker有効化時の処理
 * 古いキャッシュを削除するための処理
 */
self.addEventListener('activate', event => {
    // 現在のキャッシュ名のリスト（これは残す）
    const cacheWhitelist = [CACHE_NAME];
    
    event.waitUntil(
        // すべてのキャッシュ名を取得
        caches.keys().then(cacheNames => {
            // 古いキャッシュを削除
            return Promise.all(
                cacheNames.map(cacheName => {
                    // 現在のキャッシュリストにないものは削除
                    if (cacheWhitelist.indexOf(cacheName) === -1) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});
