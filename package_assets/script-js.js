/**
 * 小説ビューアー用JavaScriptファイル
 * 小説データをHTMLとして閲覧するための機能を提供
 */

// DOMの読み込み完了時に実行
document.addEventListener('DOMContentLoaded', function() {
    
    // ---------- フォントサイズ調整機能 ----------
    initFontSizeControls();
    
    // ---------- 検索機能 ----------
    initSearchFunction();
    
    // ---------- TOPに戻るボタン機能 ----------
    initBackToTopButton();
    
    // ---------- 読書設定パネル機能 ----------
    initReadingSettings();
    
    // ---------- 読書進捗保存機能 ----------
    initReadingProgress();
});

/**
 * フォントサイズ調整機能の初期化
 * エピソードページでフォントサイズを変更可能にする
 */
function initFontSizeControls() {
    const fontSizeControls = document.querySelector('.font-size-controls');
    if (fontSizeControls) {
        const contentElement = document.querySelector('.episode-content');
        if (contentElement) {
            const increaseButton = document.getElementById('increase-font');
            const decreaseButton = document.getElementById('decrease-font');
            
            // LocalStorageから前回のフォントサイズを取得（デフォルトは16px）
            let currentSize = localStorage.getItem('fontSize') || 16;
            contentElement.style.fontSize = currentSize + 'px';
            
            // フォントサイズ増加ボタン
            increaseButton.addEventListener('click', function() {
                // 最大サイズを32pxに制限
                currentSize = Math.min(parseInt(currentSize) + 2, 32);
                contentElement.style.fontSize = currentSize + 'px';
                localStorage.setItem('fontSize', currentSize);
            });
            
            // フォントサイズ減少ボタン
            decreaseButton.addEventListener('click', function() {
                // 最小サイズを12pxに制限
                currentSize = Math.max(parseInt(currentSize) - 2, 12);
                contentElement.style.fontSize = currentSize + 'px';
                localStorage.setItem('fontSize', currentSize);
            });
        }
    }
}

/**
 * 検索機能の初期化
 * 小説一覧やエピソード一覧で検索可能にする
 */
function initSearchFunction() {
    const searchBox = document.querySelector('.search-box');
    if (searchBox) {
        // 検索対象要素（小説カードまたはエピソードアイテム）
        const items = document.querySelectorAll('.novel-card, .episode-item');
        
        // 入力イベントで検索フィルタリングを実行
        searchBox.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();
            
            // 各要素について検索ワードを含むかチェック
            items.forEach(item => {
                const text = item.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    item.style.display = ''; // 表示
                } else {
                    item.style.display = 'none'; // 非表示
                }
            });
        });
    }
}

/**
 * TOPに戻るボタン機能の初期化
 * スクロール位置に応じてボタンの表示・非表示を切り替え
 */
function initBackToTopButton() {
    const backToTopButton = document.querySelector('.back-to-top');
    if (backToTopButton) {
        // スクロールイベントでボタンの表示状態を更新
        window.addEventListener('scroll', function() {
            // 300px以上スクロールしたらボタンを表示
            if (window.pageYOffset > 300) {
                backToTopButton.classList.add('visible');
            } else {
                backToTopButton.classList.remove('visible');
            }
        });
        
        // ボタンクリック時の処理
        backToTopButton.addEventListener('click', function() {
            window.scrollTo({ top: 0, behavior: 'smooth' }); // スムーズにスクロール
        });
    }
}

/**
 * 読書設定パネル機能の初期化
 * テーマ、フォント、行間などの設定を変更可能にする
 */
function initReadingSettings() {
    const settingsToggle = document.querySelector('.settings-toggle');
    if (settingsToggle) {
        const readingSettings = document.querySelector('.reading-settings');
        
        // 設定パネルの開閉トグル
        settingsToggle.addEventListener('click', function() {
            readingSettings.classList.toggle('open');
        });
        
        // ---------- テーマ切替機能 ----------
        initThemeSelector();
        
        // ---------- フォント変更機能 ----------
        initFontSelector();
        
        // ---------- 行間調整機能 ----------
        initLineHeightAdjustment();
    }
}

/**
 * テーマ選択機能の初期化
 */
function initThemeSelector() {
    const themeSelector = document.getElementById('theme-selector');
    if (themeSelector) {
        // 保存されたテーマを適用
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme) {
            document.body.classList.add(savedTheme);
            themeSelector.value = savedTheme;
        }
        
        // テーマ変更イベント
        themeSelector.addEventListener('change', function() {
            // 既存のテーマクラスを削除
            document.body.classList.remove('light-theme', 'dark-theme', 'sepia-theme');
            
            // 選択されたテーマを適用
            if (this.value !== 'default') {
                document.body.classList.add(this.value);
                localStorage.setItem('theme', this.value);
            } else {
                localStorage.removeItem('theme');
            }
        });
    }
}

/**
 * フォント選択機能の初期化
 */
