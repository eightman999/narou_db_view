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

/**
 * リスト表示/グリッド表示の切り替え機能
 */
function initViewToggle() {
  // 小説一覧ページにのみ機能を追加
  const novelList = document.querySelector('.novel-list');
  if (!novelList) return;

  // トグルボタンのコンテナを作成
  const toggleContainer = document.createElement('div');
  toggleContainer.className = 'view-toggle-container';

  // トグルボタンを作成
  const toggleButton = document.createElement('button');
  toggleButton.className = 'view-toggle-button';
  toggleButton.textContent = 'シンプルリスト表示';

  // LocalStorageから状態を復元（デフォルトはグリッド表示）
  const isListView = localStorage.getItem('novelListView') === 'list';
  if (isListView) {
    toggleButton.textContent = 'グリッド表示';
    novelList.classList.add('list-view');
  }

  // クリックイベント追加
  toggleButton.addEventListener('click', function() {
    const isListView = novelList.classList.contains('list-view');
    if (isListView) {
      // リスト表示 → グリッド表示
      toggleButton.textContent = 'シンプルリスト表示';
      novelList.classList.remove('list-view');
      localStorage.setItem('novelListView', 'grid');
    } else {
      // グリッド表示 → リスト表示
      toggleButton.textContent = 'グリッド表示';
      novelList.classList.add('list-view');
      localStorage.setItem('novelListView', 'list');
    }
  });

  // ボタンをコンテナに追加
  toggleContainer.appendChild(toggleButton);

  // トグルボタンをあらすじトグルボタンの下に挿入
  const synopsisToggleContainer = document.querySelector('.synopsis-toggle-container');
  if (synopsisToggleContainer) {
    synopsisToggleContainer.after(toggleContainer);
  } else {
    // あらすじトグルがない場合は検索ボックスの下に挿入
    const searchContainer = document.querySelector('.search-container');
    if (searchContainer) {
      searchContainer.after(toggleContainer);
    } else {
      // 検索ボックスもない場合はnovelListの前に挿入
      novelList.before(toggleContainer);
    }
  }
}

// DOMの読み込み完了時に実行されるメイン関数に追加
document.addEventListener('DOMContentLoaded', function() {
  // 既存の初期化関数を呼び出し
  initFontSizeControls();
  initSearchFunction();
  initBackToTopButton();
  initReadingSettings();
  initReadingProgress();

  // あらすじ表示切り替え機能を初期化
  initSynopsisToggle();

  // リスト表示/グリッド表示切り替え機能を初期化
  initViewToggle();
});
/**
 * 最近読んだ小説の履歴管理機能
 * 既存のscript-js.jsに追加するコード
 */

// ---------- 最近読んだ小説の履歴管理 ----------
function initRecentNovelsHistory() {
    // 履歴表示エリアの要素を取得
    const recentHistoryArea = document.querySelector('.recent-novels-list');
    if (!recentHistoryArea) return; // トップページ以外では実行しない

    // LocalStorageから履歴データを取得
    const historyData = getReadingHistory();
    if (!historyData || historyData.length === 0) {
        // 履歴がない場合のメッセージを表示
        recentHistoryArea.innerHTML = '<p>まだ履歴がありません</p>';
        return;
    }

    // 最大5件まで表示
    const displayHistory = historyData.slice(0, 5);

    // 履歴リストを構築
    const historyHTML = displayHistory.map(item => {
        const lastReadDate = new Date(item.timestamp);
        const formattedDate = `${lastReadDate.getFullYear()}年${lastReadDate.getMonth() + 1}月${lastReadDate.getDate()}日 ${lastReadDate.getHours()}:${String(lastReadDate.getMinutes()).padStart(2, '0')}`;

        return `
        <div class="recent-novel-item">
            <h3><a href="${item.novelUrl}">${item.novelTitle}</a></h3>
            <div class="recent-novel-info">
                最後に読んだ話: <a href="${item.episodeUrl}">第${item.episodeNo}話: ${item.episodeTitle}</a>
            </div>
            <div class="recent-novel-timestamp">
                ${formattedDate}
            </div>
        </div>
        `;
    }).join('');

    recentHistoryArea.innerHTML = historyHTML;
}

/**
 * 読書履歴を取得
 *
 * @returns {Array} 履歴データの配列
 */
function getReadingHistory() {
    const historyJson = localStorage.getItem('novelReadingHistory');
    return historyJson ? JSON.parse(historyJson) : [];
}

/**
 * 読書履歴を更新
 * エピソードページ閲覧時に呼び出される
 */
