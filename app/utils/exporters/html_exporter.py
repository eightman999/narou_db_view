"""
小説データをHTML形式に書き出すモジュール
Androidで読みやすいフォーマットでエクスポートします
"""
import os
import sqlite3
import datetime
import shutil
from pathlib import Path
import json
from app.utils.logger_manager import get_logger
from app.database.db_handler import DatabaseHandler
from config import DATABASE_PATH

# ロガーの設定
logger = get_logger('HTMLExporter')


class HTMLExporter:
    """
    小説データをHTML形式でエクスポートするクラス
    """

    def __init__(self, export_dir='html_export'):
        """
        初期化

        Args:
            export_dir (str): エクスポート先ディレクトリ
        """
        self.db_path = DATABASE_PATH
        self.export_dir = export_dir
        self.db_handler = DatabaseHandler()

        # エクスポート先ディレクトリの作成
        self.base_dir = Path(self.export_dir)
        self.base_dir.mkdir(exist_ok=True)

        # 必要なサブディレクトリの作成
        self.novels_dir = self.base_dir / 'novels'
        self.novels_dir.mkdir(exist_ok=True)

        self.assets_dir = self.base_dir / 'assets'
        self.assets_dir.mkdir(exist_ok=True)

        # CSSファイルの作成
        self._create_css_file()

        # JavaScriptファイルの作成
        self._create_js_file()

    def _create_css_file(self):
        """CSSファイルを作成する"""
        css_content = """
        :root {
            --main-bg-color: #f7f7f7;
            --text-color: #333;
            --link-color: #0066cc;
            --header-bg: #4a4a4a;
            --header-text: #fff;
            --card-bg: #fff;
            --card-shadow: 0 2px 5px rgba(0,0,0,0.1);
            --episode-bg: #fff;
            --episode-hover: #f0f0f0;
            --episode-border: #eaeaea;
            --font-family: 'Hiragino Sans', 'Hiragino Kaku Gothic ProN', Meiryo, sans-serif;
        }

        /* ダークモード対応 */
        @media (prefers-color-scheme: dark) {
            :root {
                --main-bg-color: #121212;
                --text-color: #e0e0e0;
                --link-color: #60a5fa;
                --header-bg: #272727;
                --header-text: #fff;
                --card-bg: #1e1e1e;
                --card-shadow: 0 2px 5px rgba(0,0,0,0.3);
                --episode-bg: #1e1e1e;
                --episode-hover: #272727;
                --episode-border: #333;
            }
        }

        body {
            font-family: var(--font-family);
            background-color: var(--main-bg-color);
            color: var(--text-color);
            line-height: 1.6;
            margin: 0;
            padding: 0;
            -webkit-text-size-adjust: 100%;
        }

        header {
            background-color: var(--header-bg);
            color: var(--header-text);
            padding: 1rem;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        h1, h2, h3 {
            margin-top: 0;
            line-height: 1.3;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 1rem;
        }

        .novel-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }

        .novel-card {
            background-color: var(--card-bg);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: var(--card-shadow);
            transition: transform 0.2s;
        }

        .novel-card:hover {
            transform: translateY(-2px);
        }

        .novel-card h3 {
            margin-top: 0;
            font-size: 1.1rem;
        }

        .novel-info {
            font-size: 0.9rem;
            margin-bottom: 0.5rem;
        }

        .novel-synopsis {
            font-size: 0.9rem;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            color: #666;
        }

        a {
            color: var(--link-color);
            text-decoration: none;
        }

        a:hover {
            text-decoration: underline;
        }

        .back-link {
            display: inline-block;
            margin-bottom: 1rem;
        }

        .episode-list {
            list-style: none;
            padding: 0;
            margin: 1rem 0;
        }

        .episode-item {
            background-color: var(--episode-bg);
            border: 1px solid var(--episode-border);
            border-radius: 4px;
            margin-bottom: 0.5rem;
            transition: background-color 0.2s;
        }

        .episode-item:hover {
            background-color: var(--episode-hover);
        }

        .episode-link {
            display: block;
            padding: 0.75rem 1rem;
            color: var(--text-color);
        }

        .episode-content {
            padding: 1rem;
            line-height: 1.8;
            max-width: 40em;
            margin: 0 auto;
        }

        .episode-content p {
            margin-bottom: 1.5em;
            text-indent: 1em;
        }

        .novel-meta {
            background-color: var(--card-bg);
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 1rem;
            box-shadow: var(--card-shadow);
        }

        .episode-nav {
            display: flex;
            justify-content: space-between;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--episode-border);
        }

        .nav-button {
            padding: 0.5rem 1rem;
            background-color: var(--card-bg);
            border: 1px solid var(--episode-border);
            border-radius: 4px;
            color: var(--text-color);
        }

        @media (max-width: 600px) {
            .novel-list {
                grid-template-columns: 1fr;
            }

            .container {
                padding: 0.5rem;
            }

            h1 {
                font-size: 1.5rem;
            }

            .episode-content {
                padding: 0.5rem;
            }
        }

        /* フォントサイズ調整ボタン */
        .font-size-controls {
            position: fixed;
            bottom: 1rem;
            right: 1rem;
            display: flex;
            gap: 0.5rem;
            z-index: 100;
        }

        .font-button {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background-color: var(--header-bg);
            color: var(--header-text);
            border: none;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }

        /* 検索ボックス */
        .search-container {
            margin: 1rem 0;
        }

        .search-box {
            width: 100%;
            padding: 0.6rem;
            border: 1px solid var(--episode-border);
            border-radius: 4px;
            font-size: 1rem;
            background-color: var(--card-bg);
            color: var(--text-color);
        }

        /* ページ上部に戻るボタン */
        .back-to-top {
            position: fixed;
            bottom: 1rem;
            left: 1rem;
            background-color: var(--header-bg);
            color: var(--header-text);
            border: none;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            text-align: center;
            line-height: 40px;
            cursor: pointer;
            opacity: 0;
            transition: opacity 0.3s;
            z-index: 100;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }

        .back-to-top.visible {
            opacity: 1;
        }

        /* 読書設定 */
        .reading-settings {
            position: fixed;
            top: 60px;
            right: -250px;
            width: 250px;
            background-color: var(--card-bg);
            border-radius: 8px 0 0 8px;
            box-shadow: var(--card-shadow);
            padding: 1rem;
            transition: right 0.3s;
            z-index: 99;
        }

        .reading-settings.open {
            right: 0;
        }

        .settings-toggle {
            position: absolute;
            left: -40px;
            top: 10px;
            width: 40px;
            height: 40px;
            background-color: var(--header-bg);
            color: var(--header-text);
            border: none;
            border-radius: 8px 0 0 8px;
            cursor: pointer;
        }

        .settings-group {
            margin-bottom: 1rem;
        }

        .settings-group h3 {
            font-size: 1rem;
            margin-bottom: 0.5rem;
        }

        .theme-selector, .font-selector, .line-height-slider {
            width: 100%;
            padding: 0.5rem;
            background-color: var(--main-bg-color);
            color: var(--text-color);
            border: 1px solid var(--episode-border);
            border-radius: 4px;
        }
        """

        css_path = self.assets_dir / 'style.css'
        with open(css_path, 'w', encoding='utf-8') as f:
            f.write(css_content)

        logger.info(f"CSSファイルを作成しました: {css_path}")

    def _create_js_file(self):
        """JavaScriptファイルを作成する"""
        js_content = """
        document.addEventListener('DOMContentLoaded', function() {
            // フォントサイズの調整
            const fontSizeControls = document.querySelector('.font-size-controls');
            if (fontSizeControls) {
                const contentElement = document.querySelector('.episode-content');
                if (contentElement) {
                    const increaseButton = document.getElementById('increase-font');
                    const decreaseButton = document.getElementById('decrease-font');

                    // 現在のフォントサイズを取得（デフォルトは16px）
                    let currentSize = localStorage.getItem('fontSize') || 16;
                    contentElement.style.fontSize = currentSize + 'px';

                    increaseButton.addEventListener('click', function() {
                        currentSize = Math.min(parseInt(currentSize) + 2, 32);
                        contentElement.style.fontSize = currentSize + 'px';
                        localStorage.setItem('fontSize', currentSize);
                    });

                    decreaseButton.addEventListener('click', function() {
                        currentSize = Math.max(parseInt(currentSize) - 2, 12);
                        contentElement.style.fontSize = currentSize + 'px';
                        localStorage.setItem('fontSize', currentSize);
                    });
                }
            }

            // 検索機能
            const searchBox = document.querySelector('.search-box');
            if (searchBox) {
                const items = document.querySelectorAll('.novel-card, .episode-item');

                searchBox.addEventListener('input', function() {
                    const searchTerm = this.value.toLowerCase();

                    items.forEach(item => {
                        const text = item.textContent.toLowerCase();
                        if (text.includes(searchTerm)) {
                            item.style.display = '';
                        } else {
                            item.style.display = 'none';
                        }
                    });
                });
            }

            // TOPに戻るボタン
            const backToTopButton = document.querySelector('.back-to-top');
            if (backToTopButton) {
                window.addEventListener('scroll', function() {
                    if (window.pageYOffset > 300) {
                        backToTopButton.classList.add('visible');
                    } else {
                        backToTopButton.classList.remove('visible');
                    }
                });

                backToTopButton.addEventListener('click', function() {
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                });
            }

            // 読書設定
            const settingsToggle = document.querySelector('.settings-toggle');
            if (settingsToggle) {
                const readingSettings = document.querySelector('.reading-settings');

                settingsToggle.addEventListener('click', function() {
                    readingSettings.classList.toggle('open');
                });

                // テーマ切替
                const themeSelector = document.getElementById('theme-selector');
                if (themeSelector) {
                    // 保存されたテーマを適用
                    const savedTheme = localStorage.getItem('theme');
                    if (savedTheme) {
                        document.body.classList.add(savedTheme);
                        themeSelector.value = savedTheme;
                    }

                    themeSelector.addEventListener('change', function() {
                        // 既存のテーマクラスを削除
                        document.body.classList.remove('light-theme', 'dark-theme', 'sepia-theme');

                        if (this.value !== 'default') {
                            document.body.classList.add(this.value);
                            localStorage.setItem('theme', this.value);
                        } else {
                            localStorage.removeItem('theme');
                        }
                    });
                }

                // フォント変更
                const fontSelector = document.getElementById('font-selector');
                if (fontSelector) {
                    // 保存されたフォントを適用
                    const savedFont = localStorage.getItem('fontFamily');
                    if (savedFont) {
                        document.body.style.fontFamily = savedFont;
                        fontSelector.value = savedFont;
                    }

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

                // 行間調整
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

                        lineHeightSlider.addEventListener('input', function() {
                            contentElement.style.lineHeight = this.value;
                            localStorage.setItem('lineHeight', this.value);
                        });
                    }
                }
            }

            // 進捗保存（最後に読んだ位置を保存）
            const episodeContent = document.querySelector('.episode-content');
            if (episodeContent) {
                const novelId = document.body.getAttribute('data-novel-id');
                const episodeId = document.body.getAttribute('data-episode-id');

                if (novelId && episodeId) {
                    const scrollKey = `scroll_${novelId}_${episodeId}`;
                    const savedPosition = localStorage.getItem(scrollKey);

                    if (savedPosition) {
                        window.scrollTo(0, parseInt(savedPosition));
                    }

                    window.addEventListener('scroll', function() {
                        localStorage.setItem(scrollKey, window.pageYOffset);
                    });
                }
            }
        });
        """

        js_path = self.assets_dir / 'script.js'
        with open(js_path, 'w', encoding='utf-8') as f:
            f.write(js_content)

        logger.info(f"JavaScriptファイルを作成しました: {js_path}")

    def export_all_novels(self):
        """全ての小説をエクスポート"""
        try:
            # 小説リストの取得
            novels = self.db_handler.get_all_novels()

            if not novels:
                logger.warning("エクスポートする小説がありません")
                return False

            # インデックスページの作成
            self._create_index_page(novels)

            # 各小説のページを作成
            for i, novel in enumerate(novels):
                try:
                    ncode = novel[0]
                    logger.info(f"小説のエクスポート中 ({i + 1}/{len(novels)}): {ncode}")
                    self.export_novel(ncode)
                except Exception as e:
                    logger.error(f"小説 {ncode} のエクスポート中にエラーが発生しました: {e}")

            logger.info(f"全ての小説のエクスポートが完了しました。合計: {len(novels)}作品")
            return True

        except Exception as e:
            logger.error(f"小説のエクスポートに失敗しました: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def export_novel(self, ncode):
        """
        指定された小説をエクスポート

        Args:
            ncode (str): 小説コード

        Returns:
            bool: 成功したかどうか
        """
        try:
            # 小説情報の取得
            novel = self.db_handler.get_novel_by_ncode(ncode)
            if not novel:
                logger.warning(f"小説 {ncode} が見つかりません")
                return False

            # 小説タイトルの取得
            title = novel[1] if novel[1] else "無題の小説"
            author = novel[2] if novel[2] else "著者不明"
            synopsis = novel[7] if len(novel) > 7 and novel[7] else "あらすじはありません"

            # エピソードの取得
            episodes = self.db_handler.get_episodes_by_ncode(ncode)
            if not episodes:
                logger.warning(f"小説 {ncode} にはエピソードがありません")
                episodes = []

            # 小説用ディレクトリの作成
            novel_dir = self.novels_dir / ncode
            novel_dir.mkdir(exist_ok=True)

            # 小説情報ページの作成
            self._create_novel_page(novel_dir, novel, episodes)

            # 各エピソードのページを作成
            for episode in episodes:
                episode_no, title, body = episode
                self._create_episode_page(novel_dir, novel, episode, episodes)

            logger.info(f"小説 {ncode} のエクスポートが完了しました。エピソード数: {len(episodes)}")
            return True

        except Exception as e:
            logger.error(f"小説 {ncode} のエクスポート中にエラーが発生しました: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def _create_index_page(self, novels):
        """
        インデックスページを作成

        Args:
            novels (list): 小説のリスト
        """
        # 現在日時を取得
        now = datetime.datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>小説ライブラリ</title>
            <link rel="stylesheet" href="assets/style.css">
            <script src="assets/script.js" defer></script>
        </head>
        <body>
            <header>
                <div class="container">
                    <h1>小説ライブラリ</h1>
                </div>
            </header>

            <main class="container">
                <div class="search-container">
                    <input type="text" class="search-box" placeholder="小説を検索...">
                </div>

                <div class="novel-list">
        """

        # 小説カードを追加
        for novel in novels:
            ncode = novel[0]
            title = novel[1] if novel[1] else "無題の小説"
            author = novel[2] if novel[2] else "著者不明"
            updated_at = novel[3] if novel[3] else "更新日不明"
            episodes = novel[5] if len(novel) > 5 and novel[5] is not None else 0
            synopsis = novel[7] if len(novel) > 7 and novel[7] else "あらすじはありません"

            # あらすじの短縮
            if len(synopsis) > 150:
                synopsis = synopsis[:150] + "..."

            html_content += f"""
            <div class="novel-card">
                <h3><a href="novels/{ncode}/index.html">{title}</a></h3>
                <div class="novel-info">作者: {author} | エピソード数: {episodes}</div>
                <div class="novel-info">更新: {updated_at}</div>
                <div class="novel-synopsis">{synopsis}</div>
            </div>
            """

        html_content += """
                </div>
            </main>

            <button class="back-to-top">↑</button>

            <footer class="container">
                <p>エクスポート日時: {0}</p>
            </footer>
        </body>
        </html>
        """.format(now)

        # ファイルに書き込み
        index_path = self.base_dir / 'index.html'
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"インデックスページを作成しました: {index_path}")

    def _create_novel_page(self, novel_dir, novel, episodes):
        """
        小説情報ページを作成

        Args:
            novel_dir (Path): 小説ディレクトリのパス
            novel (tuple): 小説情報
            episodes (list): エピソードのリスト
        """
        ncode = novel[0]
        title = novel[1] if novel[1] else "無題の小説"
        author = novel[2] if novel[2] else "著者不明"
        updated_at = novel[3] if novel[3] else "更新日不明"
        synopsis = novel[7] if len(novel) > 7 and novel[7] else "あらすじはありません"

        # 目次を作成
        episodes_html = ""
        for episode in sorted(episodes, key=lambda x: int(x[0]) if x[0].isdigit() else 0):
            episode_no, episode_title, _ = episode
            episodes_html += f"""
            <li class="episode-item">
                <a href="episode_{episode_no}.html" class="episode-link">第{episode_no}話: {episode_title}</a>
            </li>
            """

        html_content = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title} - 小説ライブラリ</title>
            <link rel="stylesheet" href="../../assets/style.css">
            <script src="../../assets/script.js" defer></script>
        </head>
        <body>
            <header>
                <div class="container">
                    <h1>{title}</h1>
                </div>
            </header>

            <main class="container">
                <a href="../../index.html" class="back-link">← 小説一覧に戻る</a>

                <div class="novel-meta">
                    <h2>{title}</h2>
                    <p>作者: {author}</p>
                    <p>最終更新: {updated_at}</p>
                    <p>エピソード数: {len(episodes)}</p>
                    <h3>あらすじ</h3>
                    <p>{synopsis}</p>
                </div>

                <div class="search-container">
                    <input type="text" class="search-box" placeholder="エピソードを検索...">
                </div>

                <h3>目次</h3>
                <ul class="episode-list">
                    {episodes_html}
                </ul>
            </main>

            <button class="back-to-top">↑</button>
        </body>
        </html>
        """

        # ファイルに書き込み
        index_path = novel_dir / 'index.html'
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logger.info(f"小説情報ページを作成しました: {index_path}")

    def _create_episode_page(self, novel_dir, novel, episode, all_episodes):
        """
        エピソードページを作成

        Args:
            novel_dir (Path): 小説ディレクトリのパス
            novel (tuple): 小説情報
            episode (tuple): エピソード情報
            all_episodes (list): すべてのエピソードのリスト
        """
        ncode = novel[0]
        novel_title = novel[1] if novel[1] else "無題の小説"
        author = novel[2] if novel[2] else "著者不明"

        episode_no, episode_title, episode_body = episode

        # 前後のエピソードへのリンクを準備
        sorted_episodes = sorted(all_episodes, key=lambda x: int(x[0]) if x[0].isdigit() else 0)
        episode_index = next((i for i, ep in enumerate(sorted_episodes) if ep[0] == episode_no), -1)

        prev_link = ""
        next_link = ""

        if episode_index > 0:
            prev_episode = sorted_episodes[episode_index - 1]
            prev_no = prev_episode[0]
            prev_title = prev_episode[1]
            prev_link = f'<a href="episode_{prev_no}.html" class="nav-button">← 前話: 第{prev_no}話</a>'
        else:
            prev_link = '<span></span>'

        if episode_index < len(sorted_episodes) - 1:
            next_episode = sorted_episodes[episode_index + 1]
            next_no = next_episode[0]
            next_title = next_episode[1]
            next_link = f'<a href="episode_{next_no}.html" class="nav-button">次話: 第{next_no}話 →</a>'
        else:
            next_link = '<span></span>'

        # 読書設定パネル
        settings_panel = """
        <div class="reading-settings">
            <button class="settings-toggle">⚙</button>
            <div class="settings-group">
                <h3>テーマ</h3>
                <select id="theme-selector" class="theme-selector">
                    <option value="default">デフォルト</option>
                    <option value="light-theme">ライト</option>
                    <option value="dark-theme">ダーク</option>
                    <option value="sepia-theme">セピア</option>
                </select>
            </div>

            <div class="settings-group">
                <h3>フォント</h3>
                <select id="font-selector" class="font-selector">
                    <option value="default">デフォルト</option>
                    <option value="'Hiragino Mincho ProN', serif">明朝体</option>
                    <option value="'Hiragino Sans', sans-serif">ゴシック体</option>
                    <option value="'Meiryo', sans-serif">メイリオ</option>
                    <option value="'Yu Gothic', sans-serif">游ゴシック</option>
                </select>
            </div>

            <div class="settings-group">
                <h3>行間</h3>
                <input type="range" id="line-height-slider" class="line-height-slider" min="1.2" max="2.4" step="0.1" value="1.8">
            </div>
        </div>"""