function initFontSelector() {
    const fontSelector = document.getElementById('font-selector');
    if (fontSelector) {
        // 保存されたフォントを適用
        const savedFont = localStorage.getItem('fontFamily');
        if (savedFont) {
            document.body.style.fontFamily = savedFont;
            fontSelector.value = savedFont;
        }
        
        // フォント変更イベント
        fontSelector.addEventListener('change', function() {
            if (this.value !== 'default') {
                document.body.style.fontFamily = this.value;
                localStorage.setItem('fontFamily', this.value);
            } else {
                document.body.style.fontFamily = '';
                localStorage.removeItem('fontFamily');
            }
        });
    }
}

/**
 * 行間調整機能の初期化
 */
function initLineHeightAdjustment() {
    const lineHeightSlider = document.getElementById('line-height-slider');
    if (lineHeightSlider) {
        const contentElement = document.querySelector('.episode-content');
        if (contentElement) {
            // 保存された行間を適用
            const savedLineHeight = localStorage.getItem('lineHeight');
            if (savedLineHeight) {
                contentElement.style.lineHeight = savedLineHeight;
                lineHeightSlider.value = parseFloat(savedLineHeight);
            }
            
            // スライダー操作時の処理
            lineHeightSlider.addEventListener('input', function() {
                contentElement.style.lineHeight = this.value;
                localStorage.setItem('lineHeight', this.value);
            });
        }
    }
}

/**
 * 読書進捗保存機能の初期化
 * 最後に読んだ位置を記憶して次回表示時に復元する
 */
function initReadingProgress() {
    const episodeContent = document.querySelector('.episode-content');
    if (episodeContent) {
        // 小説ID・エピソードIDを取得
        const novelId = document.body.getAttribute('data-novel-id');
        const episodeId = document.body.getAttribute('data-episode-id');
        
        if (novelId && episodeId) {
            // LocalStorageのキー
            const scrollKey = `scroll_${novelId}_${episodeId}`;
            
            // 前回のスクロール位置を復元
            const savedPosition = localStorage.getItem(scrollKey);
            if (savedPosition) {
                window.scrollTo(0, parseInt(savedPosition));
            }
            
            // スクロール位置を随時保存
            window.addEventListener('scroll', function() {
                localStorage.setItem(scrollKey, window.pageYOffset);
            });
        }
    }
}
/**
 * あらすじの表示/非表示を切り替える機能
 */

// あらすじ表示切り替えボタン初期化関数を追加
function initSynopsisToggle() {
  // 小説一覧ページにのみ機能を追加
  const novelList = document.querySelector('.novel-list');
  if (!novelList) return;

  // トグルボタンのコンテナを作成
  const toggleContainer = document.createElement('div');
  toggleContainer.className = 'synopsis-toggle-container';
  toggleContainer.style.margin = '1rem 0';
  toggleContainer.style.textAlign = 'right';

  // トグルボタンを作成
  const toggleButton = document.createElement('button');
  toggleButton.className = 'synopsis-toggle-button';
  toggleButton.textContent = 'あらすじを非表示';
  toggleButton.style.padding = '0.5rem 1rem';
  toggleButton.style.backgroundColor = 'var(--header-bg)';
  toggleButton.style.color = 'var(--header-text)';
  toggleButton.style.border = 'none';
  toggleButton.style.borderRadius = '4px';
  toggleButton.style.cursor = 'pointer';

  // LocalStorageから状態を復元（デフォルトは表示）
  const synopsisHidden = localStorage.getItem('synopsisHidden') === 'true';
  if (synopsisHidden) {
    toggleButton.textContent = 'あらすじを表示';
    hideSynopsis();
  }

  // クリックイベント追加
  toggleButton.addEventListener('click', function() {
    const isHidden = toggleButton.textContent === 'あらすじを表示';
    if (isHidden) {
      toggleButton.textContent = 'あらすじを非表示';
      showSynopsis();
      localStorage.setItem('synopsisHidden', 'false');
    } else {
      toggleButton.textContent = 'あらすじを表示';
      hideSynopsis();
      localStorage.setItem('synopsisHidden', 'true');
    }
  });

  // ボタンをコンテナに追加
  toggleContainer.appendChild(toggleButton);

  // トグルボタンを検索ボックスの下に挿入
  const searchContainer = document.querySelector('.search-container');
  if (searchContainer) {
    searchContainer.parentNode.insertBefore(toggleContainer, searchContainer.nextSibling);
  } else {
    // 検索ボックスがない場合はnovelListの前に挿入
    novelList.parentNode.insertBefore(toggleContainer, novelList);
  }
}

// あらすじを非表示にする関数
function hideSynopsis() {
  const synopses = document.querySelectorAll('.novel-synopsis');
  synopses.forEach(synopsis => {
    synopsis.style.display = 'none';
  });

  // カードの高さを調整
  const cards = document.querySelectorAll('.novel-card');
  cards.forEach(card => {
    card.style.minHeight = '0';
  });
}

// あらすじを表示する関数
function showSynopsis() {
  const synopses = document.querySelectorAll('.novel-synopsis');
  synopses.forEach(synopsis => {
    synopsis.style.display = 'block';
  });

  // カードの高さを元に戻す
  const cards = document.querySelectorAll('.novel-card');
  cards.forEach(card => {
    card.style.minHeight = '';
  });
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
});