function updateReadingHistory() {
    // エピソードページでのみ実行
    const body = document.body;
    const novelId = body.getAttribute('data-novel-id');
    const episodeId = body.getAttribute('data-episode-id');

    if (!novelId || !episodeId) return;

    // 現在のページ情報を取得
    const novelTitle = document.querySelector('header h1').textContent;
    const episodeTitle = document.querySelector('header h2').textContent.replace(`第${episodeId}話: `, '');

    // 小説・エピソードへのURL
    const novelUrl = `./index.html`;
    const episodeUrl = `./episode_${episodeId}.html`;

    // 新しい履歴項目を作成
    const newHistoryItem = {
        novelId: novelId,
        novelTitle: novelTitle,
        novelUrl: novelUrl,
        episodeNo: episodeId,
        episodeTitle: episodeTitle,
        episodeUrl: episodeUrl,
        timestamp: new Date().toISOString(),
        scrollPosition: window.pageYOffset
    };

    // 既存の履歴を取得
    let history = getReadingHistory();

    // 同じ小説の既存エントリーを削除
    history = history.filter(item => item.novelId !== novelId);

    // 新しい項目を先頭に追加
    history.unshift(newHistoryItem);

    // 履歴が多すぎる場合は古いものを削除（最大20件）
    if (history.length > 20) {
        history = history.slice(0, 20);
    }

    // 更新した履歴を保存
    localStorage.setItem('novelReadingHistory', JSON.stringify(history));
}

/**
 * 前回の続きから読む機能
 *
 * @param {string} novelId 小説ID
 * @returns {Object|null} 最後に読んだエピソード情報
 */
function getLastReadEpisode(novelId) {
    const history = getReadingHistory();
    return history.find(item => item.novelId === novelId) || null;
}

/**
 * 「続きから読む」ボタンの表示
 */
function showContinueReadingButton() {
    // 小説詳細ページでのみ実行
    if (!document.querySelector('.novel-meta')) return;

    const novelId = window.location.pathname.split('/').slice(-2)[0]; // URLからnovelIdを取得
    const lastRead = getLastReadEpisode(novelId);

    if (lastRead) {
        // 「続きから読む」ボタンを作成
        const continueButton = document.createElement('div');
        continueButton.className = 'continue-reading-button';
        continueButton.innerHTML = `
            <a href="${lastRead.episodeUrl}" class="nav-button continue-reading">
                続きから読む（第${lastRead.episodeNo}話: ${lastRead.episodeTitle}）
            </a>
        `;

        // ボタンを挿入
        const novelMeta = document.querySelector('.novel-meta');
        novelMeta.appendChild(continueButton);
    }
}

// エピソードページでは履歴更新とスクロール位置の保存
function enhancedReadingProgress() {
    const body = document.body;
    const novelId = body.getAttribute('data-novel-id');
    const episodeId = body.getAttribute('data-episode-id');

    if (novelId && episodeId) {
        // ページロード時に履歴を更新
        updateReadingHistory();

        // スクロール位置の更新（60秒ごと & スクロール停止後）
        let scrollTimeout;
        window.addEventListener('scroll', function() {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(function() {
                updateReadingHistory();
            }, 1000);  // スクロール停止から1秒後に更新
        });

        // 定期的に履歴を更新（60秒ごと）
        setInterval(updateReadingHistory, 60000);

        // ページを離れる前にも保存
        window.addEventListener('beforeunload', updateReadingHistory);
    }
}

// DOMの読み込み完了時に実行するイベントに追加
document.addEventListener('DOMContentLoaded', function() {
    // 既存の初期化関数を呼び出し
    initFontSizeControls();
    initSearchFunction();
    initBackToTopButton();
    initReadingSettings();
    initReadingProgress();
    initSynopsisToggle();

    // 新機能を初期化
    initRecentNovelsHistory();
    showContinueReadingButton();
    enhancedReadingProgress();
});

// ---------- スタイル拡張 ----------
// 必要なCSSルールをページに追加
function addCustomStyles() {
    const customStyle = document.createElement('style');
    customStyle.textContent = `
        /* 最近読んだ小説セクション */
        .recent-novels-section {
            margin-top: 2rem;
            margin-bottom: 2rem;
        }
        
        .recent-novels-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1rem;
        }
        
        .recent-novel-item {
            background-color: var(--card-bg);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: var(--card-shadow);
            border-left: 4px solid #60a5fa;
        }
        
        .recent-novel-item h3 {
            margin-top: 0;
            font-size: 1.1rem;
        }
        
        .recent-novel-info {
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }
        
        .recent-novel-timestamp {
            font-size: 0.8rem;
            color: #666;
        }
        
        /* 続きから読むボタン */
        .continue-reading-button {
            margin-top: 1rem;
            margin-bottom: 1rem;
        }
        
        .continue-reading {
            display: inline-block;
            background-color: #60a5fa;
            color: white;
            padding: 0.75rem 1.5rem;
            border-radius: 4px;
            font-weight: bold;
            text-align: center;
        }
        
        .continue-reading:hover {
            background-color: #3b82f6;
            text-decoration: none;
        }
        
        /* ダークモード対応 */
        @media (prefers-color-scheme: dark) {
            .recent-novel-timestamp {
                color: #aaa;
            }
        }
    `;
    document.head.appendChild(customStyle);
}

// ページ読み込み時にスタイルを追加
window.addEventListener('DOMContentLoaded', addCustomStyles);